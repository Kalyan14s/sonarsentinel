"""ST-050/051: train the YOLO11-seg detector and register the result.

Augmentations follow docs/architecture/03-ml-models.md §3.2 (no rotation/perspective/hue, flips,
brightness 0.3, scale 0.3, mosaic with close_mosaic, copy-paste). The best weights, training
arguments and the Ultralytics results table are copied to
``models/detector/<name>/<version>/``; the registry folder is git-ignored (DVC).

CPU note: this machine has no CUDA GPU, so Sprint 3 baselines use short schedules; the values
used are recorded in each experiment log.

    python ml/train_detector.py --data data/processed/yolo/0.1.0-real/data.yaml \
        --name yolo11s-seg-sonar-real --version 0.1.0 --epochs 12 --imgsz 640 --batch 8
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import time
from pathlib import Path

# Windows: conda NumPy/SciPy load Intel OpenMP (libiomp5md) and pip PyTorch loads LLVM OpenMP
# (libomp); without this, training aborts with "OMP: Error #15". Documented workaround.
os.environ.setdefault("KMP_DUPLICATE_LIB_OK", "TRUE")

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--data", type=Path, required=True)
    parser.add_argument("--model", default="yolo11s-seg.pt")
    parser.add_argument("--name", required=True)
    parser.add_argument("--version", default="0.1.0")
    parser.add_argument("--epochs", type=int, default=200)
    parser.add_argument("--patience", type=int, default=40)
    parser.add_argument("--imgsz", type=int, default=640)
    parser.add_argument("--batch", type=int, default=16)
    parser.add_argument("--freeze", type=int, default=10)
    parser.add_argument("--close-mosaic", type=int, default=15)
    parser.add_argument("--workers", type=int, default=0, help="0 avoids Windows worker issues")
    parser.add_argument("--device", default="cpu")
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    from ultralytics import YOLO

    train_args = {
        "data": str(args.data),
        "imgsz": args.imgsz,
        "epochs": args.epochs,
        "batch": args.batch,
        "patience": args.patience,
        "freeze": args.freeze,
        "degrees": 0.0,
        "perspective": 0.0,
        "shear": 0.0,
        "hsv_h": 0.0,
        "hsv_s": 0.0,
        "hsv_v": 0.3,
        "fliplr": 0.5,
        "flipud": 0.5,
        "scale": 0.3,
        "mosaic": 1.0,
        "close_mosaic": min(args.close_mosaic, max(args.epochs - 1, 0)),
        "copy_paste": 0.4,
        "cos_lr": True,
        "seed": args.seed,
        "device": args.device,
        "workers": args.workers,
        "project": str(ROOT / "runs" / "detector"),
        "name": args.name,
        "exist_ok": True,
        "plots": True,
        "deterministic": True,
    }
    started = time.time()
    model = YOLO(args.model)
    results = model.train(**train_args)
    run_dir = Path(results.save_dir)
    registry = ROOT / "models" / "detector" / args.name / args.version
    registry.mkdir(parents=True, exist_ok=True)
    shutil.copy2(run_dir / "weights" / "best.pt", registry / "best.pt")
    for extra in ("results.csv", "args.yaml"):
        if (run_dir / extra).exists():
            shutil.copy2(run_dir / extra, registry / extra)
    record = {
        "name": args.name,
        "version": args.version,
        "base_model": args.model,
        "train_args": train_args,
        "run_dir": str(run_dir),
        "wall_clock_h": round((time.time() - started) / 3600, 2),
    }
    (registry / "train_record.json").write_text(json.dumps(record, indent=2), encoding="utf-8")
    print(json.dumps(record, indent=2))


if __name__ == "__main__":
    main()
