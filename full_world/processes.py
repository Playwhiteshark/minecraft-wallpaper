"""Safely recover only *this app's* detached Vantage listeners after crashes.

The native renderer intentionally outlives the GUI for Lively. Historically
the GUI removed a stale PID file on failure and then treated an orphan from
an earlier engine version as a foreign viewer. We inspect the Windows TCP
listener's actual PID, executable and command line before adopting/stopping it.

Never terminate a listener based on its page title, port, process name or
PID file alone. It must be this app's private versioned engine, with a loopback
live server and an output cache inside this app's state directory.
"""
from __future__ import annotations

import ctypes
import json
import os
import re
import socket
import struct
import subprocess
from pathlib import Path


def _command_value(command: str, key: str) -> str | None:
    # Windows Vantage command line uses space-separated --flags; allow values
    # inside quotes because saves and private data roots may contain spaces.
    expression = r'(?i)(?:^|\s)' + re.escape(key) + r'\s+(?:"([^"]+)"|([^\s"]+))'
    match = re.search(expression, command)
    return (match.group(1) or match.group(2)) if match else None


def verified_owned_listener(root: Path, port: int, candidate: dict) -> int | None:
    """Accept only a Vantage process from this app's versioned engine folder.

    This is an additional identity proof, not a replacement for the PID file.
    A different program also bound to 127.0.0.1:port remains untouched.
    """
    try:
        pid = int(candidate["pid"])
        if pid < 1:
            return None
        binary = Path(candidate["binary"]).resolve()
        engine_root = (Path(root).resolve() / "engines")
        parts = binary.relative_to(engine_root).parts
        if (len(parts) != 2 or not parts[0].startswith("vantage-") or
                parts[1].casefold() != ("vantage.exe" if os.name == "nt" else "vantage")):
            return None
        cmd = str(candidate["command_line"])
        if not re.search(r"(?i)(?:^|\s)live(?=\s)", cmd):
            return None
        if _command_value(cmd, "--port") != str(int(port)):
            return None
        if _command_value(cmd, "--host") != "127.0.0.1":
            return None
        output = _command_value(cmd, "--out")
        if not output:
            return None
        cache = Path(output).resolve()
        relative = cache.relative_to(Path(root).resolve() / "full-world")
        # Our live cache is full-world/<world_key>/live-cache/vantage-*/<dim>.
        if len(relative.parts) != 4 or relative.parts[1] != "live-cache":
            return None
        if not re.fullmatch(r"[a-f0-9]{24}", relative.parts[0]):
            return None
        if not relative.parts[2].startswith("vantage-"):
            return None
        return pid
    except (ValueError, TypeError, KeyError, OSError):
        return None



def listener_pid_windows(port: int) -> int | None:
    """Read Windows' actual IPv4 TCP LISTEN owner through the IP Helper API.

    Get-NetTCPConnection is not reliably installed/permitted in every Windows
    environment. This standard-library call avoids a brittle PowerShell query.
    Only LISTEN sockets on 127.0.0.1 qualify; no process is stopped here.
    """
    if os.name != "nt":
        return None
    port = int(port)
    if not 1024 <= port <= 65535:
        raise ValueError("Port out of range")
    try:
        dll = ctypes.WinDLL("iphlpapi.dll", use_last_error=True)
        fn = dll.GetExtendedTcpTable
        fn.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.c_ulong),
                       ctypes.c_int, ctypes.c_ulong, ctypes.c_int, ctypes.c_ulong]
        fn.restype = ctypes.c_ulong
        size = ctypes.c_ulong(0)
        # AF_INET, TCP_TABLE_OWNER_PID_LISTENER
        first = fn(None, ctypes.byref(size), 0, 2, 3, 0)
        if first not in (0, 122) or not 4 <= size.value <= 16 * 1024 * 1024:
            return None
        buffer = ctypes.create_string_buffer(size.value)
        if fn(buffer, ctypes.byref(size), 0, 2, 3, 0) != 0:
            return None
        count = struct.unpack_from("<I", buffer, 0)[0]
        if count > (size.value - 4) // 24:
            return None
        for i in range(count):
            state, addr, network_port, _, _, pid = struct.unpack_from(
                "<IIIIII", buffer, 4 + i * 24)
            if state != 2 or not pid:  # MIB_TCP_STATE_LISTEN
                continue
            if socket.inet_ntoa(struct.pack("<I", addr)) != "127.0.0.1":
                continue
            if socket.ntohs(network_port & 0xFFFF) == port:
                return int(pid)
    except (OSError, ValueError, TypeError, AttributeError, struct.error):
        return None
    return None


def _powershell(script: str, timeout: int = 8) -> str:
    result = subprocess.run(
        ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", script],
        capture_output=True, text=True, timeout=timeout,
    )
    return result.stdout.strip() if result.returncode == 0 else ""


def _powershell_listener_pid(port: int) -> int | None:
    """Legacy diagnostic fallback if the Windows IP Helper API cannot query."""
    output = _powershell(
        f"$c=Get-NetTCPConnection -LocalPort {int(port)} -State Listen "
        "-ErrorAction SilentlyContinue | "
        "Where-Object {$_.LocalAddress -eq '127.0.0.1'} | "
        "Select-Object -First 1; if($c){$c.OwningProcess}")
    try:
        return int(output) if output else None
    except ValueError:
        return None


def listener_process(port: int) -> dict | None:
    """Inspect the *real socket owner* and its command line without killing it.

    When process information cannot be queried, keep the PID and describe the
    failure. This stops the GUI from claiming an unidentified foreign process
    without explaining what it observed.
    """
    if os.name != "nt":
        return None
    pid = listener_pid_windows(port) or _powershell_listener_pid(port)
    if pid is None:
        return None
    # Avoid shell interpolation of user-supplied paths; only a numeric PID.
    script = (
        f"$p=Get-CimInstance Win32_Process -Filter 'ProcessId={int(pid)}' "
        "-ErrorAction SilentlyContinue;"
        "if($p){[pscustomobject]@{"
        "pid=[int]$p.ProcessId;binary=$p.ExecutablePath;"
        "command_line=$p.CommandLine} | ConvertTo-Json -Compress}"
    )
    data = _powershell(script)
    if data:
        try:
            value = json.loads(data)
            if isinstance(value, dict) and int(value.get("pid", 0)) == pid:
                return value
        except (ValueError, TypeError):
            pass
    return {"pid": pid, "binary": "", "command_line": "",
            "reason": "Windows returned the listening PID but denied or failed process details"}


def _rejection_reason(root: Path, port: int, candidate: dict) -> str:
    """Exact explanation of an unverified listener; no untrusted process kills."""
    try:
        path = candidate.get("binary")
        if not path:
            return "Windows did not expose its executable path"
        engine = Path(path).resolve()
        parts = engine.relative_to((Path(root).resolve() / "engines")).parts
        if (len(parts) != 2 or not parts[0].startswith("vantage-") or
                parts[1].casefold() != ("vantage.exe" if os.name == "nt" else "vantage")):
            return "Executable is not a versioned Vantage binary inside this app's engine directory"
        cmd = str(candidate.get("command_line") or "")
        if not cmd:
            return "Windows did not expose the process command line"
        if not re.search(r"(?i)(?:^|\s)live(?=\s)", cmd):
            return "Process command is not a Vantage live session"
        if _command_value(cmd, "--port") != str(int(port)):
            return "Command-line port does not match the listening port"
        if _command_value(cmd, "--host") != "127.0.0.1":
            return "Command does not explicitly bind to loopback"
        output = _command_value(cmd, "--out")
        if not output:
            return "Command does not identify a private tile cache"
        relative = Path(output).resolve().relative_to(Path(root).resolve() / "full-world").parts
        if (len(relative) != 4 or not re.fullmatch(r"[a-f0-9]{24}", relative[0]) or
                relative[1] != "live-cache" or not relative[2].startswith("vantage-") or
                relative[3] not in ("overworld", "the_nether", "the_end")):
            return "Renderer output is not a recognized private world/dimension cache"
    except (OSError, TypeError, ValueError, KeyError):
        return "The renderer binary or cache is outside this app's state directory"
    return ""


def listener_report(root: Path, port: int) -> dict:
    """Actionable, read-only ownership diagnostic for CLI and GUI errors."""
    process = listener_process(port)
    if process is None:
        return {"port": int(port), "pid": None,
                "verified": False, "reason": "No IPv4 loopback TCP listener PID could be read"}
    reason = _rejection_reason(root, port, process)
    return {
        "port": int(port), "pid": process["pid"],
        "binary": process.get("binary") or "unavailable",
        "command_line": process.get("command_line") or "unavailable",
        "verified": not reason,
        "reason": reason or "Verified app-owned Vantage live process",
    }


def listening_owned_pid(root: Path, port: int) -> int | None:
    """Return an exact verified socket owner, never an arbitrary Vantage PID."""
    process = listener_process(port)
    return verified_owned_listener(root, port, process) if process else None
