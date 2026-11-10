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
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "tests"))
from test_pipeline import make_world, region, root
from full_world_convert_smoke import minimal_assets

def create_263_chunk(world: Path) -> None:
    """Two truly adjacent 26.3 chunks, one using compact strings and one
    using empty-key compact compounds; deep foundations prove surface culling.
    """
    import math
    import zlib

    def chunk_bytes(cx: int) -> bytes:
        # 9 real full sections below ground, including negative Y.
        sections = []
        for sy in range(-4, 5):
            palette = (8, ["minecraft:stone"]) if cx == 0 else (
                10, [[("", 8, "minecraft:stone")]])
            sections.append([
                ("Y", 1, sy),
                ("block_states", 10, [("palette", 9, palette)]),
            ])
        indices = [1 if i // 256 == 0 else 0 for i in range(4096)]
        longs = []
        for start in range(0, 4096, 16):
            number = sum(v << (k * 4) for k, v in enumerate(indices[start:start + 16]))
            longs.append(number if number < (1 << 63) else number - (1 << 64))
        # Both chunks have actual surface stone and air; second uses compound
        # palette with compact empty-key default-block entries.
        palette = (8, ["minecraft:air", "minecraft:stone"]) if cx == 0 else (
            10, [[("", 8, "minecraft:air")], [("", 8, "minecraft:stone")]])
        sections.append([
            ("Y", 1, 5),
            ("block_states", 10, [
                ("palette", 9, palette),
                ("data", 12, longs),
            ]),
        ])
        # Lowercase id/properties branch, with a full 16-block-high block wall
        # that survives visible surface culling.
        sections.append([
            ("Y", 1, 6),
            ("block_states", 10, [
                ("palette", 9, (10, [[
                    ("id", 8, "minecraft:oak_planks"),
                    ("properties", 10, []),
                ]])),
            ]),
        ])
        return root([
            ("DataVersion", 3, 5023),
            ("xPos", 3, cx), ("zPos", 3, 0),
            ("sections", 9, (10, sections)),
        ])

    # Genuine Anvil 8 KiB header: two adjacent chunks in one region.
    header = bytearray(8192)
    sectors = []
    next_sector = 2
    for cx in range(2):
        compressed = zlib.compress(chunk_bytes(cx))
        raw = struct.pack(">I", len(compressed) + 1) + b"\x02" + compressed
        count = math.ceil(len(raw) / 4096)
        header[cx * 4:(cx + 1) * 4] = ((next_sector << 8) | count).to_bytes(4, "big")
        next_sector += count
        sectors.append(raw.ljust(count * 4096, b"\x00"))
    region_path = world / "region" / "r.0.0.mca"
    region_path.write_bytes(bytes(header) + b"".join(sectors))

def check_offline(binary: Path, world: Path, assets: Path, out: Path) -> int:
    command = [str(binary), "render", str(world), "--out", str(out),
               "--assets", str(assets), "--memory", "512", "--threads", "1"]
    result = subprocess.run(command, capture_output=True, text=True, timeout=180)
    diagnostics = result.stdout + result.stderr
    if result.returncode:
        raise AssertionError("Patched Vantage native render failed:\n" + diagnostics[-7000:])
    m = re.search(r"mesh:\s*(\d+) vertices,\s*(\d+) triangles", diagnostics)
    assert m, "No real native geometry statistics:\n" + diagnostics[-7000:]
    assert int(m.group(1)) > 0 and int(m.group(2)) > 0, (
        "Minecraft 26.3 palette still maps to empty terrain:\n" + diagnostics[-7000:])
    assert list(out.rglob("*.vtile")), "No Vantage mesh tile generated"
    print("PASS: two adjacent native 26.3 chunks (strings, id/properties, empty-key compounds) produce",
          m.group(1), "vertices and", m.group(2), "triangles")
    return int(m.group(1))

def check_live(binary: Path, world: Path, assets: Path, cache: Path, full_vertices: int) -> None:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    command = [str(binary), "live", str(world), "--out", str(cache),
               "--assets", str(assets), "--memory", "512", "--threads", "1",
               "--port", str(port), "--host", "127.0.0.1", "--prebake", "off",
               "--lod", "on", "--players", "off", "--surface-depth", "16"]
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
        if blob[:2] == b"\x1f\x8b":
            blob = gzip.decompress(blob)
        assert blob[:3] == b"VTL", "Native viewer did not produce genuine mesh-format geometry"
        assert len(blob) >= 12, "Native tile has no solid geometry header"
        solid_vertices = struct.unpack_from("<I", blob, 8)[0]
        assert solid_vertices > 0, (
            "Native live tile has zero vertices despite a populated Minecraft 26.3 save")
        assert solid_vertices < full_vertices, (
            f"Surface mode did not eliminate deep exposed wall geometry: "
            f"{solid_vertices} versus untrimmed {full_vertices}")
        print("PASS: native surface-only Vantage live contains", solid_vertices,
              "real solid vertices (untrimmed:", full_vertices, ")")
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
        full_vertices = check_offline(binary, world, assets, rootdir / "offline")
        check_live(binary, world, assets, rootdir / "live", full_vertices)

if __name__ == "__main__":
    main()
