"""ST-012: build the normal-seafloor tile pool for PatchCore.

**Source change:** the public SeabedObjects-KLSG repository we downloaded (D3) contains only ship
and airplane crops, no seafloor images. The pool is therefore built from mine-SSS (D2, CC BY 4.0)
images whose label file is empty (no MILCO/NOMBO objects), grouped by survey year. KLSG seafloor
crops can be added later if the authors publish them.

Each source image is cut into non-overlapping ``crop_px`` squares, resized to ``tile_px`` and kept
unless the tile is nearly blank (water column, dropout or padding). Outputs under
``data/processed/anomaly/normal/``: tiles, ``manifest.csv`` and a ``contact_sheet.png`` for the
spot check.

    python ml/datasets/build_normal_pool.py --raw data/raw/mine_sss_2024
"""

from __future__ import annotations

import argparse
import csv
import json
import random
import zipfile
from collections import Counter
from pathlib import Path

import numpy as np


def tile_grid(height: int, width: int, crop_px: int) -> list[tuple[int, int]]:
    """Top-left corners of non-overlapping ``crop_px`` squares that fit in the image."""
    return [
        (r, c)
        for r in range(0, height - crop_px + 1, crop_px)
        for c in range(0, width - crop_px + 1, crop_px)
    ]


def is_usable(
    tile: np.ndarray, min_mean: float = 12.0, min_std: float = 4.0, max_dark_fraction: float = 0.3
) -> bool:
    """Reject blank tiles: too dark, too flat, or with a large near-black area."""
    t = tile.astype(np.float32)
    return bool(t.mean() >= min_mean and t.std() >= min_std and (t < 5).mean() <= max_dark_fraction)


def build(raw: Path, out: Path, crop_px: int = 512, tile_px: int = 256, seed: int = 0) -> dict:
    import cv2

    rows = []
    counts: Counter[str] = Counter()
    for zpath in sorted(raw.glob("[0-9][0-9][0-9][0-9].zip")):
        year = zpath.stem
        with zipfile.ZipFile(zpath) as zf:
            names = set(zf.namelist())
            for name in sorted(n for n in names if n.lower().endswith(".jpg")):
                label = name[:-4] + ".txt"
                if label not in names or zf.read(label).strip():
                    continue  # only images annotated as object-free
                counts["source_images"] += 1
                image = cv2.imdecode(np.frombuffer(zf.read(name), np.uint8), cv2.IMREAD_GRAYSCALE)
                if image is None:
                    counts["unreadable"] += 1
                    continue
                for r, c in tile_grid(*image.shape, crop_px):
                    crop = image[r : r + crop_px, c : c + crop_px]
                    tile = cv2.resize(crop, (tile_px, tile_px), interpolation=cv2.INTER_AREA)
                    if not is_usable(tile):
                        counts["rejected_blank"] += 1
                        continue
                    rel = Path(year) / f"{Path(name).stem}_r{r}_c{c}.png"
                    (out / year).mkdir(parents=True, exist_ok=True)
                    cv2.imwrite(str(out / rel), tile)
                    rows.append(
                        {
                            "tile": rel.as_posix(),
                            "group": year,
                            "source": name,
                            "row": r,
                            "col": c,
                            "mean": round(float(tile.mean()), 1),
                            "std": round(float(tile.std()), 1),
                        }
                    )
                    counts[f"tiles_{year}"] += 1
    out.mkdir(parents=True, exist_ok=True)
    with (out / "manifest.csv").open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(
            fh, fieldnames=["tile", "group", "source", "row", "col", "mean", "std"]
        )
        writer.writeheader()
        writer.writerows(rows)

    sample = random.Random(seed).sample(rows, min(64, len(rows)))
    if sample:
        thumbs = [
            cv2.resize(cv2.imread(str(out / s["tile"]), cv2.IMREAD_GRAYSCALE), (96, 96))
            for s in sample
        ]
        thumbs += [np.zeros((96, 96), np.uint8)] * (-len(thumbs) % 8)
        grid = np.vstack([np.hstack(thumbs[i : i + 8]) for i in range(0, len(thumbs), 8)])
        cv2.imwrite(str(out / "contact_sheet.png"), grid)

    summary = {
        "tiles": len(rows),
        "crop_px": crop_px,
        "tile_px": tile_px,
        **counts,
        "source": "D2 mine_sss_2024 images with empty labels (CC BY 4.0)",
    }
    (out / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--raw", type=Path, default=Path("data/raw/mine_sss_2024"))
    parser.add_argument("--out", type=Path, default=Path("data/processed/anomaly/normal"))
    args = parser.parse_args()
    print(json.dumps(build(args.raw, args.out), indent=2))


if __name__ == "__main__":
    main()
