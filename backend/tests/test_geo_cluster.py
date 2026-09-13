"""ST-038 cross-line clustering and persistence (TC-GEO-013)."""

import copy
from typing import Any

import pytest
from pyproj import Geod

from sonarsentinel.geo.cluster import cluster_detections, haversine_m, persistence_score

GEOD = Geod(ellps="WGS84")
LAT0, LON0 = 13.08, 80.29


def _offset(east_m: float) -> tuple[float, float]:
    lon, lat, _ = GEOD.fwd(LON0, LAT0, 90.0, east_m)
    return round(lat, 7), round(lon, 7)


def _det(
    det_id: str, east_m: float | None, source: str, *, cls: str = "cylinder", conf: float = 60.0
) -> dict[str, Any]:
    lat, lon = _offset(east_m) if east_m is not None else (None, None)
    return {
        "detection_id": det_id,
        "class": cls,
        "confidence": conf,
        "position": {"lat": lat, "lon": lon, "depth_m": 10.0, "uncertainty_m": None},
        "sonar_ref": {"source_file": source, "side": "starboard"},
        "scores": {"detector": conf / 100, "fused": conf / 100},
        "quality_flags": [] if east_m is not None else ["NOT_GEOTAGGED"],
        "n_views": 1,
    }


def test_persistence_score() -> None:
    assert persistence_score(1) == 0.5
    assert persistence_score(2) == 0.75
    assert persistence_score(3) == 0.875


def test_haversine_matches_geod_at_small_scale() -> None:
    lat, lon = _offset(5.0)
    assert haversine_m(LAT0, LON0, lat, lon) == pytest.approx(5.0, rel=0.005)


def test_tc_geo_013_two_lines_merged_and_averaged() -> None:
    a = _det("SRV-1-D0001", 0.0, "line_01.xtf", conf=70.0)
    b = _det("SRV-1-D0002", 3.0, "line_02.xtf", conf=85.0)
    before = copy.deepcopy([a, b])
    result = cluster_detections([a, b], radius_m=5.0)
    assert [a, b] == before  # input untouched
    assert len(result.detections) == 1
    kept = result.detections[0]
    assert kept["detection_id"] == "SRV-1-D0002"  # higher confidence
    assert kept["n_views"] == 2 and kept["scores"]["persistence"] == 0.75
    assert result.removed == {"SRV-1-D0001": "SRV-1-D0002"}
    mid_lat, mid_lon = _offset(1.5)
    assert kept["position"]["lat"] == pytest.approx(mid_lat, abs=2e-6)
    assert kept["position"]["lon"] == pytest.approx(mid_lon, abs=2e-6)
    assert kept["confidence"] == 85.0  # rescoring is the caller's job


def test_eight_metres_apart_not_merged() -> None:
    result = cluster_detections(
        [_det("D1", 0.0, "line_01.xtf"), _det("D2", 8.0, "line_02.xtf")], radius_m=5.0
    )
    assert [d["detection_id"] for d in result.detections] == ["D1", "D2"]
    assert all(d["n_views"] == 1 and d["scores"]["persistence"] == 0.5 for d in result.detections)
    assert result.removed == {}


def test_different_class_not_merged() -> None:
    result = cluster_detections(
        [_det("D1", 0.0, "a.xtf"), _det("D2", 1.0, "b.xtf", cls="pipe")], radius_m=5.0
    )
    assert len(result.detections) == 2


def test_same_source_file_not_merged() -> None:
    result = cluster_detections([_det("D1", 0.0, "a.xtf"), _det("D2", 1.0, "a.xtf")], radius_m=5.0)
    assert len(result.detections) == 2 and result.removed == {}


def test_not_geotagged_passes_through() -> None:
    lone = _det("D9", None, "img.png")
    result = cluster_detections([lone, _det("D1", 0.0, "a.xtf")], radius_m=5.0)
    out = result.detections[0]
    assert out["detection_id"] == "D9" and out["position"]["lat"] is None
    assert out["n_views"] == 1 and out["scores"]["persistence"] == 0.5


def test_chain_links_three_lines() -> None:
    dets = [
        _det("D1", 0.0, "a.xtf", conf=50.0),
        _det("D2", 4.0, "b.xtf", conf=40.0),
        _det("D3", 8.0, "c.xtf", conf=50.0),
    ]
    result = cluster_detections(dets, radius_m=5.0)
    assert len(result.detections) == 1
    kept = result.detections[0]
    assert kept["detection_id"] == "D1"  # tie on confidence → lowest id
    assert kept["n_views"] == 3 and kept["scores"]["persistence"] == 0.875
    assert result.removed == {"D2": "D1", "D3": "D1"}
    mid_lat, mid_lon = _offset(4.0)
    assert kept["position"]["lon"] == pytest.approx(mid_lon, abs=2e-6)
