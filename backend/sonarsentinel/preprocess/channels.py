"""Three-channel model input (ST-045, stage S7): raw | Lee despeckled | local standard deviation.

This is the **only** implementation: training (``ml/``) and inference both import
:func:`to_three_channel` from here so their inputs can't drift apart (TC-PRE-007).
See ``docs/architecture/02-data-pipeline.md`` S7.
"""

from __future__ import annotations

from typing import Any

import numpy as np
import numpy.typing as npt

from sonarsentinel.errors import ValidationError

FloatArray = npt.NDArray[np.float64]


def _box_mean(x: FloatArray, window: int) -> FloatArray:
    from scipy.ndimage import uniform_filter

    return np.asarray(uniform_filter(x, size=window, mode="reflect"), dtype=np.float64)


def lee_filter(image: npt.ArrayLike, window: int = 5) -> FloatArray:
    """Lee speckle filter: blend local mean and pixel by local vs overall noise variance."""
    x = np.asarray(image, dtype=np.float64)
    mean = _box_mean(x, window)
    variance = np.maximum(_box_mean(x * x, window) - mean * mean, 0.0)
    noise = float(np.mean(variance))
    if noise <= 0:
        return mean
    weight = variance / (variance + noise)
    return mean + weight * (x - mean)


def local_std(image: npt.ArrayLike, window: int = 7) -> FloatArray:
    """Standard deviation in a ``window`` × ``window`` neighbourhood (texture)."""
    x = np.asarray(image, dtype=np.float64)
    mean = _box_mean(x, window)
    return np.sqrt(np.maximum(_box_mean(x * x, window) - mean * mean, 0.0))


def to_three_channel(
    image: npt.NDArray[Any], *, lee_window: int = 5, std_window: int = 7
) -> npt.NDArray[np.uint8]:
    """Stack ``(H, W)`` uint8 into ``(H, W, 3)`` uint8: raw, Lee-filtered, local std × 2."""
    img = np.asarray(image)
    if img.ndim != 2 or img.dtype != np.uint8:
        raise ValidationError(
            "to_three_channel expects a 2-D uint8 image", shape=img.shape, dtype=str(img.dtype)
        )
    despeckled = np.clip(np.rint(lee_filter(img, lee_window)), 0, 255)
    texture = np.clip(np.rint(local_std(img, std_window) * 2.0), 0, 255)  # std of uint8 ≤ 127.5
    return np.stack([img, despeckled.astype(np.uint8), texture.astype(np.uint8)], axis=-1)
