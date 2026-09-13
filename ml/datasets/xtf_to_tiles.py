"""Sonar log → preprocessed 3-channel tiles for labelling and pseudo-labelling (ST-014 support).

Runs the backend preprocessing (stages S2–S7, same code as inference) on each chunk, cuts 640 px
tiles with 25% overlap, skips mostly masked tiles, and writes for every tile a PNG plus a JSON
sidecar with the chunk/tile offsets, ping range and corner positions, so labels can be mapped back
to sonar pings and WGS84 later.

    python ml/datasets/xtf_to_tiles.py data/raw/usgs/grandbay_2015-315-FA/*.xtf \
        --out data/interim/tiles
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "backend"))

from sonarsentinel.config import load_config  # noqa: E402
from sonarsentinel.geo.georef import pixels_to_latlon  # noqa: E402
from sonarsentinel.ingest.reader import read_source  # noqa: E402
from sonarsentinel.preprocess.channels import to_three_channel  # noqa: E402
from sonarsentinel.preprocess.pipeline import preprocess_log  # noqa: E402
from sonarsentinel.preprocess.tiling import iter_tiles, row_col_mask  # noqa: E402


def export_tiles(
    source: Path, out: Path, epsg: str | None = None, max_tiles: int | None = None
) -> int:
    import cv2

    config = load_config()
    tiling = config["tiling"]
    log = read_source(source, epsg=epsg, allow_no_gps=True)
    written = 0
    for chunk in preprocess_log(log, config):
        three = to_three_channel(chunk.image)
        mask = row_col_mask(
            chunk.image.shape,
            rows=chunk.masks["dropout"],
            cols=chunk.masks["near_nadir"],
        )
        for tile, pixels in iter_tiles(
            three,
            mask=mask,
            size=tiling["size_px"],
            overlap=tiling["overlap"],
            skip_if_masked_fraction_gt=tiling["skip_if_masked_fraction_gt"],
        ):
            name = f"{source.stem}_c{chunk.chunk_id:03d}_t{tile.index:04d}"
            # Same channel order on disk as prepare_yolo.py writes and the YOLO adapter feeds.
            cv2.imwrite(str(out / f"{name}.png"), pixels)
            rows = np.arange(tile.row, min(tile.row + tile.size, chunk.image.shape[0]))
            meta = {
                "source_file": log.source_file,
                "chunk_id": chunk.chunk_id,
                "tile": {"index": tile.index, "row": tile.row, "col": tile.col, "size": tile.size},
                "ping_start": int(chunk.row_to_ping[rows[0]]),
                "ping_end": int(chunk.row_to_ping[rows[-1]]),
                "nadir_col": chunk.nadir_col,
                "ground_res_m": chunk.ground_res_m,
                "warnings": chunk.warnings,
            }
            if chunk.geotagged:
                last_row = int(rows[-1])
                last_col = min(tile.col + tile.size, chunk.image.shape[1]) - 1
                corners_r = np.array([tile.row, tile.row, last_row, last_row])
                corners_c = np.array([tile.col, last_col, last_col, tile.col])
                lat, lon = pixels_to_latlon(corners_r, corners_c, chunk.geo_frame())
                meta["corners_latlon"] = [
                    [round(float(a), 7), round(float(b), 7)] for a, b in zip(lat, lon, strict=True)
                ]
            (out / f"{name}.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
            written += 1
            if max_tiles is not None and written >= max_tiles:
                return written
    return written


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("sources", type=Path, nargs="+")
    parser.add_argument("--out", type=Path, default=Path("data/interim/tiles"))
    parser.add_argument("--utm-epsg", default=None)
    parser.add_argument("--max-tiles", type=int, default=None)
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    for source in args.sources:
        n = export_tiles(source, args.out, args.utm_epsg, args.max_tiles)
        print(f"{source.name}: {n} tiles")


if __name__ == "__main__":
    main()
