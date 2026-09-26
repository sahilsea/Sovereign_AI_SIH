"""Shared Pydantic contracts and schemas for SEVERANCE.

This module is the single cross-file vocabulary for data structures across
the entire system. It contains shapes and type constraints only, with zero
business logic and zero side effects.
"""

from __future__ import annotations

from enum import Enum
from typing import Any, Literal, Optional
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


# ---------------------------------------------------------------------------
# Core Enums
# ---------------------------------------------------------------------------

class Tier(str, Enum):
    """Ranked security classification tiers in ascending sensitivity."""
    PUBLIC = "public"
    INTERNAL = "internal"
    CONFIDENTIAL = "confidential"
    SECRET = "secret"


class Compartment(str, Enum):
    """Unranked, orthogonal clearance compartments."""
    HSE = "hse"
    VIGILANCE = "vigilance"
    LEGAL = "legal"
    COMMERCIAL = "commercial"
    TECHNICAL = "technical"


# Valid MRPL Pay Grades
# Officers: A through I
# Non-Management: S1-S4, JM1-JM6, TS1-TS6
VALID_OFFICER_GRADES = {"A", "B", "C", "D", "E", "F", "G", "H", "I"}
VALID_NON_MGMT_GRADES = {
    "S1", "S2", "S3", "S4",
    "JM1", "JM2", "JM3", "JM4", "JM5", "JM6",
    "TS1", "TS2", "TS3", "TS4", "TS5", "TS6",
}
VALID_MRPL_GRADES = VALID_OFFICER_GRADES | VALID_NON_MGMT_GRADES


# ---------------------------------------------------------------------------
# Security & Access Shapes
# ---------------------------------------------------------------------------

class Label(BaseModel):
    """Two-axis security label applied to passages, documents, and generated answers."""
    model_config = ConfigDict(frozen=True)

    tier: Tier = Field(
        default=Tier.INTERNAL,
        description="Hierarchical security classification tier (public, internal, confidential, secret)"
    )
    compartments: frozenset[Compartment] = Field(
        default_factory=frozenset,
        description="Set of unranked compartments required to access this resource"
    )


class Principal(BaseModel):
    """Immutable identity and clearance attributes of an authenticated actor."""
    model_config = ConfigDict(frozen=True)

    person_id: str = Field(description="Unique alphanumeric employee ID (e.g. cvo-001, emp-102)")
    name: str = Field(description="Full legal name of the employee")
    job_title: str = Field(description="Official organizational designation or role")
    grade: str = Field(description="MRPL pay grade (officers A-I, non-management S1-S4, JM1-JM6, TS1-TS6)")
    compartments: frozenset[Compartment] = Field(
        default_factory=frozenset,
        description="Active granted compartments for this principal"
    )
    is_admin: bool = Field(
        default=False,
        description="Whether this principal possesses administrative account provisioning authority"
    )

    @field_validator("grade")
    @classmethod
    def validate_grade(cls, v: str) -> str:
        v_upper = v.strip().upper()
        if v_upper not in VALID_MRPL_GRADES:
            raise ValueError(
                f"Invalid MRPL grade '{v}'. Must be one of officers {sorted(VALID_OFFICER_GRADES)} "
                f"or non-management {sorted(VALID_NON_MGMT_GRADES)}"
            )
        return v_upper


# ---------------------------------------------------------------------------
# Document & Retrieval Shapes
# ---------------------------------------------------------------------------

class Passage(BaseModel):
    """A single page-level passage extracted from a document."""
    doc_id: str = Field(description="Unique document identifier")
    page: int = Field(description="1-based page number within the document")
    text: str = Field(description="Raw text content extracted from this page")
    label: Label = Field(description="Two-axis security label governing access to this passage")
    title: str = Field(default="", description="Descriptive human-readable document title")


class Denial(BaseModel):
    """Record of a passage or document withheld by the security gate.

    CRITICAL: A Denial carries only identifiers and deterministic reasons.
    It NEVER contains text or content snippets, guaranteeing that withheld
    information cannot leak downstream.
    """
    model_config = ConfigDict(frozen=True)

    doc_id: str = Field(description="Identifier of the document that was withheld")
    reason: str = Field(description="Deterministic security reason why access was denied")
    required_label: Optional[Label] = Field(
        default=None,
        description="Security label required to access the withheld resource"
    )


class Citation(BaseModel):
    """A verified or proposed verbatim quote supporting an answer statement."""
    model_config = ConfigDict(frozen=True)

    doc_id: str = Field(description="Identifier of the document containing the cited text")
    page: int = Field(description="1-based page number within the document")
    quote: str = Field(
        min_length=20,
        max_length=300,
        description="Exact verbatim text copied from the passage (20 to 300 characters, minimum 5 words)"
    )

    @field_validator("quote")
    @classmethod
    def validate_quote_words(cls, v: str) -> str:
        words = v.strip().split()
        if len(words) < 5:
            raise ValueError(
                f"Citation quote must contain at least 5 words to represent substantive content, got {len(words)}"
            )
        return v


# ---------------------------------------------------------------------------
# Agent Draft & Exchange Shapes
# ---------------------------------------------------------------------------

class Draft(BaseModel):
    """Structured response proposed by a drafting agent before verification."""
    answer: str = Field(description="Proposed textual answer synthesized from provided passages")
    citations: list[Citation] = Field(
        default_factory=list,
        description="Structured citations claiming exact verbatim quotes from provided passages"
    )


# ---------------------------------------------------------------------------
# API Request & Response Shapes
# ---------------------------------------------------------------------------

class AskRequest(BaseModel):
    """Request payload for the /ask workbench endpoint."""
    question: str = Field(min_length=3, description="Natural language question to ask against the corpus")
    top_k: int = Field(
        default=3,
        ge=1,
        le=10,
        description="Number of top readable passages to retrieve for synthesis"
    )
    upload_id: Optional[str] = Field(
        default=None,
        description=(
            "ID of a previously uploaded ephemeral file (image or .pptx), from POST /ask/upload. "
            "When set, the question is answered from THAT file's content instead of the governed "
            "corpus -- no two-axis clearance gate applies, since this is the caller's own session-"
            "scoped content, not corpus data."
        ),
    )
    conversation_id: Optional[str] = Field(
        default=None,
        description=(
            "ID of an existing persisted conversation (from GET /conversations) to continue. "
            "Omit to start a new conversation -- one is created automatically from this question."
        ),
    )
    mode: Literal["auto", "agent"] = Field(
        default="auto",
        description=(
            "'auto' lets the intent router pick the path (document Q&A, code, capability, or a "
            "multi-step agent task). 'agent' always runs the tool-using agent loop "
            "(harness/agent_loop.py)."
        ),
    )


class AgentStep(BaseModel):
    """One tool call made by the agent loop, as actually executed.

    `ok`/`observation` come from the deterministic tool implementation
    (harness/agent_tools.py), never from the model's own account of it.
    """
    step: int = Field(description="1-based step number")
    thought: str = Field(default="", description="The model's stated reason for this step")
    tool: str = Field(description="Tool name that was called")
    args: dict[str, Any] = Field(default_factory=dict, description="Arguments passed (long values truncated)")
    ok: bool = Field(description="Whether the tool succeeded")
    observation: str = Field(description="Truncated tool result fed back to the model")
    duration_seconds: float = Field(default=0.0, description="Wall-clock tool time")


class WorkspaceFile(BaseModel):
    """A file in the caller's private agent workspace (harness/workspace.py)."""
    name: str = Field(description="Flat filename inside the caller's workspace")
    size_bytes: int = Field(description="File size")
    modified: str = Field(description="ISO 8601 modification time")
    origin: str = Field(default="agent", description="'agent' (written by a tool) or 'upload'")
    label: Label = Field(
        default_factory=lambda: Label(tier=Tier.PUBLIC),
        description="Classification inherited from every corpus passage the agent had seen when writing it",
    )


Outcome = Literal["sourced", "computed", "general", "unavailable", "restricted"]

VERIFICATION_NOTES: dict[str, str] = {
    "sourced": (
        "Each quotation below was matched word-for-word against its source page. The summary around "
        "the quotations was written by the model from those pages and is not itself verified; check "
        "important details against the quoted sources."
    ),
    "computed": (
        "Code and tool steps shown were actually executed, and their outputs are real. Any wording "
        "around those outputs was written by the model."
    ),
    "general": "No document sources were used, so nothing in this answer was checked against a source.",
    "unavailable": "No answer could be grounded in a document you can read, so none is given.",
    "restricted": (
        "Documents matching this question exist, but you are not cleared to read them. Their contents "
        "were never shown to the model."
    ),
}


class AskResponse(BaseModel):
    """Response returned by the /ask workbench endpoint."""
    status: Literal["answered", "abstained"] = Field(
        description="Outcome status: answered if grounded and verified, abstained if withheld or unverified"
    )
    answer: str = Field(description="Synthesized answer text or formal abstention notification")
    citations: list[Citation] = Field(
        default_factory=list,
        description="Verified verbatim citations supporting the answer"
    )
    denials: list[Denial] = Field(
        default_factory=list,
        description="List of withheld documents and reasons (never contains withheld text)"
    )
    effective_label: Label = Field(
        description="Inherited security classification of the synthesized answer"
    )
    ledger_row_id: Optional[int] = Field(
        default=None,
        description="Primary key of the immutable audit ledger entry recording this transaction"
    )
    conversation_id: Optional[str] = Field(
        default=None,
        description="ID of the persisted conversation this turn was saved to"
    )
    code: Optional[str] = Field(
        default=None,
        description=(
            "Present only when the query was routed to the code-execution path (see "
            "harness/code_runner.py). The exact source code that was actually run in the "
            "sandbox -- never edited after execution, so this is always what code_execution "
            "reports the outcome of."
        ),
    )
    code_execution: Optional["CodeExecutionResult"] = Field(
        default=None,
        description="Deterministic sandbox execution outcome for `code`, when present.",
    )
    approval_note: Optional["ApprovalNote"] = Field(
        default=None,
        description=(
            "Present only when this response was produced by the approval-note pipeline "
            "(harness/approval_note.py) from a scanned/uploaded report, instead of the "
            "general Q&A path."
        ),
    )
    model_used: Optional[str] = Field(
        default=None,
        description=(
            "Local Ollama model that actually produced this answer (e.g. the drafting model, "
            "a promoted fallback model, the code model, or the vision model), as reported by "
            "the agent. None when no model call was made at all (immediate abstention, or the "
            "MockAgent backend)."
        ),
    )
    plan: list[str] = Field(
        default_factory=list,
        description="Agent tasks only: the step-by-step plan the planner model proposed up front.",
    )
    agent_trace: list[AgentStep] = Field(
        default_factory=list,
        description="Agent tasks only: every tool call actually executed, in order.",
    )
    artifacts: list[WorkspaceFile] = Field(
        default_factory=list,
        description="Agent tasks only: deliverable files written to the caller's workspace during this run.",
    )
    outcome: Optional[Outcome] = Field(
        default=None,
        description=(
            "What kind of result this is, decided by deterministic code (never the model): "
            "'sourced' = answer with verified quotations from sources; 'computed' = result produced by "
            "executed code/tools; 'general' = answer with no document sources (e.g. about the assistant); "
            "'unavailable' = no answer could be grounded; 'restricted' = matching documents exist but the "
            "caller is not cleared to read them. Filled in automatically when not set explicitly."
        ),
    )
    verification_note: str = Field(
        default="",
        description=(
            "Plain statement of exactly what was machine-checked for this result. Citation checks cover "
            "the quoted text only -- never the model-written summary around it."
        ),
    )

    @model_validator(mode="after")
    def _fill_outcome(self) -> "AskResponse":
        if self.outcome is None:
            if self.status == "answered":
                if self.citations:
                    self.outcome = "sourced"
                elif self.code_execution is not None or self.artifacts or self.agent_trace:
                    self.outcome = "computed"
                else:
                    self.outcome = "general"
            else:
                self.outcome = "unavailable"
        if not self.verification_note:
            self.verification_note = VERIFICATION_NOTES[self.outcome]
        return self


# ---------------------------------------------------------------------------
# Code Execution Shapes (Sandboxed Agentic Coding Task)
# ---------------------------------------------------------------------------

class CodeExecutionResult(BaseModel):
    """Deterministic, ground-truth outcome of running `code` in the sandbox.

    NON-NEGOTIABLE: this is produced ONLY by agents/sandbox.py actually
    executing the code in an isolated subprocess. It is never inferred,
    summarized, or guessed by a model -- exactly the same "code disposes"
    discipline harness/verify.py applies to citations.
    """
    model_config = ConfigDict(frozen=True)

    stdout: str = Field(description="Captured standard output, truncated to a safe max length")
    stderr: str = Field(description="Captured standard error, truncated to a safe max length")
    exit_code: int = Field(description="Process exit code (0 = success). -1 if the process was killed.")
    timed_out: bool = Field(description="True if execution was killed for exceeding the time limit")
    duration_seconds: float = Field(description="Wall-clock execution time")


class CodeAnswer(BaseModel):
    """Structured response proposed by a coding drafting agent before execution."""
    code: str = Field(description="Proposed Python source code to run, complete and self-contained")
    explanation: str = Field(default="", description="Brief explanation of what the code does")


# ---------------------------------------------------------------------------
# Approval Note Shapes (Scanned Report -> Approval Note pipeline)
# ---------------------------------------------------------------------------

class ApprovalNote(BaseModel):
    """Structured approval note synthesized from a scanned/uploaded report.

    Findings mix two provenances that must never be presented with equal
    confidence: `verified_findings` are citation-checked verbatim substrings
    of OCR/text-extracted page content (same discipline as Citation above);
    `visual_observations` are unverified vision-model descriptions of pages
    or images that had no recoverable text layer. See harness/approval_note.py.
    """
    title: str = Field(description="Short descriptive title for the approval note")
    summary: str = Field(description="2-4 sentence executive summary of the source report")
    verified_findings: list[Citation] = Field(
        default_factory=list,
        description="Key findings grounded in verbatim, citation-verified text from the source",
    )
    visual_observations: list[str] = Field(
        default_factory=list,
        description="Unverified vision-model descriptions of pages/images with no text layer",
    )
    recommendation: str = Field(description="Proposed recommendation or action for the approving authority")
    source_filename: str = Field(description="Filename of the original uploaded report")


# ---------------------------------------------------------------------------
# Audit Ledger Shapes
# ---------------------------------------------------------------------------

class LedgerEntry(BaseModel):
    """An immutable, cryptographically hash-chained audit record."""
    model_config = ConfigDict(frozen=True)

    row_id: int = Field(description="Sequential auto-increment row ID")
    timestamp: str = Field(description="ISO 8601 UTC timestamp of the entry")
    actor: str = Field(description="person_id of the user or system component initiating the action")
    action: str = Field(description="Action identifier (e.g. ASK_QUERY, GRANT_COMPARTMENT, SET_GRADE)")
    details: dict[str, Any] = Field(description="Structured details of the event")
    prev_hash: str = Field(description="SHA-256 hash of the immediately preceding row (64 zeros for row 1)")
    hash: str = Field(description="SHA-256 hash of canonical JSON serialization of this row")


# ---------------------------------------------------------------------------
# Authentication & Administration Shapes
# ---------------------------------------------------------------------------

class LoginRequest(BaseModel):
    """Credentials payload for session establishment."""
    person_id: str = Field(description="Employee ID")
    password: str = Field(description="Account password")


class CreateUserRequest(BaseModel):
    """Account provisioning payload.

    CRITICAL: Admins assign pay grades. Admins CANNOT assign compartments.
    Therefore, compartments are strictly absent from this schema.
    """
    person_id: str = Field(description="Unique employee ID for the new account")
    name: str = Field(description="Full legal name")
    job_title: str = Field(description="Designation or job title")
    grade: str = Field(description="Initial MRPL pay grade (e.g. A, B, S1, JM2)")

    @field_validator("grade")
    @classmethod
    def validate_grade(cls, v: str) -> str:
        v_upper = v.strip().upper()
        if v_upper not in VALID_MRPL_GRADES:
            raise ValueError(f"Invalid MRPL grade '{v}'.")
        return v_upper


class UpdateGradeRequest(BaseModel):
    """Payload to update an employee's pay grade (admin only, never self)."""
    grade: str = Field(description="New MRPL pay grade")

    @field_validator("grade")
    @classmethod
    def validate_grade(cls, v: str) -> str:
        v_upper = v.strip().upper()
        if v_upper not in VALID_MRPL_GRADES:
            raise ValueError(f"Invalid MRPL grade '{v}'.")
        return v_upper


class GrantCompartmentRequest(BaseModel):
    """Payload to grant a compartment (sponsor of that compartment only, never self)."""
    person_id: str = Field(description="Target employee receiving the compartment clearance")
    compartment: Compartment = Field(description="Compartment to grant")


class RevokeCompartmentRequest(BaseModel):
    """Payload to revoke a compartment (sponsor of that compartment only, never self)."""
    person_id: str = Field(description="Target employee whose clearance is being revoked")
    compartment: Compartment = Field(description="Compartment to revoke")


class SetCompartmentsRequest(BaseModel):
    """Payload for the System Administrator to set a user's full compartment set (never self)."""
    compartments: list[Compartment] = Field(
        description="The complete set of compartments the target should hold; anything not listed is removed"
    )


class ChangePasswordRequest(BaseModel):
    """Payload for password change, required on must_change_password accounts."""
    old_password: str = Field(description="Current password")
    new_password: str = Field(min_length=8, description="New password (minimum 8 characters)")


class UserSummary(BaseModel):
    """Public profile representation of an employee account."""
    person_id: str = Field(description="Employee ID")
    name: str = Field(description="Full legal name")
    job_title: str = Field(description="Designation")
    grade: str = Field(description="MRPL pay grade")
    compartments: list[Compartment] = Field(description="Compartments this person can read (granted + sponsored)")
    sponsor_of: list[Compartment] = Field(default_factory=list, description="Compartment(s) this person sponsors")
    is_admin: bool = Field(description="Whether account has admin privileges")
    is_active: bool = Field(description="Whether account is active")
    must_change_password: bool = Field(description="Whether user must update password upon next login")
