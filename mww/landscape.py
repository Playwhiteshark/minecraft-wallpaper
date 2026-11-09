"""Small, optional saved-world heightfield layer for distant scenery.

The near/base mesher owns detailed blocks. This adapter reads Minecraft chunk
Heightmaps and samples a bounded coarse grid; the viewer consumes versioned
surface records. No invented terrain, Minecraft runtime, or third-party packages.
Missing chunks remain missing.
"""
from __future__ import annotations

import base64
import math
import struct
from collections import defaultdict
from pathlib import Path

from .nbt import RegionReader, block_name, unpack_palette

SAMPLE = struct.Struct('<hBBB')  # Y relative to scene centre, RGB; -32768 = missing
MISSING = -32768


def _surface_heights(chunk):
    """Read 256 packed Java heightmap entries (z-major), or return None."""
    root = chunk.get('Level', chunk)
    heightmaps = root.get('Heightmaps') or root.get('heightmaps') or {}
    values = (heightmaps.get('WORLD_SURFACE') or heightmaps.get('MOTION_BLOCKING')
              or heightmaps.get('MOTION_BLOCKING_NO_LEAVES'))
    if not isinstance(values, list) or not values:
        return None
    sections = root.get('sections') or root.get('Sections') or []
    if not sections:
        return None
    section_ys = [int(s.get('Y', 0)) for s in sections]
    min_y = min(section_ys) * 16
    world_height = (max(section_ys) - min(section_ys) + 1) * 16
    bits = max(1, world_height.bit_length())
    per_long = 64 // bits
    if len(values) < math.ceil(256 / per_long):
        return None
    mask = (1 << bits) - 1
    result = []
    for k in range(256):
        value = (int(values[k // per_long]) & 0xFFFFFFFFFFFFFFFF) >> ((k % per_long) * bits)
        height = value & mask
        result.append(min_y + height - 1 if height else None)
    return result


def _top_block(chunk, lx, y, lz):
    """Sample one actual block name at the indicated surface height."""
    root = chunk.get('Level', chunk)
    sections = root.get('sections') or root.get('Sections') or []
    target = y // 16
    for section in sections:
        if int(section.get('Y', 0)) != target:
            continue
        states = section.get('block_states') or section
        palette = states.get('palette') or states.get('Palette') or []
        if not palette:
            return None
        try:
            if len(palette) == 1:
                state = palette[0]
            else:
                data = states.get('data') or states.get('BlockStates') or []
                idx = (y % 16) * 256 + lz * 16 + lx
                indices = unpack_palette(data, len(palette), int(chunk.get('DataVersion', 3000)))
                state = palette[indices[idx]]
            return block_name(state)
        except (ValueError, IndexError, TypeError, KeyError):
            return None
    return None


def build_landscape(dim: Path, centre, near_radius: int, radius: int = 128, step: int = 8, color_for=None):
    """Return a compact optional terrain layer in local coordinates."""
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
            if not chunk:
                continue
            heights = _surface_heights(chunk)
            if heights is None:
                continue
            for n, lx, lz in positions:
                y = heights[lz * 16 + lx]
                if y is None or not -32767 <= y - centre[1] <= 32767:
                    continue
                block = _top_block(chunk, lx, y, lz)
                rgb = color_for(block) if block and color_for else (112, 149, 115)
                samples[n] = SAMPLE.pack(int(y - centre[1]), *rgb)
                present += 1
    return {
        'version': 1,
        'step': step,
        'radius': radius,
        'size': side,
        'x0': x0 - centre[0],
        'z0': z0 - centre[2],
        'samples': base64.b64encode(b''.join(samples)).decode('ascii'),
        'present': present,
    }
