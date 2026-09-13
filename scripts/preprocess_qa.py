"""ST-048: preprocessing QA panels (before/after each stage) for the M2 review.

For one sonar file this writes PNG panels and a summary JSON to ``--out/<file stem>/``:

1. ``1_raw_bottom.png``: raw waterfall (log scale), port | starboard, with the tracked first
   return (red) and recorded altitude (green) drawn on each side
2. ``2_gain.png``: after dropout repair and gain normalisation (stage S4)
3. ``3_ground.png``: slant-range corrected and along-track resampled image (stage S5)
4. ``4_channels.png``: crop of the raw | Lee | local-std channels (stage S7)
5. ``5_masks.png``: dropout (red) and high-motion (yellow) rows, near-nadir columns (blue)
6. ``6_track.png``: raw fixes (grey) and cleaned track (green)

    python scripts/preprocess_qa.py data/raw/usgs/grandbay_2015-315-FA/15CCT03_SSS_150528201100.xtf
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from sonarsentinel.config import load_config  # noqa: E402
from sonarsentinel.geo.navigation import clean_navigation  # noqa: E402
from sonarsentinel.ingest.chunking import slice_log  # noqa: E402
from sonarsentinel.ingest.reader import read_source  # noqa: E402
from sonarsentinel.preprocess.bottom import track_bottom  # noqa: E402
from sonarsentinel.preprocess.dropout import detect_dropouts, repair_dropouts  # noqa: E402
from sonarsentinel.preprocess.gain import normalize_gain  # noqa: E402
from sonarsentinel.preprocess.pipeline import preprocess_chunk  # noqa: E402


def _to_u8(x: np.ndarray) -> np.ndarray:
    v = np.log1p(np.asarray(x, dtype=np.float64))
    lo, hi = np.percentile(v, [1, 99.5])
    return np.clip((v - lo) / max(hi - lo, 1e-9) * 255, 0, 255).astype(np.uint8)


def _waterfall(port: np.ndarray, stbd: np.ndarray) -> np.ndarray:
    return np.hstack([port[:, ::-1], stbd])


def _fit(image: np.ndarray, width: int = 1200, height: int = 1400) -> np.ndarray:
    import cv2

    h, w = image.shape[:2]
    scale = min(width / w, height / h, 1.0)
    return cv2.resize(
        image, (max(1, int(w * scale)), max(1, int(h * scale))), interpolation=cv2.INTER_AREA
    )


def run_qa(
    source: Path, out: Path, max_pings: int = 2000, epsg: str | None = None
) -> dict[str, Any]:
    import cv2

    config = load_config()
    pre = config["preprocess"]
    log = read_source(source, epsg=epsg, allow_no_gps=True)
    log = slice_log(log, 0, min(log.n_pings, max_pings))
    target = out / source.stem
    target.mkdir(parents=True, exist_ok=True)
    assert log.port is not None and log.starboard is not None
    n_samples = log.sonar.samples_per_channel

    slant = log.nav["slant_range_m"].to_numpy(np.float64)
    bt = pre["bottom_tracking"]
    track = track_bottom(
        log.port,
        log.starboard,
        slant,
        threshold_k=bt["threshold_k"],
        median_window=bt["median_window"],
    )
    raw = cv2.cvtColor(_to_u8(_waterfall(log.port, log.starboard)), cv2.COLOR_GRAY2BGR)
    recorded = log.nav["altitude_m"].to_numpy(np.float64)
    for row in range(log.n_pings):
        for sample, colour in ((track.first_return[row], (0, 0, 255)),
                               (recorded[row] / slant[row] * n_samples, (0, 255, 0))):  # fmt: skip
            if np.isfinite(sample) and 0 <= sample < n_samples:
                s = int(sample)
                raw[row, n_samples - 1 - s] = colour
                raw[row, n_samples + s] = colour
    near = max(50, int(n_samples * 0.15))  # near-nadir samples, where the bottom track is visible
    cv2.imwrite(str(target / "1_raw_bottom.png"), _fit(raw[:, n_samples - near : n_samples + near]))

    dropout = detect_dropouts(
        log.port, log.starboard, min_row_std_ratio=pre["dropout"]["min_row_std_ratio"]
    )
    repaired = repair_dropouts(
        log.port, log.starboard, dropout, max_gap=pre["dropout"]["max_inpaint_gap_pings"]
    )
    gain = normalize_gain(repaired.port, repaired.starboard,
                          along_track_window_pings=pre["gain"]["along_track_window_pings"],
                          clip_percentiles=pre["gain"]["clip_percentiles"])  # fmt: skip
    assert gain.port is not None and gain.starboard is not None
    cv2.imwrite(str(target / "2_gain.png"), _fit(_waterfall(gain.port, gain.starboard)))

    chunk = preprocess_chunk(log, config)
    cv2.imwrite(str(target / "3_ground.png"), _fit(chunk.image))
    r0 = max(0, chunk.image.shape[0] // 2 - 200)
    c0 = max(0, chunk.nadir_col + 50)
    crop = chunk.image_3ch[r0 : r0 + 400, c0 : c0 + 400]
    cv2.imwrite(str(target / "4_channels.png"), np.hstack([crop[..., i] for i in range(3)]))

    masks = np.zeros((*chunk.image.shape, 3), np.uint8)
    masks[chunk.masks["dropout"]] = (0, 0, 255)
    masks[chunk.masks["motion"]] = (0, 255, 255)
    masks[:, chunk.masks["near_nadir"]] = (255, 0, 0)
    overlay = cv2.addWeighted(cv2.cvtColor(chunk.image, cv2.COLOR_GRAY2BGR), 0.6, masks, 0.4, 0)
    cv2.imwrite(str(target / "5_masks.png"), _fit(overlay))

    summary: dict[str, Any] = {
        "source": log.source_file, "pings": log.n_pings, "samples_per_channel": n_samples,
        "image_shape": list(chunk.image.shape), "nadir_col": chunk.nadir_col,
        "warnings": chunk.warnings, "quality_events": len(chunk.quality_events),
        "dropout_pings": int(dropout.sum()), "masked_pings": int(repaired.masked.sum()),
        "tracked_altitude_m": _stats(track.altitude_m), "recorded_altitude_m": _stats(recorded),
        "altitude_used_m": _stats(chunk.altitude_m),
    }  # fmt: skip
    if log.has_navigation:
        cleaned = clean_navigation(log.nav)
        summary["invalid_fixes"] = int(cleaned.invalid.sum())
        canvas = np.full((800, 800, 3), 255, np.uint8)
        lat_r, lon_r = log.nav["lat"].to_numpy(), log.nav["lon"].to_numpy()
        lat_c, lon_c = cleaned.nav["lat"].to_numpy(), cleaned.nav["lon"].to_numpy()
        ok = np.isfinite(lat_r) & np.isfinite(lon_r) & ~cleaned.invalid
        lo_lat, hi_lat = np.nanmin(lat_c), np.nanmax(lat_c)
        lo_lon, hi_lon = np.nanmin(lon_c), np.nanmax(lon_c)
        span = max(hi_lat - lo_lat, (hi_lon - lo_lon) * np.cos(np.radians(lo_lat)), 1e-9)

        def xy(la: np.ndarray, lo: np.ndarray) -> np.ndarray:
            x = (lo - lo_lon) * np.cos(np.radians(lo_lat)) / span * 740 + 30
            y = 770 - (la - lo_lat) / span * 740
            return np.stack([x, y], axis=1).astype(np.int32)

        for x, y in xy(lat_r[ok], lon_r[ok]):
            cv2.circle(canvas, (int(x), int(y)), 2, (160, 160, 160), -1)
        cv2.polylines(canvas, [xy(lat_c, lon_c)], False, (0, 160, 0), 2)
        cv2.imwrite(str(target / "6_track.png"), canvas)
    (target / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    return summary


def _stats(values: np.ndarray) -> dict[str, float | None]:
    v = np.asarray(values, dtype=np.float64)
    v = v[np.isfinite(v)]
    if not v.size:
        return {"median": None, "p5": None, "p95": None}
    return {"median": round(float(np.median(v)), 2), "p5": round(float(np.percentile(v, 5)), 2),
            "p95": round(float(np.percentile(v, 95)), 2)}  # fmt: skip


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("sources", type=Path, nargs="+")
    parser.add_argument("--out", type=Path, default=ROOT / "data" / "results" / "qa")
    parser.add_argument("--max-pings", type=int, default=2000)
    parser.add_argument("--utm-epsg", default=None)
    args = parser.parse_args()
    for source in args.sources:
        print(json.dumps(run_qa(source, args.out, args.max_pings, args.utm_epsg), indent=2))


if __name__ == "__main__":
    main()
