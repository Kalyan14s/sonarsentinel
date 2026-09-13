"""Merge and de-duplicate detections across tiles and chunks (ST-054, stage S11).

1. **Tiles → chunk:** shift tile detections into chunk coordinates, then greedily merge same-class
   detections that overlap (IoU ≥ ``iou`` or intersection-over-smaller ≥ ``ios``, which catches an
   object clipped at a tile edge). The merged detection keeps the best score and the union of the
   masks.
2. **Chunks → survey:** chunks are resampled independently, so detections are compared in survey
   coordinates (ping range × across-track metres). Of two overlapping same-class copies, the one
   whose centre is farther from its chunk's edge is kept.

See ``docs/architecture/02-data-pipeline.md`` S11.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field, replace
from typing import Any

import numpy as np
import numpy.typing as npt

from sonarsentinel.detect.base import RawDetection
from sonarsentinel.preprocess.tiling import Tile


def box_intersection(a: tuple[int, int, int, int], b: tuple[int, int, int, int]) -> int:
    w = min(a[2], b[2]) - max(a[0], b[0])
    h = min(a[3], b[3]) - max(a[1], b[1])
    return max(w, 0) * max(h, 0)


def _area(box: tuple[int, int, int, int]) -> int:
    return max(box[2] - box[0], 0) * max(box[3] - box[1], 0)


def box_iou(a: tuple[int, int, int, int], b: tuple[int, int, int, int]) -> float:
    inter = box_intersection(a, b)
    union = _area(a) + _area(b) - inter
    return inter / union if union else 0.0


def box_ios(a: tuple[int, int, int, int], b: tuple[int, int, int, int]) -> float:
    """Intersection over the smaller box."""
    smaller = min(_area(a), _area(b))
    return box_intersection(a, b) / smaller if smaller else 0.0


def _union(a: RawDetection, b: RawDetection) -> RawDetection:
    x1, y1 = min(a.box[0], b.box[0]), min(a.box[1], b.box[1])
    x2, y2 = max(a.box[2], b.box[2]), max(a.box[3], b.box[3])
    mask = np.zeros((y2 - y1, x2 - x1), dtype=bool)
    for det in (a, b):
        dx, dy = det.box[0] - x1, det.box[1] - y1
        mask[dy : dy + det.height, dx : dx + det.width] |= det.full_mask()
    best = a if a.score >= b.score else b
    return RawDetection(best.cls, best.score, (x1, y1, x2, y2), mask)


def merge_detections(
    detections: Sequence[RawDetection], *, iou: float = 0.5, ios: float = 0.7
) -> list[RawDetection]:
    """Greedy same-class merging, highest score first, repeated until nothing overlaps."""
    pending = sorted(detections, key=lambda d: (-d.score, d.box))
    merged: list[RawDetection] = []
    for det in pending:
        current = det
        changed = True
        while changed:
            changed = False
            for i, other in enumerate(merged):
                if other.cls != current.cls:
                    continue
                if box_iou(other.box, current.box) >= iou or box_ios(other.box, current.box) >= ios:
                    current = _union(other, current)
                    merged.pop(i)
                    changed = True
                    break
        merged.append(current)
    return sorted(merged, key=lambda d: (d.box[1], d.box[0], d.cls))


def tiles_to_image(
    per_tile: Sequence[Sequence[RawDetection]],
    tiles: Sequence[Tile],
    image_shape: tuple[int, int],
) -> list[RawDetection]:
    """Shift tile detections into image coordinates, clipping to the image (tiles may be padded)."""
    height, width = image_shape
    out = []
    for tile, dets in zip(tiles, per_tile, strict=True):
        for det in dets:
            shifted = det.shifted(tile.row, tile.col)
            x1, y1, x2, y2 = shifted.box
            cx1, cy1, cx2, cy2 = max(x1, 0), max(y1, 0), min(x2, width), min(y2, height)
            if cx2 <= cx1 or cy2 <= cy1:
                continue
            mask = shifted.full_mask()[cy1 - y1 : cy2 - y1, cx1 - x1 : cx2 - x1]
            if not mask.any():
                continue
            out.append(replace(shifted, box=(cx1, cy1, cx2, cy2), mask=mask))
    return out


@dataclass
class SurveyDetection:
    """A detection placed in survey coordinates, with whatever the pipeline attached to it."""

    detection: RawDetection
    chunk_id: int
    ping_start: int
    ping_end: int
    across_start_m: float  # signed: negative = port, positive = starboard
    across_end_m: float
    chunk_ping_start: int
    chunk_ping_end: int
    extra: dict[str, Any] = field(default_factory=dict)

    @property
    def center_ping(self) -> float:
        return (self.ping_start + self.ping_end) / 2

    @property
    def edge_margin(self) -> float:
        """Pings between the centre and the nearer chunk edge."""
        return min(self.center_ping - self.chunk_ping_start, self.chunk_ping_end - self.center_ping)


def to_survey(
    det: RawDetection,
    *,
    row_to_ping: npt.NDArray[np.int64],
    nadir_col: int,
    ground_res_m: float,
    chunk_id: int,
    chunk_ping_range: tuple[int, int],
    extra: dict[str, Any] | None = None,
) -> SurveyDetection:
    """Convert a chunk-image detection to survey coordinates (``row_to_ping`` is global)."""
    x1, y1, x2, y2 = det.box
    rows = np.clip([y1, y2 - 1], 0, len(row_to_ping) - 1)
    pings = row_to_ping[rows]
    return SurveyDetection(
        detection=det,
        chunk_id=chunk_id,
        ping_start=int(pings.min()),
        ping_end=int(pings.max()),
        across_start_m=(x1 - nadir_col) * ground_res_m,
        across_end_m=(x2 - nadir_col) * ground_res_m,
        chunk_ping_start=chunk_ping_range[0],
        chunk_ping_end=chunk_ping_range[1],
        extra=dict(extra or {}),
    )


def _survey_iou(a: SurveyDetection, b: SurveyDetection) -> float:
    ping_overlap = min(a.ping_end, b.ping_end) - max(a.ping_start, b.ping_start) + 1
    across_overlap = min(a.across_end_m, b.across_end_m) - max(a.across_start_m, b.across_start_m)
    if ping_overlap <= 0 or across_overlap <= 0:
        return 0.0
    area_a = (a.ping_end - a.ping_start + 1) * (a.across_end_m - a.across_start_m)
    area_b = (b.ping_end - b.ping_start + 1) * (b.across_end_m - b.across_start_m)
    inter = ping_overlap * across_overlap
    return float(inter / (area_a + area_b - inter))


def dedupe_across_chunks(
    detections: Sequence[SurveyDetection], *, iou: float = 0.3
) -> list[SurveyDetection]:
    """Remove copies of the same object seen in two overlapping chunks."""
    ordered = sorted(detections, key=lambda d: (-d.edge_margin, -d.detection.score, d.chunk_id))
    kept: list[SurveyDetection] = []
    for det in ordered:
        duplicate = any(
            other.chunk_id != det.chunk_id
            and other.detection.cls == det.detection.cls
            and _survey_iou(other, det) >= iou
            for other in kept
        )
        if not duplicate:
            kept.append(det)
    return sorted(kept, key=lambda d: (d.ping_start, d.across_start_m, d.detection.cls))
