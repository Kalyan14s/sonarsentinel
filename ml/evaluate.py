"""ST-057: detector evaluation — AP@50 (box and mask), PR curves, confusion matrix, bootstrap CI.

Works on any model through a predictions file, or directly on Ultralytics weights:

    python ml/evaluate.py --data data/processed/sonar-seg --split val --model runs/.../best.pt \
        --out models/detector/<name>/<version>/eval_val
    python ml/evaluate.py --data data/processed/sonar-seg --split val --predictions preds.jsonl

Predictions JSONL: one line per image ``{"image": "<file name>", "detections": [{"cls": 2,
"score": 0.8, "polygon": [[x, y], ...]}]}`` with normalised coordinates (same as YOLO-seg labels).

Outputs: ``metrics.json`` (per class AP@50 box/mask, precision/recall at ``--conf``, mAP@50 with a
95% bootstrap CI over images), ``pr_<class>.csv`` and ``confusion.csv``.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent / "datasets"))
from yolo_seg import CLASS_IDS  # noqa: E402

NAMES = {v: k for k, v in CLASS_IDS.items()}
MASK_SIZE = 256  # polygons are rasterised on this grid for mask IoU


@dataclass
class Instance:
    cls: int
    polygon: np.ndarray  # (n, 2) normalised x, y
    score: float = 1.0

    @property
    def box(self) -> tuple[float, float, float, float]:
        xs, ys = self.polygon[:, 0], self.polygon[:, 1]
        return float(xs.min()), float(ys.min()), float(xs.max()), float(ys.max())


@dataclass
class ImageRecord:
    name: str
    truths: list[Instance] = field(default_factory=list)
    predictions: list[Instance] = field(default_factory=list)


def read_labels(path: Path) -> list[Instance]:
    out = []
    if not path.exists():
        return out
    for line in path.read_text(encoding="utf-8").splitlines():
        parts = line.split()
        if len(parts) >= 7:
            coords = np.array([float(v) for v in parts[1:]], dtype=np.float64).reshape(-1, 2)
            out.append(Instance(int(parts[0]), coords))
    return out


def box_iou(a: tuple[float, ...], b: tuple[float, ...]) -> float:
    w = min(a[2], b[2]) - max(a[0], b[0])
    h = min(a[3], b[3]) - max(a[1], b[1])
    inter = max(w, 0.0) * max(h, 0.0)
    union = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - inter
    return inter / union if union > 0 else 0.0


def _raster(poly: np.ndarray) -> np.ndarray:
    import cv2

    mask = np.zeros((MASK_SIZE, MASK_SIZE), np.uint8)
    pts = np.rint(poly * (MASK_SIZE - 1) * 16).astype(np.int32)
    cv2.fillPoly(mask, [pts], 1, shift=4)
    return mask.astype(bool)


def mask_iou(a: Instance, b: Instance) -> float:
    ma, mb = _raster(a.polygon), _raster(b.polygon)
    union = np.logical_or(ma, mb).sum()
    return float(np.logical_and(ma, mb).sum() / union) if union else 0.0


def match_image(
    record: ImageRecord, cls: int, iou_thr: float = 0.5, kind: str = "box"
) -> tuple[list[tuple[float, bool]], int]:
    """Greedy matching by score; returns ``[(score, is_tp)]`` and the number of truths."""
    truths = [t for t in record.truths if t.cls == cls]
    preds = sorted((p for p in record.predictions if p.cls == cls), key=lambda p: -p.score)
    used = [False] * len(truths)
    results = []
    for p in preds:
        best, best_iou = -1, iou_thr
        for i, t in enumerate(truths):
            if used[i]:
                continue
            iou = box_iou(p.box, t.box) if kind == "box" else mask_iou(p, t)
            if iou >= best_iou:
                best, best_iou = i, iou
        if best >= 0:
            used[best] = True
        results.append((p.score, best >= 0))
    return results, len(truths)


def average_precision(matches: list[tuple[float, bool]], n_truth: int) -> tuple[float, np.ndarray]:
    """COCO-style 101-point interpolated AP, plus the PR curve ``(score, precision, recall)``."""
    if n_truth == 0:
        return float("nan"), np.zeros((0, 3))
    if not matches:
        return 0.0, np.zeros((0, 3))
    order = sorted(matches, key=lambda m: -m[0])
    tp = np.cumsum([m[1] for m in order])
    fp = np.cumsum([not m[1] for m in order])
    recall = tp / n_truth
    precision = tp / np.maximum(tp + fp, 1)
    envelope = np.maximum.accumulate(precision[::-1])[::-1]
    grid = np.linspace(0, 1, 101)
    idx = np.searchsorted(recall, grid, side="left")
    ap = float(np.mean([envelope[i] if i < len(envelope) else 0.0 for i in idx]))
    curve = np.stack([[m[0] for m in order], precision, recall], axis=1)
    return ap, curve


def evaluate(
    records: list[ImageRecord],
    conf: float = 0.25,
    kinds: tuple[str, ...] = ("box", "mask"),
    bootstrap: int = 200,
    seed: int = 0,
) -> tuple[dict[str, Any], dict[str, np.ndarray]]:
    classes = sorted(
        {t.cls for r in records for t in r.truths} | {p.cls for r in records for p in r.predictions}
    )
    metrics: dict[str, Any] = {"images": len(records), "conf_threshold": conf, "per_class": {}}
    curves: dict[str, np.ndarray] = {}
    for kind in kinds:
        aps = []
        for cls in classes:
            matches, n_truth = [], 0
            for r in records:
                m, n = match_image(r, cls, kind=kind)
                matches += m
                n_truth += n
            ap, curve = average_precision(matches, n_truth)
            entry = metrics["per_class"].setdefault(NAMES.get(cls, str(cls)), {"n_truth": n_truth})
            entry[f"ap50_{kind}"] = None if np.isnan(ap) else round(ap, 4)
            if kind == "box":
                kept = [m for m in matches if m[0] >= conf]
                tps = sum(1 for m in kept if m[1])
                entry["precision"] = round(tps / len(kept), 4) if kept else None
                entry["recall"] = round(tps / n_truth, 4) if n_truth else None
                curves[NAMES.get(cls, str(cls))] = curve
            if not np.isnan(ap):
                aps.append(ap)
        metrics[f"map50_{kind}"] = round(float(np.mean(aps)), 4) if aps else None

    if bootstrap and records:
        rng = np.random.default_rng(seed)
        samples = []
        for _ in range(bootstrap):
            pick = [records[i] for i in rng.integers(0, len(records), len(records))]
            sample_metrics, _ = evaluate(pick, conf, kinds=("box",), bootstrap=0)
            if sample_metrics["map50_box"] is not None:
                samples.append(sample_metrics["map50_box"])
        if samples:
            lo, hi = np.percentile(samples, [2.5, 97.5])
            metrics["map50_box_ci95"] = [round(float(lo), 4), round(float(hi), 4)]
    metrics["confusion"] = confusion(records, conf)
    return metrics, curves


def confusion(
    records: list[ImageRecord], conf: float = 0.25, iou_thr: float = 0.5
) -> dict[str, dict[str, int]]:
    """Rows = true class (``background`` for unmatched predictions); columns = predicted class."""
    table: dict[str, dict[str, int]] = {}

    def add(true: str, pred: str) -> None:
        table.setdefault(true, {}).setdefault(pred, 0)
        table[true][pred] += 1

    for r in records:
        preds = [p for p in r.predictions if p.score >= conf]
        used = [False] * len(preds)
        for t in r.truths:
            best, best_iou = -1, iou_thr
            for i, p in enumerate(preds):
                if not used[i] and (iou := box_iou(p.box, t.box)) >= best_iou:
                    best, best_iou = i, iou
            if best >= 0:
                used[best] = True
                add(NAMES.get(t.cls, str(t.cls)), NAMES.get(preds[best].cls, str(preds[best].cls)))
            else:
                add(NAMES.get(t.cls, str(t.cls)), "missed")
        for i, p in enumerate(preds):
            if not used[i]:
                add("background", NAMES.get(p.cls, str(p.cls)))
    return table


def load_split(data: Path, split: str) -> list[ImageRecord]:
    images = sorted((data / "images" / split).glob("*"))
    return [
        ImageRecord(img.name, read_labels(data / "labels" / split / f"{img.stem}.txt"))
        for img in images
    ]


def attach_predictions_jsonl(records: list[ImageRecord], path: Path) -> None:
    by_name = {r.name: r for r in records}
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        item = json.loads(line)
        record = by_name.get(item["image"])
        if record is None:
            continue
        for det in item["detections"]:
            record.predictions.append(
                Instance(int(det["cls"]), np.asarray(det["polygon"], float), float(det["score"]))
            )


def attach_predictions_ultralytics(
    records: list[ImageRecord],
    data: Path,
    split: str,
    weights: Path,
    imgsz: int = 640,
    batch: int = 8,
) -> None:
    from ultralytics import YOLO

    model = YOLO(str(weights))
    paths = [str(data / "images" / split / r.name) for r in records]
    for start in range(0, len(paths), batch):
        results = model.predict(
            paths[start : start + batch], imgsz=imgsz, conf=0.001, verbose=False
        )
        for record, res in zip(records[start : start + batch], results, strict=True):
            if res.masks is None:
                continue
            for poly, cls, score in zip(
                res.masks.xyn, res.boxes.cls.tolist(), res.boxes.conf.tolist(), strict=True
            ):
                if len(poly) >= 3:
                    record.predictions.append(
                        Instance(int(cls), np.asarray(poly, float), float(score))
                    )


def write_outputs(out: Path, metrics: dict[str, Any], curves: dict[str, np.ndarray]) -> None:
    out.mkdir(parents=True, exist_ok=True)
    (out / "metrics.json").write_text(json.dumps(metrics, indent=2), encoding="utf-8")
    for name, curve in curves.items():
        lines = ["score,precision,recall"] + [f"{s:.5f},{p:.5f},{r:.5f}" for s, p, r in curve]
        (out / f"pr_{name}.csv").write_text("\n".join(lines) + "\n", encoding="utf-8")
    cols = sorted({c for row in metrics["confusion"].values() for c in row})
    rows = ["true\\pred," + ",".join(cols)]
    for true, row in sorted(metrics["confusion"].items()):
        rows.append(true + "," + ",".join(str(row.get(c, 0)) for c in cols))
    (out / "confusion.csv").write_text("\n".join(rows) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--data", type=Path, default=Path("data/processed/sonar-seg"))
    parser.add_argument("--split", default="val")
    parser.add_argument("--model", type=Path, default=None)
    parser.add_argument("--predictions", type=Path, default=None)
    parser.add_argument("--imgsz", type=int, default=640)
    parser.add_argument("--conf", type=float, default=0.25)
    parser.add_argument("--bootstrap", type=int, default=200)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    records = load_split(args.data, args.split)
    if args.predictions:
        attach_predictions_jsonl(records, args.predictions)
    elif args.model:
        attach_predictions_ultralytics(records, args.data, args.split, args.model, args.imgsz)
    else:
        parser.error("give --model or --predictions")
    metrics, curves = evaluate(records, args.conf, bootstrap=args.bootstrap)
    metrics |= {"split": args.split, "model": str(args.model) if args.model else None}
    write_outputs(args.out, metrics, curves)
    print(json.dumps({k: v for k, v in metrics.items() if k != "confusion"}, indent=2))


if __name__ == "__main__":
    main()
