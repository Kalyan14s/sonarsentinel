"""Shadow consistency score and object height (ST-060, ADR-017 §1).

A raised object returns a bright highlight followed, further from the track, by an acoustic
shadow. In the ground-range image (columns across track, nadir at ``nadir_col``, starboard at
larger columns) a starboard object's shadow lies at larger columns and a port object's at smaller
ones. A dark patch without a highlight, the usual shadow-only false positive, scores 0.

Score = √(contrast · darkness) · min(1, coverage / 0.5), where

* ``contrast``: (mean object − ring background) / background, clipped to [0, 1];
* ``darkness``: (background − mean shadow) / background over the shadow runs, clipped to [0, 1];
* ``coverage``: fraction of object rows with a shadow run of at least 2 pixels.

Height from shadow length (``docs/architecture/04-geotagging-engine.md``): ``h = Ls·H / (r + Ls)``
with ``Ls`` the median shadow length, ``r`` the ground range to the object's far edge and ``H`` the
altitude. No height when fewer than 30% of rows have a shadow or the shadow runs off the window.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
import numpy.typing as npt

MIN_RUN_PX = 2


@dataclass(frozen=True)
class ShadowResult:
    score: float
    contrast: float
    darkness: float
    coverage: float
    shadow_length_m: float | None
    height_m: float | None
    band: tuple[int, int, int, int] | None  # shadow search area (x1, y1, x2, y2), end-exclusive


EMPTY = ShadowResult(0.0, 0.0, 0.0, 0.0, None, None, None)


def _dark_run(dark: npt.NDArray[np.bool_], max_gap: int) -> tuple[int, int]:
    """Start and length of the first dark run beginning within ``max_gap`` pixels.

    Single bright pixels inside the run (speckle) do not end it.
    """
    n = int(dark.size)
    start = next((i for i in range(min(max_gap + 1, n)) if dark[i]), -1)
    if start < 0:
        return 0, 0
    end = start
    while end < n:
        if dark[end]:
            end += 1
        elif end + 1 < n and dark[end + 1]:
            end += 2
        else:
            break
    return start, end - start


def shadow_score(
    image: npt.NDArray[np.uint8],
    mask: npt.NDArray[np.bool_],
    box: tuple[int, int, int, int],
    *,
    nadir_col: int,
    ground_res_m: float,
    altitude_m: float | None,
    ring_px: int = 6,
    max_shadow_m: float = 15.0,
    dark_ratio: float = 0.6,
    max_gap_px: int = 3,
) -> ShadowResult:
    """Shadow consistency for one detection.

    Args:
        image: Ground-range grey image of the chunk (uint8, 0 = no data).
        mask: Object mask with the shape of ``box``.
        box: ``(x1, y1, x2, y2)`` in image pixels, end-exclusive.
        nadir_col: Column of the track line.
        ground_res_m: Metres per pixel.
        altitude_m: Sensor altitude for the height estimate.
    """
    x1, y1, x2, y2 = box
    height, width = image.shape
    img = image.astype(np.float32)
    obj = img[y1:y2, x1:x2][mask]
    if obj.size == 0:
        return EMPTY
    starboard = (x1 + x2) / 2.0 >= nadir_col

    ry1, ry2 = max(0, y1 - ring_px), min(height, y2 + ring_px)
    rx1, rx2 = max(0, x1 - ring_px), min(width, x2 + ring_px)
    region = img[ry1:ry2, rx1:rx2]
    ring = np.ones(region.shape, dtype=bool)
    ring[y1 - ry1 : y2 - ry1, x1 - rx1 : x2 - rx1] &= ~mask
    if starboard:  # the far side holds the shadow, not background
        ring[:, x2 - rx1 :] = False
    else:
        ring[:, : x1 - rx1] = False
    ring_values = region[ring]
    ring_values = ring_values[ring_values > 0]
    if ring_values.size < 8:
        return EMPTY
    background = max(float(np.median(ring_values)), 1.0)
    contrast = float(np.clip((float(obj.mean()) - background) / background, 0.0, 1.0))

    max_px = max(1, round(max_shadow_m / ground_res_m))
    threshold = background * dark_ratio
    lengths: list[int] = []
    shadow_values: list[npt.NDArray[np.float32]] = []
    truncated = 0
    for r in np.flatnonzero(mask.any(axis=1)):
        cols = np.flatnonzero(mask[r]) + x1
        y = y1 + int(r)
        if starboard:
            edge = int(cols.max()) + 1
            segment = img[y, edge : min(width, edge + max_px + max_gap_px)]
        else:
            edge = int(cols.min())
            segment = img[y, max(0, edge - max_px - max_gap_px) : edge][::-1]
        start, length = _dark_run(segment < threshold, max_gap_px)
        lengths.append(length)
        if length >= MIN_RUN_PX:
            shadow_values.append(segment[start : start + length])
            truncated += start + length >= segment.size
    runs = np.asarray(lengths)
    coverage = float(np.mean(runs >= MIN_RUN_PX)) if runs.size else 0.0
    if not shadow_values:
        return ShadowResult(0.0, round(contrast, 4), 0.0, 0.0, None, None, None)

    darkness = float(
        np.clip((background - float(np.concatenate(shadow_values).mean())) / background, 0.0, 1.0)
    )
    length_px = float(np.median(runs[runs >= MIN_RUN_PX]))
    shadow_length_m = length_px * ground_res_m
    score = math.sqrt(contrast * darkness) * min(1.0, coverage / 0.5)

    height_m = None
    far_range_m = (x2 - nadir_col if starboard else nadir_col - x1) * ground_res_m
    usable = coverage >= 0.3 and truncated <= len(shadow_values) / 2
    if usable and altitude_m is not None and math.isfinite(altitude_m) and altitude_m > 0:
        height_m = round(
            shadow_length_m * altitude_m / (max(far_range_m, 0.0) + shadow_length_m), 2
        )

    band_len = round(length_px)
    band = (
        (x2, y1, min(width, x2 + band_len), y2)
        if starboard
        else (max(0, x1 - band_len), y1, x1, y2)
    )
    return ShadowResult(
        score=round(float(np.clip(score, 0.0, 1.0)), 4),
        contrast=round(contrast, 4),
        darkness=round(darkness, 4),
        coverage=round(coverage, 4),
        shadow_length_m=round(shadow_length_m, 2),
        height_m=height_m,
        band=band,
    )
