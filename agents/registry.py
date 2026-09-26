"""Local model registry and task-based auto-selection.

The backend is not locked to one model. config/models.json lists every
open-weight model this deployment knows about, with the task types each is
suited to and a priority. For each task the router picks:

  1. the env-var pin for that task (e.g. OLLAMA_CODE_MODEL), if installed;
  2. otherwise the highest-priority registry model for that task that is
     actually installed on the local Ollama server right now;
  3. otherwise the pin (or the top registry entry) anyway, so the failure
     surfaces as a clear "model not found" instead of a silent substitution.

Adding a model later is `ollama pull <id>` plus one JSON entry -- no code
change. The only network call here is to OLLAMA_API_BASE (local by design).
"""

from __future__ import annotations

import json
import os
import threading
import time
from pathlib import Path
from typing import Optional

import httpx

REGISTRY_PATH = Path(__file__).parent.parent / "config" / "models.json"

TASKS = ("document", "planning", "code", "vision", "embedding")

# Which env var pins which task. "planning" falls back to the document pin,
# since both are general instruction-following text models.
_TASK_ENV = {
    "document": ("OLLAMA_MODEL",),
    "planning": ("OLLAMA_PLANNER_MODEL", "OLLAMA_MODEL"),
    "code": ("OLLAMA_CODE_MODEL",),
    "vision": ("OLLAMA_VISION_MODEL",),
    "embedding": ("OLLAMA_EMBED_MODEL",),
}

_INSTALLED_TTL_SECONDS = 30.0
_installed_cache: tuple[float, Optional[set[str]]] = (0.0, None)
_cache_lock = threading.Lock()


def normalize(model_id: str) -> str:
    """Ollama reports untagged models as '<name>:latest'."""
    model_id = (model_id or "").strip()
    return model_id if not model_id or ":" in model_id else f"{model_id}:latest"


def load_registry() -> list[dict]:
    try:
        data = json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))
        models = data.get("models", [])
    except (OSError, ValueError):
        models = []
    for m in models:
        m["id"] = normalize(m.get("id", ""))
    return [m for m in models if m["id"]]


def installed_models(force: bool = False) -> Optional[set[str]]:
    """Model ids pulled on the local Ollama server, or None if unreachable.
    Cached briefly so per-request agent construction stays cheap."""
    global _installed_cache
    with _cache_lock:
        fetched_at, cached = _installed_cache
        if not force and cached is not None and time.time() - fetched_at < _INSTALLED_TTL_SECONDS:
            return cached
    base = os.getenv("OLLAMA_API_BASE", "http://localhost:11434").rstrip("/")
    try:
        with httpx.Client(timeout=1.5) as client:
            res = client.get(f"{base}/api/tags")
            res.raise_for_status()
            ids = {normalize(m.get("name") or m.get("model", "")) for m in res.json().get("models", [])}
    except Exception:
        ids = None
    with _cache_lock:
        _installed_cache = (time.time(), ids)
    return ids


def _pin(task: str) -> str:
    for var in _TASK_ENV.get(task, ()):
        value = os.getenv(var, "").strip()
        if value:
            return value
    return ""


def candidates(task: str) -> list[dict]:
    """Registry entries for a task, best first."""
    return sorted(
        (m for m in load_registry() if task in m.get("tasks", [])),
        key=lambda m: m.get("priority", 0),
        reverse=True,
    )


def pick(task: str, default: str = "") -> str:
    """Resolve the model id to use for `task`. See module docstring."""
    pin = _pin(task)
    installed = installed_models()
    if installed is not None:
        if pin and normalize(pin) in installed:
            return pin
        for m in candidates(task):
            if m["id"] in installed:
                return m["id"]
    if pin:
        return pin
    ranked = candidates(task)
    return ranked[0]["id"] if ranked else default


def selection_table() -> dict:
    """Everything the Models page needs: each registry model with install
    status, plus which model each task currently resolves to and why."""
    installed = installed_models(force=True)
    registry = load_registry()
    known = {m["id"] for m in registry}
    selected = {task: pick(task) for task in TASKS}

    def reason(task: str, model_id: str) -> str:
        pin = _pin(task)
        if pin and normalize(pin) == normalize(model_id):
            return "pinned by environment"
        return "auto-selected: highest-priority installed model for this task"

    models = []
    for m in registry:
        models.append({
            **{k: v for k, v in m.items() if k != "id"},
            "id": m["id"],
            "installed": None if installed is None else m["id"] in installed,
            "selected_for": [t for t, sel in selected.items() if normalize(sel) == m["id"]],
        })
    # Pinned models that aren't in the registry still show up.
    for task, sel in selected.items():
        if sel and normalize(sel) not in known:
            known.add(normalize(sel))
            models.append({
                "id": normalize(sel), "tasks": [task], "priority": None, "family": "", "params": "",
                "installed": None if installed is None else normalize(sel) in installed,
                "selected_for": [t for t, s in selected.items() if normalize(s) == normalize(sel)],
            })
    return {
        "ollama_reachable": installed is not None,
        "selection": {t: {"model": s, "reason": reason(t, s)} for t, s in selected.items() if s},
        "models": models,
        "unregistered_installed": sorted((installed or set()) - known),
    }
