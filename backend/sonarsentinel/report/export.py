"""Report files: JSON and CSV (P0). GeoJSON and KML follow in ST-072.

CSV columns and conventions follow ``docs/architecture/06-data-models.md`` §3.1: one row per
detection, 6-decimal coordinates, ``;``-separated quality flags, empty cells for null.
"""

from __future__ import annotations

import csv
import io
import json
from pathlib import Path
from typing import Any

from sonarsentinel.errors import ValidationError

SUPPORTED_FORMATS = ("json", "csv")

CSV_COLUMNS = (
    "detection_id",
    "survey_id",
    "class",
    "confidence",
    "alert_tier",
    "lat",
    "lon",
    "depth_m",
    "uncertainty_m",
    "length_m",
    "width_m",
    "area_m2",
    "height_m",
    "orientation_deg",
    "side",
    "ping_start",
    "ping_end",
    "ground_range_m",
    "time_utc",
    "n_views",
    "quality_flags",
    "review_status",
    "source_file",
)


def _cell(value: Any, decimals: int | None = None) -> str:
    if value is None:
        return ""
    if decimals is not None:
        return f"{float(value):.{decimals}f}"
    return str(value)


def detection_row(det: dict[str, Any], survey_id: str) -> dict[str, str]:
    pos, dims, ref = det["position"], det["dimensions"], det["sonar_ref"]
    return {
        "detection_id": det["detection_id"],
        "survey_id": survey_id,
        "class": det["class"],
        "confidence": _cell(det["confidence"], 1),
        "alert_tier": det["alert_tier"],
        "lat": _cell(pos["lat"], 6),
        "lon": _cell(pos["lon"], 6),
        "depth_m": _cell(pos["depth_m"]),
        "uncertainty_m": _cell(pos["uncertainty_m"]),
        "length_m": _cell(dims["length_m"]),
        "width_m": _cell(dims["width_m"]),
        "area_m2": _cell(dims["area_m2"]),
        "height_m": _cell(dims["height_m"]),
        "orientation_deg": _cell(det["orientation_deg"]),
        "side": ref["side"],
        "ping_start": _cell(ref.get("ping_start")),
        "ping_end": _cell(ref.get("ping_end")),
        "ground_range_m": _cell(ref.get("ground_range_m")),
        "time_utc": _cell(ref.get("time_utc")),
        "n_views": _cell(det["n_views"]),
        "quality_flags": ";".join(det["quality_flags"]),
        "review_status": det["review"]["status"],
        "source_file": ref["source_file"],
    }


def to_csv(report: dict[str, Any]) -> str:
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=CSV_COLUMNS, lineterminator="\n")
    writer.writeheader()
    survey_id = report["survey"]["survey_id"]
    for det in report["detections"]:
        writer.writerow(detection_row(det, survey_id))
    return buffer.getvalue()


def write_reports(
    report: dict[str, Any], out_dir: str | Path, formats: tuple[str, ...] | list[str] = ("json",)
) -> dict[str, Path]:
    """Write ``<out_dir>/<survey_id>/report.<format>`` files; returns their paths by format."""
    unknown = [f for f in formats if f not in SUPPORTED_FORMATS]
    if unknown:
        raise ValidationError(
            f"Unsupported report format(s): {', '.join(unknown)}",
            supported=list(SUPPORTED_FORMATS),
        )
    target = Path(out_dir) / report["survey"]["survey_id"]
    target.mkdir(parents=True, exist_ok=True)
    paths: dict[str, Path] = {}
    if "json" in formats:
        paths["json"] = target / "report.json"
        paths["json"].write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    if "csv" in formats:
        paths["csv"] = target / "report.csv"
        paths["csv"].write_text(to_csv(report), encoding="utf-8")
    return paths
