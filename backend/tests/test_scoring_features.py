"""ST-061 shape/texture features: complete, deterministic, under 5 ms per detection."""

import math
import time

import numpy as np
import pytest

cv2 = pytest.importorskip("cv2")

from sonarsentinel.scoring.features import (  # noqa: E402
    FEATURE_NAMES,
    detection_features,
    feature_vector,
    glcm_stats,
)
from sonarsentinel.scoring.shadow import shadow_score  # noqa: E402


def _scene() -> tuple[np.ndarray, tuple[int, int, int, int], np.ndarray]:
    rng = np.random.default_rng(0)
    image = np.clip(rng.normal(100, 10, (500, 800)), 1, 255).astype(np.uint8)
    image[200:240, 520:580] = 210
    image[200:240, 580:600] = 20
    return image, (520, 200, 580, 240), np.ones((40, 60), dtype=bool)


def _features(image: np.ndarray, box: tuple[int, int, int, int], mask: np.ndarray) -> dict:
    shadow = shadow_score(image, mask, box, nadir_col=400, ground_res_m=0.1, altitude_m=8.0)
    return detection_features(
        image,
        mask,
        box,
        cls="cylinder",
        detector_score=0.8,
        shadow=shadow,
        length_m=6.0,
        width_m=4.0,
        area_m2=24.0,
        orientation_deg=90.0,
        heading_deg=10.0,
        anomaly_mean=0.4,
        anomaly_max=0.9,
        dropout_fraction=0.1,
        motion=True,
        near_nadir=False,
        ground_range_m=15.0,
    )


def test_all_features_present_and_deterministic() -> None:
    image, box, mask = _scene()
    first = _features(image, box, mask)
    assert tuple(first) == FEATURE_NAMES
    assert len(FEATURE_NAMES) >= 25
    second = _features(image, box, mask)
    assert feature_vector(first) == pytest.approx(feature_vector(second), nan_ok=True)
    assert first["class_cylinder"] == 1.0 and first["class_pipe"] == 0.0
    assert first["aspect_ratio"] == pytest.approx(1.5)
    assert first["orientation_rel_track_deg"] == pytest.approx(80.0)
    assert first["motion_flag"] == 1.0 and first["highlight_contrast"] > 0.5
    assert first["solidity"] == pytest.approx(1.0, abs=0.05)
    assert first["right_angle_corners"] >= 3


def test_under_five_ms_per_detection() -> None:
    image, box, mask = _scene()
    _features(image, box, mask)  # warm up OpenCV
    durations = []
    for _ in range(20):
        start = time.perf_counter()
        _features(image, box, mask)
        durations.append(time.perf_counter() - start)
    assert float(np.median(durations)) < 0.005


def test_large_object_is_shrunk_and_missing_values_are_nan() -> None:
    rng = np.random.default_rng(1)
    image = np.clip(rng.normal(100, 10, (900, 900)), 1, 255).astype(np.uint8)
    box = (100, 100, 700, 700)
    mask = np.ones((600, 600), dtype=bool)
    shadow = shadow_score(image, mask, box, nadir_col=0, ground_res_m=0.1, altitude_m=None)
    f = detection_features(
        image,
        mask,
        box,
        cls="shipwreck",
        detector_score=0.5,
        shadow=shadow,
        length_m=60.0,
        width_m=0.0,
        area_m2=3600.0,
    )
    assert math.isnan(f["aspect_ratio"]) and math.isnan(f["anomaly_mean"])
    assert math.isnan(f["orientation_rel_track_deg"]) and math.isnan(f["ground_range_m"])


def test_glcm_uniform_patch() -> None:
    contrast, homogeneity, energy = glcm_stats(np.full((10, 10), 128, dtype=np.uint8))
    assert contrast == 0.0 and homogeneity == pytest.approx(1.0) and energy == pytest.approx(1.0)
