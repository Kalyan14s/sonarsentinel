"""ST-084/086/072 over HTTP on a finished job: surveys, TC-API-004 (filters), TC-API-005 (review and
label store), TC-API-007 (downloads in four formats), TC-REP-007 (scopes), track and chips."""

from __future__ import annotations

import csv
import io
import json
import time
import xml.etree.ElementTree as ET
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("httpx")
pytest.importorskip("sqlalchemy")
pytest.importorskip("pyxtf")
pytest.importorskip("scipy")
pytest.importorskip("cv2")

from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import func, select  # noqa: E402
from tools.make_synthetic_xtf import write_synthetic_xtf  # noqa: E402

from sonarsentinel.api.filters import parse_query, query_detections  # noqa: E402
from sonarsentinel.api.main import API_PREFIX, create_app  # noqa: E402
from sonarsentinel.config import load_config  # noqa: E402
from sonarsentinel.storage.models import Review  # noqa: E402

API = API_PREFIX
FINISHED = {"completed", "completed_with_warnings", "failed", "cancelled"}
Setup = tuple[TestClient, dict[str, Any], Path]


def _wait(client: TestClient, job_id: str, timeout: float = 120.0) -> dict[str, Any]:
    deadline = time.monotonic() + timeout
    while True:
        body: dict[str, Any] = client.get(f"{API}/jobs/{job_id}").json()
        if body["status"] in FINISHED or time.monotonic() > deadline:
            return body
        time.sleep(0.1)


@pytest.fixture(scope="module")
def setup(tmp_path_factory: pytest.TempPathFactory) -> Iterator[Setup]:
    root = tmp_path_factory.mktemp("results_api")
    survey = write_synthetic_xtf(
        root / "line_results.xtf",
        n_pings=600,
        samples_per_side=400,
        step_m=0.1,
        targets=[(150, "starboard", 250), (430, "port", 300)],
        target_extent=(12, 30),
    )
    cfg = load_config()
    cfg["chunking"] = {"pings_per_chunk": 150, "overlap_pings": 30}
    data = root / "data"
    with TestClient(create_app(cfg, data_dir=data)) as client:
        response = client.post(
            f"{API}/surveys",
            files=[("files", ("line_results.xtf", Path(survey.path).read_bytes(), "x/octet"))],
            data={"options": json.dumps({"detector_model": "classical", "anomaly_scan": False})},
        )
        assert response.status_code == 202, response.text
        body = response.json()
        job = _wait(client, body["job_id"])
        assert job["status"] in {"completed", "completed_with_warnings"}, job
        report = json.loads(
            (data / "results" / body["survey_id"] / "report.json").read_text("utf-8")
        )
        assert report["detections"], "synthetic targets should be detected"
        yield client, report, data


def test_survey_list_and_detail(setup: Setup) -> None:
    client, report, _ = setup
    sid = report["survey"]["survey_id"]
    listing = client.get(f"{API}/surveys").json()
    assert listing["total"] == 1 and listing["items"][0]["survey_id"] == sid
    detail = client.get(f"{API}/surveys/{sid}").json()
    assert detail["summary"] == report["summary"]
    assert detail["source_files"] == ["line_results.xtf"]
    assert detail["job"]["status"] in {"completed", "completed_with_warnings"}
    assert detail["job"]["duration_s"] is not None and detail["bbox"] is not None
    assert sorted(detail["report_urls"]) == ["csv", "geojson", "json", "kml"]
    assert detail["report_urls"]["kml"] == f"{API}/surveys/{sid}/report?format=kml"
    assert client.get(f"{API}/surveys/SRV-19990101-001").status_code == 404


def test_detection_queries(setup: Setup) -> None:
    """TC-API-004: filters, sort, paging, totals and bbox match the shared module."""
    client, report, _ = setup
    sid = report["survey"]["survey_id"]
    items = report["detections"]
    confidences = sorted(d["confidence"] for d in items)
    middle = confidences[len(confidences) // 2]
    first = items[0]
    lat, lon = first["position"]["lat"], first["position"]["lon"]
    cases: list[dict[str, Any]] = [
        {},
        {"sort": "confidence"},
        {"sort": "-ping"},
        {"sort": "class"},
        {"class": first["class"]},
        {"tier": first["alert_tier"]},
        {"min_conf": middle},
        {"max_conf": middle, "sort": "-area"},
        {"bbox": f"{lon - 1e-4},{lat - 1e-4},{lon + 1e-4},{lat + 1e-4}"},
        {"review_status": "pending"},
    ]
    for params in cases:
        body = client.get(f"{API}/surveys/{sid}/detections", params=params).json()
        query = parse_query(
            cls=params.get("class"),
            min_conf=params.get("min_conf"),
            max_conf=params.get("max_conf"),
            tier=params.get("tier"),
            review_status=params.get("review_status"),
            bbox=params.get("bbox"),
            sort=params.get("sort"),
        )
        expected = [d["detection_id"] for d in query_detections(items, query)]
        assert body["total"] == len(expected), params
        assert [d["detection_id"] for d in body["items"]] == expected[:100], params
    bbox_ids = client.get(
        f"{API}/surveys/{sid}/detections", params={"bbox": cases[8]["bbox"]}
    ).json()["items"]
    assert first["detection_id"] in {d["detection_id"] for d in bbox_ids}

    page = client.get(f"{API}/surveys/{sid}/detections", params={"limit": 1, "offset": 1}).json()
    assert page["total"] == len(items) and len(page["items"]) == min(1, len(items) - 1)
    for bad in ({"sort": "size"}, {"class": "whale"}, {"limit": 5001}, {"bbox": "1,2"}):
        response = client.get(f"{API}/surveys/{sid}/detections", params=bad)
        assert response.status_code == 400, bad
        assert response.json()["error"]["code"] == "VALIDATION_ERROR"
    assert client.get(f"{API}/surveys/SRV-19990101-001/detections").status_code == 404


def test_downloads_in_four_formats(setup: Setup) -> None:
    """TC-API-007: media types and Content-Disposition; contents match the stored detections."""
    client, report, _ = setup
    sid = report["survey"]["survey_id"]
    expected_types = {
        "json": "application/json",
        "csv": "text/csv",
        "geojson": "application/geo+json",
        "kml": "application/vnd.google-earth.kml+xml",
    }
    for fmt, media in expected_types.items():
        response = client.get(f"{API}/surveys/{sid}/report", params={"format": fmt})
        assert response.status_code == 200, (fmt, response.text)
        assert response.headers["content-type"].startswith(media)
        assert (
            response.headers["content-disposition"] == f'attachment; filename="{sid}_report.{fmt}"'
        )
        if fmt == "json":
            assert [d["detection_id"] for d in response.json()["detections"]] == [
                d["detection_id"] for d in report["detections"]
            ]
        elif fmt == "csv":
            rows = list(csv.DictReader(io.StringIO(response.text)))
            assert len(rows) == len(report["detections"])
        elif fmt == "geojson":
            features = response.json()["features"]
            points = [f for f in features if f["properties"]["feature_kind"] == "detection"]
            assert len(points) == len(report["detections"])
            assert any(f["properties"]["feature_kind"] == "track" for f in features)
        else:
            ET.fromstring(response.text)
    bad = client.get(f"{API}/surveys/{sid}/report", params={"format": "pdf"})
    assert bad.status_code == 400 and bad.json()["error"]["code"] == "VALIDATION_ERROR"
    assert client.get(f"{API}/surveys/{sid}/report", params={"scope": "some"}).status_code == 400


def test_track_and_chips(setup: Setup) -> None:
    client, report, _ = setup
    sid = report["survey"]["survey_id"]
    track = client.get(f"{API}/surveys/{sid}/track").json()
    line = track["features"][0]
    assert line["properties"]["segment"] == "track" and line["geometry"]["type"] == "LineString"
    assert len(line["geometry"]["coordinates"]) >= 2
    lon, lat = line["geometry"]["coordinates"][0]
    bbox = report["survey"]["bbox"]
    assert bbox[0] - 1e-3 <= lon <= bbox[2] + 1e-3 and bbox[1] - 1e-3 <= lat <= bbox[3] + 1e-3

    det_id = report["detections"][0]["detection_id"]
    for overlay in ("mask", "shadow", "anomaly", "none"):
        chip = client.get(f"{API}/detections/{det_id}/chip.png", params={"overlay": overlay})
        assert chip.status_code == 200 and chip.headers["content-type"] == "image/png"
        assert chip.content.startswith(b"\x89PNG")
    assert (
        client.get(f"{API}/detections/{det_id}/chip.png", params={"overlay": "x"}).status_code
        == 400
    )
    assert client.get(f"{API}/detections/SRV-19990101-001-D0001/chip.png").status_code == 404
    assert client.get(f"{API}/detections/{det_id}").json() == report["detections"][0]


def test_mosaic_in_survey_detail_and_endpoint(setup: Setup) -> None:
    """ST-036: the job writes a mosaic; survey detail gives its URL and Leaflet bounds."""
    client, report, _ = setup
    sid = report["survey"]["survey_id"]
    mosaic = client.get(f"{API}/surveys/{sid}").json()["mosaic"]
    assert mosaic is not None and mosaic["url"] == f"{API}/surveys/{sid}/mosaic.png"
    (south, west), (north, east) = mosaic["bounds"]
    for det in report["detections"]:
        assert south <= det["position"]["lat"] <= north and west <= det["position"]["lon"] <= east
    image = client.get(mosaic["url"])
    assert image.status_code == 200 and image.headers["content-type"] == "image/png"
    missing = client.get(f"{API}/surveys/SRV-20000101-999/mosaic.png")
    assert missing.status_code == 404 and missing.json()["error"]["code"] == "NOT_FOUND"


def test_review_decisions_label_store_and_scopes(setup: Setup) -> None:
    """TC-API-005 and TC-REP-007: review rows, label records, reclassification in exports."""
    client, report, data = setup
    sid = report["survey"]["survey_id"]
    det = report["detections"][0]
    det_id = det["detection_id"]
    url = f"{API}/detections/{det_id}"
    labels = data / "labels"
    context = client.app.state.context  # type: ignore[attr-defined]

    confirmed = client.patch(url, json={"review_status": "confirmed", "reviewer": "analyst-02"})
    assert confirmed.status_code == 200, confirmed.text
    assert confirmed.json()["review"]["status"] == "confirmed"
    assert confirmed.json()["review"]["updated_utc"]
    folders = list(labels.glob(f"*/{det_id}"))
    assert len(folders) == 1
    record = json.loads((folders[0] / "label.json").read_text("utf-8"))
    assert record["verdict"] == "confirmed" and record["survey_id"] == sid
    assert record["class_final"] == det["class"] and record["source_file"] == "line_results.xtf"
    assert (folders[0] / "chip.png").is_file()

    scoped = client.get(
        f"{API}/surveys/{sid}/report", params={"format": "json", "scope": "confirmed"}
    ).json()
    assert [d["detection_id"] for d in scoped["detections"]] == [det_id]
    assert scoped["summary"]["total_detections"] == 1

    missing = client.patch(url, json={"review_status": "rejected"})
    assert (
        missing.status_code == 400
        and missing.json()["error"]["details"]["field"] == "reject_reason"
    )
    rejected = client.patch(url, json={"review_status": "rejected", "reject_reason": "rock"})
    assert rejected.json()["review"]["reject_reason"] == "rock"
    default_export = client.get(f"{API}/surveys/{sid}/report", params={"format": "csv"})
    assert det_id not in default_export.text
    with_rejected = client.get(
        f"{API}/surveys/{sid}/report", params={"format": "csv", "include_rejected": "true"}
    )
    assert det_id in with_rejected.text
    assert len(list(labels.glob(f"*/{det_id}"))) == 1

    new_class = "pipe" if det["class"] != "pipe" else "cylinder"
    same = client.patch(url, json={"review_status": "reclassified", "class": det["class"]})
    assert same.status_code == 400
    moved = client.patch(url, json={"review_status": "reclassified", "class": new_class})
    assert moved.status_code == 200 and moved.json()["class"] == new_class
    rows = list(
        csv.DictReader(
            io.StringIO(client.get(f"{API}/surveys/{sid}/report", params={"format": "csv"}).text)
        )
    )
    assert next(r for r in rows if r["detection_id"] == det_id)["class"] == new_class
    by_class = client.get(f"{API}/surveys/{sid}/detections", params={"class": new_class}).json()
    assert det_id in {d["detection_id"] for d in by_class["items"]}
    assert client.get(f"{API}/surveys/{sid}").json()["summary"]["by_class"][new_class] >= 1

    threshold = sorted(d["confidence"] for d in report["detections"])[
        len(report["detections"]) // 2
    ]
    filtered = client.get(
        f"{API}/surveys/{sid}/report",
        params={"format": "json", "scope": "filtered", "min_conf": threshold},
    ).json()["detections"]
    assert filtered and all(d["confidence"] >= threshold for d in filtered)
    hazards = client.get(
        f"{API}/surveys/{sid}/report", params={"format": "json", "scope": "hazards"}
    ).json()["detections"]
    assert all(d["alert_tier"] == "hazard" for d in hazards)

    undo = client.patch(url, json={"review_status": "pending"})
    assert undo.status_code == 200 and undo.json()["review"]["status"] == "pending"
    assert not list(labels.glob(f"*/{det_id}"))
    with context.database.session() as session:
        history = session.scalar(
            select(func.count()).select_from(Review).where(Review.detection_id == det_id)
        )
    assert history == 4  # confirmed, rejected, reclassified, pending

    for body in ({"review_status": "maybe"}, {"review_status": "confirmed", "colour": "red"}, [1]):
        assert client.patch(url, json=body).status_code == 400
    assert (
        client.patch(
            url, content=b"{not json", headers={"content-type": "application/json"}
        ).status_code
        == 400
    )
    assert (
        client.patch(
            f"{API}/detections/SRV-19990101-001-D0001", json={"review_status": "confirmed"}
        ).status_code
        == 404
    )
