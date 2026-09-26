"""Multi-step, tool-using agent loop: plan -> act -> observe -> iterate.

This is the "assistant that acts like an agent" path. The planner model
(agents/registry.py task "planning") first writes a numbered plan, then
repeatedly chooses ONE tool call at a time (harness/agent_tools.py),
sees the real result, and decides the next step -- revising the plan when
a step fails -- until it declares the task finished.

The same "model proposes, code disposes" discipline as everywhere else:
1. The model only ever PROPOSES a tool call as JSON. Deterministic Python
   executes it and reports what really happened; the model's own claims
   about a result are never recorded as the result.
2. The loop is a plain bounded for-loop (MAX_STEPS). A repeated identical
   call is refused, so a stuck model can't burn the whole budget.
3. If the agent read any corpus passage, its final answer must carry
   citations that verify verbatim (harness/verify.py) against exactly the
   passages it was shown; otherwise the failure is fed back, and after
   MAX_FINAL_ATTEMPTS the answer is withheld (files it wrote are listed but
   flagged). The answer and every file inherit the classification of every
   passage the agent saw (trust/labels.inherit_label).
4. Every run -- plan, each tool call, outcome -- is written to the
   hash-chained ledger.
"""

from __future__ import annotations

import json
import re
import time
from typing import Any, Callable, Optional, Sequence

from contracts import AgentStep, AskResponse, Citation, Label, Passage, Tier
from harness import workspace
from harness.agent_tools import ToolContext, call_tool, tool_manual
from harness.verify import check as verify_check
from ingest.ephemeral import EphemeralUpload
from trust.conversations import append_turn, conversation_owner, create_conversation
from trust.ledger import log as ledger_log
from trust.reports import save_report_data

MAX_STEPS = 10
MAX_FINAL_ATTEMPTS = 2
_ARG_PREVIEW_CHARS = 400


def _system_prompt() -> str:
    return (
        "You are SEVERANCE Agent, an on-premise assistant for refinery/PSU knowledge work. You complete "
        "the user's task by calling local tools one at a time, reading each result, and deciding the next "
        "step. Nothing you do leaves this machine.\n\n"
        f"TOOLS:\n{tool_manual()}\n\n"
        "RULES:\n"
        "1. Respond ONLY with one JSON object per turn, in one of these shapes:\n"
        '   {"thought": "why this step", "tool": "<tool name>", "args": {...}}\n'
        '   {"thought": "why done", "final_answer": "Markdown summary for the user", '
        '"citations": [{"doc_id": "...", "page": 1, "quote": "exact words"}]}\n'
        "2. One tool per turn. Wait for its OBSERVATION before the next step. Never invent a tool result.\n"
        "3. Use tools for facts: search_documents for policy/SOP/manual content, read_file / read_spreadsheet "
        "for the user's files, calculate for a single arithmetic expression, run_python for multi-row or multi-step "
        "computations (print each step), analyze_image for "
        "scans, drawings, photos and handwriting.\n"
        "4. When the user asks for a deliverable (Word, Excel, PowerPoint, file, note, report), you MUST create "
        "it with the matching tool before finishing, and name the file in final_answer.\n"
        "5. If a tool returns an error, fix the arguments or try another approach. Don't repeat a failing call.\n"
        "5a. DATA DISCIPLINE: never retype numbers or rows from an observation into code or files. In run_python, "
        "pass the file in input_files and load it with read_rows('name.csv') (an .xlsx arrives as name.csv). "
        "Save computed tables with write_rows('result.csv', rows), then call write_spreadsheet with "
        "{\"filename\": \"out.xlsx\", \"from_csv\": \"result.csv\"}. In final_answer, only state numbers that "
        "appear in an observation.\n"
        "6. If you used search_documents, final_answer must include 1-2 citations whose quote is copied "
        "character-for-character (8-25 words) from a passage you were shown, with its doc_id and page. "
        "Otherwise give \"citations\": [].\n"
        "7. Finish as soon as the task is done. Keep final_answer concise: what you did, key results, files created."
    )


def _extract_json(raw: str) -> Optional[dict]:
    clean = (raw or "").strip()
    if clean.startswith("```"):
        clean = re.sub(r"^```(?:json)?\n?", "", clean)
        clean = re.sub(r"\n?```$", "", clean)
    try:
        parsed = json.loads(clean)
    except ValueError:
        match = re.search(r"\{.*\}", clean, re.DOTALL)
        if not match:
            return None
        try:
            parsed = json.loads(match.group(0))
        except ValueError:
            return None
    return parsed if isinstance(parsed, dict) else None


def _preview_args(args: dict) -> dict:
    out = {}
    for k, v in (args or {}).items():
        text = v if isinstance(v, str) else json.dumps(v, default=str)
        out[k] = text if len(text) <= _ARG_PREVIEW_CHARS else text[:_ARG_PREVIEW_CHARS] + "…"
    return out


_DELIVERABLE_WORDS = {
    "docx": re.compile(r"\b(word|docx|approval note|memo)\b", re.I),
    "xlsx": re.compile(r"\b(excel|xlsx|spreadsheet|workbook)\b", re.I),
    "pptx": re.compile(r"\b(powerpoint|pptx|slides?|deck|presentation)\b", re.I),
}
_FILENAME_RE = re.compile(r"\b[\w\-. ()]+\.(docx|xlsx|pptx|csv|txt|md|json)\b", re.I)


def requested_deliverables(question: str) -> set[str]:
    """File types the user explicitly asked to receive (deterministic)."""
    wanted = {m.group(1).lower() for m in _FILENAME_RE.finditer(question)}
    asks_for_output = re.search(r"\b(save|create|make|generate|prepare|draft|write|build|export|produce|put)\b", question, re.I)
    if asks_for_output:
        wanted |= {ext for ext, rx in _DELIVERABLE_WORDS.items() if rx.search(question)}
    return wanted


def _parse_citations(raw: Any) -> list[Citation]:
    citations = []
    for c in raw if isinstance(raw, list) else []:
        if not isinstance(c, dict):
            continue
        try:
            citations.append(Citation(doc_id=str(c.get("doc_id", "")).strip(), page=int(c.get("page", 1)),
                                      quote=str(c.get("quote", "")).strip()))
        except Exception:
            continue
    return citations


def run_agent_task(
    question: str,
    principal,
    agent,
    db_path: str,
    corpus: Sequence[Passage],
    emit: Optional[Callable[[dict], None]] = None,
    conversation_id: Optional[str] = None,
    upload: Optional[EphemeralUpload] = None,
    max_steps: int = MAX_STEPS,
) -> AskResponse:
    def _emit(event: dict) -> None:
        if emit is not None:
            emit(event)

    if conversation_id and conversation_owner(db_path, conversation_id) != principal.person_id:
        conversation_id = None
    if not conversation_id:
        conversation_id = create_conversation(db_path, principal.person_id, question)

    chat = getattr(agent, "chat_json", None)
    if chat is None:
        return _finish(db_path, principal, question, conversation_id, status="abstained",
                       answer="The active agent backend does not support multi-step tool use.",
                       ctx=None, plan=[], trace=[], reason="agent_backend_unavailable")

    ctx = ToolContext(principal=principal, corpus=corpus, agent=agent)
    ctx.observe_numbers(question)

    attached_note = ""
    if upload is not None and upload.raw_bytes:
        name = workspace.unique_name(principal.person_id, upload.filename)
        workspace.write_bytes(principal.person_id, name, upload.raw_bytes, origin="upload")
        attached_note = f"\nThe user attached a file, saved in the workspace as '{name}'."
        if upload.ocr_pages:
            attached_note += (" On-device OCR already recovered its printed text: read_file returns it instantly. "
                              "Use analyze_image only for what OCR can't capture (symbols, handwriting, photos, layout).")
        elif upload.images and not upload.text_chunks:
            attached_note += " It has no machine-readable text: use analyze_image to read it."
        _emit({"stage": "extraction", "status": "done", "filename": name,
               "text_chunks": len(upload.text_chunks), "images": len(upload.images),
               "ocr_pages": upload.ocr_pages})

    existing = [f.name for f in workspace.list_files(principal.person_id)][:20]
    task_msg = (
        f"TASK: {question}{attached_note}\n"
        f"Workspace files: {', '.join(existing) if existing else '(empty)'}"
    )
    messages = [{"role": "system", "content": _system_prompt()}]

    # The plan is written in the SAME model call as the first tool call
    # (one round-trip fewer on slow hardware), and surfaced as its own event.
    _emit({"stage": "agent_plan", "status": "start"})
    plan: list[str] = []
    messages.append({"role": "user", "content": task_msg + (
        '\n\nFirst reply: a short numbered plan (2-6 steps naming the tool for each) AND your first tool call, as '
        '{"plan": ["1. ...", "2. ..."], "thought": "...", "tool": "<tool name>", "args": {...}}.')})

    trace: list[AgentStep] = []
    seen_calls: dict[str, int] = {}
    wanted_files = requested_deliverables(question)
    deliverable_nudges = 0
    empty_nudges = 0
    final_attempts = 0
    final_answer: Optional[str] = None
    final_citations: list[Citation] = []
    verified = False

    model_errors = 0
    for step in range(1, max_steps + 1):
        try:
            raw = chat(messages, purpose="planning")
            model_errors = 0
        except Exception as exc:
            model_errors += 1
            _emit({"stage": "agent_step", "status": "error", "step": step, "message": str(exc)})
            if model_errors >= 3:
                return _finish(db_path, principal, question, conversation_id, status="abstained",
                               answer=f"Task stopped: the local model server failed 3 times in a row ({exc}).",
                               ctx=ctx, plan=plan, trace=trace, reason="agent_model_unavailable",
                               artifacts=[workspace.describe(principal.person_id, n) for n in ctx.artifacts
                                          if workspace.exists(principal.person_id, n)])
            time.sleep(1.5 * model_errors)  # e.g. Ollama swapping models in/out of memory
            continue
        ctx.models_used.append(getattr(agent, "last_model_used", None) or "")
        messages.append({"role": "assistant", "content": raw})
        decision = _extract_json(raw)
        if decision is None:
            messages.append({"role": "user", "content": "That was not valid JSON. Respond with ONE JSON object: a tool call or final_answer."})
            continue
        if not plan and isinstance(decision.get("plan"), list):
            plan = [str(p).strip() for p in decision["plan"] if str(p).strip()][:8]
            _emit({"stage": "agent_plan", "status": "done", "plan": plan, "model": getattr(agent, "last_model_used", None)})
            if not (decision.get("tool") or decision.get("action") or "final_answer" in decision):
                messages.append({"role": "user", "content": "Plan noted. Now respond with your first tool call as JSON."})
                continue

        if "final_answer" in decision:
            answer = str(decision.get("final_answer") or "").strip()
            citations = _parse_citations(decision.get("citations"))
            if not answer and empty_nudges < 2:
                empty_nudges += 1
                messages.append({"role": "user", "content": (
                    "final_answer was empty. Write a short Markdown summary of what you did and the key results.")})
                continue
            produced = {n.rsplit(".", 1)[-1].lower() for n in ctx.artifacts}
            missing = sorted(wanted_files - produced)
            if missing and deliverable_nudges < 2:
                # Deterministic check: the user asked for a file this run
                # hasn't produced. Don't let the model declare victory.
                deliverable_nudges += 1
                _emit({"stage": "agent_final", "status": "fail", "attempt": final_attempts + 1,
                       "reason": f"requested .{', .'.join(missing)} file not created yet"})
                tools = {"docx": "create_word_document", "xlsx": "write_spreadsheet", "pptx": "create_presentation"}
                messages.append({"role": "user", "content": (
                    f"NOT DONE: the user asked for a .{', .'.join(missing)} file and none was created. Call "
                    f"{', '.join(tools.get(m, 'write_file') for m in missing)} now, then finish.")})
                continue
            final_attempts += 1
            _emit({"stage": "agent_final", "status": "start", "attempt": final_attempts,
                   "citations_claimed": len(citations)})
            if ctx.seen_passages:
                passages = list(ctx.seen_passages.values())
                failure = verify_check(citations, passages)
                repair = getattr(agent, "_repair_citations", None)
                if failure is not None and repair is not None:
                    # Same narrow second pass the document Q&A path uses: given
                    # the written answer, only extract supporting verbatim quotes.
                    # Still fully machine-verified below.
                    repaired = repair(getattr(agent, "ollama_planner_model", None) or agent.ollama_model, answer, passages)
                    if repaired and verify_check(repaired, passages) is None:
                        citations, failure = repaired, None
                if failure is None:
                    final_answer, final_citations, verified = answer, citations, True
                    _emit({"stage": "agent_final", "status": "pass", "attempt": final_attempts})
                    break
                _emit({"stage": "agent_final", "status": "fail", "attempt": final_attempts, "reason": failure})
                final_answer = answer
                if final_attempts >= MAX_FINAL_ATTEMPTS:
                    break
                excerpts = "\n".join(
                    f"- doc_id={p.doc_id} page={p.page}: {' '.join(p.text.split())[:350]}" for p in passages[:4])
                messages.append({"role": "user", "content": (
                    f"CITATION CHECK FAILED: {failure}\nPassages you were shown (copy 8-25 consecutive words "
                    f"exactly from ONE of these, and only claim what they say):\n{excerpts}\n"
                    "Respond with final_answer JSON again.")})
                continue
            final_answer, final_citations, verified = answer, [], True
            _emit({"stage": "agent_final", "status": "pass", "attempt": final_attempts})
            break

        tool = str(decision.get("tool") or decision.get("action") or "").strip()
        args = decision.get("args") or decision.get("arguments") or {}
        if not isinstance(args, dict):
            args = {}
        thought = str(decision.get("thought") or "")[:500]

        signature = json.dumps([tool, args], sort_keys=True, default=str)
        seen_calls[signature] = seen_calls.get(signature, 0) + 1
        _emit({"stage": "agent_step", "status": "start", "step": step, "tool": tool,
               "thought": thought, "args": _preview_args(args)})
        if seen_calls[signature] > 2:
            ok, observation, seconds = False, json.dumps({"error": "You already made this exact call twice. Change approach or finish."}), 0.0
        else:
            ok, observation, seconds = call_tool(ctx, tool, args)
        trace.append(AgentStep(step=step, thought=thought, tool=tool or "(none)", args=_preview_args(args),
                               ok=ok, observation=observation, duration_seconds=seconds))
        _emit({"stage": "agent_step", "status": "done", "step": step, "tool": tool, "ok": ok,
               "seconds": seconds, "observation": observation[:300]})
        messages.append({"role": "user", "content": f"OBSERVATION ({tool}, {'ok' if ok else 'error'}):\n{observation}\n\n"
                         "Next step as JSON (a tool call, or final_answer when the task is complete)."})

    artifacts = [workspace.describe(principal.person_id, n) for n in ctx.artifacts if workspace.exists(principal.person_id, n)]

    missing = sorted(wanted_files - {a.name.rsplit(".", 1)[-1].lower() for a in artifacts})
    if missing:
        # Never report a task as done when the file the user asked for doesn't exist.
        return _finish(db_path, principal, question, conversation_id, status="abstained",
                       answer=(f"Task not completed: the requested .{', .'.join(missing)} file was not produced. "
                               + (f"Partial output: {final_answer}" if final_answer else "")).strip(),
                       ctx=ctx, plan=plan, trace=trace, reason="agent_deliverable_missing", artifacts=artifacts)
    if final_answer is not None and not final_answer.strip():
        final_answer = "Task completed." if artifacts else None
        if final_answer is None:
            return _finish(db_path, principal, question, conversation_id, status="abstained",
                           answer="Task not completed: the agent produced no answer and no files.",
                           ctx=ctx, plan=plan, trace=trace, reason="agent_empty_answer")

    if final_answer is None:
        if artifacts:
            final_answer = "The step budget ran out before the agent wrote a summary. Files it produced are listed below."
            verified = not ctx.seen_passages
        else:
            return _finish(db_path, principal, question, conversation_id, status="abstained",
                           answer=f"Task not completed: the agent used its {max_steps}-step budget without finishing.",
                           ctx=ctx, plan=plan, trace=trace, reason="agent_step_budget_exhausted")

    if not verified:
        return _finish(db_path, principal, question, conversation_id, status="abstained",
                       answer=("Response withheld: the agent's claims about internal documents could not be verified "
                               "verbatim against the passages it read. Files it wrote are listed below but are "
                               "unverified -- review them before use."),
                       ctx=ctx, plan=plan, trace=trace, reason="agent_citations_unverified", artifacts=artifacts)

    if artifacts:
        final_answer += "\n\n**Files created:** " + ", ".join(f"`{a.name}`" for a in artifacts)
    return _finish(db_path, principal, question, conversation_id, status="answered", answer=final_answer,
                   ctx=ctx, plan=plan, trace=trace, citations=final_citations, artifacts=artifacts)


def _agent_note(status, citations, artifacts, ctx) -> str:
    if status != "answered":
        return ""  # default note for the outcome
    parts = ["Every tool result shown was produced by real execution, not reported by the model."]
    if citations:
        parts.append("The quotations were matched word-for-word against the passages the agent read; "
                     "the summary around them is model-written.")
    if artifacts:
        parts.append("Files were written by the agent and are not themselves verified"
                     + (" (Word files list the sources consulted)." if ctx and ctx.seen_passages else "."))
    return " ".join(parts)


def _finish(db_path, principal, question, conversation_id, status, answer, ctx, plan, trace,
            citations=None, artifacts=None, reason=None) -> AskResponse:
    label = ctx.current_label() if ctx else Label(tier=Tier.PUBLIC)
    denials = list(ctx.denials.values()) if ctx else []
    models = [m for m in (ctx.models_used if ctx else []) if m]
    last_code = ctx.code_runs[-1] if ctx and ctx.code_runs else None
    ledger_entry = ledger_log(
        db_path=db_path,
        actor=principal.person_id,
        action="AGENT_TASK_ANSWERED" if status == "answered" else "AGENT_TASK_ABSTAINED",
        details={
            "question": question,
            "category": "agent",
            "reason": reason,
            "plan": plan,
            "steps": [{"tool": s.tool, "ok": s.ok} for s in trace],
            "files": [a.name for a in (artifacts or [])],
            "passages_seen": [f"{d}:{p}" for d, p in (ctx.seen_passages if ctx else {})],
            "effective_tier": label.tier.value,
            "effective_compartments": sorted(c.value for c in label.compartments),
        },
    )
    response = AskResponse(
        status=status,
        answer=answer,
        citations=citations or [],
        denials=denials,
        effective_label=label,
        ledger_row_id=ledger_entry.row_id,
        conversation_id=conversation_id,
        model_used=models[-1] if models else None,
        plan=plan,
        agent_trace=trace,
        artifacts=artifacts or [],
        code=last_code["code"] if last_code else None,
        code_execution=last_code["result"] if last_code else None,
        verification_note=_agent_note(status, citations or [], artifacts or [], ctx),
    )
    if status == "answered":
        save_report_data(db_path=db_path, ledger_row_id=ledger_entry.row_id,
                         person_id=principal.person_id, question=question, response=response)
    append_turn(db_path, conversation_id, question, response)
    return response
