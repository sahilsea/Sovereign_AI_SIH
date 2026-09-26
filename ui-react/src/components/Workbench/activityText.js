import {
  GitBranch, Search, PenLine, ShieldCheck, Info, Code, Terminal, Eye,
  FileSearch, FileSignature, CheckCircle2, XCircle, ListChecks, Wrench, Calculator,
} from 'lucide-react';

// Which agent runs each backend stage (harness/runner.py, code_runner.py,
// approval_note.py). `role` = the configured model role it uses;
// `engine` = a deterministic step that involves no LLM at all.
export const STAGES = {
  intent: { agent: 'Intent Router', role: 'primary', icon: GitBranch },
  extraction: { agent: 'Document Parser', engine: 'text & image extraction', icon: FileSearch },
  retrieval: { agent: 'Retrieval Engine', engine: 'document search + security gate', icon: Search },
  drafting: { agent: 'Drafting Agent', role: 'primary', icon: PenLine },
  verification: { agent: 'Citation Verifier', engine: 'exact text match', icon: ShieldCheck },
  capability: { agent: 'Capability Agent', role: 'primary', icon: Info },
  code_drafting: { agent: 'Code Agent', role: 'code', icon: Code },
  code_execution: { agent: 'Python Sandbox', engine: 'isolated subprocess', icon: Terminal },
  vision: { agent: 'Vision Agent', role: 'vision', icon: Eye },
  approval_note_drafting: { agent: 'Findings Agent', role: 'primary', icon: FileSearch },
  approval_note_synthesis: { agent: 'Approval Note Agent', role: 'primary', icon: FileSignature },
  calculator: { agent: 'Calculator', engine: 'exact arithmetic', icon: Calculator },
  agent_plan: { agent: 'Planner Agent', role: 'planner', icon: ListChecks },
  agent_step: { agent: 'Tool Call', engine: 'deterministic tool', icon: Wrench },
  agent_final: { agent: 'Citation Verifier', engine: 'exact text match', icon: ShieldCheck },
  final: { agent: 'Pipeline', icon: CheckCircle2 },
  error: { agent: 'Pipeline', icon: XCircle },
};

const ROUTES = {
  content: 'document question → search corpus, draft, verify citations',
  code: 'coding request → Code Agent + Python sandbox',
  capability: 'question about the assistant → capability answer',
  other: 'not a real question → no drafting',
  calculation: 'calculation → model writes the expression, the exact calculator computes it',
  task: 'multi-step task → Planner Agent + local tools (search, files, spreadsheets, sandbox, vision)',
};

export function describe(ev) {
  const attempt = ev.attempt ? `Attempt ${ev.attempt}${ev.max_attempts ? `/${ev.max_attempts}` : ''}: ` : '';
  switch (`${ev.stage}:${ev.status || ''}`) {
    case 'intent:start': return ['Classifying what kind of request this is', 'running'];
    case 'intent:done':
      return ev.fallback
        ? [`Classifier model gave no usable answer — routed by keyword rules as "${ev.category}" — ${ROUTES[ev.category] || 'processing'}`, 'fail']
        : [`Routed as "${ev.category}" — ${ROUTES[ev.category] || 'processing'}`, 'ok'];
    case 'extraction:done': return [
      `Extracted ${ev.text_chunks} text chunk(s)${ev.ocr_pages ? ` (${ev.ocr_pages} via on-device OCR)` : ''} and ${ev.images} image(s) from ${ev.filename}`, 'ok',
    ];
    case 'calculator:start': return [ev.translated_by ? `Model ${ev.translated_by} wrote the expression — evaluating it exactly` : 'Recognised a calculation — evaluating it exactly', 'running'];
    case 'calculator:done': return [`${ev.expression} = ${ev.result} (${ev.steps} step${ev.steps === 1 ? '' : 's'})`, 'ok'];
    case 'calculator:error': return [`Calculator rejected it — ${ev.message}`, 'fail'];
    case 'agent_plan:start': return ['Planning the steps for this task', 'running'];
    case 'agent_plan:done': return [
      ev.plan?.length ? `Plan: ${ev.plan.join('  ')}` : 'No explicit plan — acting step by step', ev.plan?.length ? 'ok' : 'info',
    ];
    case 'agent_plan:error': return [`Planning failed — ${ev.message}`, 'fail'];
    case 'agent_step:start': return [
      `Step ${ev.step}: ${ev.tool}(${Object.keys(ev.args || {}).join(', ')})${ev.thought ? ` — ${ev.thought}` : ''}`, 'running',
    ];
    case 'agent_step:done': return [
      `Step ${ev.step}: ${ev.tool} ${ev.ok ? 'succeeded' : 'failed'} in ${ev.seconds}s — ${ev.observation || ''}`, ev.ok ? 'ok' : 'fail',
    ];
    case 'agent_step:error': return [`Step ${ev.step}: model call failed — ${ev.message}`, 'fail'];
    case 'agent_final:start': return [`Checking the agent's final answer (${ev.citations_claimed} citation(s))`, 'running'];
    case 'agent_final:pass': return ['Final answer accepted', 'ok'];
    case 'agent_final:fail': return [`Final answer rejected — ${ev.reason}`, 'fail'];
    case 'retrieval:start': return [`Searching the document corpus (${ev.mode || 'lexical'})`, 'running'];
    case 'retrieval:done': return [
      `Found ${ev.passages_found} readable passage(s); ${ev.denials_found} document(s) withheld by the security gate`,
      ev.passages_found > 0 ? 'ok' : 'fail',
    ];
    case 'drafting:start': return [`${attempt}writing an answer from the passages`, 'running'];
    case 'drafting:done': return [`${attempt}draft ready with ${ev.citations_claimed} citation(s)`, 'ok'];
    case 'drafting:error': return [`${attempt}drafting failed — ${ev.message}`, 'fail'];
    case 'verification:start': return [`${attempt}checking every quote against the source text`, 'running'];
    case 'verification:pass': return [`${attempt}all citations verified verbatim`, 'ok'];
    case 'verification:fail': return [`${attempt}rejected — ${ev.reason}`, 'fail'];
    case 'capability:start': return ['Answering from real system and access facts', 'running'];
    case 'capability:done': return ['Capability answer ready', 'ok'];
    case 'code_drafting:start': return [`${attempt}writing a Python script`, 'running'];
    case 'code_drafting:done': return [`${attempt}script ready`, 'ok'];
    case 'code_drafting:error': return [`${attempt}${ev.message}`, 'fail'];
    case 'code_execution:start': return [`${attempt}running the script in the sandbox`, 'running'];
    case 'code_execution:done': return [
      `${attempt}exit code ${ev.exit_code}${ev.timed_out ? ' (timed out)' : ''}`,
      ev.exit_code === 0 && !ev.timed_out ? 'ok' : 'fail',
    ];
    case 'vision:start': return [`Analyzing image ${ev.label}`, 'running'];
    case 'vision:done': return [`Described ${ev.label}`, 'ok'];
    case 'vision:error': return [`Could not analyze ${ev.label} — ${ev.message}`, 'fail'];
    case 'approval_note_drafting:start': return [`${attempt}extracting findings from the report`, 'running'];
    case 'approval_note_drafting:pass': return [`${attempt}findings verified verbatim`, 'ok'];
    case 'approval_note_drafting:fail': return [`${attempt}rejected — ${ev.reason}`, 'fail'];
    case 'approval_note_drafting:error': return [`${attempt}${ev.message}`, 'fail'];
    case 'approval_note_synthesis:start': return ['Writing title, summary and recommendation', 'running'];
    case 'approval_note_synthesis:done': return ['Approval note ready', 'ok'];
    default:
      if (ev.stage === 'final') {
        const r = ev.response || {};
        const cites = r.citations?.length || 0;
        return r.status === 'answered'
          ? [`Answered${cites ? ` with ${cites} verified citation(s)` : ''}`, 'ok']
          : ['Response withheld (abstained)', 'fail'];
      }
      if (ev.stage === 'error') return [ev.message || 'Request failed', 'fail'];
      return [`${ev.stage} ${ev.status || ''}`.trim(), 'info'];
  }
}


// One plain-language line for the current step of a running request -- the
// single prominent progress message in the chat. Details stay in "View activity".
export function progressMessage(events) {
  const ev = events[events.length - 1];
  if (!ev) return 'Sending your request…';
  switch (ev.stage) {
    case 'intent': return ev.status === 'start' ? 'Understanding your request…' : 'Choosing how to handle it…';
    case 'extraction': return 'Reading your file…';
    case 'retrieval': return 'Searching documents…';
    case 'drafting': return ev.attempt > 1 ? 'Rewriting the answer…' : 'Writing the answer…';
    case 'verification': return 'Checking citations…';
    case 'capability': return 'Preparing an answer…';
    case 'code_drafting': return ev.attempt > 1 ? 'Fixing the code…' : 'Writing code…';
    case 'code_execution': return 'Running code in the sandbox…';
    case 'vision': return 'Reading the image…';
    case 'approval_note_drafting': return 'Extracting findings from the report…';
    case 'approval_note_synthesis': return 'Writing the approval note…';
    case 'calculator': return 'Calculating…';
    case 'agent_plan': return 'Planning the task…';
    case 'agent_step': {
      const label = {
        calculate: 'Calculating', search_documents: 'Searching documents', read_file: 'Reading a file', read_spreadsheet: 'Reading the spreadsheet',
        run_python: 'Running code in the sandbox', analyze_image: 'Reading the image', write_file: 'Writing a file',
        write_spreadsheet: 'Creating the spreadsheet', create_word_document: 'Creating the Word document',
        create_presentation: 'Creating the presentation', list_files: 'Checking your files',
      }[ev.tool] || 'Working';
      return `Step ${ev.step}: ${label}…`;
    }
    case 'agent_final': return 'Checking citations…';
    default: return 'Working…';
  }
}

/**
 * Turns the raw backend event stream into numbered steps. A stage's "start"
 * and its matching "done/pass/fail/error" become ONE step that goes from
 * running to finished, so the list reads as "what happened, in order"
 * instead of a wall of start/stop lines.
 *
 * events: backend events, each with `_at` (ms timestamp when received).
 */
export function buildSteps(events) {
  const steps = [];
  const open = {};
  for (const ev of events) {
    if (ev.stage === 'final') continue;
    const key = `${ev.stage}|${ev.step ?? ev.attempt ?? ev.label ?? ''}`;
    const [text, tone] = describe(ev);
    if (ev.status === 'start') {
      const step = { key, stage: ev.stage, startAt: ev._at, endAt: null, tone: 'running', text, model: ev.model, ev };
      open[key] = step;
      steps.push(step);
    } else if (open[key]) {
      Object.assign(open[key], { endAt: ev._at, tone, text, model: ev.model || open[key].model, ev });
      delete open[key];
    } else {
      steps.push({ key, stage: ev.stage, startAt: ev._at, endAt: ev._at, tone, text, model: ev.model, ev });
    }
  }
  return steps;
}

