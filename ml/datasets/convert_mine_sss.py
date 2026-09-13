"""ST-011: convert the mine-detection SSS dataset (D2) to YOLO-seg labels.

The Figshare release ships one zip per year with ``NNNN_YYYY.jpg`` images and YOLO box labels
(``class xc yc w h``; ``obj.names``: 0 = MILCO, 1 = NOMBO). Mapping (docs/data/DATASETS.md §3 D2):

- MILCO → ``cylinder`` as a 4-corner box polygon (boxes only; masks are refined later if needed).
- NOMBO → not labelled yet. Every NOMBO box is written to ``nombo_review.csv`` with a crop so an
  analyst can mark it ``debris_other`` (clearly man-made) or ``background`` (natural/ambiguous).

Outputs under ``data/interim/mine_sss/``: ``images/<year>/``, ``labels/<year>/``, ``nombo_crops/``,
``nombo_review.csv``, ``qa_overlays/`` (random images with polygons drawn) and ``summary.json``.

    python ml/datasets/convert_mine_sss.py --raw data/raw/mine_sss_2024 --out data/interim/mine_sss
"""

from __future__ import annotations

import argparse
import csv
import json
import random
import zipfile
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from yolo_seg import CLASS_IDS, box_to_polygon, format_polygon

MILCO, NOMBO = 0, 1
SOURCE_CLASSES = {MILCO: "MILCO", NOMBO: "NOMBO"}


@dataclass(frozen=True)
class Box:
    source_class: int
    xc: float
    yc: float
    w: float
    h: float


def parse_labels(text: str) -> list[Box]:
    """Parse a YOLO box label file; blank lines are ignored, malformed lines raise ValueError."""
    boxes = []
    for number, line in enumerate(text.splitlines(), start=1):
        parts = line.split()
        if not parts:
            continue
        if len(parts) != 5:
            raise ValueError(f"line {number}: expected 5 values, got {len(parts)}")
        cls = int(parts[0])
        if cls not in SOURCE_CLASSES:
            raise ValueError(f"line {number}: unknown class {cls}")
        xc, yc, w, h = (float(v) for v in parts[1:])
        boxes.append(Box(cls, xc, yc, w, h))
    return boxes


def convert_boxes(boxes: list[Box]) -> tuple[list[str], list[Box]]:
    """Return ``(yolo-seg lines for MILCO → cylinder, NOMBO boxes for review)``."""
    lines = [
        format_polygon(CLASS_IDS["cylinder"], box_to_polygon(b.xc, b.yc, b.w, b.h))
        for b in boxes
        if b.source_class == MILCO
    ]
    return lines, [b for b in boxes if b.source_class == NOMBO]


def _crop(image: np.ndarray, box: Box, pad: float = 1.0) -> np.ndarray:
    h, w = image.shape[:2]
    bw, bh = box.w * w * (1 + pad), box.h * h * (1 + pad)
    x1, x2 = int(max(box.xc * w - bw / 2, 0)), int(min(box.xc * w + bw / 2, w))
    y1, y2 = int(max(box.yc * h - bh / 2, 0)), int(min(box.yc * h + bh / 2, h))
    return image[y1:y2, x1:x2]


def _overlay(image: np.ndarray, boxes: list[Box]) -> np.ndarray:
    import cv2

    out = image.copy() if image.ndim == 3 else cv2.cvtColor(image, cv2.COLOR_GRAY2BGR)
    h, w = out.shape[:2]
    for b in boxes:
        pts = np.array([(x * w, y * h) for x, y in box_to_polygon(b.xc, b.yc, b.w, b.h)], np.int32)
        colour = (0, 255, 255) if b.source_class == MILCO else (255, 0, 255)
        cv2.polylines(out, [pts], True, colour, 2)
    return out


def convert(raw: Path, out: Path, n_overlays: int = 20, seed: int = 0) -> dict[str, object]:
    import cv2

    counts: Counter[str] = Counter()
    review_rows = []
    labelled: list[tuple[Path, list[Box]]] = []
    for zpath in sorted(raw.glob("[0-9][0-9][0-9][0-9].zip")):
        year = zpath.stem
        (out / "images" / year).mkdir(parents=True, exist_ok=True)
        (out / "labels" / year).mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(zpath) as zf:
            for name in sorted(n for n in zf.namelist() if n.lower().endswith(".jpg")):
                stem = Path(name).stem
                label_name = name[:-4] + ".txt"
                text = zf.read(label_name).decode("utf-8") if label_name in zf.namelist() else ""
                boxes = parse_labels(text)
                lines, nombo = convert_boxes(boxes)
                image_bytes = zf.read(name)
                image_path = out / "images" / year / f"{stem}.jpg"
                image_path.write_bytes(image_bytes)
                (out / "labels" / year / f"{stem}.txt").write_text(
                    "\n".join(lines) + ("\n" if lines else ""), encoding="utf-8"
                )
                counts["images"] += 1
                counts["milco_to_cylinder"] += len(lines)
                counts["nombo_for_review"] += len(nombo)
                counts["images_without_objects"] += not boxes
                if boxes:
                    labelled.append((image_path, boxes))
                if nombo:
                    image = cv2.imdecode(np.frombuffer(image_bytes, np.uint8), cv2.IMREAD_COLOR)
                    (out / "nombo_crops").mkdir(parents=True, exist_ok=True)
                    for i, b in enumerate(nombo):
                        crop_name = f"{year}_{stem}_n{i}.png"
                        cv2.imwrite(str(out / "nombo_crops" / crop_name), _crop(image, b))
                        review_rows.append(
                            {
                                "group": year,
                                "image": f"images/{year}/{stem}.jpg",
                                "crop": f"nombo_crops/{crop_name}",
                                "xc": f"{b.xc:.6f}",
                                "yc": f"{b.yc:.6f}",
                                "w": f"{b.w:.6f}",
                                "h": f"{b.h:.6f}",
                                "decision": "",
                                "reviewer": "",
                            }
                        )

    with (out / "nombo_review.csv").open("w", newline="", encoding="utf-8") as fh:
        fields = ["group", "image", "crop", "xc", "yc", "w", "h", "decision", "reviewer"]
        writer = csv.DictWriter(fh, fieldnames=fields)
        writer.writeheader()
        writer.writerows(review_rows)

    overlay_dir = out / "qa_overlays"
    overlay_dir.mkdir(parents=True, exist_ok=True)
    for image_path, boxes in random.Random(seed).sample(labelled, min(n_overlays, len(labelled))):
        image = cv2.imread(str(image_path), cv2.IMREAD_COLOR)
        name = f"{image_path.parent.name}_{image_path.stem}.jpg"
        cv2.imwrite(str(overlay_dir / name), _overlay(image, boxes))

    summary: dict[str, object] = {
        "dataset": "D2 mine_sss_2024 (CC BY 4.0)",
        "class_mapping": {"MILCO": "cylinder", "NOMBO": "pending manual review"},
        "group_key": "year of the source zip",
        **counts,
    }
    (out / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--raw", type=Path, default=Path("data/raw/mine_sss_2024"))
    parser.add_argument("--out", type=Path, default=Path("data/interim/mine_sss"))
    parser.add_argument("--overlays", type=int, default=20)
    args = parser.parse_args()
    print(json.dumps(convert(args.raw, args.out, args.overlays), indent=2))


if __name__ == "__main__":
    main()
