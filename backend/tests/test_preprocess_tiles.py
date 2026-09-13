"""TC-PRE-007 (3-channel input) and TC-PRE-010 (tiling round trip): ST-045 and ST-046."""

import numpy as np
import pytest

pytest.importorskip("scipy")

from sonarsentinel.errors import ValidationError  # noqa: E402
from sonarsentinel.preprocess.channels import lee_filter, local_std, to_three_channel  # noqa: E402
from sonarsentinel.preprocess.tiling import (  # noqa: E402
    extract_tile,
    iter_tiles,
    row_col_mask,
    tile_grid,
    tile_starts,
)


def test_three_channel_contract() -> None:
    """TC-PRE-007: shape (H, W, 3), uint8, raw channel unchanged."""
    rng = np.random.default_rng(0)
    img = rng.integers(0, 256, (64, 80), dtype=np.uint8)
    out = to_three_channel(img)
    assert out.shape == (64, 80, 3) and out.dtype == np.uint8
    assert np.array_equal(out[..., 0], img)
    assert out[..., 1].std() < img.std()  # despeckled is smoother
    with pytest.raises(ValidationError):
        to_three_channel(img.astype(np.float32))
    with pytest.raises(ValidationError):
        to_three_channel(np.zeros((4, 4, 3), np.uint8))


def test_training_and_inference_share_the_function() -> None:
    """TC-PRE-007: the ML dataset tooling imports the backend implementation, not a copy."""
    import importlib.util
    from pathlib import Path

    script = Path(__file__).resolve().parents[2] / "ml" / "datasets" / "xtf_to_tiles.py"
    source = script.read_text(encoding="utf-8")
    assert "from sonarsentinel.preprocess.channels import to_three_channel" in source
    assert "def to_three_channel" not in source
    assert importlib.util.find_spec("sonarsentinel.preprocess.channels") is not None


def test_filters_on_constant_image() -> None:
    img = np.full((10, 10), 7.0)
    assert np.allclose(lee_filter(img), 7.0)
    assert np.allclose(local_std(img), 0.0)


def test_tile_starts_cover_the_axis() -> None:
    assert tile_starts(640, 640, 0.25) == [0]
    assert tile_starts(100, 640, 0.25) == [0]
    assert tile_starts(1500, 640, 0.25) == [0, 480, 860]
    with pytest.raises(ValidationError):
        tile_starts(100, 64, 1.0)


def test_tile_round_trip_is_exact() -> None:
    """TC-PRE-010: every chunk pixel maps to tile coordinates and back exactly."""
    height, width, size = 1500, 1300, 640
    tiles = tile_grid(height, width, size, 0.25)
    assert [(t.row, t.col) for t in tiles[:3]] == [(0, 0), (0, 480), (0, 660)]
    covered = np.zeros((height, width), dtype=bool)
    image = np.arange(height * width, dtype=np.int64).reshape(height, width)
    for tile in tiles:
        pixels = extract_tile(image, tile)
        y, x = 123, 456
        row, col = tile.to_chunk(y, x)
        assert tile.contains(row, col) and tile.from_chunk(row, col) == (y, x)
        assert pixels[y, x] == image[row, col]
        covered[tile.row : tile.row + size, tile.col : tile.col + size] = True
    assert covered.all()
    assert tiles[1].col - tiles[0].col == 480  # 25% overlap


def test_masked_tiles_are_skipped() -> None:
    image = np.ones((1280, 640), dtype=np.uint8)
    mask = row_col_mask(image.shape, rows=np.arange(1280) < 1100)
    kept = list(iter_tiles(image, mask=mask, size=640, overlap=0.0))
    assert [t.row for t, _ in kept] == [640]  # only the bottom tile is < 80% masked
    small = list(iter_tiles(np.ones((100, 100, 3), np.uint8), mask=np.zeros((100, 100), bool)))
    assert len(small) == 0  # 97.6% of the padded tile is outside the image
    padded = extract_tile(np.ones((100, 100, 3), np.uint8), tile_grid(100, 100)[0])
    assert padded.shape == (640, 640, 3) and padded.sum() == 100 * 100 * 3
