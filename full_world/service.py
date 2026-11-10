"""Local viewer process adapter around Vantage's embedded Three.js viewer.

A tiny native HTTP process is intentional: it streams real binary chunk tiles
and works with Lively's WebView2 without file:// CORS workarounds or a Node
server. It binds to loopback only and never launches Minecraft.
"""
from __future__ import annotations

import json
import os
import socket
import signal
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

from .backend import (VERSION, ConversionError, backend_path, prepare_client_assets,
                      require_engine, write_json_atomic)
from mww.scene import check_world_closed
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


def port_is_listening(port: int) -> bool:
    """TCP socket occupancy, independent of HTTP routing or page contents."""
    try:
        with socket.create_connection(("127.0.0.1", int(port)), timeout=0.4):
            return True
    except (OSError, ValueError):
        return False


def occupied_port_message(root: Path, port: int) -> str:
    """Show the actual port-owning process, not an unjustified 'foreign' claim."""
    from .processes import listener_report
    details = listener_report(root, port)
    pid = details.get("pid")
    return (
        f"Port {port} still has a listening process. Nothing was killed.\n"
        + (f"Listening PID: {pid}\n" if pid else "Listening PID: unavailable\n")
        + f"Executable: {details.get('binary', 'unavailable')}\n"
        + f"Ownership check: {details.get('reason', 'unknown')}\n"
        + "Run 'py -3 full_world.py --port-status' to inspect its command "
        "and determine whether it is an old app-owned Vantage process."
    )


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


def stop_viewer(root: Path | None = None, *, port: int | None = None) -> bool:
    """Stop only our verified native Vantage process, including orphaned builds.

    The previous version erased the PID record even when the process remained
    alive. That made an old detached engine indistinguishable from a foreign
    listener on the next app startup. Do not lose a live owned PID again.
    """
    from .processes import listening_owned_pid
    root = (root or state_dir()).resolve()
    record = owned_record(root)
    target_port = int(port if port is not None else
                      (record.get("port", 8787) if record else 8787))
    viewer_url(target_port)

    # First trust the PID file only after verifying the *actual* executable
    # path. For old app versions with lost/stale records, inspect the port's
    # owning Windows process and validate app engine directory + command line.
    recorded_pid = record["pid"] if record and _pid_matches(record) else None
    listener_pid = listening_owned_pid(root, target_port) if (ping(target_port) or port_is_listening(target_port)) else None
    pid = recorded_pid or listener_pid
    if pid is None:
        # Forget stale metadata, never claim that a foreign listener was
        # stopped. We deliberately do not terminate anything by port alone.
        (root / SERVICE_FILE).unlink(missing_ok=True)
        return False

    if os.name == "nt":
        result = subprocess.run(
            ["taskkill", "/PID", str(pid), "/F"],
            capture_output=True, text=True, timeout=10)
        # A failure is tolerable only if the verified process already exited.
        if result.returncode and (
                (recorded_pid and record and _pid_matches(record)) or
                listening_owned_pid(root, target_port) == pid):
            raise ConversionError("Windows could not stop the app-owned Vantage process "
                                  f"(PID {pid}): {result.stderr.strip()}")
    else:
        try:
            os.kill(pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
        except OSError as exc:
            raise ConversionError(f"Could not stop app-owned Vantage PID {pid}: {exc}") from exc

    # Give Windows a moment to release its listening socket. A delayed release
    # must not turn a successful stop into a permanently orphaned process.
    for _ in range(30):
        if not (ping(target_port) or port_is_listening(target_port)):
            break
        time.sleep(0.1)
    if ping(target_port) or port_is_listening(target_port):
        # A verified record may still belong to a living Vantage process even
        # if Windows cannot query the socket owner (CIM restrictions/races).
        # Do not erase that record: the next launch must still be able to stop it.
        still_recorded = bool(recorded_pid and record and _pid_matches(record))
        still_listening = listening_owned_pid(root, target_port) == pid
        if still_recorded or still_listening:
            raise ConversionError(
                f"Vantage PID {pid} is still running on port {target_port}. "
                "The ownership record was preserved.")
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
    if record or ping(port) or port_is_listening(port):
        # Automatically retire a *verified* orphan from an older app build.
        # A foreign listener is left intact and diagnosed, never killed.
        stop_viewer(root, port=port)
        time.sleep(0.2)
    if ping(port) or port_is_listening(port):
        raise ConversionError(occupied_port_message(root, port))
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



LIVE_DIMENSIONS = frozenset(("overworld", "the_nether", "the_end"))
# Exposed-surface skirt, not an underground cave renderer. Keep editable.
SURFACE_DEPTH_BLOCKS = 16


def live_command(binary: Path, world: Path, cache: Path, port: int,
                 dimension: str, memory_mib: int = 768,
                 assets: Path | None = None,
                 surface_depth: int = SURFACE_DEPTH_BLOCKS) -> list[str]:
    """Vantage's native lazy tile producer, not an invented Python mesher.

    Full saved-world coordinates are indexed but only requested tiles are baked.
    Default cave horizon excludes invisible deep underground geometry. The
    browser's existing tile manager controls visible-tile GPU residency.
    """
    viewer_url(port)
    if dimension not in LIVE_DIMENSIONS:
        raise ValueError("Unknown Minecraft dimension")
    if not 256 <= memory_mib <= 8192:
        raise ValueError("Live tile memory budget must be 256–8192 MiB")
    if not 1 <= surface_depth <= 64:
        raise ValueError("Surface skirt must be 1–64 blocks")
    command = [
        str(binary), "live", str(world), "--out", str(cache),
        "--host", "127.0.0.1", "--port", str(port),
        "--dimension", dimension, "--memory", str(memory_mib),
        "--prebake", "off", "--lod", "on", "--players", "off",
    ]
    if dimension == "overworld":
        # Native Vantage still reads genuine 3D chunks for model/lighting and
        # emits surface faces plus a shallow, terrain-aware skirt. No extra
        # underground walls, no fabricated flat heightfield or fake bottom.
        command.extend(["--surface-depth", str(surface_depth)])
    if assets is not None:
        command.extend(["--assets", str(assets)])
    return command


def _live_manifest_ready(port: int) -> bool:
    """The embedded homepage alone isn't proof of a readable Minecraft scene."""
    try:
        with urllib.request.urlopen(viewer_url(port) + "manifest.json", timeout=1) as response:
            manifest = json.loads(response.read(4 * 1024 * 1024))
        return (isinstance(manifest, dict) and
                isinstance(manifest.get("tiles"), list) and
                len(manifest["tiles"]) > 0)
    except (OSError, ValueError, TypeError, urllib.error.URLError):
        return False


def start_live_viewer(world: Path, world_key: str, dimension: str, port: int,
                      root: Path | None = None, *, client_jar: Path | None = None,
                      memory_mib: int = 768, allow_download: bool = False,
                      camera: tuple[float, float, float] | None = None) -> str:
    """Start the genuine Vantage on-demand renderer for one camera dimension.

    A dimension switch restarts this small native process but preserves the
    per-dimension cache. No batch conversion or upfront cave geometry required.
    """
    root = root or state_dir()
    world = Path(world).expanduser().resolve()
    if not (world / "level.dat").is_file():
        raise ConversionError("Select a Minecraft Java save containing level.dat")
    if len(world_key) != 24 or any(c not in "0123456789abcdef" for c in world_key):
        raise ConversionError("Invalid private world identifier")
    if dimension not in LIVE_DIMENSIONS:
        raise ConversionError("Unknown Minecraft dimension")
    if not 256 <= memory_mib <= 8192:
        raise ConversionError("Live tile memory budget must be 256–8192 MiB")
    check_world_closed(world)
    binary = require_engine(root, allow_download=allow_download)
    assets = prepare_client_assets(binary, client_jar)
    # Never reuse tiles baked by older native decoders: a 26.3 chunk could
    # have been cached as a perfectly valid but completely empty VTL4 tile.
    # Tag the cache by engine build; old cache remains available for rollback.
    cache = (root / "full-world" / world_key / "live-cache" /
             ("vantage-" + VERSION) / dimension).resolve()
    cache.mkdir(parents=True, exist_ok=True)
    # Entirely separate scene overlay. It neither reads terrain geometry nor
    # depends on --surface-depth, a future visibility preparer, or Vantage LOD.
    from .mobs import build_mob_overlay, empty_mob_overlay
    try:
        if camera is not None:
            build_mob_overlay(world, dimension, cache, camera, client_jar)
        else:
            empty_mob_overlay(cache, dimension, "No saved camera supplied for mob selection")
    except Exception as exc:
        empty_mob_overlay(cache, dimension,
                          "Saved mobs unavailable: " + type(exc).__name__ + ": " + str(exc))
    address = viewer_url(port)
    command = live_command(binary, world, cache, port, dimension, memory_mib, assets)
    record = owned_record(root)
    if record and _pid_matches(record) and ping(port):
        if (record.get("mode") == "live" and
                record.get("world_dir") == str(world) and
                record.get("dimension") == dimension and
                record.get("assets") == (str(assets) if assets else "") and
                record.get("render_dir") == str(cache) and
                _live_manifest_ready(port)):
            return address

    if record or ping(port) or port_is_listening(port):
        # Old versions of this app deliberately detached Vantage for Lively.
        # After updating the executable they may have a stale/lost PID record.
        # The orphan probe inspects the *actual socket owner*, checks that it
        # runs from our versioned engine directory with our private cache, and
        # stops it safely. It does not touch any foreign Vantage instance.
        stop_viewer(root, port=port)
        time.sleep(0.2)
    if ping(port) or port_is_listening(port):
        raise ConversionError(occupied_port_message(root, port))

    log_path = root / "full-world-service.log"
    root.mkdir(parents=True, exist_ok=True)
    flags = 0
    if os.name == "nt":
        flags = subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.DETACHED_PROCESS
    with log_path.open("ab") as log:
        process = subprocess.Popen(
            command, cwd=str(cache), stdin=subprocess.DEVNULL,
            stdout=log, stderr=subprocess.STDOUT, close_fds=True,
            creationflags=flags, start_new_session=os.name != "nt")
    for _ in range(160):
        if process.poll() is not None:
            break
        if ping(port) and _live_manifest_ready(port):
            write_json_atomic(root / SERVICE_FILE, {
                "schema": 1, "pid": process.pid, "binary": str(binary.resolve()),
                "mode": "live", "world_dir": str(world), "render_dir": str(cache),
                "dimension": dimension, "assets": str(assets) if assets else "",
                "port": int(port),
            })
            return address
        time.sleep(0.25)

    if process.poll() is None:
        process.terminate()
    tail = log_path.read_text(encoding="utf-8", errors="replace")[-3500:]
    raise ConversionError(
        "Vantage could not start a usable on-demand scene. "
        "The world may contain an unsupported chunk format or missing assets. "
        "Native diagnostics:\n" + tail)

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
