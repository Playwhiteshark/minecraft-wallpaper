"""One-time Minecraft world conversion using the maintained Vantage native engine.

No custom NBT meshing, terrain approximation, asset resolver, or shader code.
This module is a replaceable conversion adapter; Vantage is MIT licensed.
"""
from __future__ import annotations

import hashlib
import json
import os
import platform
import shutil
import stat
import subprocess
import tarfile
import tempfile
import time
import urllib.request
import zipfile
from dataclasses import dataclass
from pathlib import Path

from mww.scene import check_world_closed

VERSION = "0.15.1"
RELEASE = "https://github.com/thoughts-on-things/vantage-mc/releases/download/v" + VERSION
ARCHIVES = {
    "Windows": ("vantage-x86_64-windows.zip",
                "d333a297e0e0027dff0c26f20cb111c9eab97cc97bfa65bbad382201b7812b15"),
    "Linux": ("vantage-x86_64-linux.tar.gz",
              "ff1fb5059017c536d8cd3dc8654155333fba763a12888fa308c1949458f5d89c"),
}
MAX_DOWNLOAD_BYTES = 15 * 1024 * 1024


class ConversionError(RuntimeError):
    pass


@dataclass(frozen=True)
class RenderResult:
    directory: Path
    dimensions: int
    tiles: int
    previous: Path | None


def backend_path(state_root: Path) -> Path:
    return state_root / "engines" / ("vantage-" + VERSION) / (
        "vantage.exe" if os.name == "nt" else "vantage")


def require_engine(state_root: Path, *, allow_download: bool = False) -> Path:
    """Explicit GUI build action may bootstrap Vantage once, securely pinned."""
    exe = backend_path(state_root)
    if exe.is_file():
        return exe
    if not allow_download:
        raise ConversionError("The native Vantage converter has not been installed. Click Build World to install it once.")
    kind = platform.system()
    if kind not in ARCHIVES or platform.machine().lower() not in (
            "amd64", "x86_64", "x64"):
        raise ConversionError("This release supports Windows/Linux x86-64; install a supported Vantage binary separately.")
    name, expected = ARCHIVES[kind]
    req = urllib.request.Request(RELEASE + "/" + name,
                                 headers={"User-Agent": "MinecraftLivingWorldWallpaper/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=90) as source:
            raw = source.read(MAX_DOWNLOAD_BYTES + 1)
    except Exception as exc:
        raise ConversionError("Cannot download pinned official Vantage release: " + str(exc)) from exc
    if len(raw) > MAX_DOWNLOAD_BYTES or hashlib.sha256(raw).hexdigest() != expected:
        raise ConversionError("Vantage download did not match the pinned SHA-256. Nothing was installed.")
    import io
    if name.endswith(".zip"):
        with zipfile.ZipFile(io.BytesIO(raw)) as archive:
            matches = [m for m in archive.infolist()
                       if Path(m.filename).name.lower() == "vantage.exe" and not m.is_dir()]
            if len(matches) != 1 or matches[0].file_size > 30 * 1024 * 1024:
                raise ConversionError("Unexpected Windows Vantage archive layout")
            payload = archive.read(matches[0])
    else:
        with tarfile.open(fileobj=io.BytesIO(raw), mode="r:gz") as archive:
            matches = [m for m in archive.getmembers()
                       if Path(m.name).name == "vantage" and m.isfile()]
            if len(matches) != 1 or matches[0].size > 30 * 1024 * 1024:
                raise ConversionError("Unexpected Linux Vantage archive layout")
            payload = archive.extractfile(matches[0]).read()
    exe.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=exe.parent, prefix=".vantage-", delete=False) as tmp:
        tmp.write(payload)
        temp = Path(tmp.name)
    try:
        temp.chmod(temp.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP)
        os.replace(temp, exe)
    finally:
        temp.unlink(missing_ok=True)
    return exe


def validate_render(folder: Path) -> tuple[int, int]:
    """Check the native output contract, not a toy/heightfield scene."""
    index = folder / "world.json"
    manifests = []
    if index.is_file():
        try:
            world = json.loads(index.read_text(encoding="utf-8"))
        except (ValueError, OSError) as exc:
            raise ConversionError("Invalid Vantage world.json") from exc
        if not isinstance(world.get("dimensions"), list) or not world["dimensions"]:
            raise ConversionError("Vantage did not publish any dimensions")
        for item in world["dimensions"]:
            entry = item.get("manifest")
            if not isinstance(entry, str) or ".." in Path(entry).parts or Path(entry).is_absolute():
                raise ConversionError("Invalid Vantage dimension manifest path")
            manifests.append(folder / entry)
    elif (folder / "manifest.json").is_file():
        manifests.append(folder / "manifest.json")
    else:
        raise ConversionError("Vantage rendered no world index or manifest")

    tile_count = 0
    for manifest in manifests:
        if not manifest.is_file():
            raise ConversionError("Missing Vantage dimension manifest: " + manifest.name)
        try:
            obj = json.loads(manifest.read_text(encoding="utf-8"))
        except (ValueError, OSError) as exc:
            raise ConversionError("Invalid Vantage dimension manifest") from exc
        # Actual native geometry files (not merely a plausible tile count).
        tile_count += len(list((manifest.parent / "tiles").glob("*.vtile")))
    if tile_count == 0:
        raise ConversionError("Vantage produced zero real high-resolution chunk tiles")
    return len(manifests), tile_count


def world_snapshot(world: Path) -> list:
    """Cheap source metadata guard. Never copy, write or upload save data."""
    candidates = [world / "level.dat"]
    for path in world.rglob("r.*.*.mca"):
        if path.parent.name in ("region", "entities", "poi"):
            candidates.append(path)
    return sorted((str(p.relative_to(world)), p.stat().st_mtime_ns, p.stat().st_size)
                  for p in candidates if p.is_file())


class VantageConverter:
    """Replace this converter independently of UI, scenes, and Lively hosting."""

    def __init__(self, state_root: Path):
        self.state_root = Path(state_root)

    def render(self, world: Path, world_key: str, *, allow_download: bool = False,
               memory_mib: int = 768, on_progress=None) -> RenderResult:
        world = Path(world).resolve()
        if not (world / "level.dat").is_file():
            raise ConversionError("Select a Minecraft Java save folder containing level.dat")
        if not world_key or not all(ch in "0123456789abcdef" for ch in world_key):
            raise ConversionError("Invalid private world identifier")
        if not (256 <= memory_mib <= 8192):
            raise ConversionError("Conversion memory budget must be 256–8192 MiB")
        check_world_closed(world)
        binary = require_engine(self.state_root, allow_download=allow_download)
        home = self.state_root / "full-world" / world_key
        versions = home / "versions"
        versions.mkdir(parents=True, exist_ok=True)
        staging = Path(tempfile.mkdtemp(prefix=".building-", dir=home))
        stamp = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
        version = stamp + "-" + os.urandom(4).hex()
        destination = versions / version
        previous = active_render(home)
        before_files = world_snapshot(world)
        command = [
            str(binary), "render", str(world), "--out", str(staging),
            "--caves", "full", "--memory", str(memory_mib),
        ]  # No --radius: render every saved generated chunk.
        try:
            if on_progress:
                on_progress("Vantage is converting real chunks across the saved world…")
            with (home / "last-render.log").open("wb") as log:
                completed = subprocess.run(command, cwd=str(world.parent),
                                           stdout=log, stderr=subprocess.STDOUT,
                                           check=False)
            if completed.returncode:
                excerpt = (home / "last-render.log").read_text(
                    encoding="utf-8", errors="replace")[-2200:]
                raise ConversionError("Vantage conversion failed:\n" + excerpt)
            dimensions, tiles = validate_render(staging)
            check_world_closed(world)
            if before_files != world_snapshot(world):
                raise ConversionError("The saved Minecraft world changed while rendering; previous wallpaper preserved")
            # Atomic publication: failed conversion cannot replace last-good.
            os.replace(staging, destination)
            active_path = home / "current.json"
            write_json_atomic(active_path, {"schema": 1, "version": version})
            if on_progress:
                on_progress(f"Complete: {tiles:,} real geometry tiles across {dimensions} dimension(s).")
            return RenderResult(destination, dimensions, tiles, previous)
        finally:
            if staging.exists():
                shutil.rmtree(staging)


def write_json_atomic(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8",
                                     dir=path.parent, prefix=".mww-", delete=False) as f:
        json.dump(value, f, indent=2)
        f.write("\n")
        temp = Path(f.name)
    try:
        os.replace(temp, path)
    finally:
        temp.unlink(missing_ok=True)


def active_render(home: Path) -> Path | None:
    path = home / "current.json"
    if not path.is_file():
        return None
    try:
        record = json.loads(path.read_text(encoding="utf-8"))
        name = record["version"]
        if not isinstance(name, str) or not name or "/" in name or "\\" in name or name.startswith("."):
            return None
        folder = home / "versions" / name
        return folder if folder.is_dir() else None
    except (ValueError, KeyError, OSError, TypeError):
        return None
