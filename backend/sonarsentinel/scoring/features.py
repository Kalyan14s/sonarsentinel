"""Shape, texture and context features per detection (ST-061).

Feature groups follow ``docs/architecture/03-ml-models.md`` §5 (model, shadow, geometry,
edges/lines, texture, context, quality). Missing values are ``nan`` so the LightGBM false-positive
filter (ST-062) can handle them. Crops larger than ``MAX_PATCH_PX`` are shrunk before texture and
frequency measures to keep the cost per detection below 5 ms.
"""

from __future__ import annotations

import math

import numpy as np
import numpy.typing as npt

from sonarsentinel.scoring.shadow import ShadowResult

CLASSES = ("shipwreck", "pipe", "cylinder", "ghost_net", "debris_other", "unknown_anomaly")
MAX_PATCH_PX = 128
CONTEXT_PX = 16

FEATURE_NAMES: tuple[str, ...] = (
    "detector_score",
    *(f"class_{c}" for c in CLASSES),
    "anomaly_mean",
    "anomaly_max",
    "highlight_contrast",
    "shadow_darkness",
    "shadow_coverage",
    "shadow_length_m",
    "height_m",
    "length_m",
    "width_m",
    "area_m2",
    "aspect_ratio",
    "solidity",
    "extent",
    "orientation_rel_track_deg",
    "hough_line_count",
    "longest_line_ratio",
    "right_angle_corners",
    "glcm_contrast",
    "glcm_homogeneity",
    "glcm_energy",
    "fft_peak_ratio",
    "local_std_mean",
    "ring_contrast",
    "ring_texture_similarity",
    "ripple_fft_peak",
    "dropout_fraction",
    "motion_flag",
    "near_nadir_flag",
    "ground_range_m",
)

NAN = float("nan")


def _shrink(patch: npt.NDArray[np.uint8]) -> npt.NDArray[np.uint8]:
    import cv2

    h, w = patch.shape
    scale = MAX_PATCH_PX / max(h, w)
    if scale >= 1.0:
        return patch
    size = (max(1, round(w * scale)), max(1, round(h * scale)))
    return np.asarray(cv2.resize(patch, size, interpolation=cv2.INTER_AREA), dtype=np.uint8)


def glcm_stats(patch: npt.NDArray[np.uint8], levels: int = 8) -> tuple[float, float, float]:
    """Contrast, homogeneity and energy of the symmetric horizontal co-occurrence matrix."""
    if patch.shape[1] < 2:
        return NAN, NAN, NAN
    q = patch.astype(np.int64) * levels // 256
    pairs = q[:, :-1].ravel() * levels + q[:, 1:].ravel()
    counts = np.bincount(pairs, minlength=levels * levels).reshape(levels, levels).astype(float)
    counts += counts.T
    p = counts / counts.sum()
    i, j = np.indices(p.shape)
    return (
        float((p * (i - j) ** 2).sum()),
        float((p / (1.0 + np.abs(i - j))).sum()),
        float(np.sqrt((p**2).sum())),
    )


def fft_peak_ratio(patch: npt.NDArray[np.uint8]) -> float:
    """Strongest non-DC spatial frequency relative to the mean magnitude (periodicity)."""
    if min(patch.shape) < 8:
        return NAN
    values = patch.astype(np.float32)
    spectrum = np.abs(np.fft.rfft2(values - values.mean()))
    spectrum[0, 0] = 0.0
    mean = float(spectrum.mean())
    return float(spectrum.max() / mean) if mean > 0 else 0.0


def _edges_and_corners(
    patch: npt.NDArray[np.uint8], mask: npt.NDArray[np.bool_]
) -> tuple[float, float, float, float]:
    """Hough line count, longest line / patch diagonal, right-angle corners, solidity."""
    import cv2

    edges = cv2.Canny(patch, 50, 150)
    min_len = max(5, int(0.3 * min(patch.shape)))
    lines = cv2.HoughLinesP(
        edges, 1, np.pi / 180, threshold=15, minLineLength=min_len, maxLineGap=2
    )
    diagonal = math.hypot(*patch.shape)
    if lines is None:
        count, longest = 0.0, 0.0
    else:
        seg = lines.reshape(-1, 4).astype(float)
        lengths = np.hypot(seg[:, 2] - seg[:, 0], seg[:, 3] - seg[:, 1])
        count, longest = float(len(seg)), float(lengths.max() / diagonal)

    contours, _ = cv2.findContours(
        mask.astype(np.uint8), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE
    )
    if not contours:
        return count, longest, 0.0, NAN
    contour = max(contours, key=cv2.contourArea)
    hull_area = float(cv2.contourArea(cv2.convexHull(contour)))
    solidity = min(float(mask.sum()) / hull_area, 1.0) if hull_area > 0 else 1.0
    approx = cv2.approxPolyDP(contour, 0.02 * cv2.arcLength(contour, True), True).reshape(-1, 2)
    corners = 0
    n = len(approx)
    for k in range(n if n >= 3 else 0):
        v1 = (approx[k - 1] - approx[k]).astype(float)
        v2 = (approx[(k + 1) % n] - approx[k]).astype(float)
        norm = float(np.linalg.norm(v1) * np.linalg.norm(v2))
        if norm == 0:
            continue
        angle = math.degrees(math.acos(float(np.clip(np.dot(v1, v2) / norm, -1.0, 1.0))))
        corners += abs(angle - 90.0) <= 15.0
    return count, longest, float(corners), solidity


def detection_features(
    image: npt.NDArray[np.uint8],
    mask: npt.NDArray[np.bool_],
    box: tuple[int, int, int, int],
    *,
    cls: str,
    detector_score: float,
    shadow: ShadowResult,
    length_m: float,
    width_m: float,
    area_m2: float,
    orientation_deg: float | None = None,
    heading_deg: float | None = None,
    anomaly_mean: float | None = None,
    anomaly_max: float | None = None,
    texture: npt.NDArray[np.uint8] | None = None,
    dropout_fraction: float = 0.0,
    motion: bool = False,
    near_nadir: bool = False,
    ground_range_m: float | None = None,
) -> dict[str, float]:
    """Feature vector for one detection, keyed by :data:`FEATURE_NAMES`.

    Args:
        image: Ground-range grey image (uint8).
        mask: Object mask with the shape of ``box``.
        box: ``(x1, y1, x2, y2)`` in image pixels, end-exclusive.
        texture: Local standard-deviation channel of the same image, if available.
    """
    x1, y1, x2, y2 = box
    height, width = image.shape
    patch = image[y1:y2, x1:x2]
    obj = patch[mask]
    f: dict[str, float] = dict.fromkeys(FEATURE_NAMES, NAN)

    f["detector_score"] = float(detector_score)
    for c in CLASSES:
        f[f"class_{c}"] = float(cls == c)
    f["anomaly_mean"] = NAN if anomaly_mean is None else float(anomaly_mean)
    f["anomaly_max"] = NAN if anomaly_max is None else float(anomaly_max)

    f["highlight_contrast"] = shadow.contrast
    f["shadow_darkness"] = shadow.darkness
    f["shadow_coverage"] = shadow.coverage
    f["shadow_length_m"] = NAN if shadow.shadow_length_m is None else shadow.shadow_length_m
    f["height_m"] = NAN if shadow.height_m is None else shadow.height_m

    f["length_m"], f["width_m"], f["area_m2"] = float(length_m), float(width_m), float(area_m2)
    f["aspect_ratio"] = float(length_m / width_m) if width_m > 0 else NAN
    f["extent"] = float(mask.sum()) / max(mask.size, 1)
    if orientation_deg is not None and heading_deg is not None and math.isfinite(heading_deg):
        rel = (orientation_deg - heading_deg) % 180.0
        f["orientation_rel_track_deg"] = min(rel, 180.0 - rel)

    small = _shrink(patch)
    small_mask = mask
    if small.shape != patch.shape:
        import cv2

        small_mask = cv2.resize(
            mask.astype(np.uint8), small.shape[::-1], interpolation=cv2.INTER_NEAREST
        ).astype(bool)
    lines, longest, corners, solidity = _edges_and_corners(small, small_mask)
    f["hough_line_count"], f["longest_line_ratio"] = lines, longest
    f["right_angle_corners"], f["solidity"] = corners, solidity

    f["glcm_contrast"], f["glcm_homogeneity"], f["glcm_energy"] = glcm_stats(small)
    f["fft_peak_ratio"] = fft_peak_ratio(small)
    if obj.size:
        f["local_std_mean"] = (
            float(texture[y1:y2, x1:x2][mask].mean()) if texture is not None else float(obj.std())
        )

    cy1, cy2 = max(0, y1 - CONTEXT_PX), min(height, y2 + CONTEXT_PX)
    cx1, cx2 = max(0, x1 - CONTEXT_PX), min(width, x2 + CONTEXT_PX)
    window = image[cy1:cy2, cx1:cx2]
    ring = np.ones(window.shape, dtype=bool)
    ring[y1 - cy1 : y2 - cy1, x1 - cx1 : x2 - cx1] &= ~mask
    ring_values = window[ring].astype(np.float32)
    if obj.size and ring_values.size:
        ring_mean = max(float(ring_values.mean()), 1.0)
        f["ring_contrast"] = (float(obj.mean()) - ring_mean) / ring_mean
        obj_std, ring_std = float(obj.std()), float(ring_values.std())
        f["ring_texture_similarity"] = 1.0 - abs(obj_std - ring_std) / max(obj_std, ring_std, 1.0)
    f["ripple_fft_peak"] = fft_peak_ratio(_shrink(window))

    f["dropout_fraction"] = float(dropout_fraction)
    f["motion_flag"] = float(motion)
    f["near_nadir_flag"] = float(near_nadir)
    f["ground_range_m"] = NAN if ground_range_m is None else float(ground_range_m)
    return f


def feature_vector(features: dict[str, float]) -> list[float]:
    """Values in :data:`FEATURE_NAMES` order."""
    return [features[name] for name in FEATURE_NAMES]
