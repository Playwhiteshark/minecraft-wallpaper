"""Regression for blank terrain with non-square texture counts.

The WebGL viewer uses an 8x8 atlas for 31 textures, but only four rows are
populated. An upload-wide vertical flip makes the shader read transparent
padding for every block. These checks intentionally tie the sampling contract
to the code used by the wallpaper.
"""
import math
from pathlib import Path

VIEWER = (Path(__file__).resolve().parents[1] / 'web' / 'viewer.js').read_text(encoding='utf-8')


def _atlas_cols(count):
    return 1 << (math.ceil(math.log2(math.ceil(math.sqrt(count)))))


def _sample_pixel(index, uv_x, uv_y, cols):
    # Same texel-centre mapping as the GLSL terrain vertex shader.
    tile_x, tile_y = index % cols, index // cols
    x = tile_x * 36 + 2.5 + uv_x * 31
    y = tile_y * 36 + 2.5 + (1 - uv_y) * 31
    return x, y


def test_viewer_atlas_orientation_contract():
    assert 'gl.pixelStorei(gl.UNPACK_FLIP_Y_WEBGL,false);' in VIEWER
    assert 'vUv=(tile*36.+vec2(2.5+uv.x*31.,2.5+(1.-uv.y)*31.))/(36.*uCols);' in VIEWER


def test_all_tiles_sample_populated_pixels_for_31_textures():
    # Includes every row of the incomplete, power-of-two square atlas.
    for count in (1, 4, 5, 16, 17, 31, 32, 33, 63):
        cols = _atlas_cols(count)
        for index in range(count):
            tile_x, tile_y = index % cols, index // cols
            for u, v in ((0, 0), (1, 1), (0.5, 0.5)):
                x, y = _sample_pixel(index, u, v, cols)
                assert tile_x * 36 + 2 <= x < tile_x * 36 + 34
                assert tile_y * 36 + 2 <= y < tile_y * 36 + 34
                assert 0 <= x < cols * 36
                assert 0 <= y < cols * 36


def test_31_textures_were_blank_when_flipped():
    cols = _atlas_cols(31)
    assert cols == 8
    # With the old full-atlas flip, all four populated rows were sampled from
    # the EMPTY bottom half (rows 4-7). That's why pets rendered and blocks did not.
    for index in range(31):
        _, y = _sample_pixel(index, 0.5, 0.5, cols)
        old_canvas_y = cols * 36 - y
        assert old_canvas_y >= 4 * 36
