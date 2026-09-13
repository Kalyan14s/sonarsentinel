"""ST-052 / TC-DET-004: small-object recall with and without SAHI sliced inference.

Runs the same YOLO11-seg weights through ``YoloDetector`` twice on one split — whole image at
``--imgsz`` and SAHI slices of ``--slice-px`` — and reports recall at IoU ≥ 0.5 for all objects and
for small objects (longest box side < ``--small-px`` pixels in the original image). Images are
the 3-channel PNGs written by ``prepare_yolo.py``.

    python ml/compare_sahi.py --data data/processed/yolo/0.1.0-real --split val \
        --model models/detector/yolo11s-seg-sonar-real/0.1.0/best.pt \
        --out models/detector/yolo11s-seg-sonar-real/0.1.0/sahi_val.json
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path
from typing import Any

import numpy as np

os.environ.setdefault("KMP_DUPLICATE_LIB_OK", "TRUE")  # see train_detector.py
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from sonarsentinel.detect.merge import box_iou  # noqa: E402


def truth_boxes(label: Path, width: int, height: int) -> list[tuple[int, int, int, int]]:
    boxes = []
    if label.exists():
        for line in label.read_text(encoding="utf-8").splitlines():
            parts = line.split()
            if len(parts) < 7:
                continue
            xy = np.array([float(v) for v in parts[1:]]).reshape(-1, 2) * [width, height]
            x1, y1 = np.floor(xy.min(axis=0)).astype(int)
            x2, y2 = np.ceil(xy.max(axis=0)).astype(int)
            boxes.append((int(x1), int(y1), int(x2), int(y2)))
    return boxes


def recall(pairs: list[tuple[list[Any], list[Any]]], small_px: int) -> dict[str, float | int]:
    found = total = small_found = small_total = 0
    for truths, preds in pairs:
        used = [False] * len(preds)
        for t in truths:
            is_small = max(t[2] - t[0], t[3] - t[1]) < small_px
            hit = -1
            for i, p in enumerate(preds):
                if not used[i] and box_iou(t, p.box) >= 0.5:
                    hit = i
                    break
            if hit >= 0:
                used[hit] = True
            total += 1
            found += hit >= 0
            small_total += is_small
            small_found += is_small and hit >= 0
    return {
        "objects": total,
        "recall": round(found / total, 4) if total else 0.0,
        "small_objects": small_total,
        "small_recall": round(small_found / small_total, 4) if small_total else 0.0,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--data", type=Path, required=True)
    parser.add_argument("--split", default="val")
    parser.add_argument("--model", type=Path, required=True)
    parser.add_argument("--imgsz", type=int, default=640)
    parser.add_argument("--slice-px", type=int, default=512)
    parser.add_argument("--small-px", type=int, default=32)
    parser.add_argument("--conf", type=float, default=0.2)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()

    import cv2
    from sonarsentinel.detect.yolo import YoloDetector

    images = sorted((args.data / "images" / args.split).glob("*.png"))
    loaded = [(p, cv2.imread(str(p), cv2.IMREAD_COLOR)) for p in images]
    truths = [
        truth_boxes(args.data / "labels" / args.split / f"{p.stem}.txt", img.shape[1], img.shape[0])
        for p, img in loaded
    ]
    result: dict[str, Any] = {"images": len(images), "split": args.split, "model": str(args.model)}
    for mode, sahi in (("full_image", False), ("sahi", True)):
        detector = YoloDetector(
            args.model, imgsz=args.imgsz, conf=args.conf, sahi=sahi, slice_px=args.slice_px
        )
        started = time.time()
        preds = [detector.predict([img])[0] for _, img in loaded]
        result[mode] = recall(list(zip(truths, preds, strict=True)), args.small_px) | {
            "seconds_per_image": round((time.time() - started) / max(len(images), 1), 2)
        }
    result["sliced_small_recall_ge_full"] = (
        result["sahi"]["small_recall"] >= result["full_image"]["small_recall"]
    )
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
