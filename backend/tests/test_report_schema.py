"""Report schema 1.0 (Gate G1 contract): the documented example is valid; key rules are enforced."""

import copy
import json
from importlib import resources
from typing import Any

import pytest

jsonschema = pytest.importorskip("jsonschema")


def _load(name: str) -> dict[str, Any]:
    text = resources.files("sonarsentinel.report").joinpath("schema", name).read_text("utf-8")
    data: dict[str, Any] = json.loads(text)
    return data


@pytest.fixture(scope="module")
def validator() -> Any:
    schema = _load("report-1.0.schema.json")
    jsonschema.Draft202012Validator.check_schema(schema)
    return jsonschema.Draft202012Validator(schema)


@pytest.fixture
def report() -> dict[str, Any]:
    return copy.deepcopy(_load("example-report-1.0.json"))


def _errors(validator: Any, doc: dict[str, Any]) -> list[str]:
    return [e.message for e in validator.iter_errors(doc)]


def test_example_report_is_valid(validator: Any, report: dict[str, Any]) -> None:
    assert _errors(validator, report) == []


def test_not_geotagged_detection(validator: Any, report: dict[str, Any]) -> None:
    """AC-02 / TC-ING-011: null lat/lon and a pixel box are required together."""
    det = report["detections"][0]
    det["quality_flags"] = ["NOT_GEOTAGGED"]
    det["position"].update(lat=None, lon=None)
    det["footprint"] = None
    assert _errors(validator, report)  # pixel_bbox missing
    det["sonar_ref"]["pixel_bbox"] = [120, 40, 188, 96]
    report["survey"]["bbox"] = None
    assert _errors(validator, report) == []


def test_geotagged_detection_needs_coordinates(validator: Any, report: dict[str, Any]) -> None:
    report["detections"][0]["position"]["lat"] = None
    assert _errors(validator, report)


@pytest.mark.parametrize(
    ("path", "value"),
    [
        (("detections", 0, "class"), "tyre"),
        (("detections", 0, "confidence"), 101),
        (("detections", 0, "alert_tier"), "urgent"),
        (("detections", 0, "position", "lat"), 91.0),
        (("detections", 0, "scores", "fused"), 1.2),
        (("detections", 0, "quality_flags"), ["UNKNOWN_FLAG"]),
        (("detections", 0, "detection_id"), "D3"),
        (("report_version",), "1.1"),
        (("survey", "datum"), "ED50"),
    ],
)
def test_invalid_values_are_rejected(
    validator: Any, report: dict[str, Any], path: tuple[Any, ...], value: object
) -> None:
    target: Any = report
    for key in path[:-1]:
        target = target[key]
    target[path[-1]] = value
    assert _errors(validator, report)


def test_rejection_needs_reason(validator: Any, report: dict[str, Any]) -> None:
    review = report["detections"][0]["review"]
    review["status"] = "rejected"
    assert _errors(validator, report)
    review["reject_reason"] = "rock"
    assert _errors(validator, report) == []
