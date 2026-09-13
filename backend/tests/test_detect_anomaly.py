"""ST-053 PatchCore: coreset, scoring, save/load and unknown_anomaly regions.

Uses a random-init backbone (no weight download); skipped without torch/torchvision (CI).
"""

import os
from pathlib import Path

import numpy as np
import pytest

os.environ.setdefault("KMP_DUPLICATE_LIB_OK", "TRUE")
torch = pytest.importorskip("torch")
pytest.importorskip("torchvision")
pytest.importorskip("cv2")

from sonarsentinel.detect.anomaly import PatchCoreModel, greedy_coreset  # noqa: E402
from sonarsentinel.errors import ModelsNotLoadedError  # noqa: E402


def _seafloor(rng: np.random.Generator, n: int, size: int = 64) -> list[np.ndarray]:
    return [
        np.clip(rng.normal(110, 12, (size, size, 3)), 0, 255).astype(np.uint8) for _ in range(n)
    ]


def test_greedy_coreset_covers_clusters() -> None:
    generator = torch.Generator().manual_seed(0)
    centres = torch.tensor([[0.0, 0.0], [10.0, 0.0], [0.0, 10.0]])
    points = torch.cat([c + 0.1 * torch.randn(50, 2, generator=generator) for c in centres])
    idx = greedy_coreset(points, 3, projection_dim=8)
    chosen = points[idx]
    nearest = torch.cdist(centres, chosen).min(dim=1).values
    assert torch.all(nearest < 1.0)  # one point from each cluster


def test_scores_higher_for_bright_object_and_regions(tmp_path: Path) -> None:
    rng = np.random.default_rng(0)
    model = PatchCoreModel(torch.zeros((1, 384)), input_px=64, pretrained=False, version="0.0.1")
    feats = model.patch_features(_seafloor(rng, 12))
    model.memory_bank = feats[greedy_coreset(feats, 200)]
    normal = model.score(_seafloor(rng, 4))
    odd = _seafloor(rng, 1)[0]
    odd[20:40, 20:40] = 255
    anomalous = model.score([odd])
    assert anomalous.scores[0] > normal.scores.max()
    assert anomalous.heatmaps.shape == (1, 64, 64)

    model.threshold = float(normal.scores.max())
    model.pixel_threshold = float(np.percentile(normal.heatmaps, 99.9))
    regions = model.regions(anomalous.heatmaps[0], tile_px=64, min_area_px=4)
    assert regions and regions[0].cls == "unknown_anomaly"
    x1, y1, x2, y2 = regions[0].box
    assert x1 <= 30 <= x2 and y1 <= 30 <= y2
    assert (
        model.regions(anomalous.heatmaps[0], 64, min_area_px=4, exclude_boxes=[regions[0].box])
        == []
    )

    model.save(tmp_path / "pc")
    loaded = PatchCoreModel.load(tmp_path / "pc")
    assert loaded.model_version == "patchcore-seafloor@0.0.1" and loaded.input_px == 64
    with pytest.raises(ModelsNotLoadedError):
        PatchCoreModel.load(tmp_path / "missing")
