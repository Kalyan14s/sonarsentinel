"""ST-054 merge/dedupe and the rule-based detector; TC-DET-006 (object in a 4-tile overlap)."""

import numpy as np
import pytest

cv2 = pytest.importorskip("cv2")

from sonarsentinel.detect.base import RawDetection, describe  # noqa: E402
from sonarsentinel.detect.classical import BrightTargetDetector  # noqa: E402
from sonarsentinel.detect.merge import (  # noqa: E402
    box_ios,
    box_iou,
    dedupe_across_chunks,
    merge_detections,
    tiles_to_image,
    to_survey,
)
from sonarsentinel.preprocess.tiling import extract_tile, tile_grid  # noqa: E402


def _seabed(shape: tuple[int, int], seed: int = 0) -> np.ndarray:
    rng = np.random.default_rng(seed)
    return np.clip(rng.normal(110, 15, shape), 0, 255).astype(np.uint8)


def test_box_overlaps() -> None:
    assert box_iou((0, 0, 10, 10), (5, 0, 15, 10)) == pytest.approx(50 / 150)
    assert box_ios((0, 0, 10, 10), (2, 2, 4, 4)) == 1.0
    assert box_iou((0, 0, 1, 1), (2, 2, 3, 3)) == 0.0


def test_detector_finds_bright_targets_only() -> None:
    image = _seabed((640, 640))
    image[100:110, 200:215] = 250
    image[400:402, 400:402] = 255  # 4 px speckle-sized spot: ignored
    (dets,) = BrightTargetDetector().predict([np.dstack([image] * 3)])
    assert len(dets) == 1
    det = dets[0]
    assert det.box == (200, 100, 215, 110) and det.cls == "debris_other"
    assert det.mask is not None and det.mask.all() and 0.2 <= det.score <= 0.6
    assert describe(BrightTargetDetector()) == "classical-bright-target@0.1.0"


def test_object_in_four_tile_overlap_is_detected_once() -> None:
    """TC-DET-006."""
    image = _seabed((1200, 1200), seed=1)
    image[500:520, 505:530] = 250  # inside tiles starting at 0 and 480 on both axes
    image[300:320, 630:652] = 250  # crosses the right edge of the first tile column
    three = np.dstack([image] * 3)
    tiles = tile_grid(1200, 1200, 640, 0.25)
    per_tile = BrightTargetDetector().predict([extract_tile(three, t) for t in tiles])
    raw = tiles_to_image(per_tile, tiles, image.shape)
    assert len(raw) >= 5  # seen in several tiles
    merged = merge_detections(raw)
    assert [d.box for d in merged] == [(630, 300, 652, 320), (505, 500, 530, 520)]
    assert all(d.mask is not None and d.mask.sum() == d.area for d in merged)


def test_merge_keeps_classes_apart_and_best_score() -> None:
    a = RawDetection("pipe", 0.4, (0, 0, 10, 10))
    b = RawDetection("pipe", 0.9, (2, 0, 12, 10))
    c = RawDetection("cylinder", 0.8, (0, 0, 10, 10))
    merged = merge_detections([a, b, c])
    assert sorted((d.cls, d.score, d.box) for d in merged) == [
        ("cylinder", 0.8, (0, 0, 10, 10)),
        ("pipe", 0.9, (0, 0, 12, 10)),
    ]


def test_dedupe_keeps_copy_farther_from_chunk_edge() -> None:
    rows = np.arange(2000, dtype=np.int64)
    det = RawDetection("debris_other", 0.5, (1010, 1850, 1030, 1870))
    in_first = to_survey(
        det,
        row_to_ping=rows,
        nadir_col=1000,
        ground_res_m=0.1,
        chunk_id=0,
        chunk_ping_range=(0, 1999),
    )
    second_rows = np.arange(1800, 3800, dtype=np.int64)
    det2 = RawDetection("debris_other", 0.45, (1011, 50, 1031, 70))
    in_second = to_survey(
        det2,
        row_to_ping=second_rows,
        nadir_col=1000,
        ground_res_m=0.1,
        chunk_id=1,
        chunk_ping_range=(1800, 3799),
    )
    far = RawDetection("debris_other", 0.5, (1500, 900, 1520, 920))
    other = to_survey(
        far,
        row_to_ping=rows,
        nadir_col=1000,
        ground_res_m=0.1,
        chunk_id=0,
        chunk_ping_range=(0, 1999),
    )
    kept = dedupe_across_chunks([in_first, in_second, other])
    assert len(kept) == 2
    # first chunk: centre 139.5 pings from its end; second chunk: 59.5 pings from its start
    assert in_first in kept and in_second not in kept
    assert in_first.across_start_m == pytest.approx(1.0)
