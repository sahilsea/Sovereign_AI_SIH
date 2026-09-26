"""Raw Python snippet execution -- standard library ONLY.

Shared by two callers so the execution rules exist in exactly one place:
  * agents/sandbox.py, in-process fallback for local development, and
  * sandbox/server.py, inside the locked-down `sandbox` container.

Zero model calls, zero project imports (no contracts, no pydantic): the
sandbox image contains this directory and nothing else.
"""

from __future__ import annotations

import base64
import os
import signal
import subprocess
import sys
import tempfile
import time
from pathlib import Path

MAX_CAPTURED_CHARS = 4000
# Files a snippet may be given, and may hand back (written into its cwd).
MAX_FILES = 10
MAX_FILE_BYTES = 4 * 1024 * 1024


def _safe_name(name: str) -> str:
    """Flat, traversal-free filename inside the snippet's working directory."""
    base = os.path.basename(str(name).replace("\\", "/"))
    if not base or base.startswith(".") or base == "snippet.py":
        raise ValueError(f"invalid sandbox filename: {name!r}")
    return base


def _limit_resources(memory_mb: int):
    """preexec_fn capping child memory and disabling core dumps (POSIX only)."""
    try:
        import resource
    except ImportError:
        return None

    mem_bytes = memory_mb * 1024 * 1024

    def _apply() -> None:
        for limit, value in (
            (resource.RLIMIT_AS, mem_bytes),
            (resource.RLIMIT_CORE, 0),
            (resource.RLIMIT_FSIZE, 16 * 1024 * 1024),
        ):
            try:
                resource.setrlimit(limit, (value, value))
            except (ValueError, OSError):
                pass

    return _apply


def _kill_group(proc: subprocess.Popen) -> None:
    """Kill the snippet and anything it spawned, not just the direct child."""
    if sys.platform == "win32":
        proc.kill()
        return
    try:
        os.killpg(proc.pid, signal.SIGKILL)
    except (ProcessLookupError, PermissionError):
        pass


def _collect_outputs(tmpdir: str, inputs: dict[str, bytes]) -> dict[str, str]:
    """New or modified files the snippet left in its cwd, base64-encoded."""
    out: dict[str, str] = {}
    for path in sorted(Path(tmpdir).iterdir()):
        if len(out) >= MAX_FILES:
            break
        if not path.is_file() or path.name == "snippet.py" or path.name.startswith("."):
            continue
        data = path.read_bytes()
        if len(data) > MAX_FILE_BYTES or inputs.get(path.name) == data:
            continue
        out[path.name] = base64.b64encode(data).decode("ascii")
    return out


def execute(code: str, timeout_seconds: float, memory_mb: int, files: dict | None = None) -> dict:
    """Run `code` as a standalone script in a fresh subprocess.

    `files` ({name: base64}) are placed in the snippet's working directory
    first; any file the snippet creates or changes there comes back in
    "files_out". Returns a plain dict with the CodeExecutionResult fields
    (+ "files_out"). Never raises: a failure to launch is reported as
    exit_code=-1 (fail closed).
    """
    start = time.monotonic()
    inputs: dict[str, bytes] = {}
    tmpdir_holder: list[str] = []

    def _result(stdout: str, stderr: str, exit_code: int, timed_out: bool) -> dict:
        files_out = {}
        if tmpdir_holder:
            try:
                files_out = _collect_outputs(tmpdir_holder[0], inputs)
            except OSError:
                files_out = {}
        return {
            "stdout": (stdout or "")[:MAX_CAPTURED_CHARS],
            "stderr": (stderr or "")[:MAX_CAPTURED_CHARS],
            "exit_code": exit_code,
            "timed_out": timed_out,
            "duration_seconds": round(time.monotonic() - start, 3),
            "files_out": files_out,
        }

    try:
        with tempfile.TemporaryDirectory(prefix="severance_sandbox_") as tmpdir:
            for name, b64 in list((files or {}).items())[:MAX_FILES]:
                data = base64.b64decode(b64)
                if len(data) > MAX_FILE_BYTES:
                    raise ValueError(f"input file {name!r} exceeds {MAX_FILE_BYTES} bytes")
                safe = _safe_name(name)
                (Path(tmpdir) / safe).write_bytes(data)
                inputs[safe] = data
            tmpdir_holder.append(tmpdir)
            script_path = Path(tmpdir) / "snippet.py"
            script_path.write_text(code, encoding="utf-8")

            posix = sys.platform != "win32"
            proc = subprocess.Popen(
                [sys.executable, "-I", "-S", str(script_path)],
                cwd=tmpdir,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                preexec_fn=_limit_resources(memory_mb) if posix else None,
                start_new_session=posix,
                env={"PATH": "/usr/bin:/bin"},  # stripped env: no inherited secrets/config
            )
            try:
                stdout, stderr = proc.communicate(timeout=timeout_seconds)
                return _result(stdout, stderr, proc.returncode, False)
            except subprocess.TimeoutExpired:
                _kill_group(proc)
                stdout, _ = proc.communicate()
                return _result(
                    stdout,
                    f"Execution exceeded the {timeout_seconds}s sandbox time limit and was terminated.",
                    -1,
                    True,
                )
            finally:
                # Reap any background children the snippet left behind.
                _kill_group(proc)
    except Exception as exc:  # noqa: BLE001 - fail closed
        tmpdir_holder.clear()
        return _result("", f"Sandbox failed to execute code: {exc}", -1, False)
