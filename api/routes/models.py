"""Model inventory endpoint for the workbench's Models page.

ZERO ACCESS DECISIONS INSIDE.
Read-only: reports the local model registry (config/models.json), which
model each task type currently auto-selects (agents/registry.py), and
whether each is actually pulled on the local Ollama server. Never leaves
the machine -- the only network call is to OLLAMA_API_BASE.
"""

from __future__ import annotations

import os
from fastapi import APIRouter, Depends
from agents import registry
from contracts import Principal
from auth.deps import current_principal

router = APIRouter(prefix="/models", tags=["Models"])

# Task -> the role names the frontend already uses for highlighting.
_TASK_ROLE = {"document": "primary", "planning": "planner", "code": "code", "vision": "vision", "embedding": "embedding"}


@router.get("")
def list_models(
    principal: Principal = Depends(current_principal),
):
    """List registry models with install status and per-task auto-selection."""
    backend = os.getenv("AGENT_BACKEND", "ollama").lower()
    table = registry.selection_table()

    fallback = os.getenv("OLLAMA_FALLBACK_MODEL", "").strip()
    models = []
    for m in table["models"]:
        roles = [_TASK_ROLE[t] for t in m["selected_for"] if t in _TASK_ROLE]
        if fallback and registry.normalize(fallback) == m["id"]:
            roles.append("fallback")
        status = "unknown" if m["installed"] is None else ("installed" if m["installed"] else "missing")
        models.append({**m, "roles": roles, "status": status})
    # Selected / installed models first, then the rest of the registry.
    models.sort(key=lambda m: (not m["roles"], m["status"] != "installed", -(m.get("priority") or 0)))

    return {
        "backend": backend,
        "ollama_api_base": os.getenv("OLLAMA_API_BASE", "http://localhost:11434").rstrip("/"),
        "ollama_reachable": table["ollama_reachable"],
        "selection": table["selection"],
        "unregistered_installed": table["unregistered_installed"],
        "models": models,
    }
