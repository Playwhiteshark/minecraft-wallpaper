"""One bounded, source-faithful landscape adapter regression."""
import base64
import struct

from mww import landscape


def _test_chunk(height=80, min_y=0, section_start=0, section_end=15):
    # Vanilla 256-block-height fixture, 9-bit padded heightmap; top at Y=80.
    bits = 9
    per_long = 64 // bits
    values = []
    for first in range(0, 256, per_long):
        packed = 0
        for j in range(min(per_long, 256 - first)):
            packed |= (height - min_y + 1) << (j * bits)
        values.append(packed if packed < 2**63 else packed - 2**64)
    sections = [{'Y': sy, 'block_states': {'palette': [{'Name': 'minecraft:grass_block'}]}}
                for sy in range(section_start, section_end+1)]
    return {'yPos': min_y // 16, 'sections': sections, 'Heightmaps': {'WORLD_SURFACE': values}, 'DataVersion': 4000}


def test_padded_heightmap_decoding():
    chunk = _test_chunk()
    heights = landscape._surface_heights(chunk)
    assert len(heights) == 256
    assert set(heights) == {80}
    assert landscape._top_block(chunk, 4, 80, 12) == 'minecraft:grass_block'



def test_heightmaps_use_chunk_min_y_even_when_empty_sections_are_omitted():
    # A modern overworld chunk has a base of -64, but may store only its
    # occupied Y=80 section. The heightmap is still relative to -64.
    chunk = _test_chunk(height=80, min_y=-64, section_start=5, section_end=5)
    assert set(landscape._surface_heights(chunk)) == {80}
    assert landscape._top_block(chunk, 2, 80, 7) == 'minecraft:grass_block'


def test_complete_saved_ring_can_join_to_detailed_geometry(monkeypatch, tmp_path):
    chunk = _test_chunk(height=80, min_y=-64, section_start=5, section_end=5)

    class FakeReader:
        def __init__(self, path): pass
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def chunk(self, cx, cz): return chunk

    monkeypatch.setattr(landscape, 'RegionReader', FakeReader)
    result = landscape.build_landscape(tmp_path, [0, 70, 0], 8, radius=32, step=8)
    assert result['joinable'] is True
    assert result['present'] > 0
    sample = base64.b64decode(result['samples'])
    values = [struct.unpack_from('<hBBB', sample, i) for i in range(0, len(sample), 5)]
    assert (10, 112, 149, 115) in values

def test_bounded_landscape_does_not_fill_missing_chunks(monkeypatch, tmp_path):
    chunk = _test_chunk()

    class FakeReader:
        def __init__(self, path): pass
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def chunk(self, cx, cz): return chunk if cx == cz == 0 else None

    monkeypatch.setattr(landscape, 'RegionReader', FakeReader)
    result = landscape.build_landscape(tmp_path, [0, 70, 0], 8, radius=32, step=8,
                                       color_for=lambda block: (40, 120, 60))
    assert result['version'] == 1
    assert result['size'] == 9
    assert result['joinable'] is False
    assert 0 < result['present'] < result['size'] ** 2
    data = base64.b64decode(result['samples'])
    assert len(data) == result['size'] ** 2 * 5
    records = [struct.unpack_from('<hBBB', data, offset) for offset in range(0, len(data), 5)]
    assert (-32768, 0, 0, 0) in records
    assert (10, 40, 120, 60) in records
    assert landscape.build_landscape(tmp_path, [0, 70, 0], 8, radius=0) is None
