"""Read-only saved-chunk coverage diagnostics.

This ONLY examines the 4 KiB Anvil region location tables. It never attempts to
reimplement Vantage's NBT decoder, block models, mesher, or renderer. It helps
distinguish: (a) chunks not saved on disk, (b) saved chunks Vantage failed to
render. No missing terrain is synthesized.
"""
from __future__ import annotations

import math
from pathlib import Path

DIMENSION_REGIONS = {
    "overworld": ("region", "dimensions/minecraft/overworld/region"),
    "the_nether": ("DIM-1/region", "dimensions/minecraft/the_nether/region"),
    "the_end": ("DIM1/region", "dimensions/minecraft/the_end/region"),
}


def region_folder(world: Path, dimension: str) -> Path:
    if dimension not in DIMENSION_REGIONS:
        raise ValueError("Unsupported dimension for local chunk inspection")
    for candidate in DIMENSION_REGIONS[dimension]:
        folder = Path(world) / candidate
        if folder.is_dir() and any(folder.glob("r.*.*.mca")):
            return folder
    raise FileNotFoundError("No Anvil terrain region files found for " + dimension)


def inspect_near_camera(world: Path, dimension: str, x: float, z: float,
                        radius_chunks: int = 6) -> dict:
    """Count location-table entries around one camera, not whole-world blocks.

    The ASCII map is centered on the camera (C is a saved camera chunk, c an
    absent camera chunk; # is present and . absent). Rows run north→south.
    A populated location entry does not mean its NBT decodes correctly.
    """
    if not 1 <= radius_chunks <= 32:
        raise ValueError("Diagnostic radius must be 1–32 chunks")
    if not math.isfinite(x) or not math.isfinite(z):
        raise ValueError("Camera coordinates must be finite")
    folder = region_folder(world, dimension)
    cx, cz = math.floor(x / 16), math.floor(z / 16)
    headers = {}
    rows = []
    present_count = 0
    missing_count = 0
    for dz in range(-radius_chunks, radius_chunks + 1):
        chars = []
        for dx in range(-radius_chunks, radius_chunks + 1):
            chunk_x, chunk_z = cx + dx, cz + dz
            rx, rz = chunk_x // 32, chunk_z // 32
            key = (rx, rz)
            if key not in headers:
                name = folder / f"r.{rx}.{rz}.mca"
                if name.is_file():
                    with name.open("rb") as source:
                        headers[key] = source.read(4096)
                else:
                    headers[key] = b""
            header = headers[key]
            offset = (chunk_z % 32 * 32 + chunk_x % 32) * 4
            if len(header) == 4096:
                raw = int.from_bytes(header[offset:offset + 4], "big")
                saved = (raw >> 8) != 0 and (raw & 255) != 0
            else:
                saved = False
            if saved:
                present_count += 1
            else:
                missing_count += 1
            chars.append(("C" if saved else "c") if dx == 0 and dz == 0 else ("#" if saved else "."))
        rows.append("".join(chars))
    return {
        "dimension": dimension,
        "region_directory": str(folder),
        "camera_chunk": [cx, cz],
        "radius_chunks": radius_chunks,
        "saved": present_count,
        "missing": missing_count,
        "fraction_saved": present_count / (present_count + missing_count),
        "grid": rows,
    }
