"""YOLO11-seg adapter: registry naming, polygon masks, and a smoke run with a random-init model.

Skipped when the ML dependencies (torch, ultralytics) aren't installed, e.g. in CI.
"""

from pathlib import Path

import numpy as np
import pytest

from sonarsentinel.errors import ModelsNotLoadedError

cv2 = pytest.importorskip("cv2")


def test_registry_version_and_polygon_mask() -> None:
    from sonarsentinel.detect.yolo import polygon_mask, registry_version

    assert registry_version(Path("models/detector/yolo11s-seg-sonar/0.1.0/best.pt")) == (
        "yolo11s-seg-sonar@0.1.0"
    )
    assert registry_version(Path("runs/exp/weights/best.pt")) == "best@0.0.0"
    mask = polygon_mask(np.array([[10, 10], [20, 10], [20, 20], [10, 20]]), (10, 10, 21, 21))
    assert mask.shape == (11, 11) and mask.sum() >= 100
    assert polygon_mask(np.array([[1, 1], [2, 2]]), (0, 0, 4, 4)).all()


def test_missing_weights_raise_models_not_loaded(tmp_path: Path) -> None:
    pytest.importorskip("ultralytics")
    from sonarsentinel.detect.yolo import YoloDetector

    with pytest.raises(ModelsNotLoadedError):
        YoloDetector(tmp_path / "missing.pt")


def test_predict_smoke_with_random_model() -> None:
    pytest.importorskip("torch")
    pytest.importorskip("ultralytics")
    from sonarsentinel.detect.yolo import YoloDetector

    detector = YoloDetector("yolo11n-seg.yaml", imgsz=160, conf=0.5)
    tiles = [np.random.default_rng(0).integers(0, 255, (160, 160, 3), dtype=np.uint8)] * 2
    out = detector.predict(tiles)
    assert len(out) == 2 and all(isinstance(t, list) for t in out)
    assert detector.model_version == "yolo11n-seg@0.0.0"
    assert detector.predict([]) == []
