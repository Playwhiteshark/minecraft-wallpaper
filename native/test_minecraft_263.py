#!/usr/bin/env python3
"""Real Vantage 26.3 integration gate: current NBT palettes must make geometry.

Only original upstream Zig plus native/patch_vantage_263.py may pass. The
fixture is generated locally, contains no copyrighted assets or private worlds.
"""
from __future__ import annotations

import gzip
import json
import re
import socket
import struct
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "tests"))
from test_pipeline import make_world, region, root
from full_world_convert_smoke import minimal_assets

def create_263_chunk(world: Path) -> None:
    # 26.3 uses TAG_String for default block states or TAG_Compound with
    # lowercase id/properties. Each NBT list is homogeneous.
    # Y=5: 16x16 stone floor at 80; remaining air.
    indices = [1 if i // 256 == 0 else 0 for i in range(4096)]
    longs = []
    for start in range(0, 4096, 16):
        number = sum(v << (k * 4) for k, v in enumerate(indices[start:start + 16]))
        longs.append(number if number < (1 << 63) else number - (1 << 64))

    modern_string = [
        ("Y", 1, 5),
        ("block_states", 10, [
            ("palette", 9, (8, ["minecraft:air", "minecraft:stone"])),
            ("data", 12, longs),
        ]),
    ]
    # Y=6: all oak planks, lowercase id/properties compound representation.
    modern_compound = [
        ("Y", 1, 6),
        ("block_states", 10, [
            ("palette", 9, (10, [[
                ("id", 8, "minecraft:oak_planks"),
                ("properties", 10, []),
            ]])),
        ]),
    ]
    chunk = root([
        ("DataVersion", 3, 5023), ("xPos", 3, 0), ("zPos", 3, 0),
        ("sections", 9, (10, [modern_string, modern_compound])),
    ])
    region(world / "region" / "r.0.0.mca", chunk)

def check_offline(binary: Path, world: Path, assets: Path, out: Path) -> None:
    command = [str(binary), "render", str(world), "--out", str(out),
               "--assets", str(assets), "--memory", "512", "--threads", "1"]
    result = subprocess.run(command, capture_output=True, text=True, timeout=180)
    diagnostics = result.stdout + result.stderr
    if result.returncode:
        raise AssertionError("Patched Vantage native render failed:\\n" + diagnostics[-7000:])
    m = re.search(r"mesh:\\s*(\\d+) vertices,\\s*(\\d+) triangles", diagnostics)
    assert m, "No real native geometry statistics:\\n" + diagnostics[-7000:]
    assert int(m.group(1)) > 0 and int(m.group(2)) > 0, (
        "Minecraft 26.3 palette still maps to empty terrain:\\n" + diagnostics[-7000:])
    assert list(out.rglob("*.vtile")), "No Vantage mesh tile generated"
    print("PASS: native Minecraft 26.3 string and id/properties palettes produce",
          m.group(1), "vertices and", m.group(2), "triangles")

def check_live(binary: Path, world: Path, assets: Path, cache: Path) -> None:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    command = [str(binary), "live", str(world), "--out", str(cache),
               "--assets", str(assets), "--memory", "512", "--threads", "1",
               "--port", str(port), "--host", "127.0.0.1", "--prebake", "off",
               "--lod", "on", "--players", "off"]
    process = subprocess.Popen(command, stdout=subprocess.PIPE,
                               stderr=subprocess.STDOUT, text=True)
    try:
        manifest = None
        for _ in range(120):
            if process.poll() is not None:
                break
            try:
                with urllib.request.urlopen(
                        f"http://127.0.0.1:{port}/manifest.json", timeout=1) as response:
                    manifest = json.load(response)
                if manifest.get("tiles"):
                    break
            except (OSError, ValueError, urllib.error.URLError):
                pass
            time.sleep(.1)
        assert manifest and manifest.get("tiles"), "Native Vantage live did not advertise real tiles"
        with urllib.request.urlopen(
                f"http://127.0.0.1:{port}/tiles/t.0.0.vtile", timeout=30) as response:
            blob = response.read()
        if blob[:2] == b"\\x1f\\x8b":
            blob = gzip.decompress(blob)
        assert blob[:3] == b"VTL", "Native viewer did not produce genuine mesh-format geometry"
        assert (cache / "tiles" / "t.0.0.vtile").is_file()
        print("PASS: Vantage live serves and caches Minecraft 26.3 geometry over HTTP")
    finally:
        if process.poll() is None:
            process.terminate()
        try:
            stdout, _ = process.communicate(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()
            stdout, _ = process.communicate()
        if process.returncode not in (None, 0, -15, 143):
            print("Native live diagnostics:", stdout[-4000:])

def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit("Usage: test_minecraft_263.py /path/to/patched/vantage")
    binary = Path(sys.argv[1]).resolve()
    if not binary.is_file():
        raise FileNotFoundError(binary)
    with tempfile.TemporaryDirectory(prefix="mww-263-") as dirname:
        rootdir = Path(dirname)
        fixture = rootdir / "fixture"
        fixture.mkdir()
        world, _ = make_world(fixture)
        create_263_chunk(world)
        assets = minimal_assets(rootdir)
        check_offline(binary, world, assets, rootdir / "offline")
        check_live(binary, world, assets, rootdir / "live")

if __name__ == "__main__":
    main()
