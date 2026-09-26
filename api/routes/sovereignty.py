"""Live sovereignty evidence for the Sovereignty page.

ZERO ACCESS DECISIONS INSIDE. Read-only views over trust/egress.py (guard +
OS socket-table monitor) and plain facts about where data lives.
"""

from __future__ import annotations

import os
import socket
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, status

from auth.deps import current_principal, get_db_path, require_admin
from contracts import Principal
from trust import egress
from trust.ledger import log as ledger_log

router = APIRouter(prefix="/sovereignty", tags=["Sovereignty"])

# A well-known public address used ONLY for the guard self-test below. The
# probe runs only in "block" mode, where the guard raises before connect()
# is ever called -- no packet is sent.
_PROBE_TARGET = ("1.1.1.1", 443)


@router.get("/network")
def network_status(principal: Principal = Depends(current_principal)):
    """Live egress evidence: guard mode + blocked attempts, and what the OS
    socket table says the SEVERANCE and Ollama processes are connected to."""
    snap = egress.snapshot()
    snap["ollama_api_base"] = os.getenv("OLLAMA_API_BASE", "http://localhost:11434")
    snap["sandbox_mode"] = "container (no network interface)" if os.getenv("SANDBOX_SOCKET") else "local subprocess"
    return snap


@router.post("/network/probe")
def probe_guard(principal: Principal = Depends(require_admin)):
    """Deliberately attempt an outbound connection to a public address and
    report what the guard did. Refused unless the guard is blocking, so this
    can never itself cause egress."""
    mode = egress.snapshot()["guard"]["mode"]
    if mode != "block":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Egress guard is in '{mode}' mode; the probe only runs when it is blocking.",
        )
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(2.0)
    try:
        sock.connect(_PROBE_TARGET)
        outcome = {"blocked": False, "detail": "Connection was NOT blocked."}
    except egress.EgressBlocked as exc:
        outcome = {"blocked": True, "detail": str(exc)}
    except OSError as exc:
        outcome = {"blocked": False, "detail": f"Not blocked by the guard; failed at the OS level: {exc}"}
    finally:
        sock.close()
    ledger_log(
        db_path=get_db_path(),
        actor=principal.person_id,
        action="EGRESS_GUARD_PROBE",
        details={"target": f"{_PROBE_TARGET[0]}:{_PROBE_TARGET[1]}", **outcome},
    )
    return outcome


@router.get("/facts")
def data_residency(principal: Principal = Depends(current_principal)):
    """Where this deployment actually keeps its data -- real paths, not claims."""
    root = Path(__file__).parent.parent.parent
    db_path = Path(get_db_path())
    if not db_path.is_absolute():
        db_path = (Path.cwd() / db_path).resolve()
    return {
        "database": str(db_path),
        "corpus_dir": str((root / "corpus" / "documents").resolve()),
        "workspace_dir": str(Path(os.getenv("SEVERANCE_WORKSPACE_DIR", root / "workspace")).resolve()),
        "ollama_api_base": os.getenv("OLLAMA_API_BASE", "http://localhost:11434"),
        "at_rest_encryption": "Not applied by the app -- use full-disk encryption (FileVault/LUKS/BitLocker) on the host.",
    }
