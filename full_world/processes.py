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

import json
import os
import re
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


def listening_owned_pid(root: Path, port: int) -> int | None:
    """Discover a real detached Windows listener; verify before adopting it.

    Uses built-in PowerShell/CIM only. Not run on non-Windows, and does not
    enumerate or kill arbitrary background processes.
    """
    if os.name != "nt":
        return None
    port = int(port)
    if not 1024 <= port <= 65535:
        raise ValueError("Invalid viewer port")
    script = (
        "$ErrorActionPreference='Stop';"
        f"$c=Get-NetTCPConnection -LocalPort {port} -State Listen "
        "-ErrorAction SilentlyContinue | "
        "Where-Object {$_.LocalAddress -eq '127.0.0.1'} | "
        "Select-Object -First 1;"
        "if($c){"
        "$p=Get-CimInstance Win32_Process -Filter "
        "('ProcessId=' + [string]$c.OwningProcess);"
        "if($p){[pscustomobject]@{"
        "pid=$p.ProcessId;binary=$p.ExecutablePath;"
        "command_line=$p.CommandLine} | ConvertTo-Json -Compress}}"
    )
    try:
        result = subprocess.run(
            ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", script],
            text=True, capture_output=True, timeout=9,
        )
        if result.returncode or not result.stdout.strip():
            return None
        return verified_owned_listener(root, port, json.loads(result.stdout))
    except (OSError, ValueError, subprocess.SubprocessError, json.JSONDecodeError):
        return None
