"""Score fusion, isotonic calibration and the false-positive filter at run time (ST-062…065).

``docs/architecture/03-ml-models.md`` §5 and ADR-017:

* ``fused = Σ wᵢ·sᵢ / Σ wᵢ`` over the components present (detector, anomaly, shadow, fp_filter,
  persistence), minus the dropout and motion penalties, clipped to [0, 1];
* ``confidence = 100 × calibrator(fused)``;
* the calibrator is isotonic regression (pool-adjacent-violators) stored as JSON breakpoints and
  applied by linear interpolation, so no scikit-learn or pickle is needed at run time;
* the FP filter is a LightGBM text model, used only when ``lightgbm`` is installed.
"""

from __future__ import annotations

import importlib.util
import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np

COMPONENTS = ("detector", "anomaly", "shadow", "fp_filter", "persistence")
IDENTITY_CALIBRATOR = "identity@0.1.0"
REPO_ROOT = Path(__file__).resolve().parents[3]


def repo_path(value: str | Path) -> Path:
    """Config paths are relative to the repository root."""
    path = Path(value)
    return path if path.is_absolute() else REPO_ROOT / path


def fuse(
    scores: Mapping[str, float | None],
    weights: Mapping[str, float],
    *,
    dropout_penalty: float = 0.0,
    motion_penalty: float = 0.0,
) -> float:
    """Weighted mean of the available components minus penalties, in [0, 1]."""
    used = [
        (float(weights.get(name, 0.0)), float(value))
        for name in COMPONENTS
        if (value := scores.get(name)) is not None and float(weights.get(name, 0.0)) > 0
    ]
    total = sum(w for w, _ in used)
    base = sum(w * v for w, v in used) / total if total > 0 else 0.0
    return min(max(base - dropout_penalty - motion_penalty, 0.0), 1.0)


def fit_isotonic(
    scores: Sequence[float], labels: Sequence[float]
) -> tuple[list[float], list[float]]:
    """Non-decreasing least-squares fit (pool adjacent violators); returns breakpoints ``x, y``."""
    order = np.argsort(np.asarray(scores, dtype=float), kind="stable")
    x = np.asarray(scores, dtype=float)[order]
    y = np.asarray(labels, dtype=float)[order]
    blocks: list[list[float]] = []  # [sum_y, count, x_min, x_max]
    for xi, yi in zip(x, y, strict=True):
        blocks.append([yi, 1.0, xi, xi])
        while len(blocks) > 1 and blocks[-2][0] / blocks[-2][1] > blocks[-1][0] / blocks[-1][1]:
            s, c, lo, _ = blocks.pop(-2)
            blocks[-1] = [blocks[-1][0] + s, blocks[-1][1] + c, lo, blocks[-1][3]]
    xs: list[float] = []
    ys: list[float] = []
    for s, c, lo, hi in blocks:
        value = s / c
        xs.append(float(lo))
        ys.append(float(value))
        if hi > lo:
            xs.append(float(hi))
            ys.append(float(value))
    return xs, ys


def expected_calibration_error(
    probabilities: Sequence[float], labels: Sequence[float], bins: int = 10
) -> float:
    """ECE with equal-width bins: Σ (nᵦ/N)·|mean label − mean probability|."""
    p = np.asarray(probabilities, dtype=float)
    y = np.asarray(labels, dtype=float)
    if p.size == 0:
        return float("nan")
    index = np.minimum((p * bins).astype(int), bins - 1)
    error = 0.0
    for b in range(bins):
        selected = index == b
        if selected.any():
            error += selected.mean() * abs(float(y[selected].mean()) - float(p[selected].mean()))
    return float(error)


def reliability_table(
    probabilities: Sequence[float], labels: Sequence[float], bins: int = 10
) -> list[dict[str, float]]:
    """Per-bin count, mean predicted probability and observed frequency (reliability diagram)."""
    p = np.asarray(probabilities, dtype=float)
    y = np.asarray(labels, dtype=float)
    index = np.minimum((p * bins).astype(int), bins - 1)
    rows = []
    for b in range(bins):
        selected = index == b
        rows.append(
            {
                "bin_low": b / bins,
                "bin_high": (b + 1) / bins,
                "count": float(selected.sum()),
                "mean_predicted": float(p[selected].mean()) if selected.any() else float("nan"),
                "observed": float(y[selected].mean()) if selected.any() else float("nan"),
            }
        )
    return rows


@dataclass(frozen=True)
class IsotonicCalibrator:
    x: tuple[float, ...]
    y: tuple[float, ...]
    name: str = "isotonic"
    version: str = "0.1.0"

    def __call__(self, fused: float) -> float:
        if not self.x:
            return float(fused)
        return float(np.clip(np.interp(fused, self.x, self.y), 0.0, 1.0))

    def describe(self) -> str:
        return f"{self.name}@{self.version}"

    @classmethod
    def fit(
        cls,
        scores: Sequence[float],
        labels: Sequence[float],
        *,
        name: str = "isotonic",
        version: str = "0.1.0",
    ) -> IsotonicCalibrator:
        xs, ys = fit_isotonic(scores, labels)
        return cls(tuple(xs), tuple(ys), name, version)

    def save(self, path: str | Path, **extra: Any) -> Path:
        out = Path(path)
        out.parent.mkdir(parents=True, exist_ok=True)
        payload = {"name": self.name, "version": self.version, "x": self.x, "y": self.y, **extra}
        out.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        return out

    @classmethod
    def load(cls, path: str | Path) -> IsotonicCalibrator:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        return cls(
            tuple(float(v) for v in data["x"]),
            tuple(float(v) for v in data["y"]),
            str(data.get("name", "isotonic")),
            str(data.get("version", "0.0.0")),
        )


class FpFilter:
    """LightGBM probability that a detection is a true positive (ST-062)."""

    def __init__(self, booster: Any, feature_names: Sequence[str], name: str, version: str) -> None:
        self.booster = booster
        self.feature_names = tuple(feature_names)
        self.name = name
        self.version = version

    def describe(self) -> str:
        return f"{self.name}@{self.version}"

    def predict(self, features: Sequence[Mapping[str, float]]) -> list[float]:
        if not features:
            return []
        matrix = np.array(
            [[float(f.get(n, float("nan"))) for n in self.feature_names] for f in features]
        )
        return [round(float(v), 4) for v in self.booster.predict(matrix)]

    @classmethod
    def load(cls, folder: str | Path) -> FpFilter:
        import lightgbm

        root = Path(folder)
        meta = json.loads((root / "model.json").read_text(encoding="utf-8"))
        booster = lightgbm.Booster(model_file=str(root / "model.txt"))
        return cls(booster, meta["feature_names"], meta["name"], meta["version"])


def load_calibrator(config: Mapping[str, Any]) -> IsotonicCalibrator | None:
    """The configured isotonic calibrator, or ``None`` (identity) if it isn't there."""
    value = config.get("scoring", {}).get("calibrator")
    if not value:
        return None
    path = repo_path(value)
    return IsotonicCalibrator.load(path) if path.suffix == ".json" and path.is_file() else None


def load_fp_filter(config: Mapping[str, Any]) -> FpFilter | None:
    """The configured FP filter, or ``None`` if the model or ``lightgbm`` is missing."""
    value = config.get("scoring", {}).get("fp_filter_model")
    if not value or importlib.util.find_spec("lightgbm") is None:
        return None
    folder = repo_path(value)
    if not (folder / "model.txt").is_file() or not (folder / "model.json").is_file():
        return None
    return FpFilter.load(folder)
