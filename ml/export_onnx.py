"""ST-100: export the YOLO11-seg detector to ONNX and check parity with PyTorch (TC-EDGE-001).

Writes ``best.onnx`` next to the ``.pt`` weights (fixed 640 px input, ADR-018 §10), then runs both
through ``YoloDetector`` on ``--images`` tiles of a split and matches detections one-to-one by box
IoU. TC-EDGE-001 passes when every PyTorch detection has an ONNX match with IoU ≥ 0.95 and a
score difference ≤ 0.02 (and no extra ONNX detections). Also reports CPU time per tile for both
runtimes.

    python ml/export_onnx.py --model models/detector/yolo11s-seg-sonar-real/0.1.0/best.pt \
        --data data/processed/yolo/0.1.0-real --split val --images 100
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path
from typing import Any

os.environ.setdefault("KMP_DUPLICATE_LIB_OK", "TRUE")  # see train_detector.py
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from sonarsentinel.detect.merge import box_iou  # noqa: E402


def export(weights: Path, imgsz: int) -> Path:
    from ultralytics import YOLO

    target = weights.with_suffix(".onnx")
    produced = Path(YOLO(str(weights)).export(format="onnx", imgsz=imgsz, dynamic=False))
    if produced.resolve() != target.resolve():
        produced.replace(target)
    return target


def compare(
    torch_dets: list[Any], onnx_dets: list[Any], iou: float = 0.95, score_tol: float = 0.02
) -> dict[str, int]:
    """Greedy one-to-one matching by IoU; counts of matched, unmatched and score mismatches."""
    used = [False] * len(onnx_dets)
    matched = score_mismatch = 0
    for t in sorted(torch_dets, key=lambda d: -d.score):
        best, best_iou = -1, iou
        for j, o in enumerate(onnx_dets):
            if not used[j] and o.cls == t.cls and (value := box_iou(t.box, o.box)) >= best_iou:
                best, best_iou = j, value
        if best >= 0:
            used[best] = True
            matched += 1
            score_mismatch += abs(t.score - onnx_dets[best].score) > score_tol
    return {
        "torch_detections": len(torch_dets),
        "onnx_detections": len(onnx_dets),
        "matched": matched,
        "score_mismatch": score_mismatch,
        "onnx_extra": used.count(False),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--model", type=Path, required=True)
    parser.add_argument("--data", type=Path, required=True)
    parser.add_argument("--split", default="val")
    parser.add_argument("--images", type=int, default=100)
    parser.add_argument("--imgsz", type=int, default=640)
    parser.add_argument("--conf", type=float, default=0.20)
    parser.add_argument("--skip-export", action="store_true")
    parser.add_argument("--out", type=Path, default=None)
    args = parser.parse_args()

    import cv2
    from sonarsentinel.detect.yolo import YoloDetector

    onnx_path = args.model.with_suffix(".onnx")
    if not args.skip_export or not onnx_path.exists():
        started = time.time()
        onnx_path = export(args.model, args.imgsz)
        print(f"exported {onnx_path} in {time.time() - started:.1f} s")

    images = sorted((args.data / "images" / args.split).glob("*.png"))[: args.images]
    tiles = [cv2.imread(str(p), cv2.IMREAD_COLOR) for p in images]
    runtimes = {
        "torch": YoloDetector(args.model, imgsz=args.imgsz, conf=args.conf, sahi=False),
        "onnx": YoloDetector(onnx_path, imgsz=args.imgsz, conf=args.conf, sahi=False),
    }
    outputs: dict[str, list[list[Any]]] = {}
    timing: dict[str, float] = {}
    for name, detector in runtimes.items():
        detector.predict(tiles[:1])  # warm up
        started = time.perf_counter()
        outputs[name] = [detector.predict([tile])[0] for tile in tiles]
        timing[name] = round((time.perf_counter() - started) / max(len(tiles), 1) * 1000, 1)

    totals = {
        "torch_detections": 0,
        "onnx_detections": 0,
        "matched": 0,
        "score_mismatch": 0,
        "onnx_extra": 0,
    }
    for t, o in zip(outputs["torch"], outputs["onnx"], strict=True):
        for key, value in compare(t, o).items():
            totals[key] += value
    result = {
        "model": str(args.model),
        "onnx": str(onnx_path),
        "onnx_size_mb": round(onnx_path.stat().st_size / 1e6, 1),
        "images": len(tiles),
        "split": args.split,
        "conf": args.conf,
        **totals,
        "ms_per_tile_torch": timing["torch"],
        "ms_per_tile_onnx": timing["onnx"],
        "runtime_onnx": runtimes["onnx"].runtime,
        "tc_edge_001_pass": totals["matched"] == totals["torch_detections"]
        and totals["score_mismatch"] == 0
        and totals["onnx_extra"] == 0,
    }
    out = args.out or onnx_path.with_name("onnx_parity.json")
    out.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
