"""The distant landscape must follow real saved blocks, not unreliable heightmaps."""
import base64
import struct

from mww import landscape


def _packed_top_layer(section_y=5, local_y=0):
    # Padded 4-bit state IDs: one non-air grass layer, all other heights air.
    longs = []
    for i in range(0, 4096, 16):
        packed = 0
        for j in range(16):
            idx = i + j
            if ((idx >> 8) & 15) == local_y:
                packed |= 1 << (j * 4)
        longs.append(packed if packed < 2**63 else packed - 2**64)
    return {'Y': section_y, 'block_states': {
        'palette': [{'Name': 'minecraft:air'}, 'minecraft:grass_block'],
        'data': longs,
    }}


def _chunk():
    return {
        'yPos': -4,
        'DataVersion': 4000,
        # The heightmap deliberately disagrees with the real top of Y=80.
        'Heightmaps': {'WORLD_SURFACE': [1] * 37},
        'sections': [_packed_top_layer(5, 0),
                     {'Y': 0, 'block_states': {'palette': ['minecraft:stone']}}],
    }


def test_surface_columns_ignore_corrupt_heightmap_and_empty_sections():
    chunk = _chunk()
    result = landscape.surface_columns(chunk, {(0, 0), (4, 12), (15, 15)})
    assert result == {(0, 0): (80, 'minecraft:grass_block'),
                      (4, 12): (80, 'minecraft:grass_block'),
                      (15, 15): (80, 'minecraft:grass_block')}


def test_surface_columns_fall_back_to_lower_block_when_top_is_air():
    chunk = _chunk()
    top = chunk['sections'][0]['block_states']
    top['palette'] = ['minecraft:air']
    top.pop('data')
    assert landscape.surface_columns(chunk, {(3, 9)}) == {
        (3, 9): (15, 'minecraft:stone')}


def test_complete_saved_ring_can_join_near_geometry(monkeypatch, tmp_path):
    chunk = _chunk()

    class FakeReader:
        def __init__(self, path): pass
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def chunk(self, cx, cz): return chunk

    monkeypatch.setattr(landscape, 'RegionReader', FakeReader)
    result = landscape.build_landscape(tmp_path, [0, 70, 0], 8, radius=32, step=8,
                                       color_for=lambda block: (40, 120, 60))
    assert result['joinable'] is True
    assert result['source'] == 'saved-block-columns'
    assert result['present'] > 0
    sample = base64.b64decode(result['samples'])
    values = [struct.unpack_from('<hBBB', sample, i) for i in range(0, len(sample), 5)]
    assert (10, 40, 120, 60) in values
    assert (-55, 40, 120, 60) not in values


def test_missing_chunks_remain_missing_not_flat_ground(monkeypatch, tmp_path):
    chunk = _chunk()

    class FakeReader:
        def __init__(self, path): pass
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def chunk(self, cx, cz): return chunk if cx == cz == 0 else None

    monkeypatch.setattr(landscape, 'RegionReader', FakeReader)
    result = landscape.build_landscape(tmp_path, [0, 70, 0], 8, radius=32, step=8)
    assert result['version'] == 1
    assert result['size'] == 9
    assert result['joinable'] is False
    assert 0 < result['present'] < result['size'] ** 2
    records = [struct.unpack_from('<hBBB', base64.b64decode(result['samples']), i)
               for i in range(0, result['size'] ** 2 * 5, 5)]
    assert (-32768, 0, 0, 0) in records
    assert (10, 112, 149, 115) in records
    assert landscape.build_landscape(tmp_path, [0, 70, 0], 8, radius=0) is None
