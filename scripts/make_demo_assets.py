"""Demo asset A3: waterfall PNG + navigation CSV with a clearly labelled synthetic ghost net.

``docs/hackathon/DEMO_SCRIPT.md`` §1 asks for ``demo/harbour_synthetic.png`` and ``.csv``. The
image is one tile from the ghost-net generator v1 (``ml/synth/ghost_net_generator.py``) rendered on
an object-free Mine SSS background from the held-out site, with fixed parameters so the net is large
and visible. The navigation is a fictional straight track near Chennai; the coordinates are not a
real survey. A ground-truth JSON gives the net's pixel box and position for checking the demo.

    python scripts/make_demo_assets.py --out demo
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import sys
from dataclasses import asdict, replace
from datetime import UTC, datetime, timedelta
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "ml" / "synth"))

from ghost_net_generator import (  # noqa: E402
    GENERATOR_VERSION,
    find_backgrounds,
    render_tile,
    sample_params,
)
from pyproj import Geod  # noqa: E402

GEOD = Geod(ellps="WGS84")
START_LAT, START_LON = 13.0950, 80.3050  # fictional line off Chennai harbour
HEADING_DEG = 20.0
RES_M = 0.10
TILE_PX = 640
SEED = 20260914
PING_INTERVAL_S = 0.1


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--backgrounds", type=Path, default=ROOT / "data" / "interim" / "mine_sss")
    parser.add_argument("--group", default="2017", help="Held-out background site")
    parser.add_argument("--out", type=Path, default=ROOT / "demo")
    args = parser.parse_args()

    import cv2

    backgrounds = [b for b in find_backgrounds(args.backgrounds) if b[1] == args.group]
    if not backgrounds:
        sys.exit(f"No object-free backgrounds for group {args.group} in {args.backgrounds}")
    rng = np.random.default_rng(SEED)
    path, group = backgrounds[int(rng.integers(len(backgrounds)))]
    background = cv2.imread(str(path), cv2.IMREAD_GRAYSCALE)
    params = sample_params(rng, TILE_PX, RES_M, path, group, background.shape, SEED)
    params = replace(
        params,
        center_xy=(170, 330),  # on the port-side seabed, clear of the nadir water column
        side="port",
        clump_length_m=8.0,
        clump_width_m=4.0,
        clump_angle_deg=35.0,
        reflectivity=110.0,
        burial_fraction=0.1,
        height_m=1.0,
        altitude_m=10.0,
        ground_range_m=15.0,
        shadow_length_px=17,
        shadow_factor=0.35,
        n_ropes=2,
        n_floats=3,
    )
    image, mask = render_tile(background, params)

    args.out.mkdir(parents=True, exist_ok=True)
    png = args.out / "harbour_synthetic.png"
    cv2.imwrite(str(png), image)

    # Straight track: one image row per ping, 0.10 m apart, nadir at the image centre.
    start = datetime(2026, 9, 14, 5, 0, 0, tzinfo=UTC)
    rows = list(range(0, TILE_PX, 20)) + [TILE_PX - 1]
    lons, lats, _ = GEOD.fwd(
        np.full(len(rows), START_LON),
        np.full(len(rows), START_LAT),
        np.full(len(rows), HEADING_DEG),
        np.array(rows, dtype=float) * RES_M,
    )
    csv_path = args.out / "harbour_synthetic.csv"
    with csv_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle, lineterminator="\n")
        writer.writerow(
            [
                "ping",
                "time_utc",
                "lat",
                "lon",
                "heading_deg",
                "slant_range_m",
                "altitude_m",
                "sensor_depth_m",
            ]
        )
        for row, lat, lon in zip(rows, lats, lons, strict=True):
            writer.writerow(
                [
                    row,
                    (start + timedelta(seconds=row * PING_INTERVAL_S)).strftime(
                        "%Y-%m-%dT%H:%M:%S.%fZ"
                    ),
                    f"{lat:.7f}",
                    f"{lon:.7f}",
                    f"{HEADING_DEG:.1f}",
                    f"{TILE_PX / 2 * RES_M:.1f}",
                    f"{params.altitude_m:.1f}",
                    "2.0",
                ]
            )

    ys, xs = np.nonzero(mask)
    cx, cy = float(xs.mean()), float(ys.mean())
    across = (cx - TILE_PX / 2) * RES_M  # starboard positive
    along_lon, along_lat, _ = GEOD.fwd(START_LON, START_LAT, HEADING_DEG, cy * RES_M)
    net_lon, net_lat, _ = GEOD.fwd(along_lon, along_lat, (HEADING_DEG + 90.0) % 360.0, across)
    truth = {
        "synthetic": True,
        "class": "ghost_net",
        "pixel_bbox": [int(xs.min()), int(ys.min()), int(xs.max()) + 1, int(ys.max()) + 1],
        "centroid_px": [round(cx, 1), round(cy, 1)],
        "approx_lat": round(float(net_lat), 6),
        "approx_lon": round(float(net_lon), 6),
        "size_m": [params.clump_length_m, params.clump_width_m],
        "height_m": params.height_m,
        "generator_version": GENERATOR_VERSION,
        "params": asdict(params),
        "background_licence": "Mine SSS dataset (D2), CC BY 4.0",
        "note": "Synthetic ghost net on a real seabed background; fictional coordinates.",
    }
    (args.out / "harbour_synthetic.truth.json").write_text(
        json.dumps(truth, indent=2) + "\n", "utf-8"
    )
    print(
        f"wrote {png.name}, {csv_path.name}, harbour_synthetic.truth.json "
        f"(net at px {truth['pixel_bbox']}, ~{truth['approx_lat']}, {truth['approx_lon']}; "
        f"{math.hypot(*params.center_xy):.0f} px from origin)"
    )


if __name__ == "__main__":
    main()
