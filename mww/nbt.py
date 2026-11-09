"""Small read-only NBT/Anvil decoder for modern Java saves (not a general Minecraft engine)."""
from __future__ import annotations

import gzip
import io
import math
import re
import struct
import uuid
import zlib
from pathlib import Path


class WorldFormatError(ValueError):
    pass


class NBTReader:
    def __init__(self, data: bytes):
        self.fp = io.BytesIO(data)

    def take(self, n: int) -> bytes:
        v = self.fp.read(n)
        if len(v) != n:
            raise WorldFormatError("Truncated NBT data")
        return v

    def number(self, code: str):
        return struct.unpack('>' + code, self.take(struct.calcsize('>' + code)))[0]

    def string(self):
        n = self.number('H')
        if n > 65535:
            raise WorldFormatError('Invalid NBT string length')
        return self.take(n).decode('utf-8', errors='replace')

    def payload(self, kind: int, depth: int = 0):
        if depth > 60:
            raise WorldFormatError('NBT nesting is too deep')
        if kind == 1:
            return self.number('b')
        if kind == 2:
            return self.number('h')
        if kind == 3:
            return self.number('i')
        if kind == 4:
            return self.number('q')
        if kind == 5:
            return self.number('f')
        if kind == 6:
            return self.number('d')
        if kind == 7:
            n = self.number('i')
            if n < 0 or n > 30_000_000:
                raise WorldFormatError('Unreasonable NBT byte array')
            return self.take(n)
        if kind == 8:
            return self.string()
        if kind == 9:
            subtype, n = self.number('b'), self.number('i')
            if n < 0 or n > 1_000_000:
                raise WorldFormatError('Unreasonable NBT list')
            return [self.payload(subtype, depth + 1) for _ in range(n)]
        if kind == 10:
            result = {}
            while True:
                subtype = self.number('b')
                if subtype == 0:
                    break
                key = self.string()
                result[key] = self.payload(subtype, depth + 1)
            return result
        if kind in (11, 12):
            n = self.number('i')
            if n < 0 or n > 4_000_000:
                raise WorldFormatError('Unreasonable NBT numeric array')
            code = 'i' if kind == 11 else 'q'
            item_size = 4 if kind == 11 else 8
            raw = self.take(n * item_size)
            return list(struct.unpack('>' + str(n) + code, raw)) if n else []
        raise WorldFormatError(f'Unsupported NBT tag {kind}')

    def root(self):
        kind = self.number('b')
        if kind != 10:
            raise WorldFormatError('NBT root is not a compound')
        self.string()  # root name
        return self.payload(10)


def parse_nbt(data: bytes):
    return NBTReader(data).root()


def _saved_position(pos):
    """Read genuine saved Pos coordinates; never substitute the world spawn."""
    if not isinstance(pos, list) or len(pos) != 3:
        return None
    try:
        numbers = [float(v) for v in pos]
    except (ValueError, TypeError, OverflowError):
        return None
    if not all(math.isfinite(v) for v in numbers):
        return None
    return [math.floor(v) for v in numbers]


def _uuid_from_nbt(raw):
    """Minecraft UUID can be an NBT int[4] array or a UUID string."""
    try:
        if isinstance(raw, str):
            return str(uuid.UUID(raw))
        if isinstance(raw, list) and len(raw) == 4:
            value = b''.join((int(v) & 0xffffffff).to_bytes(4, 'big') for v in raw)
            return str(uuid.UUID(bytes=value))
        if isinstance(raw, list) and len(raw) == 2:
            value = b''.join((int(v) & 0xffffffffffffffff).to_bytes(8, 'big') for v in raw)
            return str(uuid.UUID(bytes=value))
    except (ValueError, TypeError, OverflowError):
        pass
    return None


def _playerdata_positions(world: Path):
    """Read 26.1+ players/data or older playerdata, preferring the new layout."""
    records, seen = [], set()
    for folder_name in ('players/data', 'playerdata'):
        folder = world / folder_name
        if not folder.is_dir():
            continue
        for path in sorted(folder.glob('*.dat')):
            key = path.stem.lower()
            if key in seen:
                continue
            try:
                if path.stat().st_size > 16_000_000:
                    continue
                with gzip.open(path, 'rb') as f:
                    player = parse_nbt(f.read(16_000_001))
                position = _saved_position(player.get('Pos'))
                if position is not None:
                    records.append({'id': key, 'pos': position, 'folder': folder_name})
                    seen.add(key)
            except (OSError, EOFError, ValueError, WorldFormatError):
                continue
            if len(records) >= 32:
                return records
    return records


def level_info(world: Path):
    path = world / 'level.dat'
    if not path.is_file():
        raise WorldFormatError('Not a Java world: level.dat is missing')
    with gzip.open(path, 'rb') as f:
        root = parse_nbt(f.read(16_000_001))
    data = root.get('Data', root)
    version = int(data.get('DataVersion', 0))
    if version < 2860:
        raise WorldFormatError('This starter supports modern Java 1.18+ Anvil saves only')
    player = data.get('Player')
    position = _saved_position(player.get('Pos')) if isinstance(player, dict) else None
    source = 'level.dat' if position is not None else None
    candidates = []
    if position is None:
        candidates = _playerdata_positions(world)
        selected_uuid = _uuid_from_nbt(data.get('singleplayer_uuid'))
        selected = next((r for r in candidates if r['id'] == selected_uuid), None) if selected_uuid else None
        if selected is not None:
            position = selected['pos']
            source = selected['folder'] + ' (singleplayer_uuid)'
        elif not selected_uuid and len(candidates) == 1:
            position = candidates[0]['pos']
            source = candidates[0]['folder']
    spawn = None
    if all(k in data for k in ('SpawnX', 'SpawnY', 'SpawnZ')):
        try:
            spawn = [int(data[k]) for k in ('SpawnX', 'SpawnY', 'SpawnZ')]
        except (TypeError, ValueError):
            pass
    return {
        'name': str(data.get('LevelName', world.name)),
        'data_version': version,
        'spawn': spawn,
        'player': position,
        'player_source': source,
        'player_candidates': candidates if position is None else [],
    }


REGION_NAME = re.compile(r'^r\.(-?\d+)\.(-?\d+)\.mca$')


MAX_COMPRESSED_CHUNK = 16_000_000
MAX_DECODED_CHUNK = 24_000_000


def _decode_chunk_payload(compression: int, payload: bytes, where: str) -> bytes:
    """Bound the uncompressed output, and report unsupported valid schemes."""
    if compression == 3:
        if len(payload) > MAX_DECODED_CHUNK:
            raise WorldFormatError(f'Chunk payload too large at {where}')
        return payload
    if compression == 4:
        raise WorldFormatError(f'LZ4-compressed Anvil chunk at {where}; this dependency-free starter does not support LZ4. No save data was modified.')
    if compression == 127:
        raise WorldFormatError(f'Custom server compression at {where} is not supported by the starter.')
    if compression not in (1, 2):
        raise WorldFormatError(f'Chunk compression {compression} not supported at {where}')
    try:
        decompressor = zlib.decompressobj(16 + zlib.MAX_WBITS if compression == 1 else zlib.MAX_WBITS)
        output = decompressor.decompress(payload, MAX_DECODED_CHUNK + 1)
        if len(output) > MAX_DECODED_CHUNK or decompressor.unconsumed_tail:
            raise WorldFormatError(f'Chunk decompressed beyond safety limit at {where}')
        output += decompressor.flush()
        if len(output) > MAX_DECODED_CHUNK:
            raise WorldFormatError(f'Chunk decompressed beyond safety limit at {where}')
        if not decompressor.eof:
            raise WorldFormatError(f'Truncated or invalid compressed chunk at {where}')
        return output
    except zlib.error as exc:
        raise WorldFormatError(f'Invalid chunk compression stream at {where}') from exc


class RegionReader:
    """Seek only selected chunks in Anvil .mca files; never write to the world."""
    def __init__(self, directory: Path):
        self.directory = directory
        self.handles = {}

    def __enter__(self):
        return self

    def __exit__(self, *_):
        for fp, _ in self.handles.values():
            fp.close()
        self.handles.clear()

    def chunk(self, cx: int, cz: int):
        rx, rz = cx // 32, cz // 32
        path = self.directory / f'r.{rx}.{rz}.mca'
        if path not in self.handles:
            if not path.is_file():
                return None
            fp = path.open('rb')
            header = fp.read(8192)
            if len(header) < 8192:
                fp.close()
                raise WorldFormatError(f'Bad region header: {path.name}')
            self.handles[path] = (fp, header)
        fp, header = self.handles[path]
        local = (cx % 32) + (cz % 32) * 32
        location = int.from_bytes(header[local * 4:local * 4 + 4], 'big')
        sector, sectors = location >> 8, location & 255
        if not sector and not sectors:
            return None
        if sector < 2 or sectors < 1:
            raise WorldFormatError(f'Invalid region location in {path.name} at {cx},{cz}')
        fp.seek(sector * 4096)
        raw_length = fp.read(4)
        if len(raw_length) != 4:
            raise WorldFormatError(f'Truncated chunk header in {path.name} at {cx},{cz}')
        length = struct.unpack('>I', raw_length)[0]
        if length < 1 or length > sectors * 4096 - 4 or length > MAX_COMPRESSED_CHUNK:
            raise WorldFormatError(f'Bad chunk length in {path.name} at {cx},{cz}')
        raw_tag = fp.read(1)
        if len(raw_tag) != 1:
            raise WorldFormatError(f'Missing compression type in {path.name} at {cx},{cz}')
        tag = raw_tag[0]
        compression, external = tag & 0x7f, bool(tag & 0x80)
        if external:
            if length != 1:
                raise WorldFormatError(f'Invalid external chunk marker in {path.name} at {cx},{cz}')
            external_path = self.directory / f'c.{cx}.{cz}.mcc'
            if not external_path.is_file():
                raise WorldFormatError(f'External oversized chunk missing: {external_path.name}')
            if external_path.stat().st_size > MAX_COMPRESSED_CHUNK:
                raise WorldFormatError(f'External chunk too large: {external_path.name}')
            payload = external_path.read_bytes()
        else:
            if length < 2:
                raise WorldFormatError(f'Missing compressed payload in {path.name} at {cx},{cz}')
            payload = fp.read(length - 1)
            if len(payload) != length - 1:
                raise WorldFormatError(f'Truncated region chunk in {path.name} at {cx},{cz}')
        decoded = _decode_chunk_payload(compression, payload, f'{path.name} chunk {cx},{cz}')
        return parse_nbt(decoded)


def unpack_palette(values, palette_length: int, data_version: int, count: int = 4096):
    if palette_length < 2:
        return [0] * count
    if not values:
        raise WorldFormatError('Palette has multiple states but no block data')
    if data_version >= 2529:
        # Minecraft palette encodings evolve. The array length tells us the
        # stored bit width without guessing from level.dat or hardcoding
        # old four-bit minimums. A section contains exactly 4096 indices.
        bits = next((
            b for b in range(max(1, (palette_length - 1).bit_length()), 17)
            if len(values) == (count + (64 // b) - 1) // (64 // b)
        ), None)
        if bits is None:
            raise WorldFormatError('Invalid paletted block-array length for this section')
    else:
        bits = max(4, (palette_length - 1).bit_length())
    mask = (1 << bits) - 1
    unsigned = [value & 0xFFFFFFFFFFFFFFFF for value in values]
    result = []
    if data_version >= 2529:
        per_long = 64 // bits
        for i in range(count):
            n = i // per_long
            if n >= len(unsigned):
                raise WorldFormatError('Short palette data')
            result.append((unsigned[n] >> ((i % per_long) * bits)) & mask)
    else:
        for i in range(count):
            start = i * bits
            j, shift = divmod(start, 64)
            if j >= len(unsigned):
                raise WorldFormatError('Short palette data')
            v = unsigned[j] >> shift
            if shift + bits > 64:
                if j + 1 >= len(unsigned):
                    raise WorldFormatError('Short palette data')
                v |= unsigned[j + 1] << (64 - shift)
            result.append(v & mask)
    if any(idx >= palette_length for idx in result):
        raise WorldFormatError('Invalid block palette index')
    return result


def block_name(state):
    """Minecraft 1.18+ and newer block-state identifiers, including 26.3."""
    if isinstance(state, str) and state:
        return state
    if isinstance(state, dict):
        name = state.get('Name') or state.get('id') or state.get('')
        if isinstance(name, str) and name:
            return name
    raise WorldFormatError('Unknown block-state palette entry; refusing to render it as air')


def block_properties(state):
    if not isinstance(state, dict):
        return {}
    properties = state.get('Properties')
    if properties is None:
        properties = state.get('properties')
    return properties if isinstance(properties, dict) else {}


def iterate_blocks(chunk, cx: int, cz: int, version: int, bounds):
    x_min, x_max, y_min, y_max, z_min, z_max = bounds
    sections = chunk.get('sections') or chunk.get('Sections') or chunk.get('Level', {}).get('Sections', [])
    for section in sections:
        sy = int(section.get('Y', 0))
        by = sy * 16
        if by + 15 < y_min or by > y_max:
            continue
        states = section.get('block_states') or section
        palette = states.get('palette') or states.get('Palette') or []
        if not palette:
            continue
        indexes = unpack_palette(states.get('data') or states.get('BlockStates') or [], len(palette), int(chunk.get('DataVersion', version)))
        for index, palette_index in enumerate(indexes):
            state = palette[palette_index]
            name = block_name(state)
            if name.endswith(':air') or name in ('minecraft:cave_air', 'minecraft:void_air'):
                continue
            y = by + ((index >> 8) & 15)
            z = cz * 16 + ((index >> 4) & 15)
            x = cx * 16 + (index & 15)
            if x_min <= x <= x_max and y_min <= y <= y_max and z_min <= z <= z_max:
                yield (x, y, z), state


def entity_records(record):
    if not record:
        return []
    if 'Entities' in record:
        return record['Entities']
    return record.get('Level', {}).get('Entities', [])
