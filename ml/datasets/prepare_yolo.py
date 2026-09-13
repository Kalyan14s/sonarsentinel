"""Build Ultralytics training folders from a dataset manifest (ST-050/051).

Every image goes through the backend's :func:`to_three_channel` (raw | Lee | local std), the same
function inference uses (TC-PRE-007), and is written as PNG next to its YOLO-seg label.

Variants:

- ``real``: real sites only (ST-050 baseline).
- ``real_synth``: real sites plus synthetic training tiles (ST-051), up to ``--synthetic-per-kind``
  tiles per generator.

Object-free images are subsampled to ``--background-ratio`` × the number of positive images in the
train split (docs/architecture/03-ml-models.md §3.1 asks for a small share of background tiles).
Val/test keep all their images; the synthetic holdout is written as split ``holdout``.

    python ml/datasets/prepare_yolo.py --manifest data/manifests/sonar-seg-0.1.0.json \
        --variant real --out data/processed/yolo
"""

from __future__ import annotations

import argparse
import json
import random
import shutil
import sys
from collections import Counter
from pathlib import Path
from typing import Any

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from sonarsentinel.preprocess.channels import to_three_channel  # noqa: E402
from yolo_seg import CLASS_IDS  # noqa: E402

SPLIT_NAMES = {
    "train": "train",
    "val": "val",
    "calib": "calib",
    "test": "test",
    "synthetic_holdout": "holdout",
}


def select_files(
    manifest: dict[str, Any],
    variant: str,
    background_ratio: float,
    synthetic_per_kind: int,
    seed: int = 0,
) -> list[dict[str, Any]]:
    rng = random.Random(seed)
    files = manifest["files"]
    if variant == "real":
        files = [f for f in files if not f["dataset"].startswith("synthetic")]
    elif variant == "real_synth":
        by_kind: dict[str, list[dict[str, Any]]] = {}
        for f in files:
            if f["dataset"].startswith("synthetic") and f["split"] == "train":
                by_kind.setdefault(f["dataset"], []).append(f)
        keep_synth = [f for group in by_kind.values() for f in group[:synthetic_per_kind]]
        files = [
            f for f in files if not f["dataset"].startswith("synthetic") or f["split"] != "train"
        ] + keep_synth
    else:
        raise ValueError(f"unknown variant {variant}")

    train = [f for f in files if f["split"] == "train"]
    positives = [f for f in train if f["objects"]]
    empty = [f for f in train if not f["objects"]]
    rng.shuffle(empty)
    background = empty[: int(round(background_ratio * len(positives)))]
    others = [f for f in files if f["split"] != "train"]
    return sorted(positives + background + others, key=lambda f: (f["split"], f["image"]))


def convert(files: list[dict[str, Any]], processed: Path, out: Path) -> dict[str, Any]:
    import cv2

    counts: dict[str, Counter[str]] = {}
    for f in files:
        split = SPLIT_NAMES[f["split"]]
        src = processed / f["image"]
        stem = Path(f["image"]).stem
        gray = cv2.imread(str(src), cv2.IMREAD_GRAYSCALE)
        if gray is None:
            raise FileNotFoundError(src)
        (out / "images" / split).mkdir(parents=True, exist_ok=True)
        (out / "labels" / split).mkdir(parents=True, exist_ok=True)
        cv2.imwrite(str(out / "images" / split / f"{stem}.png"), to_three_channel(gray))
        shutil.copy2(processed / f["label"], out / "labels" / split / f"{stem}.txt")
        c = counts.setdefault(split, Counter())
        c["images"] += 1
        c["positive_images"] += bool(f["objects"])
        for cls, n in f["objects"].items():
            c[cls] += n
    names = {v: k for k, v in CLASS_IDS.items()}
    yaml = [
        f"path: {out.resolve().as_posix()}",
        "train: images/train",
        "val: images/val",
        "test: images/test",
        "names:",
    ] + [f"  {i}: {names[i]}" for i in sorted(names)]
    (out / "data.yaml").write_text("\n".join(yaml) + "\n", encoding="utf-8")
    summary = {split: dict(c) for split, c in sorted(counts.items())}
    (out / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--manifest", type=Path, default=Path("data/manifests/sonar-seg-0.1.0.json")
    )
    parser.add_argument("--processed", type=Path, default=Path("data/processed/sonar-seg"))
    parser.add_argument("--variant", choices=["real", "real_synth"], required=True)
    parser.add_argument("--out", type=Path, default=Path("data/processed/yolo"))
    parser.add_argument("--background-ratio", type=float, default=0.5)
    parser.add_argument("--synthetic-per-kind", type=int, default=600)
    parser.add_argument("--seed", type=int, default=0)
    args = parser.parse_args()
    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    files = select_files(
        manifest, args.variant, args.background_ratio, args.synthetic_per_kind, args.seed
    )
    target = args.out / f"{manifest['version']}-{args.variant}"
    summary = convert(files, args.processed, target)
    print(json.dumps({"out": str(target), **summary}, indent=2))


if __name__ == "__main__":
    np.set_printoptions(suppress=True)
    main()
