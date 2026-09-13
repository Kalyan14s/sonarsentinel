"""ST-053: build the PatchCore memory bank on normal seafloor tiles and evaluate it.

- **Train:** normal pool tiles (``build_normal_pool.py`` output) from every group except the
  held-out one(s), converted with the pipeline's ``to_three_channel``.
- **Threshold:** tile threshold τ = 99th percentile of tile scores on the held-out normal group
  (≈ 1% tile false alarms, docs/architecture/03-ml-models.md §5); the pixel threshold for region
  extraction is the 99.9th percentile of held-out heatmap values.
- **Evaluate:** AUROC of tile scores, held-out normal tiles vs. 256 px crops centred on synthetic
  ghost-net and pipe masks (holdout / unseen backgrounds), plus recall at τ.

    python ml/train_anomaly.py --pool data/processed/anomaly/normal --holdout-groups 2017 \
        --positives data/synthetic/ghost_net/1.0.0/holdout --version 0.1.0
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import random
import sys
import time
from pathlib import Path

import numpy as np

os.environ.setdefault("KMP_DUPLICATE_LIB_OK", "TRUE")  # see train_detector.py
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from sonarsentinel.detect.anomaly import PatchCoreModel, greedy_coreset  # noqa: E402
from sonarsentinel.preprocess.channels import to_three_channel  # noqa: E402


def load_pool(pool: Path, holdout_groups: set[str]) -> tuple[list[np.ndarray], list[np.ndarray]]:
    import cv2

    train, held = [], []
    with (pool / "manifest.csv").open(encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            img = cv2.imread(str(pool / row["tile"]), cv2.IMREAD_GRAYSCALE)
            (held if row["group"] in holdout_groups else train).append(to_three_channel(img))
    return train, held


def positive_crops(folders: list[Path], size: int = 256, limit: int = 200) -> list[np.ndarray]:
    """Crops centred on synthetic object masks (images/ + masks/ folders)."""
    import cv2

    crops = []
    for folder in folders:
        for image_path in sorted((folder / "images").glob("*.png"))[:limit]:
            mask = cv2.imread(str(folder / "masks" / image_path.name), cv2.IMREAD_GRAYSCALE)
            ys, xs = np.nonzero(mask)
            if not len(xs):
                continue
            gray = cv2.imread(str(image_path), cv2.IMREAD_GRAYSCALE)
            cy, cx = int(ys.mean()), int(xs.mean())
            y0 = int(np.clip(cy - size // 2, 0, gray.shape[0] - size))
            x0 = int(np.clip(cx - size // 2, 0, gray.shape[1] - size))
            crops.append(to_three_channel(gray[y0 : y0 + size, x0 : x0 + size]))
    return crops


def auroc(negatives: np.ndarray, positives: np.ndarray) -> float:
    from sklearn.metrics import roc_auc_score

    labels = np.r_[np.zeros(len(negatives)), np.ones(len(positives))]
    return float(roc_auc_score(labels, np.r_[negatives, positives]))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--pool", type=Path, default=ROOT / "data/processed/anomaly/normal")
    parser.add_argument("--holdout-groups", nargs="+", default=["2017"])
    parser.add_argument(
        "--positives",
        type=Path,
        nargs="+",
        default=[ROOT / "data/synthetic/ghost_net/1.0.0/holdout"],
    )
    parser.add_argument("--max-train-tiles", type=int, default=600)
    parser.add_argument("--patch-sample", type=int, default=150_000)
    parser.add_argument("--coreset", type=int, default=3000)
    parser.add_argument("--name", default="patchcore-seafloor")
    parser.add_argument("--version", default="0.1.0")
    parser.add_argument("--seed", type=int, default=0)
    args = parser.parse_args()

    import torch

    torch.manual_seed(args.seed)
    random.seed(args.seed)
    started = time.time()
    train, held = load_pool(args.pool, set(args.holdout_groups))
    random.Random(args.seed).shuffle(train)
    train = train[: args.max_train_tiles]
    print(f"normal tiles: train {len(train)}, held-out {len(held)}", flush=True)

    model = PatchCoreModel(torch.zeros((1, 384)), name=args.name, version=args.version)
    feats = model.patch_features(train)
    print(f"patch features {tuple(feats.shape)} in {time.time() - started:.0f} s", flush=True)
    generator = torch.Generator().manual_seed(args.seed)
    sample = feats[torch.randperm(feats.shape[0], generator=generator)[: args.patch_sample]]
    idx = greedy_coreset(sample, args.coreset, seed=args.seed)
    model.memory_bank = sample[idx].clone()
    print(
        f"memory bank {tuple(model.memory_bank.shape)} after {time.time() - started:.0f} s",
        flush=True,
    )

    normal = model.score(held)
    model.threshold = float(np.percentile(normal.scores, 99))
    model.pixel_threshold = float(np.percentile(normal.heatmaps, 99.9))
    crops = positive_crops(args.positives)
    positive = model.score(crops)
    result = {
        "auroc_tile": round(auroc(normal.scores, positive.scores), 4),
        "tile_threshold_p99_normal": round(model.threshold, 4),
        "pixel_threshold_p999_normal": round(model.pixel_threshold, 4),
        "recall_at_threshold": round(float((positive.scores >= model.threshold).mean()), 4),
        "normal_false_alarm_rate": round(float((normal.scores >= model.threshold).mean()), 4),
        "n_train_tiles": len(train),
        "n_normal_eval": len(held),
        "n_positive_eval": len(crops),
        "positives": [str(p) for p in args.positives],
        "holdout_groups": args.holdout_groups,
        "memory_bank": int(model.memory_bank.shape[0]),
        "wall_clock_min": round((time.time() - started) / 60, 1),
    }
    registry = ROOT / "models" / "anomaly" / args.name / args.version
    model.save(registry, extra={"evaluation": result})
    (registry / "metrics.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
