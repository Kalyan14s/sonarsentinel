"""ST-010: convert AI4Shipwrecks (D1) segmentation masks to YOLO-seg polygons.

The dataset has to be downloaded in a browser (Deep Blue blocks scripts) into
``data/raw/ai4shipwrecks``. **Check the mask encoding on the first files:** this converter treats
any non-zero mask pixel as ``shipwreck`` and pairs masks with images by file stem, looking for a
mask folder whose name contains ``label`` or ``mask``. Adjust ``--images``/``--masks`` if the
release layout differs.

Outputs under ``data/interim/ai4shipwrecks/``: ``images/``, ``labels/``, ``qa_overlays/`` and
``summary.json`` (site ID = wreck name prefix of the file, for grouped splits).

    python ml/datasets/convert_ai4shipwrecks.py --images <dir> --masks <dir>
"""

from __future__ import annotations

import argparse
import json
import random
import re
import shutil
from collections import Counter
from pathlib import Path

import numpy as np
from yolo_seg import CLASS_IDS, format_polygon, mask_to_polygons

IMAGE_EXT = {".png", ".jpg", ".jpeg", ".tif", ".tiff"}


def site_id(stem: str) -> str:
    """Wreck/site name from a file stem: text before the first run of digits."""
    match = re.match(r"^(.*?)[_-]?\d", stem)
    return (match.group(1) if match and match.group(1) else stem).lower()


def convert(images: Path, masks: Path, out: Path, n_overlays: int = 20, seed: int = 0) -> dict:
    import cv2

    mask_by_stem = {p.stem: p for p in masks.rglob("*") if p.suffix.lower() in IMAGE_EXT}
    counts: Counter[str] = Counter()
    done = []
    (out / "images").mkdir(parents=True, exist_ok=True)
    (out / "labels").mkdir(parents=True, exist_ok=True)
    for image_path in sorted(p for p in images.rglob("*") if p.suffix.lower() in IMAGE_EXT):
        mask_path = mask_by_stem.get(image_path.stem)
        if mask_path is None:
            counts["images_without_mask"] += 1
            continue
        mask = cv2.imread(str(mask_path), cv2.IMREAD_UNCHANGED)
        if mask.ndim == 3:
            mask = mask.max(axis=2)
        polygons = mask_to_polygons(mask)
        lines = [format_polygon(CLASS_IDS["shipwreck"], poly) for poly in polygons]
        shutil.copy2(image_path, out / "images" / image_path.name)
        (out / "labels" / f"{image_path.stem}.txt").write_text(
            "\n".join(lines) + ("\n" if lines else ""), encoding="utf-8"
        )
        counts["images"] += 1
        counts["polygons"] += len(lines)
        counts[f"site:{site_id(image_path.stem)}"] += 1
        done.append((image_path, polygons))

    (out / "qa_overlays").mkdir(exist_ok=True)
    for image_path, polygons in random.Random(seed).sample(done, min(n_overlays, len(done))):
        image = cv2.imread(str(image_path), cv2.IMREAD_COLOR)
        h, w = image.shape[:2]
        for poly in polygons:
            pts = np.array([(x * w, y * h) for x, y in poly], np.int32)
            cv2.polylines(image, [pts], True, (0, 255, 255), 2)
        cv2.imwrite(str(out / "qa_overlays" / f"{image_path.stem}.jpg"), image)

    summary = {"dataset": "D1 AI4Shipwrecks (CC BY 4.0)", **counts}
    (out / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--images", type=Path, required=True)
    parser.add_argument("--masks", type=Path, required=True)
    parser.add_argument("--out", type=Path, default=Path("data/interim/ai4shipwrecks"))
    args = parser.parse_args()
    print(json.dumps(convert(args.images, args.masks, args.out), indent=2))


if __name__ == "__main__":
    main()
