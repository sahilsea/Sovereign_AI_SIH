"""Egress guard + live network monitor: the visible proof of "nothing leaves".

Two independent layers, both deterministic, both surfaced live in the UI
(GET /sovereignty/network, Sovereignty page):

1. GUARD (prevention, in-process). install_guard() wraps socket.connect so
   the SEVERANCE server process physically cannot open a connection to a
   public address: loopback, RFC1918/private, link-local and Unix sockets
   are allowed (local Ollama, the sandbox socket, a LAN GPU server);
   anything else raises before a single packet is sent, and the attempt
   (destination + time) is recorded. SEVERANCE_EGRESS_GUARD=log records
   without blocking; =off disables it. SEVERANCE_EGRESS_ALLOW adds extra
   CIDRs (e.g. an on-prem GPU server on a non-RFC1918 range).

2. MONITOR (observation, OS-reported). A background thread polls the OS
   socket table (psutil) for the SEVERANCE process tree AND the local
   Ollama server processes every second, and classifies every remote
   endpoint it sees. This does not trust the guard: it reads what the
   kernel says each process is connected to. Local connections (e.g. the
   API talking to Ollama on 127.0.0.1:11434) are counted too -- they prove
   the monitor is actually seeing traffic, not just reporting zeros.

The strongest layer remains the Docker topology (internal: true network,
see docker-compose.yml), where egress is impossible at the network layer;
ops/network_monitor.py is the standalone, out-of-process equivalent of (2).
"""

from __future__ import annotations

import datetime
import ipaddress
import os
import socket
import threading
import time
from collections import deque
from typing import Optional

try:
    import psutil
except ImportError:  # pragma: no cover - psutil is in requirements.txt
    psutil = None

_lock = threading.Lock()
_state = {
    "guard_mode": "off",
    "guard_installed_at": None,
    "monitor_started_at": None,
    "checks": 0,
    "last_check": None,
    "monitor_error": None,
    "watched_processes": [],
}
_blocked_attempts: deque = deque(maxlen=100)
_allowed_attempts = 0
_violations: deque = deque(maxlen=100)
_local_endpoints: dict[str, dict] = {}
_seen_violation_keys: set = set()
_extra_allowed: list = []


def _now() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def _load_extra_allowed() -> list:
    nets = []
    for part in os.getenv("SEVERANCE_EGRESS_ALLOW", "").split(","):
        part = part.strip()
        if part:
            try:
                nets.append(ipaddress.ip_network(part, strict=False))
            except ValueError:
                pass
    return nets


def is_local_address(host: str) -> bool:
    """True for addresses that stay on this machine or the private LAN."""
    try:
        addr = ipaddress.ip_address(host.split("%")[0])
    except ValueError:
        return False
    if addr.is_loopback or addr.is_private or addr.is_link_local or addr.is_unspecified:
        return True
    return any(addr in net for net in _extra_allowed)


# ---------------------------------------------------------------------------
# Layer 1: in-process guard
# ---------------------------------------------------------------------------

class EgressBlocked(ConnectionRefusedError):
    """Raised instead of connecting to a non-local address."""


_original_connect = socket.socket.connect
_original_connect_ex = socket.socket.connect_ex


def _check_destination(sock: socket.socket, address) -> None:
    global _allowed_attempts
    if sock.family not in (socket.AF_INET, socket.AF_INET6):
        return  # Unix domain sockets (sandbox) never leave the host
    host = address[0] if isinstance(address, tuple) and address else str(address)
    if not isinstance(host, str):
        return
    try:
        ipaddress.ip_address(host.split("%")[0])
    except ValueError:
        # connect() with a hostname resolves it first; resolve here the same
        # way so the check applies to the address actually dialled.
        try:
            host = socket.getaddrinfo(host, None)[0][4][0]
        except OSError:
            return  # unresolvable: the real connect() will fail on its own
    if is_local_address(host):
        with _lock:
            _allowed_attempts += 1
        return
    port = address[1] if isinstance(address, tuple) and len(address) > 1 else None
    entry = {"timestamp": _now(), "remote_ip": host, "remote_port": port,
             "action": "blocked" if _state["guard_mode"] == "block" else "logged"}
    with _lock:
        _blocked_attempts.append(entry)
    if _state["guard_mode"] == "block":
        raise EgressBlocked(
            f"SEVERANCE egress guard blocked an outbound connection to {host}:{port} "
            "(only loopback/private addresses are permitted)."
        )


def _guarded_connect(self, address):
    _check_destination(self, address)
    return _original_connect(self, address)


def _guarded_connect_ex(self, address):
    _check_destination(self, address)
    return _original_connect_ex(self, address)


def install_guard(mode: Optional[str] = None) -> str:
    """Idempotently install the socket guard. Returns the active mode."""
    global _extra_allowed
    mode = (mode or os.getenv("SEVERANCE_EGRESS_GUARD", "block")).lower()
    if mode not in ("block", "log", "off"):
        mode = "block"
    _extra_allowed = _load_extra_allowed()
    with _lock:
        _state["guard_mode"] = mode
        if mode != "off" and _state["guard_installed_at"] is None:
            _state["guard_installed_at"] = _now()
    if mode == "off":
        socket.socket.connect = _original_connect
        socket.socket.connect_ex = _original_connect_ex
    else:
        socket.socket.connect = _guarded_connect
        socket.socket.connect_ex = _guarded_connect_ex
    return mode


# ---------------------------------------------------------------------------
# Layer 2: OS socket-table monitor
# ---------------------------------------------------------------------------

def _watched_processes() -> list:
    """The SEVERANCE process tree plus local Ollama server/runner processes."""
    procs = {}
    try:
        me = psutil.Process(os.getpid())
        procs[me.pid] = me
        for child in me.children(recursive=True):
            procs[child.pid] = child
    except psutil.Error:
        pass
    for proc in psutil.process_iter(["name"]):
        try:
            name = proc.info.get("name") or ""  # case-sensitive: "Ollama" is the GUI
        except psutil.Error:
            continue
        # "ollama" is the server; "llama-server"/"ollama_llama_server" are its
        # per-model runners (name varies by Ollama version). The desktop tray
        # app (named "Ollama" on macOS) is a separate GUI that never sees
        # prompts, so it is excluded -- run `ollama serve` headless for demos.
        if name in ("ollama", "llama-server") or name.startswith("ollama_llama_server"):
            procs[proc.pid] = proc
    return list(procs.values())


def scan_once() -> None:
    watched = []
    for proc in _watched_processes():
        try:
            name = proc.name()
            conns = proc.net_connections(kind="inet")
        except (psutil.Error, OSError):
            continue
        watched.append({"pid": proc.pid, "name": name})
        for conn in conns:
            if not conn.raddr:
                continue  # listening socket
            ip, port = conn.raddr.ip, conn.raddr.port
            if is_local_address(ip):
                key = f"{name}->{ip}:{port if port < 32768 else '*'}"
                with _lock:
                    ep = _local_endpoints.setdefault(key, {
                        "process": name, "remote_ip": ip,
                        "remote_port": port if port < 32768 else None,
                        "first_seen": _now(), "observations": 0,
                    })
                    ep["observations"] += 1
                    ep["last_seen"] = _now()
                continue
            vkey = (proc.pid, ip, port)
            with _lock:
                if vkey in _seen_violation_keys:
                    continue
                _seen_violation_keys.add(vkey)
                _violations.append({
                    "timestamp": _now(), "pid": proc.pid, "process": name,
                    "remote_ip": ip, "remote_port": port, "status": conn.status,
                })
    with _lock:
        _state["checks"] += 1
        _state["last_check"] = _now()
        _state["watched_processes"] = watched


def _monitor_loop(interval: float) -> None:
    while True:
        try:
            scan_once()
            _state["monitor_error"] = None
        except Exception as exc:  # keep the monitor alive whatever happens
            _state["monitor_error"] = str(exc)
        time.sleep(interval)


_monitor_thread: Optional[threading.Thread] = None


def start_monitor(interval: float = 1.0) -> bool:
    global _monitor_thread
    if psutil is None:
        _state["monitor_error"] = "psutil not installed"
        return False
    if _monitor_thread is not None and _monitor_thread.is_alive():
        return True
    _state["monitor_started_at"] = _now()
    _monitor_thread = threading.Thread(target=_monitor_loop, args=(interval,), daemon=True, name="egress-monitor")
    _monitor_thread.start()
    return True


def snapshot() -> dict:
    with _lock:
        violations = list(_violations)
        blocked = list(_blocked_attempts)
        local = sorted(_local_endpoints.values(), key=lambda e: -e["observations"])
        state = dict(_state)
        allowed = _allowed_attempts
    return {
        "status": "violation" if violations else ("blocked_attempts" if blocked else "clean"),
        "guard": {
            "mode": state["guard_mode"],
            "installed_at": state["guard_installed_at"],
            "allowed_local_connections": allowed,
            "blocked_attempts": blocked[-20:],
            "blocked_count": len(blocked),
        },
        "monitor": {
            "running": _monitor_thread is not None and _monitor_thread.is_alive(),
            "started_at": state["monitor_started_at"],
            "checks": state["checks"],
            "last_check": state["last_check"],
            "error": state["monitor_error"],
            "watched_processes": state["watched_processes"],
            "external_connections": violations[-20:],
            "external_count": len(violations),
            "local_endpoints": local[:20],
        },
    }
