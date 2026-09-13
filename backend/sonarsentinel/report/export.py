"""Report files: JSON and CSV (ST-070/071), GeoJSON and KML (ST-072).

CSV columns and conventions follow ``docs/architecture/06-data-models.md`` §3.1: one row per
detection, 6-decimal coordinates, ``;``-separated quality flags, empty cells for null. GeoJSON is
RFC 7946 (``[lon, lat]``, counter-clockwise rings): a ``Point`` per geotagged detection, its
footprint ``Polygon`` and the survey track. KML 2.2 has one folder per class with class-coloured
styles and an HTML description per placemark (ADR-018 §8). Detections without a position are left
out of the geographic formats.
"""

from __future__ import annotations

import csv
import io
import json
import xml.etree.ElementTree as ET
from collections.abc import Iterable, Sequence
from pathlib import Path
from typing import Any

from sonarsentinel.errors import ValidationError
from sonarsentinel.geo.formatting import to_dms

SUPPORTED_FORMATS = ("json", "csv", "geojson", "kml")
GEO_FORMATS = ("geojson", "kml")
MEDIA_TYPES = {
    "json": "application/json",
    "csv": "text/csv",
    "geojson": "application/geo+json",
    "kml": "application/vnd.google-earth.kml+xml",
}
KML_NS = "http://www.opengis.net/kml/2.2"
CLASS_COLOURS = {  # frontend/src/styles/tokens.css
    "ghost_net": "#e5484d",
    "shipwreck": "#8e4ec6",
    "pipe": "#f76b15",
    "cylinder": "#ffb224",
    "debris_other": "#0090ff",
    "unknown_anomaly": "#d6409f",
}
TRACK_COLOUR = "#1b1d24"

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

TrackSegment = dict[str, Any]  # {"points": [[lat, lon], ...], "ping_start": int, "ping_end": int}


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


# -- geometry helpers ------------------------------------------------------------------------------


def is_geotagged(det: dict[str, Any]) -> bool:
    position = det.get("position") or {}
    return position.get("lat") is not None and position.get("lon") is not None


def report_is_geotagged(report: dict[str, Any]) -> bool:
    """True when the survey has a map position (bbox) or any detection has coordinates."""
    return report["survey"].get("bbox") is not None or any(
        is_geotagged(d) for d in report["detections"]
    )


def track_points(segments: Iterable[TrackSegment]) -> list[tuple[int, float, float]]:
    """``(ping, lat, lon)`` per track point in ping order (pings spread evenly per segment)."""
    points: list[tuple[int, float, float]] = []
    for segment in segments:
        coords = segment.get("points") or []
        if not coords:
            continue
        start = int(segment.get("ping_start") or 0)
        end_value = segment.get("ping_end")
        end = start if end_value is None else int(end_value)
        n = len(coords)
        for i, (lat, lon) in enumerate(coords):
            ping = start + round(i * (end - start) / (n - 1)) if n > 1 else start
            points.append((ping, float(lat), float(lon)))
    points.sort(key=lambda p: p[0])
    unique: list[tuple[int, float, float]] = []
    for point in points:
        if not unique or (point[1], point[2]) != (unique[-1][1], unique[-1][2]):
            unique.append(point)
    return unique


def track_coords(segments: Iterable[TrackSegment]) -> list[list[float]]:
    """Track as ``[[lat, lon], ...]`` in ping order."""
    return [[lat, lon] for _, lat, lon in track_points(segments)]


def _lonlat(coords: Sequence[Sequence[float]] | None) -> list[list[float]]:
    return [[round(float(lon), 6), round(float(lat), 6)] for lat, lon in coords or []]


def _ring(footprint: Sequence[Sequence[float]] | None) -> list[list[float]]:
    """Closed counter-clockwise ``[lon, lat]`` ring (RFC 7946 right-hand rule), or ``[]``."""
    ring = _lonlat(footprint)
    if len(ring) < 3:
        return []
    area = sum(
        ring[i][0] * ring[(i + 1) % len(ring)][1] - ring[(i + 1) % len(ring)][0] * ring[i][1]
        for i in range(len(ring))
    )
    if area < 0:
        ring.reverse()
    ring.append(list(ring[0]))
    return ring


def track_feature_collection(
    segments: Iterable[TrackSegment], quality_events: Iterable[dict[str, Any]] = ()
) -> dict[str, Any]:
    """Track ``LineString`` plus one ``LineString`` per quality event (ADR-018 §5)."""
    points = track_points(segments)
    features: list[dict[str, Any]] = []
    if len(points) >= 2:
        features.append(
            {
                "type": "Feature",
                "properties": {
                    "segment": "track",
                    "ping_start": points[0][0],
                    "ping_end": points[-1][0],
                },
                "geometry": {
                    "type": "LineString",
                    "coordinates": [[round(lon, 6), round(lat, 6)] for _, lat, lon in points],
                },
            }
        )
    for event in quality_events:
        start, end = event.get("ping_start"), event.get("ping_end")
        if start is None or end is None or len(points) < 2:
            continue
        inside = [p for p in points if start <= p[0] <= end]
        if len(inside) < 2:
            before = [p for p in points if p[0] < start][-1:]
            after = [p for p in points if p[0] > end][:1]
            inside = before + inside + after
        if len(inside) < 2:
            continue
        features.append(
            {
                "type": "Feature",
                "properties": {
                    "segment": "quality",
                    "code": event.get("code"),
                    "ping_start": int(start),
                    "ping_end": int(end),
                },
                "geometry": {
                    "type": "LineString",
                    "coordinates": [[round(lon, 6), round(lat, 6)] for _, lat, lon in inside],
                },
            }
        )
    return {"type": "FeatureCollection", "features": features}


# -- GeoJSON ---------------------------------------------------------------------------------------


def to_geojson(
    report: dict[str, Any], track: Sequence[Sequence[float]] | None = None
) -> dict[str, Any]:
    """RFC 7946 FeatureCollection; ``track`` is ``[[lat, lon], ...]``."""
    survey_id = report["survey"]["survey_id"]
    features: list[dict[str, Any]] = []
    line = _lonlat(track)
    if len(line) >= 2:
        features.append(
            {
                "type": "Feature",
                "properties": {"feature_kind": "track", "survey_id": survey_id},
                "geometry": {"type": "LineString", "coordinates": line},
            }
        )
    for det in report["detections"]:
        if not is_geotagged(det):
            continue
        position, dims = det["position"], det.get("dimensions") or {}
        features.append(
            {
                "type": "Feature",
                "properties": {
                    "feature_kind": "detection",
                    "detection_id": det["detection_id"],
                    "class": det["class"],
                    "confidence": det["confidence"],
                    "alert_tier": det["alert_tier"],
                    "length_m": dims.get("length_m"),
                    "width_m": dims.get("width_m"),
                    "depth_m": position.get("depth_m"),
                    "review_status": (det.get("review") or {}).get("status", "pending"),
                },
                "geometry": {
                    "type": "Point",
                    "coordinates": [
                        round(float(position["lon"]), 6),
                        round(float(position["lat"]), 6),
                    ],
                },
            }
        )
        ring = _ring(det.get("footprint"))
        if ring:
            features.append(
                {
                    "type": "Feature",
                    "properties": {
                        "feature_kind": "footprint",
                        "detection_id": det["detection_id"],
                        "class": det["class"],
                    },
                    "geometry": {"type": "Polygon", "coordinates": [ring]},
                }
            )
    return {"type": "FeatureCollection", "features": features}


# -- KML -------------------------------------------------------------------------------------------


def kml_colour(hex_rgb: str, alpha: str = "ff") -> str:
    """``#rrggbb`` → KML ``aabbggrr``."""
    value = hex_rgb.lstrip("#").lower()
    return f"{alpha}{value[4:6]}{value[2:4]}{value[0:2]}"


def _sub(parent: ET.Element, tag: str, text: str | None = None) -> ET.Element:
    element = ET.SubElement(parent, f"{{{KML_NS}}}{tag}")
    if text is not None:
        element.text = text
    return element


def _kml_coords(coords: Iterable[Sequence[float]]) -> str:
    return " ".join(f"{float(lon):.6f},{float(lat):.6f},0" for lat, lon in coords)


def _description(det: dict[str, Any]) -> str:
    position, dims = det["position"], det.get("dimensions") or {}
    lat, lon = float(position["lat"]), float(position["lon"])
    size = (
        f"{dims['length_m']} × {dims['width_m']} m"
        if dims.get("length_m") is not None and dims.get("width_m") is not None
        else "n/a"
    )
    depth = f"{position['depth_m']} m" if position.get("depth_m") is not None else "n/a"
    rows = [
        ("Class", det["class"]),
        ("Confidence", f"{float(det['confidence']):.1f}%"),
        ("Tier", det["alert_tier"]),
        ("Size", size),
        ("Depth", depth),
        ("Latitude", f"{lat:.6f} ({to_dms(lat, 'lat')})"),
        ("Longitude", f"{lon:.6f} ({to_dms(lon, 'lon')})"),
        ("Detection", det["detection_id"]),
    ]
    cells = "".join(f"<tr><th>{k}</th><td>{v}</td></tr>" for k, v in rows)
    return f"<table>{cells}</table>"


def to_kml(report: dict[str, Any], track: Sequence[Sequence[float]] | None = None) -> str:
    """KML 2.2 document; ``track`` is ``[[lat, lon], ...]``."""
    ET.register_namespace("", KML_NS)
    survey_id = report["survey"]["survey_id"]
    root = ET.Element(f"{{{KML_NS}}}kml")
    document = _sub(root, "Document")
    _sub(document, "name", f"SonarSentinel {survey_id}")

    geotagged = [d for d in report["detections"] if is_geotagged(d)]
    classes = [c for c in CLASS_COLOURS if any(d["class"] == c for d in geotagged)]
    classes += sorted({d["class"] for d in geotagged} - set(CLASS_COLOURS))
    for cls in classes:
        colour = CLASS_COLOURS.get(cls, "#8b8d98")
        style = _sub(document, "Style")
        style.set("id", f"class-{cls}")
        _sub(_sub(style, "IconStyle"), "color", kml_colour(colour))
        line = _sub(style, "LineStyle")
        _sub(line, "color", kml_colour(colour))
        _sub(line, "width", "2")
        _sub(_sub(style, "PolyStyle"), "color", kml_colour(colour, "66"))

    if track is not None and len(track) >= 2:
        placemark = _sub(document, "Placemark")
        _sub(placemark, "name", "Track")
        line_style = _sub(_sub(_sub(placemark, "Style"), "LineStyle"), "color", None)
        line_style.text = kml_colour(TRACK_COLOUR)
        _sub(_sub(placemark, "LineString"), "coordinates", _kml_coords(track))

    for cls in classes:
        folder = _sub(document, "Folder")
        _sub(folder, "name", cls)
        for det in geotagged:
            if det["class"] != cls:
                continue
            placemark = _sub(folder, "Placemark")
            _sub(placemark, "name", det["detection_id"])
            _sub(placemark, "styleUrl", f"#class-{cls}")
            _sub(placemark, "description", _description(det))
            position = det["position"]
            geometry = _sub(placemark, "MultiGeometry")
            _sub(
                _sub(geometry, "Point"),
                "coordinates",
                _kml_coords([[position["lat"], position["lon"]]]),
            )
            footprint = det.get("footprint")
            if footprint and len(footprint) >= 3:
                ring = [*footprint, footprint[0]]
                boundary = _sub(_sub(geometry, "Polygon"), "outerBoundaryIs")
                _sub(_sub(boundary, "LinearRing"), "coordinates", _kml_coords(ring))
    body = ET.tostring(root, encoding="unicode")
    return '<?xml version="1.0" encoding="UTF-8"?>\n' + body + "\n"


# -- files -----------------------------------------------------------------------------------------


def serialize(
    report: dict[str, Any], fmt: str, *, track: Sequence[Sequence[float]] | None = None
) -> str:
    """Report text in one of :data:`SUPPORTED_FORMATS`."""
    if fmt == "json":
        return json.dumps(report, indent=2, ensure_ascii=False)
    if fmt == "csv":
        return to_csv(report)
    if fmt == "geojson":
        return json.dumps(to_geojson(report, track), ensure_ascii=False)
    if fmt == "kml":
        return to_kml(report, track)
    raise ValidationError(f"Unsupported report format: {fmt}", supported=list(SUPPORTED_FORMATS))


def write_reports(
    report: dict[str, Any],
    out_dir: str | Path,
    formats: tuple[str, ...] | list[str] = ("json",),
    *,
    track: Sequence[Sequence[float]] | None = None,
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
    for fmt in SUPPORTED_FORMATS:
        if fmt in formats:
            paths[fmt] = target / f"report.{fmt}"
            paths[fmt].write_text(serialize(report, fmt, track=track), encoding="utf-8")
    return paths
