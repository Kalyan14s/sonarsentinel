"""ST-072 GeoJSON and KML export: TC-REP-003 (GeoJSON structure and positions) and the structural
part of TC-REP-004 (KML folders, styles, coordinates); plus the track helpers."""

from __future__ import annotations

import copy
import json
import xml.etree.ElementTree as ET
from importlib import resources
from pathlib import Path
from typing import Any

import pytest

from sonarsentinel.report.export import (
    KML_NS,
    kml_colour,
    report_is_geotagged,
    to_geojson,
    to_kml,
    track_coords,
    track_feature_collection,
    track_points,
    write_reports,
)

NS = {"k": KML_NS}


@pytest.fixture
def report() -> dict[str, Any]:
    text = resources.files("sonarsentinel.api").joinpath("fixtures", "mock_report.json")
    data: dict[str, Any] = json.loads(text.read_text("utf-8"))
    return data


def _signed_area(ring: list[list[float]]) -> float:
    return sum(
        ring[i][0] * ring[i + 1][1] - ring[i + 1][0] * ring[i][1] for i in range(len(ring) - 1)
    )


def test_geojson_points_footprints_and_track(report: dict[str, Any]) -> None:
    """TC-REP-003: RFC 7946 [lon, lat], closed counter-clockwise rings, one point per detection."""
    report = copy.deepcopy(report)
    report["detections"][0]["position"] |= {"lat": None, "lon": None}
    report["detections"][0]["footprint"] = None
    track = [[13.08, 80.31], [13.081, 80.312], [13.082, 80.314]]
    collection = to_geojson(report, track)
    assert collection["type"] == "FeatureCollection"
    kinds = [f["properties"]["feature_kind"] for f in collection["features"]]
    geotagged = [d for d in report["detections"] if d["position"]["lat"] is not None]
    assert kinds.count("detection") == len(geotagged) == len(report["detections"]) - 1
    assert kinds[0] == "track"
    line = collection["features"][0]["geometry"]
    assert line["type"] == "LineString" and line["coordinates"][0] == [80.31, 13.08]

    points = {
        f["properties"]["detection_id"]: f
        for f in collection["features"]
        if f["properties"]["feature_kind"] == "detection"
    }
    for det in geotagged:
        feature = points[det["detection_id"]]
        assert feature["geometry"]["coordinates"] == [
            det["position"]["lon"],
            det["position"]["lat"],
        ]
        assert feature["properties"]["class"] == det["class"]
        assert feature["properties"]["review_status"] == det["review"]["status"]
    polygons = [f for f in collection["features"] if f["properties"]["feature_kind"] == "footprint"]
    assert len(polygons) == sum(1 for d in geotagged if d["footprint"])
    for polygon in polygons:
        ring = polygon["geometry"]["coordinates"][0]
        assert ring[0] == ring[-1] and len(ring) >= 4
        assert _signed_area(ring) > 0
        lons = [p[0] for p in ring]
        assert all(79 < lon < 81 for lon in lons)  # lon first, not lat
    json.dumps(collection)


def test_kml_structure(report: dict[str, Any]) -> None:
    """TC-REP-004 (structure): class folders, class-coloured styles, lon,lat,0 coordinates, DMS."""
    track = [[13.08, 80.31], [13.081, 80.312]]
    text = to_kml(report, track)
    assert text.startswith('<?xml version="1.0" encoding="UTF-8"?>')
    root = ET.fromstring(text)
    assert root.tag == f"{{{KML_NS}}}kml"
    document = root.find("k:Document", NS)
    assert document is not None
    folders = {f.findtext("k:name", namespaces=NS): f for f in document.findall("k:Folder", NS)}
    assert set(folders) == {d["class"] for d in report["detections"]}
    styles = {s.get("id"): s for s in document.findall("k:Style", NS)}
    assert styles["class-ghost_net"].findtext("k:IconStyle/k:color", namespaces=NS) == "ff4d48e5"

    placemarks = {
        p.findtext("k:name", namespaces=NS): p
        for folder in folders.values()
        for p in folder.findall("k:Placemark", NS)
    }
    assert len(placemarks) == len(report["detections"])
    for det in report["detections"]:
        placemark = placemarks[det["detection_id"]]
        assert placemark.findtext("k:styleUrl", namespaces=NS) == f"#class-{det['class']}"
        coords = placemark.findtext("k:MultiGeometry/k:Point/k:coordinates", namespaces=NS)
        assert coords == f"{det['position']['lon']:.6f},{det['position']['lat']:.6f},0"
        description = placemark.findtext("k:description", namespaces=NS) or ""
        assert det["detection_id"] in description and "°" in description
        ring = placemark.findtext(
            "k:MultiGeometry/k:Polygon/k:outerBoundaryIs/k:LinearRing/k:coordinates", namespaces=NS
        )
        if det["footprint"]:
            corners = (ring or "").split()
            assert corners[0] == corners[-1] and len(corners) == len(det["footprint"]) + 1
    track_placemark = document.find("k:Placemark", NS)
    assert track_placemark is not None
    assert track_placemark.findtext("k:LineString/k:coordinates", namespaces=NS) == (
        "80.310000,13.080000,0 80.312000,13.081000,0"
    )


def test_kml_colour_order() -> None:
    assert kml_colour("#E5484D") == "ff4d48e5"
    assert kml_colour("#0090ff", "66") == "66ff9000"


def test_write_reports_four_formats(report: dict[str, Any], tmp_path: Path) -> None:
    paths = write_reports(report, tmp_path, ["json", "csv", "geojson", "kml"], track=None)
    assert sorted(paths) == ["csv", "geojson", "json", "kml"]
    assert all(p.is_file() and p.stat().st_size > 0 for p in paths.values())
    assert json.loads(paths["geojson"].read_text("utf-8"))["type"] == "FeatureCollection"
    ET.fromstring(paths["kml"].read_text("utf-8"))


def test_not_geotagged_report(report: dict[str, Any]) -> None:
    flat = copy.deepcopy(report)
    flat["survey"]["bbox"] = None
    for det in flat["detections"]:
        det["position"] |= {"lat": None, "lon": None}
    assert report_is_geotagged(report) and not report_is_geotagged(flat)
    assert to_geojson(flat)["features"] == []
    assert ET.fromstring(to_kml(flat)).find("k:Document/k:Folder", NS) is None


def test_track_points_and_quality_segments() -> None:
    segments = [
        {"points": [[13.002, 80.002], [13.003, 80.003]], "ping_start": 100, "ping_end": 199},
        {
            "points": [[13.0, 80.0], [13.001, 80.001], [13.002, 80.002]],
            "ping_start": 0,
            "ping_end": 100,
        },
    ]
    points = track_points(segments)
    assert [p[0] for p in points] == sorted(p[0] for p in points)
    assert track_coords(segments)[0] == [13.0, 80.0]
    assert len(track_coords(segments)) == 4  # the shared point at ping 100 appears once
    collection = track_feature_collection(
        segments,
        [
            {"code": "DROPOUT", "ping_start": 40, "ping_end": 60},
            {"code": "HIGH_MOTION", "ping_start": 90, "ping_end": 210},
            {"code": "DROPOUT", "ping_start": None, "ping_end": 5},
        ],
    )
    features = collection["features"]
    assert features[0]["properties"]["segment"] == "track"
    assert features[0]["geometry"]["coordinates"][0] == [80.0, 13.0]
    quality = [f for f in features if f["properties"]["segment"] == "quality"]
    assert [q["properties"]["code"] for q in quality] == ["DROPOUT", "HIGH_MOTION"]
    assert all(len(q["geometry"]["coordinates"]) >= 2 for q in quality)
    assert track_feature_collection([], [])["features"] == []
