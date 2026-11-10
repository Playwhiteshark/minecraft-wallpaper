"""Local viewer process adapter around Vantage's embedded Three.js viewer.

A tiny native HTTP process is intentional: it streams real binary chunk tiles
and works with Lively's WebView2 without file:// CORS workarounds or a Node
server. It binds to loopback only and never launches Minecraft.
"""
from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

from .backend import ConversionError, backend_path, write_json_atomic
from .config import state_dir

SERVICE_FILE = "full-world-service.json"


def viewer_url(port: int) -> str:
    port = int(port)
    if port < 1024 or port > 65535:
        raise ValueError("Viewer port must be 1024–65535")
    return f"http://127.0.0.1:{port}/"


def ping(port: int) -> bool:
    try:
        with urllib.request.urlopen(viewer_url(port), timeout=0.5) as response:
            head = response.read(2048).decode("utf-8", errors="replace").lower()
            return response.status == 200 and "vantage" in head
    except (OSError, ValueError, urllib.error.URLError):
        return False


def owned_record(root: Path):
    try:
        p = root / SERVICE_FILE
        data = json.loads(p.read_text(encoding="utf-8"))
        if (data.get("schema") == 1 and isinstance(data.get("pid"), int)
                and data["pid"] > 0):
            return data
    except (OSError, ValueError, TypeError):
        pass
    return None


def _pid_matches(record: dict) -> bool:
    """Never kill a reused PID or somebody else's process on a shared port."""
    pid = record["pid"]
    binary = str(record["binary"])
    try:
        if os.name == "nt":
            # WMI checks exact executable path before permitting taskkill.
            command = (
                f"$p=Get-CimInstance Win32_Process -Filter 'ProcessId={pid}';"
                "if($p){$p.ExecutablePath}")
            result = subprocess.run(
                ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", command],
                capture_output=True, text=True, timeout=6)
            return result.returncode == 0 and result.stdout.strip().casefold() == binary.casefold()
        data = Path(f"/proc/{pid}/cmdline").read_bytes().decode("utf-8", "replace")
        return binary in data
    except (OSError, subprocess.SubprocessError):
        return False


def stop_viewer(root: Path | None = None) -> bool:
    root = root or state_dir()
    record = owned_record(root)
    if not record:
        return False
    if _pid_matches(record):
        if os.name == "nt":
            subprocess.run(["taskkill", "/PID", str(record["pid"]), "/T", "/F"],
                           capture_output=True, timeout=8)
        else:
            os.kill(record["pid"], signal.SIGTERM)
    # If ownership can't be established, never terminate an unrelated process.
    (root / SERVICE_FILE).unlink(missing_ok=True)
    return True


def start_viewer(render_dir: Path, port: int, root: Path | None = None) -> str:
    root = root or state_dir()
    root.mkdir(parents=True, exist_ok=True)
    port = int(port)
    address = viewer_url(port)
    render_dir = Path(render_dir).resolve()
    if not ((render_dir / "world.json").is_file() or
            (render_dir / "manifest.json").is_file()):
        raise ConversionError("No validated full-world render exists at this location")
    binary = backend_path(root)
    if not binary.is_file():
        raise ConversionError("Vantage backend is not installed")
    record = owned_record(root)
    if record and ping(port) and Path(record["render_dir"]).resolve() == render_dir:
        if _pid_matches(record):
            return address
    if record:
        if not _pid_matches(record) and ping(port):
            raise ConversionError("Viewer port belongs to another process; choose a different port")
        stop_viewer(root)
        time.sleep(0.2)
    if ping(port):
        raise ConversionError("A different viewer already uses this port")
    command = [str(binary), "serve", str(render_dir),
               "--host", "127.0.0.1", "--port", str(port)]
    log = (root / "full-world-service.log").open("ab")
    flags = 0
    if os.name == "nt":
        flags = subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.DETACHED_PROCESS
    try:
        process = subprocess.Popen(
            command, cwd=str(render_dir), stdin=subprocess.DEVNULL,
            stdout=log, stderr=subprocess.STDOUT, close_fds=True,
            creationflags=flags, start_new_session=os.name != "nt")
    finally:
        log.close()
    # Only the native small viewer remains alive after this control panel exits.
    for _ in range(40):
        if process.poll() is not None:
            break
        if ping(port):
            write_json_atomic(root / SERVICE_FILE, {
                "schema": 1, "pid": process.pid, "binary": str(binary.resolve()),
                "render_dir": str(render_dir), "port": port})
            return address
        time.sleep(0.25)
    # Keep failures from shadowing a previous working wallpaper.
    if process.poll() is None:
        process.terminate()
    tail = (root / "full-world-service.log").read_text(
        encoding="utf-8", errors="replace")[-1000:]
    raise ConversionError("The Vantage viewer did not start:\n" + tail)


def startup_script_path() -> Path:
    if os.name != "nt":
        raise ValueError("Login startup shortcut is currently Windows-only")
    return (Path(os.environ.get("APPDATA", "")) / "Microsoft" / "Windows" /
            "Start Menu" / "Programs" / "Startup" /
            "Minecraft Full World Wallpaper.cmd")


def set_login_startup(enabled: bool, entrypoint: Path) -> None:
    """Opt-in only; no Task Scheduler or Windows service installation."""
    target = startup_script_path()
    if not enabled:
        target.unlink(missing_ok=True)
        return
    target.parent.mkdir(parents=True, exist_ok=True)
    exe = Path(sys.executable)
    silent = exe.with_name("pythonw.exe")
    if not silent.is_file():
        silent = exe
    command = '@echo off\r\nstart "" /min "' + str(silent) + '" "' + str(
        Path(entrypoint).resolve()) + '" --serve\r\n'
    target.write_text(command, encoding="utf-8")
