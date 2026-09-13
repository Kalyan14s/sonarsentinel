"""Dropout detection and repair (ST-043, stage S6).

A ping is a dropout when its row is flat (std below ``min_row_std_ratio`` × the median row std),
empty (mean < 1), an exact copy of the previous ping, or has invalid navigation. Gaps of at most
``max_inpaint_gap_pings`` are filled by interpolating between the neighbouring pings; longer gaps
are masked so no detections are made inside them. Work on one chunk at a time.
See ``docs/architecture/02-data-pipeline.md`` S6.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np
import numpy.typing as npt

from sonarsentinel.errors import ValidationError
from sonarsentinel.preprocess.motion import flag_segments

BoolArray = npt.NDArray[np.bool_]

DROPOUT = "DROPOUT"


def detect_dropouts(
    *channels: npt.NDArray[Any] | None,
    min_row_std_ratio: float = 0.05,
    invalid_nav: npt.ArrayLike | None = None,
) -> BoolArray:
    """Per-ping dropout flags from one or more ``(n_pings, n_samples)`` channels."""
    arrays = [np.asarray(c, dtype=np.float32) for c in channels if c is not None]
    if not arrays:
        raise ValidationError("At least one channel is needed to detect dropouts")
    rows = np.concatenate(arrays, axis=1)
    std = rows.std(axis=1)
    mean = rows.mean(axis=1)
    positive = std[std > 0]
    median_std = float(np.median(positive)) if positive.size else 0.0
    flags = (std < min_row_std_ratio * median_std) | (mean < 1.0)
    if len(rows) > 1:
        flags[1:] |= np.all(rows[1:] == rows[:-1], axis=1)
    if invalid_nav is not None:
        flags |= np.asarray(invalid_nav, dtype=bool)
    return np.asarray(flags, dtype=bool)


@dataclass
class DropoutRepair:
    """Channels after repair plus which pings were inpainted or masked."""

    port: npt.NDArray[Any] | None
    starboard: npt.NDArray[Any] | None
    inpainted: BoolArray
    masked: BoolArray


def repair_dropouts(
    port: npt.NDArray[Any] | None,
    starboard: npt.NDArray[Any] | None,
    dropout: npt.ArrayLike,
    *,
    max_gap: int = 3,
) -> DropoutRepair:
    """Inpaint short dropout gaps between valid neighbours; mask long gaps and gaps at the edges.

    Returns copies; the input arrays are not modified.
    """
    flags = np.asarray(dropout, dtype=bool)
    n = len(flags)
    inpainted = np.zeros(n, dtype=bool)
    masked = np.zeros(n, dtype=bool)
    outputs = [None if c is None else np.array(c, copy=True) for c in (port, starboard)]
    for start, end in flag_segments(flags):
        length = end - start + 1
        if length > max_gap or start == 0 or end == n - 1:
            masked[start : end + 1] = True
            continue
        inpainted[start : end + 1] = True
        weights = np.arange(1, length + 1, dtype=np.float64) / (length + 1)
        for out in outputs:
            if out is None:
                continue
            before = out[start - 1].astype(np.float64)
            after = out[end + 1].astype(np.float64)
            fill = before[None, :] * (1 - weights[:, None]) + after[None, :] * weights[:, None]
            if np.issubdtype(out.dtype, np.integer):
                fill = np.rint(fill)
            out[start : end + 1] = fill.astype(out.dtype)
    return DropoutRepair(outputs[0], outputs[1], inpainted, masked)
