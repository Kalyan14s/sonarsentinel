"""ST-037 geolocation validation against charted positions (Test Plan §6.2.2, TC-GEO-012).

For each charted object in ``--truth``, the nearest detection in the report(s) — of an allowed
class, within ``--max-distance-m`` — is taken as the match. Reports the horizontal error (WGS84
geodesic distance, metres) per object, the median and maximum error, and whether each error is
within twice the detection's reported ``uncertainty_m`` (04-geotagging §9).

Truth formats:

* ``{"wrecks": [{"name": ..., "lat": ..., "lon": ..., "chart_quality": ...}]}``
* the demo ground truth (``demo/harbour_synthetic.truth.json``: ``approx_lat``/``approx_lon``).

    python scripts/validate_charted_wreck.py --report results/SRV-.../report.json \
        --truth wrecks.json --classes shipwreck --out validation.json
"""

from __future__ import annotations

import argparse
import json
import statistics
from pathlib import Path
from typing import Any

from pyproj import Geod

GEOD = Geod(ellps="WGS84")


def load_truth(data: dict[str, Any]) -> list[dict[str, Any]]:
    """Charted objects as ``{name, lat, lon, chart_quality}``."""
    if "wrecks" in data:
        return [
            {
                "name": str(w.get("name", f"wreck {i + 1}")),
                "lat": float(w["lat"]),
                "lon": float(w["lon"]),
                "chart_quality": w.get("chart_quality"),
            }
            for i, w in enumerate(data["wrecks"])
        ]
    if "approx_lat" in data and "approx_lon" in data:
        return [
            {
                "name": str(data.get("class", "target"))
                + (" (synthetic)" if data.get("synthetic") else ""),
                "lat": float(data["approx_lat"]),
                "lon": float(data["approx_lon"]),
                "chart_quality": "synthetic ground truth" if data.get("synthetic") else None,
            }
        ]
    raise ValueError("Truth file needs a 'wrecks' list or approx_lat/approx_lon")


def distance_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    return float(GEOD.inv(lon1, lat1, lon2, lat2)[2])


def match_object(
    obj: dict[str, Any],
    detections: list[dict[str, Any]],
    *,
    classes: set[str] | None,
    max_distance_m: float,
) -> dict[str, Any]:
    """Nearest allowed detection within ``max_distance_m`` (``detection_id`` None if none)."""
    best: tuple[float, dict[str, Any]] | None = None
    for det in detections:
        lat, lon = det["position"]["lat"], det["position"]["lon"]
        if lat is None or lon is None or (classes is not None and det["class"] not in classes):
            continue
        d = distance_m(obj["lat"], obj["lon"], float(lat), float(lon))
        if d <= max_distance_m and (best is None or d < best[0]):
            best = (d, det)
    row: dict[str, Any] = {**obj, "detection_id": None, "class": None, "confidence": None}
    if best is None:
        return row | {"error_m": None, "uncertainty_m": None, "within_2_sigma": None}
    error, det = best
    uncertainty = det["position"].get("uncertainty_m")
    return row | {
        "detection_id": det["detection_id"],
        "class": det["class"],
        "confidence": det["confidence"],
        "error_m": round(error, 2),
        "uncertainty_m": uncertainty,
        "within_2_sigma": None if uncertainty is None else error <= 2 * float(uncertainty),
    }


def summarize(rows: list[dict[str, Any]]) -> dict[str, Any]:
    errors = [r["error_m"] for r in rows if r["error_m"] is not None]
    within = [r["within_2_sigma"] for r in rows if r["within_2_sigma"] is not None]
    return {
        "objects": len(rows),
        "matched": len(errors),
        "median_error_m": round(statistics.median(errors), 2) if errors else None,
        "max_error_m": round(max(errors), 2) if errors else None,
        "within_2_sigma": f"{sum(within)}/{len(within)}" if within else None,
        "target_median_m": 10.0,
        "meets_target": (statistics.median(errors) <= 10.0) if errors else None,
    }


def to_markdown(rows: list[dict[str, Any]], summary: dict[str, Any]) -> str:
    lines = [
        "| Object | Chart quality | Detection | Class | Confidence | Error (m) | ±σ (m) | ≤ 2σ |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for r in rows:
        lines.append(
            f"| {r['name']} | {r['chart_quality'] or '—'} | {r['detection_id'] or 'no match'} | "
            f"{r['class'] or '—'} | {r['confidence'] if r['confidence'] is not None else '—'} | "
            f"{r['error_m'] if r['error_m'] is not None else '—'} | "
            f"{r['uncertainty_m'] if r['uncertainty_m'] is not None else '—'} | "
            f"{'yes' if r['within_2_sigma'] else ('no' if r['within_2_sigma'] is False else '—')} |"
        )
    lines += [
        "",
        f"Matched {summary['matched']}/{summary['objects']}; median error "
        f"{summary['median_error_m']} m, max {summary['max_error_m']} m "
        f"(target median ≤ {summary['target_median_m']:g} m); "
        f"within 2σ: {summary['within_2_sigma']}.",
    ]
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--report", type=Path, nargs="+", required=True)
    parser.add_argument("--truth", type=Path, required=True)
    parser.add_argument("--classes", default="shipwreck", help="Comma-separated, or 'any'")
    parser.add_argument("--max-distance-m", type=float, default=50.0)
    parser.add_argument("--out", type=Path, default=None)
    args = parser.parse_args()

    detections: list[dict[str, Any]] = []
    for path in args.report:
        detections += json.loads(path.read_text(encoding="utf-8"))["detections"]
    truth = load_truth(json.loads(args.truth.read_text(encoding="utf-8")))
    classes = None if args.classes == "any" else {c.strip() for c in args.classes.split(",")}
    rows = [
        match_object(obj, detections, classes=classes, max_distance_m=args.max_distance_m)
        for obj in truth
    ]
    summary = summarize(rows)
    result = {"summary": summary, "objects": rows, "reports": [str(p) for p in args.report]}
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(result, indent=2), encoding="utf-8")
        args.out.with_suffix(".md").write_text(to_markdown(rows, summary), encoding="utf-8")
    print(to_markdown(rows, summary))


if __name__ == "__main__":
    main()
