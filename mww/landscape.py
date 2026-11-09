"""Read a bounded, low-detail surface from real saved Minecraft block columns.

The near renderer owns detailed blocks. This independent adapter samples only
a small set of columns per chunk, without trusting version-dependent chunk
heightmap origins, inventing missing terrain, or loading another engine.
"""
from __future__ import annotations

import base64
import math
import struct
from collections import defaultdict
from pathlib import Path

from .nbt import RegionReader, block_name, unpack_palette

SAMPLE = struct.Struct('<hBBB')  # local Y, RGB; Y=-32768 means missing
MISSING = -32768


def _is_air(name: str) -> bool:
    return name in ('minecraft:air', 'minecraft:cave_air', 'minecraft:void_air')


def surface_columns(chunk: dict, columns) -> dict:
    """Find the true highest non-air block for each sampled local X/Z column.

    Sections are processed from top to bottom. Packed 4096-state arrays are
    decoded once PER SECTION, not once for each column. This works for modern
    26.x palettes, non-standard dimension heights and omitted empty sections,
    because it never infers Y from a heightmap's compressed origin.
    """
    root = chunk.get('Level', chunk)
    sections = root.get('sections') or root.get('Sections') or []
    pending = set(columns)
    found = {}
    version = int(chunk.get('DataVersion', root.get('DataVersion', 3000)))
    for section in sorted(sections, key=lambda s: int(s.get('Y', 0)), reverse=True):
        if not pending:
            break
        sy = int(section.get('Y', 0))
        states = section.get('block_states') or section
        palette = states.get('palette') or states.get('Palette') or []
        if not palette:
            continue
        names = [block_name(state) for state in palette]
        if len(names) == 1:
            name = names[0]
            if not _is_air(name):
                for column in pending:
                    found[column] = (sy * 16 + 15, name)
                pending.clear()
            continue

        indexes = unpack_palette(states.get('data') or states.get('BlockStates') or [],
                                 len(palette), version)
        for lx, lz in tuple(pending):
            base = lz * 16 + lx
            for ly in range(15, -1, -1):
                name = names[indexes[ly * 256 + base]]
                if not _is_air(name):
                    found[(lx, lz)] = (sy * 16 + ly, name)
                    pending.remove((lx, lz))
                    break
    return found


def build_landscape(dim: Path, centre, near_radius: int, radius: int = 128,
                    step: int = 8, color_for=None):
    """Return a compact optional terrain layer, derived from real saved blocks."""
    if radius <= 0:
        return None
    if radius < near_radius + step or radius > 192 or step not in (4, 8, 16):
        raise ValueError('Surroundings radius/step is outside supported bounds')

    side = 2 * math.ceil(radius / step) + 1
    half = side // 2
    x0, z0 = int(centre[0]) - half * step, int(centre[2]) - half * step
    samples = [SAMPLE.pack(MISSING, 0, 0, 0)] * (side * side)
    by_chunk = defaultdict(list)
    for iz in range(side):
        z = z0 + iz * step
        for ix in range(side):
            x = x0 + ix * step
            if max(abs(x - centre[0]), abs(z - centre[2])) < near_radius - step:
                continue
            by_chunk[(x // 16, z // 16)].append((iz * side + ix, x % 16, z % 16))

    present = 0
    with RegionReader(dim / 'region') as reader:
        for (cx, cz), positions in by_chunk.items():
            chunk = reader.chunk(cx, cz)
            if chunk is None:
                continue
            columns = surface_columns(chunk, {(lx, lz) for _, lx, lz in positions})
            for index, lx, lz in positions:
                top = columns.get((lx, lz))
                if top is None:
                    continue
                y, block = top
                relative_y = y - centre[1]
                if not -32767 <= relative_y <= 32767:
                    continue
                rgb = color_for(block) if color_for else (112, 149, 115)
                samples[index] = SAMPLE.pack(int(relative_y), *rgb)
                present += 1

    # Hide the crop-box walls only if the ring needed to join near and far
    # is fully present in the saved chunks. Missing terrain remains missing.
    joinable = present > 0
    if joinable:
        for iz in range(side):
            for ix in range(side):
                dx = abs(x0 + ix * step - centre[0])
                dz = abs(z0 + iz * step - centre[2])
                edge = max(dx, dz)
                if near_radius - step <= edge <= near_radius + step:
                    if SAMPLE.unpack(samples[iz * side + ix])[0] == MISSING:
                        joinable = False
                        break
            if not joinable:
                break

    return {
        'version': 1,
        'source': 'saved-block-columns',
        'joinable': joinable,
        'step': step,
        'radius': radius,
        'size': side,
        'x0': x0 - centre[0],
        'z0': z0 - centre[2],
        'samples': base64.b64encode(b''.join(samples)).decode('ascii'),
        'present': present,
    }
