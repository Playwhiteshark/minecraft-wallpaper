"""On-demand, read-only discovery of saved Minecraft entities.

Discovery is deliberately independent of the small set of models supported by
the WebGL viewer. Identity is UUID-based when saved; fallback position IDs are
explicitly marked nonpersistent. No UUIDs/owner details are emitted in scenes.
"""
from __future__ import annotations

import json
import math
import re
from pathlib import Path

from .nbt import RegionReader, _uuid_from_nbt, entity_records

# This describes the current WEB VIEWER only; it is not an entity scanner
# whitelist. Future model implementations register here independently.
MODEL_TYPES = frozenset({
    'minecraft:happy_ghast', 'minecraft:horse', 'minecraft:wolf',
    'minecraft:cat', 'minecraft:parrot', 'minecraft:fox', 'minecraft:allay',
})

# NBT entities are broader than mobs. Exclude common inanimate/projectile
# classes without requiring a complete Minecraft species registry.
NON_MOB_TYPES = frozenset({
    'item', 'experience_orb', 'painting', 'item_frame', 'glow_item_frame',
    'armor_stand', 'area_effect_cloud', 'falling_block', 'interaction',
    'leash_knot', 'marker', 'arrow', 'spectral_arrow', 'trident', 'fireball',
    'small_fireball', 'dragon_fireball', 'snowball', 'egg', 'ender_pearl',
    'potion', 'llama_spit', 'wind_charge', 'firework_rocket', 'tnt',
    'block_display', 'item_display', 'text_display', 'fishing_bobber',
    'eye_of_ender', 'experience_bottle', 'shulker_bullet',
})


def _name_component(value):
    """Read common literal Minecraft text components, not translation keys."""
    if isinstance(value, str):
        if not value.strip():
            return ''
        try:
            parsed = json.loads(value)
        except (ValueError, TypeError):
            return value.strip()[:120]
        if isinstance(parsed, str):
            return parsed.strip()[:120]
        value = parsed
    if isinstance(value, list):
        return ''.join(_name_component(item) for item in value)[:120]
    if isinstance(value, dict):
        own = value.get('text', '')
        result = str(own) if isinstance(own, str) else ''
        extra = value.get('extra', [])
        if isinstance(extra, list):
            result += ''.join(_name_component(item) for item in extra)
        return result.strip()[:120]
    return ''


def _custom_name(obj):
    components = obj.get('components')
    raw = obj.get('CustomName') or obj.get('custom_name')
    if not raw and isinstance(components, dict):
        raw = components.get('minecraft:custom_name') or components.get('custom_name')
    return _name_component(raw)


def _tame_status(obj):
    owner = (obj.get('Owner') or obj.get('owner') or
             obj.get('OwnerUUID') or obj.get('owner_uuid'))
    if _uuid_from_nbt(owner):
        return 'tamed'
    flag = obj.get('Tame', obj.get('tame'))
    if flag is not None:
        return 'tamed' if bool(flag) else 'wild'
    return 'unknown'



_HARNESS_COLORS = frozenset({
    'white', 'orange', 'magenta', 'light_blue', 'yellow', 'lime',
    'pink', 'gray', 'light_gray', 'cyan', 'purple', 'blue', 'brown',
    'green', 'red', 'black',
})


def _harness_color(obj):
    """Read the actual happy-ghast body equipment slot, not a visual guess."""
    equipment = obj.get('equipment') or obj.get('Equipment') or {}
    body = equipment.get('body') if isinstance(equipment, dict) else None
    if body is None:
        body = obj.get('body_armor_item')  # earlier saves
    if not isinstance(body, dict):
        return None
    item_id = body.get('id')
    if not isinstance(item_id, str):
        return None
    name = item_id.removeprefix('minecraft:')
    if not name.endswith('_harness'):
        return None
    color = name[:-len('_harness')]
    return color if color in _HARNESS_COLORS else None

def _record(obj, bounds, *, scan_all_heights=False):
    name = obj.get('id')
    if not isinstance(name, str) or not name:
        return None
    kind = name.rsplit(':', 1)[-1]
    if kind in NON_MOB_TYPES or kind.endswith(('_boat', '_minecart')):
        return None
    pos = obj.get('Pos')
    if not isinstance(pos, list) or len(pos) < 3:
        return None
    try:
        coords = [float(p) for p in pos[:3]]
    except (TypeError, ValueError, OverflowError):
        return None
    if not all(math.isfinite(p) for p in coords):
        return None
    x, y, z = coords
    xmin, xmax, ymin, ymax, zmin, zmax = bounds
    if not (xmin <= x <= xmax and zmin <= z <= zmax):
        return None
    if not scan_all_heights and ymin is not None and ymax is not None and not (ymin <= y <= ymax):
        return None
    uid = _uuid_from_nbt(obj.get('UUID') or obj.get('uuid'))
    stable = uid is not None
    # A missing UUID is not a persistent identity: a moved creature will
    # become missing, rather than selecting some other creature in its place.
    key = 'uuid:' + uid if uid else (
        f'position:{name}:{x:.3f}:{y:.3f}:{z:.3f}')
    title = _custom_name(obj)
    rotation = obj.get('Rotation')
    yaw = 0.0
    if isinstance(rotation, list) and rotation:
        try:
            yaw = float(rotation[0])
            if not math.isfinite(yaw):
                yaw = 0.0
        except (ValueError, TypeError):
            pass
    tame = _tame_status(obj)
    return {
        'key': key,
        'stable': stable,
        'type': kind,
        'resource': name,
        'name': title,
        'tame': tame,
        'renderable': name in MODEL_TYPES,
        'pos': [round(p, 3) for p in coords],
        'yaw': yaw,
        'baby': bool(obj.get('IsBaby', False) or obj.get('Age', 0) < 0),
        'variant': obj.get('variant', obj.get('Variant', obj.get('CatType'))),
        'collar': obj.get('CollarColor', obj.get('collar_color')),
        'harness': _harness_color(obj) if kind == 'happy_ghast' else None,
    }


def scan_saved_entities(dim: Path, bounds, *, all_heights=False):
    """Return sorted records from only nearby entity chunks; never write a save.

    bounds: (xmin, xmax, ymin, ymax, zmin, zmax). all_heights allows a mob
    discovery window broader than the detailed scene's Y extraction bounds.
    """
    xmin, xmax, _, _, zmin, zmax = bounds
    results = {}
    with RegionReader(dim / 'entities') as reader:
        for cx in range(xmin // 16, xmax // 16 + 1):
            for cz in range(zmin // 16, zmax // 16 + 1):
                chunk = reader.chunk(cx, cz)
                for obj in entity_records(chunk):
                    if not isinstance(obj, dict):
                        continue
                    entry = _record(obj, bounds, scan_all_heights=all_heights)
                    if entry is not None:
                        results.setdefault(entry['key'], entry)

    def order(entry):
        named, tamed = bool(entry['name']), entry['tame'] == 'tamed'
        priority = 0 if named and tamed else 1 if named else 2 if tamed else 3
        return (priority, (entry['name'] or entry['type']).casefold(),
                entry['type'], entry['key'])
    return sorted(results.values(), key=order)


def scan_world_mobs(world: Path, dimension: str, centre, radius: int):
    """User-triggered, bounded read of saved entities; never modifies the world.

    A scan searches X/Z independently of the detailed render bounds and all
    saved Y levels. Caller keeps UUIDs in local configuration only.
    """
    if not 8 <= int(radius) <= 192:
        raise ValueError('Mob search radius must be between 8 and 192')
    centre = [int(v) for v in centre]
    radius = int(radius)
    bounds = (centre[0]-radius, centre[0]+radius, None, None,
              centre[2]-radius, centre[2]+radius)
    from .scene import dimension_directory, check_world_closed, nearby_files
    world = Path(world).expanduser().resolve()
    dim = dimension_directory(world, dimension)
    check_world_closed(world)
    paths = list(nearby_files(dim / 'entities', bounds))
    def snapshot():
        return [(str(p), p.stat().st_mtime_ns, p.stat().st_size) for p in paths]
    before = snapshot()
    mobs = scan_saved_entities(dim, bounds, all_heights=True)
    after = snapshot()
    check_world_closed(world)
    if before != after:
        raise ValueError('World changed during mob scan. Close Minecraft and retry.')
    return mobs

def find_named_mobs(world: Path, dimension: str, query: str, *, max_chunks=50000):
    """Search saved entity region indexes on demand, not on every wallpaper update.

    This can locate a named pet outside the near-base mob picker radius.
    Every opened chunk is selected from its region header's populated entries.
    We do not scan blocks or read full world terrain, nor invent unsaved mobs.
    """
    query = str(query).strip()
    if not 1 <= len(query) <= 120:
        raise ValueError('Enter a name to find (up to 120 characters).')
    from .scene import dimension_directory, check_world_closed
    world = Path(world).expanduser().resolve()
    check_world_closed(world)
    directory = dimension_directory(world, dimension) / 'entities'
    names = []
    for path in sorted(directory.glob('r.*.*.mca')):
        m = re.fullmatch(r'r\.(-?\d+)\.(-?\d+)\.mca', path.name)
        if m:
            names.append((path, int(m.group(1)), int(m.group(2))))
    snapshot = [(p, p.stat().st_mtime_ns, p.stat().st_size) for p, _, _ in names]
    matches = {}
    count = 0
    with RegionReader(directory) as reader:
        for path, rx, rz in names:
            with path.open('rb') as handle:
                header = handle.read(4096)
            if len(header) < 4096:
                raise ValueError('Corrupt entity region header: ' + path.name)
            for index in range(1024):
                if not int.from_bytes(header[index*4:index*4+4], 'big'):
                    continue
                count += 1
                if count > max_chunks:
                    raise ValueError('Named mob search exceeded its safety limit. Narrow the world or region.')
                cx = rx * 32 + index % 32
                cz = rz * 32 + index // 32
                chunk = reader.chunk(cx, cz)
                for obj in entity_records(chunk):
                    if not isinstance(obj, dict):
                        continue
                    # Use a broad bounding rectangle only for record validation;
                    # actual query is by saved custom name.
                    entry = _record(obj, (-1e15,1e15,None,None,-1e15,1e15),
                                    scan_all_heights=True)
                    if entry and entry['name'] and query.casefold() in entry['name'].casefold():
                        matches.setdefault(entry['key'], entry)
    after = [(p, p.stat().st_mtime_ns, p.stat().st_size) for p, _, _ in names]
    check_world_closed(world)
    if snapshot != after:
        raise ValueError('World changed during search. Close Minecraft and retry.')
    return sorted(matches.values(), key=lambda e: (e['name'].casefold(), e['type'], e['key']))
