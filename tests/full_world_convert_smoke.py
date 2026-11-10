"""Real native integration smoke: two adjacent Anvil chunks → Vantage geometry.

Uses synthetic self-generated blocks/textures only. This exercises the actual
native world reader, model resolver, mesher and tile writer, not our mocks.
No Minecraft game, Mojang jar, or runtime dependency in CI.
"""
from __future__ import annotations

import gzip
import json
import math
import os
import struct
import subprocess
import sys
import tempfile
import zlib
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_pipeline import make_world, fake_png
from full_world.backend import require_engine, validate_render


def second_chunk(region_path):
    original = bytearray(region_path.read_bytes())
    first_sector = original[8192:]
    length = struct.unpack(">I", first_sector[:4])[0]
    compression = first_sector[4]
    assert compression == 2
    chunk = zlib.decompress(first_sector[5:4+length])
    key = b"\x03\x00\x04xPos\x00\x00\x00\x00"
    assert key in chunk
    second = chunk.replace(key, b"\x03\x00\x04xPos\x00\x00\x00\x01", 1)
    encoded = zlib.compress(second)
    blob = struct.pack(">I", len(encoded)+1) + b"\x02" + encoded
    padded = blob.ljust(math.ceil(len(blob)/4096)*4096,b"\x00")
    first_count = (length + 4 + 4095) // 4096
    second_start = 2 + first_count
    original[4:8] = ((second_start<<8) | (len(padded)//4096)).to_bytes(4, "big")
    original.extend(padded)
    region_path.write_bytes(original)


def minimal_assets(root):
    minecraft = root / "assets" / "minecraft"
    for name in ("stone", "oak_planks", "glass", "lantern"):
        blockstate = minecraft / "blockstates" / (name + ".json")
        model = minecraft / "models" / "block" / (name + ".json")
        texture = minecraft / "textures" / "block" / (name + ".png")
        for folder in (blockstate.parent, model.parent, texture.parent):
            folder.mkdir(parents=True, exist_ok=True)
        blockstate.write_text(
            json.dumps({"variants": {"": {"model": "minecraft:block/" + name}}}),
            encoding="utf-8")
        faces = {side: {"texture": "#all", "cullface": side}
                 for side in ("north","south","east","west","up","down")}
        model.write_text(json.dumps({
            "textures":{"all":"minecraft:block/"+name},
            "elements":[{"from":[0,0,0],"to":[16,16,16],"faces":faces}]
        }),encoding="utf-8")
        texture.write_bytes(fake_png())
    return minecraft


def run():
    with tempfile.TemporaryDirectory(prefix="mww-real-native-") as tmp:
        root = Path(tmp)
        fixture_dir = root / "fixture"
        fixture_dir.mkdir()
        world, _ = make_world(fixture_dir)
        second_chunk(world / "region" / "r.0.0.mca")
        assets = minimal_assets(root)
        native = require_engine(root, allow_download=True)
        out = root / "rendered"
        command = [str(native),"render",str(world),"--out",str(out),
                   "--assets",str(assets),"--caves","full",
                   "--memory","512","--threads","1"]
        result = subprocess.run(command,capture_output=True,text=True,timeout=180)
        if result.returncode:
            raise AssertionError("Native 2-chunk conversion failed:\n"+
                                 (result.stdout+result.stderr)[-7500:])
        dimensions, tiles = validate_render(out)
        assert dimensions >= 1 and tiles >= 1
        assert (out / "terrain.vtexarr").is_file(), "Real native texture-array missing"
        assert (world / "region" / "r.0.0.mca").is_file()
        print(f"PASS: two adjacent genuine synthetic Anvil chunks → {tiles} real native Vantage tile(s), textures and manifests")


if __name__=="__main__":
    run()
