"""ST-037 validation tooling (scripts/validate_charted_wreck.py) on synthetic truth and reports."""

import sys
from pathlib import Path

import pytest
from pyproj import Geod

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))

from validate_charted_wreck import (  # noqa: E402
    distance_m,
    load_truth,
    match_object,
    summarize,
    to_markdown,
)

GEOD = Geod(ellps="WGS84")
BASE = (13.08, 80.30)


def _offset(north_m: float) -> tuple[float, float]:
    lon, lat, _ = GEOD.fwd(BASE[1], BASE[0], 0.0, north_m)
    return lat, lon


def _det(i: int, cls: str, north_m: float, uncertainty: float | None = 2.0) -> dict:
    lat, lon = _offset(north_m)
    return {
        "detection_id": f"SRV-20260914-001-D{i:04d}",
        "class": cls,
        "confidence": 80.0,
        "position": {"lat": lat, "lon": lon, "uncertainty_m": uncertainty},
    }


def test_nearest_allowed_class_error_and_two_sigma() -> None:
    wreck = {"name": "W1", "lat": BASE[0], "lon": BASE[1], "chart_quality": "surveyed"}
    detections = [_det(1, "shipwreck", 6.0), _det(2, "cylinder", 1.0), _det(3, "shipwreck", 100.0)]
    detections.append({**_det(4, "shipwreck", 0.5), "position": {"lat": None, "lon": None}})

    row = match_object(wreck, detections, classes={"shipwreck"}, max_distance_m=50.0)
    assert row["detection_id"].endswith("D0001")
    assert row["error_m"] == pytest.approx(6.0, abs=0.05)
    assert row["within_2_sigma"] is False

    any_class = match_object(wreck, detections, classes=None, max_distance_m=50.0)
    assert any_class["class"] == "cylinder" and any_class["within_2_sigma"] is True

    nothing = match_object(wreck, detections, classes={"pipe"}, max_distance_m=50.0)
    assert nothing["detection_id"] is None and nothing["error_m"] is None


def test_summary_and_markdown() -> None:
    wrecks = [
        {"name": "W1", "lat": BASE[0], "lon": BASE[1], "chart_quality": None},
        {"name": "W2", "lat": _offset(1000.0)[0], "lon": BASE[1], "chart_quality": None},
    ]
    detections = [_det(1, "shipwreck", 4.0), _det(2, "shipwreck", 1008.0, uncertainty=None)]
    rows = [match_object(w, detections, classes={"shipwreck"}, max_distance_m=50.0) for w in wrecks]
    summary = summarize(rows)
    assert summary["matched"] == 2 and summary["median_error_m"] == pytest.approx(6.0, abs=0.1)
    assert summary["max_error_m"] == pytest.approx(8.0, abs=0.1)
    assert summary["within_2_sigma"] == "1/1" and summary["meets_target"] is True
    table = to_markdown(rows, summary)
    assert "| W1 |" in table and "Matched 2/2" in table
    assert distance_m(BASE[0], BASE[1], BASE[0], BASE[1]) == 0.0


def test_truth_formats() -> None:
    charted = load_truth({"wrecks": [{"name": "SS X", "lat": 13.1, "lon": 80.3}]})
    assert charted == [{"name": "SS X", "lat": 13.1, "lon": 80.3, "chart_quality": None}]
    demo = load_truth(
        {"synthetic": True, "class": "ghost_net", "approx_lat": 13.09, "approx_lon": 80.30}
    )
    assert demo[0]["name"] == "ghost_net (synthetic)"
    assert demo[0]["chart_quality"] == "synthetic ground truth"
    with pytest.raises(ValueError, match="Truth file"):
        load_truth({"something": 1})
