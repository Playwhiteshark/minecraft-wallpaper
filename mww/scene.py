"""Read a bounded region and write a compact, offline, WebGL2 scene.

Only the Minecraft save and optionally the local client jar are read. No world
mutations, network access, Minecraft process, or runtime webserver are needed.
"""
from __future__ import annotations

import base64
import hashlib
import json
import math
import os
import re
import shutil
import struct
import sys
import tempfile
import time
import zipfile
from pathlib import Path

from .nbt import RegionReader, WorldFormatError, block_name, block_properties, entity_records, iterate_blocks, level_info
from .landscape import build_landscape, SAMPLE
from .entities import scan_saved_entities
from .mob_assets import build_entity_assets

AIR = {'minecraft:air', 'minecraft:cave_air', 'minecraft:void_air'}
GAS = {'minecraft:water', 'minecraft:lava'}
NO_CUBE = ('_flower', '_sapling', '_bush', '_grass', '_fern', '_mushroom', '_torch', '_rail', '_vine',
           '_seagrass', 'dandelion', 'poppy', 'lily_of_the_valley', 'azure_bluet', 'dead_bush',
           'grass', 'fern', 'tall_grass', 'short_grass', 'torch', 'sugar_cane', 'wheat', 'carrots',
           'potatoes', 'allium', 'blue_orchid', 'cornflower', 'oxeye_daisy', 'sunflower', 'lilac',
           'rose_bush', 'peony', 'cactus_flower')
PARTIAL = ('_slab', '_stairs', '_door', '_trapdoor', '_fence', '_wall', '_pane', '_carpet', '_button',
           '_pressure_plate', '_sign', '_gate', 'bed', 'chest', 'lantern', 'ladder')
TRANSPARENT = ('glass', 'water', 'lava', 'ice', 'leaves', 'scaffolding', 'barrier', 'honey_block', 'slime_block')
LIGHT = {'torch': 12, 'lantern': 15, 'sea_lantern': 15, 'glowstone': 15, 'shroomlight': 15,
         'end_rod': 14, 'soul_lantern': 10, 'campfire': 13, 'lava': 15, 'redstone_lamp': 12,
         'jack_o_lantern': 15, 'froglight': 15, 'candle': 8, 'glow_lichen': 7}
ENTITY_TYPES = {'minecraft:happy_ghast', 'minecraft:horse', 'minecraft:wolf', 'minecraft:cat',
                'minecraft:parrot', 'minecraft:fox', 'minecraft:allay'}
MAX_RADIUS = 48
MAX_FACES = 370_000
# x,y,z: signed 16-bit relative position; face: byte; tile: u16; tint: rgb bytes; shape: byte
FACE = struct.Struct('<hhhBxHBBBBxx')


def dimension_directory(world: Path, dimension: str) -> Path:
    """Select Minecraft 26.1 dimension folders, retaining older saves."""
    names = {'overworld': 'overworld', 'nether': 'the_nether', 'end': 'the_end'}
    if dimension not in names:
        raise ValueError('Unknown dimension')
    modern = world / 'dimensions' / 'minecraft' / names[dimension]
    legacy = world if dimension == 'overworld' else world / ('DIM-1' if dimension == 'nether' else 'DIM1')
    if modern.is_dir():
        return modern
    if (legacy / 'region').is_dir() or (legacy / 'entities').is_dir():
        return legacy
    if (world / 'dimensions' / 'minecraft').is_dir():
        return modern
    return legacy


def nearby_files(folder: Path, bounds):
    xmin, xmax, _, _, zmin, zmax = bounds
    for rx in range((xmin // 16) // 32, (xmax // 16) // 32 + 1):
        for rz in range((zmin // 16) // 32, (zmax // 16) // 32 + 1):
            p = folder / f'r.{rx}.{rz}.mca'
            if p.exists():
                yield p


def input_fingerprint(world: Path, dimension: str, bounds, jar: Path | None):
    dim = dimension_directory(world, dimension)
    paths = [world / 'level.dat']
    paths.extend(nearby_files(dim / 'region', bounds))
    paths.extend(nearby_files(dim / 'entities', bounds))
    if jar and jar.is_file():
        paths.append(jar)
    items = []
    for p in sorted(set(paths)):
        s = p.stat()
        items.append((str(p), s.st_mtime_ns, s.st_size))
    return items


def check_world_closed(world: Path):
    """Best-effort lock probe; caller must still compare source file metadata."""
    path = world / 'session.lock'
    if not path.exists():
        return
    try:
        with path.open('r+b') as f:
            if os.name == 'nt':
                import msvcrt
                f.seek(0)
                msvcrt.locking(f.fileno(), msvcrt.LK_NBLCK, 1)
                msvcrt.locking(f.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl
                fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
                fcntl.flock(f, fcntl.LOCK_UN)
    except (PermissionError, OSError) as e:
        raise WorldFormatError('World may be open in Minecraft (session.lock is locked). Close it first.') from e


def is_plant(name: str) -> bool:
    kind = name.split(':')[-1]
    return any(kind.endswith(s) or kind == s for s in NO_CUBE)


def is_transparent(name: str) -> bool:
    kind = name.split(':')[-1]
    return is_plant(name) or any(t in kind for t in TRANSPARENT) or kind.endswith(('_slab', '_stairs', '_door', '_trapdoor', '_pane', '_fence', '_wall', '_carpet'))


def slab_shape(name: str, state) -> int:
    if name.endswith('_slab'):
        mode = block_properties(state).get('type', 'bottom')
        return 1 if mode == 'top' else 2 if mode == 'bottom' else 0
    if name.endswith('_carpet'):
        return 3
    return 0


def base_texture(name: str):
    short = name.split(':')[-1]
    for suffix in ('_stairs', '_slab', '_wall', '_fence', '_fence_gate'):
        if short.endswith(suffix):
            short = short[:-len(suffix)]
            break
    woods = ('oak', 'spruce', 'birch', 'jungle', 'acacia', 'dark_oak', 'mangrove', 'cherry', 'bamboo', 'pale_oak', 'crimson', 'warped')
    if short in woods:
        return short + '_planks'
    if short in ('stone_brick', 'mossy_stone_brick', 'cracked_stone_brick'):
        return short + 's'
    if short.endswith('_bed'):
        return short[:-4] + '_wool'
    if short.endswith('_carpet'):
        return short[:-7] + '_wool'
    if short.endswith('_chest') or short in ('chest', 'trapped_chest'):
        return 'oak_planks'
    if short.endswith('_door'):
        return short + '_bottom'
    if short == 'water':
        return 'water_still'
    if short == 'lava':
        return 'lava_still'
    if short == 'grass':
        return 'short_grass'
    if short.endswith('_log'):
        return short
    return short


def texture_for(name: str, face: int):
    short = name.split(':')[-1]
    if short == 'grass_block':
        return 'grass_block_top' if face == 5 else 'dirt' if face == 4 else 'grass_block_side'
    if short == 'dirt_path':
        return 'dirt_path_top' if face == 5 else 'dirt' if face == 4 else 'dirt_path_side'
    if short == 'mycelium':
        return 'mycelium_top' if face == 5 else 'dirt' if face == 4 else 'mycelium_side'
    if short == 'podzol':
        return 'podzol_top' if face == 5 else 'dirt' if face == 4 else 'podzol_side'
    if short.endswith('_log') or short.endswith('_stem'):
        return short + '_top' if face in (4, 5) else short
    if short == 'sandstone':
        return 'sandstone_top' if face == 5 else 'sandstone_bottom' if face == 4 else 'sandstone'
    if short == 'farmland':
        return 'farmland' if face == 5 else 'dirt'
    return base_texture(name)


def tint_for(name: str):
    short = name.split(':')[-1]
    if short == 'grass_block':
        return (124, 178, 99)
    if 'leaves' in short or short in ('vine', 'short_grass', 'tall_grass', 'grass', 'fern'):
        return (118, 169, 103)
    if short == 'water':
        return (90, 146, 216)
    if short == 'lava':
        return (255, 188, 101)
    return (255, 255, 255)


def fallback_color(name: str):
    short = name.split(':')[-1]
    colors = (
        (('grass', 'leaves', 'moss', 'fern', 'vine'), (103, 155, 86)),
        (('water',), (65, 130, 197)),
        (('lava', 'magma'), (233, 112, 51)),
        (('oak', 'spruce', 'birch', 'plank', 'wood', 'log', 'chest'), (166, 126, 79)),
        (('stone', 'cobble', 'deepslate', 'andesite', 'tuff'), (116, 125, 136)),
        (('dirt', 'mud', 'farmland'), (127, 94, 67)),
        (('sand', 'end_stone'), (213, 203, 143)),
        (('glass', 'ice'), (170, 213, 222)),
        (('snow', 'quartz', 'white'), (225, 229, 231)),
        (('black', 'obsidian'), (46, 45, 61)),
        (('torch', 'lantern', 'glowstone'), (244, 200, 107)),
    )
    for words, rgb in colors:
        if any(x in short for x in words):
            return rgb
    h = hashlib.sha1(name.encode('utf-8')).digest()
    return (100 + h[0] // 3, 105 + h[1] // 3, 105 + h[2] // 3)


def find_client_jar(preferred: str = '') -> Path | None:
    if preferred:
        p = Path(preferred).expanduser()
        return p if p.is_file() else None
    if os.name == 'nt':
        root = Path(os.environ.get('APPDATA', '')) / '.minecraft' / 'versions'
    else:
        root = Path.home() / '.minecraft' / 'versions'
    if not root.is_dir():
        return None
    jars = [p for p in root.glob('*/*.jar') if p.is_file()]
    return max(jars, key=lambda p: p.stat().st_mtime_ns) if jars else None


class TextureBank:
    def __init__(self, jar: Path | None):
        self.jar = jar
        self.zip = zipfile.ZipFile(jar) if jar else None
        self.tiles = []
        self.mapping = {}

    def close(self):
        if self.zip:
            self.zip.close()

    def tile(self, texture: str):
        if texture not in self.mapping:
            entry = {'name': texture, 'rgb': fallback_color(texture)}
            if self.zip:
                asset = f'assets/minecraft/textures/block/{texture}.png'
                try:
                    with self.zip.open(asset) as f:
                        raw = f.read(750_000)
                    if raw.startswith(b'\x89PNG\r\n\x1a\n'):
                        entry['png'] = base64.b64encode(raw).decode('ascii')
                except KeyError:
                    pass
            self.mapping[texture] = len(self.tiles)
            self.tiles.append(entry)
        return self.mapping[texture]


def _neighbour_visible(name: str, other: str | None):
    if other is None:
        return True
    if name == other and is_transparent(name):
        return False
    return is_transparent(other)


def extract_blocks(dim: Path, bounds, version: int):
    xmin, xmax, _, _, zmin, zmax = bounds
    blocks = {}
    with RegionReader(dim / 'region') as rr:
        for cx in range(xmin // 16, xmax // 16 + 1):
            for cz in range(zmin // 16, zmax // 16 + 1):
                chunk = rr.chunk(cx, cz)
                if chunk:
                    for pos, state in iterate_blocks(chunk, cx, cz, version, bounds):
                        blocks[pos] = state
    if not blocks:
        raise WorldFormatError('No blocks found here. Try different X/Z coordinates or dimension.')
    return blocks


def extract_entities(dim: Path, bounds):
    xmin, xmax, ymin, ymax, zmin, zmax = bounds
    entities = []
    seen = set()
    with RegionReader(dim / 'entities') as rr:
        for cx in range(xmin // 16, xmax // 16 + 1):
            for cz in range(zmin // 16, zmax // 16 + 1):
                record = rr.chunk(cx, cz)
                for obj in entity_records(record):
                    name = str(obj.get('id', ''))
                    if name not in ENTITY_TYPES:
                        continue
                    pos = obj.get('Pos') or []
                    if len(pos) < 3:
                        continue
                    x, y, z = [float(v) for v in pos[:3]]
                    if not (xmin <= x <= xmax and ymin - 6 <= y <= ymax + 6 and zmin <= z <= zmax):
                        continue
                    uid = obj.get('UUID') or [name, x, y, z]
                    key = tuple(uid) if isinstance(uid, list) else str(uid)
                    if key in seen:
                        continue
                    seen.add(key)
                    rot = obj.get('Rotation') or [0]
                    entities.append({
                        'type': name.split(':')[-1],
                        'pos': [round(x, 3), round(y, 3), round(z, 3)],
                        'yaw': float(rot[0]) if rot else 0,
                        'baby': bool(obj.get('IsBaby', False) or obj.get('Age', 0) < 0),
                    })
    return entities


def lights_near(blocks: dict, centre):
    ranked = []
    for (x, y, z), state in blocks.items():
        short = block_name(state).split(':')[-1]
        level = next((v for k, v in LIGHT.items() if k in short), 0)
        if not level:
            continue
        if 'redstone_lamp' in short and isinstance(state, dict) and block_properties(state).get('lit') == 'false':
            continue
        dx, dy, dz = x - centre[0], y - centre[1], z - centre[2]
        dist = dx * dx + dy * dy + dz * dz
        ranked.append((dist, x, y, z, level))
    ranked.sort()
    return [[x + .5, y + .5, z + .5, int(level)] for _, x, y, z, level in ranked[:8]]


def build_mesh(blocks: dict, centre, bank: TextureBank):
    solids = bytearray()
    alpha = bytearray()
    dirs = ((0, 0, -1), (0, 0, 1), (-1, 0, 0), (1, 0, 0), (0, -1, 0), (0, 1, 0))
    for (x, y, z), state in blocks.items():
        name = block_name(state)
        local = (x - centre[0], y - centre[1], z - centre[2])
        tint = tint_for(name)
        shape = slab_shape(name, state)
        if is_plant(name):
            tid = bank.tile(texture_for(name, 0))
            for direction in (6, 7):
                alpha.extend(FACE.pack(*local, direction, tid, *tint, 0))
            continue
        for face, delta in enumerate(dirs):
            adj = (x + delta[0], y + delta[1], z + delta[2])
            next_state = blocks.get(adj)
            other = block_name(next_state) if next_state is not None else None
            if not _neighbour_visible(name, other) and shape == 0:
                continue
            texture = texture_for(name, face)
            tid = bank.tile(texture)
            record = FACE.pack(*local, face, tid, *tint, shape)
            if is_transparent(name) or shape:
                alpha.extend(record)
            else:
                solids.extend(record)
            if (len(alpha) + len(solids)) // FACE.size > MAX_FACES:
                raise WorldFormatError('This area is too complex. Reduce the radius or height range.')
    return solids, alpha


def validate_options(options: dict):
    centre = [int(options[k]) for k in ('x', 'y', 'z')]
    radius = int(options.get('radius', 24))
    if not 8 <= radius <= MAX_RADIUS:
        raise ValueError('Radius must be between 8 and 48 blocks for the starter')
    below = int(options.get('below', 14))
    above = int(options.get('above', 28))
    if not 4 <= below <= 40 or not 8 <= above <= 60:
        raise ValueError('Vertical range is out of bounds')
    light = str(options.get('light', 'golden'))
    if light not in ('golden', 'day', 'night'):
        raise ValueError('Invalid lighting preset')
    dim = str(options.get('dimension', 'overworld'))
    dimension_directory(Path('.'), dim)
    return centre, radius, below, above, light, dim


def build_scene(world: Path, options: dict):
    world = Path(world).resolve()
    info = level_info(world)
    centre, radius, below, above, light, dimname = validate_options(options)
    bounds = (centre[0] - radius, centre[0] + radius, centre[1] - below,
              centre[1] + above, centre[2] - radius, centre[2] + radius)
    jar = find_client_jar(str(options.get('jar', '')))
    surroundings_radius = int(options.get('landscape_radius', 128))
    mob_radius = int(options.get('mob_radius', max(64, radius)))
    if not 8 <= mob_radius <= 192:
        raise ValueError('Mob search radius must be between 8 and 192')
    selection = options.get('mob_ids')
    if selection is not None and (not isinstance(selection, list) or
                                  len(selection) > 256 or
                                  any(not isinstance(key, str) or len(key) > 200
                                      for key in selection)):
        raise ValueError('Invalid selected mob identities')
    if surroundings_radius < 0 or surroundings_radius > 192 or (surroundings_radius and surroundings_radius < radius + 8):
        raise ValueError('Surroundings radius must be 0 (off) or from detailed radius + 8 to 192')
    check_world_closed(world)
    source_span = max(radius, surroundings_radius, mob_radius if selection is not None else radius)
    source_bounds = (centre[0] - source_span, centre[0] + source_span, bounds[2], bounds[3],
                     centre[2] - source_span, centre[2] + source_span)
    before = input_fingerprint(world, dimname, source_bounds, jar)
    if not any('/region/' in p.replace('\\', '/') for p, _, _ in before):
        raise WorldFormatError('No region files near the selected coordinates. Check the dimension and saved base position, or confirm chunks were generated there.')
    region_dir = dimension_directory(world, dimname)
    blocks = extract_blocks(region_dir, bounds, info['data_version'])
    found = []
    chosen = []
    absent_ids = []
    if bool(options.get('pets', True)):
        scan_radius = mob_radius if selection is not None else radius
        scan_bounds = (centre[0] - scan_radius, centre[0] + scan_radius, None, None,
                       centre[2] - scan_radius, centre[2] + scan_radius)
        found = scan_saved_entities(region_dir, scan_bounds, all_heights=True)
        if selection is None:  # v0.1 backwards-compatible automatic inclusion
            chosen = [e for e in found if 'minecraft:' + e['type'] in ENTITY_TYPES and
                      bounds[0] <= e['pos'][0] <= bounds[1] and
                      bounds[2] - 6 <= e['pos'][1] <= bounds[3] + 6 and
                      bounds[4] <= e['pos'][2] <= bounds[5]]
        else:
            by_key = {e['key']: e for e in found}
            chosen = [by_key[key] for key in dict.fromkeys(selection) if key in by_key]
            absent_ids = [key for key in dict.fromkeys(selection) if key not in by_key]
    entities = [{key: e.get(key) for key in ('type', 'pos', 'yaw', 'baby',
                  'variant', 'tame', 'collar')} for e in chosen][:64]
    # Asset data is local output only, never added to this repository.
    # Missing model/texture is surfaced rather than silently being called
    # an accurately rendered Minecraft mob.
    cache_root = Path(str(options.get('model_cache') or Path.home() / '.mww-model-cache'))
    model_pack, model_warnings = build_entity_assets(
        entities, cache_root, jar, fetch_missing=bool(options.get('fetch_models', False)))
    surroundings = build_landscape(region_dir, centre, radius, surroundings_radius,
                                   color_for=fallback_color)
    bank = TextureBank(jar)
    try:
        opaque, alpha = build_mesh(blocks, centre, bank)
        tiles = bank.tiles
    finally:
        bank.close()
    after = input_fingerprint(world, dimname, source_bounds, jar)
    check_world_closed(world)
    if before != after:
        raise WorldFormatError('World files changed during refresh. Close Minecraft and retry.')
    return {
        'schema': 1, 'name': info['name'], 'dataVersion': info['data_version'],
        'origin': centre, 'radius': radius, 'below': below, 'above': above,
        'light': light, 'dimension': dimname,
        'opaque': base64.b64encode(opaque).decode('ascii'),
        'alpha': base64.b64encode(alpha).decode('ascii'),
        'tiles': tiles,
        'landscape': surroundings,
        'lights': lights_near(blocks, centre),
        'entities': entities,
        'entityAssets': model_pack,
        'camera': {'yaw': float(options.get('yaw', 42)), 'pitch': float(options.get('pitch', 22)),
                   'distance': float(options.get('distance', radius * 2.2))},
        'stats': {'blocks': len(blocks), 'faces': (len(opaque) + len(alpha)) // FACE.size,
                  'animals': len(entities), 'textures': len(tiles),
                   'mobFound': len(found), 'mobSelected': len(chosen),
                   'mobTextured': sum(bool(e.get('texture') and e['type'] in model_pack['models'])
                                      for e in entities),
                   'mobMissing': len(absent_ids), 'mobWarnings': model_warnings[:8],
                   'landscapeSamples': surroundings['present'] if surroundings else 0,
                  'sourceJar': jar.name if jar else 'none (colour fallback)'},
    }


def scene_script(scene: dict) -> bytes:
    # A normal local script is intentional: fetch() of file:// geometry can be blocked by CORS.
    compact = json.dumps(scene, separators=(',', ':'), ensure_ascii=True).replace('<', '\\u003c')
    return ("/* Minecraft Living World Wallpaper: generated local scene */\nwindow.MWW_SCENE = " + compact + ";\n").encode('utf-8')


def verify_scene_script(data: bytes):
    prefix = b'window.MWW_SCENE = '
    lines = data.split(b'\n')
    if len(lines) < 2 or not lines[1].startswith(prefix) or not lines[1].endswith(b';'):
        raise ValueError('Invalid generated scene script')
    scene = json.loads(lines[1][len(prefix):-1])
    if scene.get('schema') != 1:
        raise ValueError('Unsupported generated scene schema')
    for key in ('opaque', 'alpha'):
        if len(base64.b64decode(scene[key], validate=True)) % FACE.size:
            raise ValueError('Invalid face records')
    landscape = scene.get('landscape')
    if landscape is not None:
        if landscape.get('version') != 1 or not 1 <= int(landscape.get('size', 0)) <= 97:
            raise ValueError('Unsupported landscape format')
        payload = base64.b64decode(landscape['samples'], validate=True)
        if len(payload) != int(landscape['size']) ** 2 * SAMPLE.size:
            raise ValueError('Invalid landscape sample records')
    pack = scene.get('entityAssets')
    if pack is not None:
        if pack.get('version') != 1 or not isinstance(pack.get('models'), dict) or not isinstance(pack.get('textures'), dict):
            raise ValueError('Unsupported mob model package')
        if len(pack['models']) > 64 or len(pack['textures']) > 200:
            raise ValueError('Mob model package is too large')
        for png in pack['textures'].values():
            raw = base64.b64decode(png, validate=True)
            if not raw.startswith(b'\x89PNG\r\n\x1a\n') or len(raw) > 2_000_000:
                raise ValueError('Invalid mob texture data')
    return scene


def publish_scene(scene: dict, output: Path, web_source: Path):
    """Validate before changing output; retain one last-good scene script."""
    output.mkdir(parents=True, exist_ok=True)
    generated = scene_script(scene)
    verify_scene_script(generated)
    for filename in ('index.html', 'viewer.js', 'viewer.css'):
        if not (web_source / filename).is_file():
            raise FileNotFoundError(web_source / filename)
    for filename in ('index.html', 'viewer.js', 'viewer.css'):
        target = output / filename
        data = (web_source / filename).read_bytes()
        # Safe to replace only files created by this app's dedicated output folder.
        if not target.exists() or target.read_bytes() != data:
            with tempfile.NamedTemporaryFile(dir=output, prefix='.mww-', delete=False) as tmp:
                tmp.write(data)
                tmp_name = Path(tmp.name)
            os.replace(tmp_name, target)
    active = output / 'scene-data.js'
    previous = output / 'scene-data.previous.js'
    with tempfile.NamedTemporaryFile(dir=output, prefix='.mww-scene-', delete=False) as tmp:
        tmp.write(generated)
        tmp_name = Path(tmp.name)
    try:
        if active.exists():
            shutil.copy2(active, previous)
        os.replace(tmp_name, active)
    finally:
        if tmp_name.exists():
            tmp_name.unlink()
    return active


def scene_fingerprint(world: Path, options: dict):
    centre, radius, below, above, _, dim = validate_options(options)
    bounds = (centre[0] - radius, centre[0] + radius, centre[1] - below, centre[1] + above,
              centre[2] - radius, centre[2] + radius)
    jar = find_client_jar(str(options.get('jar', '')))
    scenery = int(options.get('landscape_radius', 128))
    mob_search = int(options.get('mob_radius', radius)) if options.get('mob_ids') is not None else radius
    if scenery < 0 or scenery > 192 or (scenery and scenery < radius + 8):
        raise ValueError('Invalid surroundings radius')
    span = max(radius, scenery, mob_search)
    extra_bounds = (centre[0] - span, centre[0] + span, bounds[2], bounds[3],
                    centre[2] - span, centre[2] + span)
    files = input_fingerprint(world, dim, extra_bounds, jar)
    stable_options = {k: v for k, v in options.items() if k != 'world'}
    payload = json.dumps([files, stable_options], sort_keys=True).encode('utf-8')
    return hashlib.sha256(payload).hexdigest()
