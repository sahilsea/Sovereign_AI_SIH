"""Per-person agent workspace: the directory the agent's file tools act on.

NON-NEGOTIABLE DESIGN PRINCIPLES:
1. One flat directory per person_id under SEVERANCE_WORKSPACE_DIR. Tool
   filenames are basenames only -- no subdirectories, no "..", no absolute
   paths, no dotfiles -- so a model-chosen filename can never address
   anything outside its owner's workspace.
2. Every file carries the classification Label inherited from every corpus
   passage the agent had seen when it wrote the file (the same inheritance
   rule harness/runner.py applies to answers). Downloads re-check that label
   against the reader's CURRENT clearance with trust/labels.can_read, so a
   revoked compartment also revokes files derived from it.
3. Only the owner (or nobody) can list, read, or download a workspace.
"""

from __future__ import annotations

import datetime
import json
import os
import re
import threading
from pathlib import Path
from typing import Optional

from contracts import Label, Tier, WorkspaceFile

_ROOT_DEFAULT = Path(__file__).parent.parent / "workspace"
_META = ".meta.json"
_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9 ._()\-]{0,119}$")
MAX_FILE_BYTES = 20 * 1024 * 1024
_lock = threading.Lock()


class WorkspaceError(ValueError):
    """Invalid filename, missing file, or oversize write."""


def root() -> Path:
    return Path(os.getenv("SEVERANCE_WORKSPACE_DIR", str(_ROOT_DEFAULT)))


def _person_dir(person_id: str) -> Path:
    safe = re.sub(r"[^A-Za-z0-9_\-]", "_", person_id)
    d = root() / safe
    d.mkdir(parents=True, exist_ok=True)
    return d


def safe_name(name: str) -> str:
    name = (name or "").strip().replace("\\", "/").split("/")[-1]
    if not _NAME_RE.match(name) or name == _META or ".." in name:
        raise WorkspaceError(
            f"Invalid filename {name!r}: use a plain name like 'summary.xlsx' "
            "(letters, digits, spaces, . _ - ( ); no folders)."
        )
    return name


def _read_meta(d: Path) -> dict:
    try:
        return json.loads((d / _META).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _write_meta(d: Path, meta: dict) -> None:
    (d / _META).write_text(json.dumps(meta, indent=1, sort_keys=True), encoding="utf-8")


def write_bytes(person_id: str, name: str, data: bytes, label: Optional[Label] = None,
                origin: str = "agent") -> WorkspaceFile:
    name = safe_name(name)
    if len(data) > MAX_FILE_BYTES:
        raise WorkspaceError(f"{name} is {len(data)} bytes; the limit is {MAX_FILE_BYTES}.")
    label = label or Label(tier=Tier.PUBLIC)
    d = _person_dir(person_id)
    with _lock:
        (d / name).write_bytes(data)
        meta = _read_meta(d)
        meta[name] = {"origin": origin, "label": json.loads(label.model_dump_json())}
        _write_meta(d, meta)
    return describe(person_id, name)


def read_bytes(person_id: str, name: str) -> bytes:
    path = _person_dir(person_id) / safe_name(name)
    if not path.is_file():
        raise WorkspaceError(f"No file named {name!r} in the workspace. Use list_files to see what exists.")
    return path.read_bytes()


def exists(person_id: str, name: str) -> bool:
    try:
        return (_person_dir(person_id) / safe_name(name)).is_file()
    except WorkspaceError:
        return False


def describe(person_id: str, name: str) -> WorkspaceFile:
    d = _person_dir(person_id)
    name = safe_name(name)
    path = d / name
    if not path.is_file():
        raise WorkspaceError(f"No file named {name!r} in the workspace.")
    stat = path.stat()
    entry = _read_meta(d).get(name, {})
    label = Label.model_validate(entry["label"]) if "label" in entry else Label(tier=Tier.PUBLIC)
    return WorkspaceFile(
        name=name,
        size_bytes=stat.st_size,
        modified=datetime.datetime.fromtimestamp(stat.st_mtime, datetime.timezone.utc).isoformat(),
        origin=entry.get("origin", "agent"),
        label=label,
    )


def list_files(person_id: str) -> list[WorkspaceFile]:
    d = _person_dir(person_id)
    files = []
    for path in sorted(d.iterdir(), key=lambda p: p.stat().st_mtime, reverse=True):
        if path.is_file() and path.name != _META and not path.name.startswith("."):
            try:
                files.append(describe(person_id, path.name))
            except WorkspaceError:
                continue
    return files


def delete(person_id: str, name: str) -> None:
    d = _person_dir(person_id)
    name = safe_name(name)
    with _lock:
        (d / name).unlink(missing_ok=True)
        meta = _read_meta(d)
        meta.pop(name, None)
        _write_meta(d, meta)


def unique_name(person_id: str, name: str) -> str:
    """'report.xlsx' -> 'report (2).xlsx' if taken, for uploads copied in."""
    name = safe_name(name)
    if not exists(person_id, name):
        return name
    stem, dot, ext = name.rpartition(".")
    if not dot:
        stem, ext = name, ""
    for n in range(2, 1000):
        candidate = f"{stem} ({n}){'.' + ext if ext else ''}"
        if not exists(person_id, candidate):
            return candidate
    raise WorkspaceError("Too many files with the same name.")
