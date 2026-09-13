"""ST-087 mock API with the ADR-018 routes: TC-API-004 (filters), TC-API-005 (review), TC-API-006
(cancel finished), TC-API-007 (four report formats), scopes, chips, track with quality segments and
the WebSocket stream (replay, resume, ping, unknown job) — against the canned fixtures."""

from __future__ import annotations

import csv
import io
import json
import xml.etree.ElementTree as ET
from importlib import resources

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("httpx")
jsonschema = pytest.importorskip("jsonschema")
from fastapi.testclient import TestClient  # noqa: E402
from starlette.websockets import WebSocketDisconnect  # noqa: E402

from sonarsentinel.api.mock import API, create_mock_app  # noqa: E402


@pytest.fixture
def client() -> TestClient:
    return TestClient(create_mock_app(event_delay_s=0.0))


def _ids(client: TestClient) -> tuple[str, str]:
    survey = client.get(f"{API}/surveys").json()["items"][0]
    return survey["survey_id"], survey["job"]["job_id"]


def test_fixture_report_is_schema_valid() -> None:
    schema = json.loads(
        resources.files("sonarsentinel.report")
        .joinpath("schema", "report-1.0.schema.json")
        .read_text()
    )
    report = json.loads(
        resources.files("sonarsentinel.api").joinpath("fixtures", "mock_report.json").read_text()
    )
    assert jsonschema.Draft202012Validator(schema).is_valid(report)
    assert report["survey"]["project"] == "mock-fixture"
    assert len({d["class"] for d in report["detections"]}) >= 4
    assert {"hazard", "review"} <= {d["alert_tier"] for d in report["detections"]}


def test_detection_filters_sort_and_paging(client: TestClient) -> None:
    """TC-API-004."""
    sid, _ = _ids(client)
    everything = client.get(f"{API}/surveys/{sid}/detections").json()
    total = everything["total"]
    hazard = client.get(f"{API}/surveys/{sid}/detections", params={"tier": "hazard"}).json()
    assert 0 < hazard["total"] < total and all(d["alert_tier"] == "hazard" for d in hazard["items"])
    nets = client.get(
        f"{API}/surveys/{sid}/detections", params={"class": "ghost_net,pipe", "min_conf": 50}
    ).json()
    assert all(d["class"] in {"ghost_net", "pipe"} and d["confidence"] >= 50 for d in nets["items"])
    ordered = everything["items"]  # default sort: -confidence
    assert [d["confidence"] for d in ordered] == sorted(
        (d["confidence"] for d in ordered), reverse=True
    )
    by_class = client.get(f"{API}/surveys/{sid}/detections", params={"sort": "class"}).json()
    assert [d["class"] for d in by_class["items"]] == sorted(d["class"] for d in ordered)
    page = client.get(f"{API}/surveys/{sid}/detections", params={"limit": 2, "offset": 1}).json()
    assert page["total"] == total and len(page["items"]) == min(2, total - 1)
    lat = ordered[0]["position"]["lat"]
    lon = ordered[0]["position"]["lon"]
    box = f"{lon - 1e-5},{lat - 1e-5},{lon + 1e-5},{lat + 1e-5}"
    inside = client.get(f"{API}/surveys/{sid}/detections", params={"bbox": box}).json()
    assert ordered[0]["detection_id"] in {d["detection_id"] for d in inside["items"]}
    for bad in ({"sort": "bogus"}, {"class": "whale"}, {"limit": 5001}, {"min_conf": 150}):
        response = client.get(f"{API}/surveys/{sid}/detections", params=bad)
        assert (
            response.status_code == 400 and response.json()["error"]["code"] == "VALIDATION_ERROR"
        )
    assert (
        client.get(f"{API}/surveys/SRV-19990101-001/detections").json()["error"]["code"]
        == "NOT_FOUND"
    )


def test_review_update(client: TestClient) -> None:
    """TC-API-005 (mock part): confirm, reject needs a reason, reclassify."""
    sid, _ = _ids(client)
    det = client.get(f"{API}/surveys/{sid}/detections").json()["items"][0]
    url = f"{API}/detections/{det['detection_id']}"
    confirmed = client.patch(url, json={"review_status": "confirmed", "reviewer": "analyst-02"})
    assert confirmed.json()["review"]["status"] == "confirmed"
    assert confirmed.json()["review"]["updated_utc"]
    bad = client.patch(url, json={"review_status": "rejected"})
    assert bad.status_code == 400 and bad.json()["error"]["code"] == "VALIDATION_ERROR"
    rejected = client.patch(url, json={"review_status": "rejected", "reject_reason": "rock"}).json()
    assert rejected["review"]["reject_reason"] == "rock"
    new_class = "debris_other" if det["class"] != "debris_other" else "pipe"
    same = client.patch(url, json={"review_status": "reclassified", "class": det["class"]})
    assert same.status_code == 400
    moved = client.patch(url, json={"review_status": "reclassified", "class": new_class}).json()
    assert moved["class"] == new_class
    assert client.get(url).json()["review"]["status"] == "reclassified"
    assert (
        client.patch(f"{API}/detections/nope", json={"review_status": "confirmed"}).status_code
        == 404
    )


def test_report_downloads_scopes_and_track(client: TestClient) -> None:
    """TC-API-007 (four formats) and TC-REP-007 (scopes)."""
    sid, _ = _ids(client)
    detail = client.get(f"{API}/surveys/{sid}").json()
    assert sorted(detail["report_urls"]) == ["csv", "geojson", "json", "kml"]
    response = client.get(f"{API}/surveys/{sid}/report", params={"format": "csv"})
    assert response.status_code == 200 and response.headers["content-type"].startswith("text/csv")
    assert f'filename="{sid}_report.csv"' in response.headers["content-disposition"]
    rows = list(csv.DictReader(io.StringIO(response.text)))
    assert len(rows) == detail["summary"]["total_detections"]
    assert (
        client.get(f"{API}/surveys/{sid}/report", params={"format": "json"}).json()[
            "report_version"
        ]
        == "1.0"
    )
    geojson = client.get(f"{API}/surveys/{sid}/report", params={"format": "geojson"})
    assert geojson.headers["content-type"].startswith("application/geo+json")
    points = [
        f for f in geojson.json()["features"] if f["properties"]["feature_kind"] == "detection"
    ]
    assert len(points) == len(rows)
    kml = client.get(f"{API}/surveys/{sid}/report", params={"format": "kml"})
    assert kml.status_code == 200 and ET.fromstring(kml.text).tag.endswith("kml")
    assert client.get(f"{API}/surveys/{sid}/report", params={"format": "pdf"}).status_code == 400

    filtered = client.get(
        f"{API}/surveys/{sid}/report",
        params={"format": "json", "scope": "filtered", "min_conf": 60},
    ).json()
    assert filtered["detections"] and all(d["confidence"] >= 60 for d in filtered["detections"])
    assert filtered["summary"]["total_detections"] == len(filtered["detections"])
    hazards = client.get(
        f"{API}/surveys/{sid}/report", params={"format": "json", "scope": "hazards"}
    ).json()["detections"]
    assert hazards and all(d["alert_tier"] == "hazard" for d in hazards)

    features = client.get(f"{API}/surveys/{sid}/track").json()["features"]
    line = features[0]
    assert line["properties"]["segment"] == "track" and line["geometry"]["type"] == "LineString"
    assert len(line["geometry"]["coordinates"]) > 10
    assert all(f["properties"]["segment"] in {"track", "quality"} for f in features)


def test_chips_jobs_and_cancel(client: TestClient) -> None:
    """Placeholder chips; TC-API-006 (finished job → 409)."""
    sid, job_id = _ids(client)
    det_id = client.get(f"{API}/surveys/{sid}/detections").json()["items"][0]["detection_id"]
    chip = client.get(f"{API}/detections/{det_id}/chip.png", params={"overlay": "shadow"})
    assert chip.status_code == 200 and chip.content.startswith(b"\x89PNG")
    assert (
        client.get(f"{API}/detections/{det_id}/chip.png", params={"overlay": "x"}).status_code
        == 400
    )
    assert client.get(f"{API}/detections/nope/chip.png").status_code == 404
    assert client.get(f"{API}/jobs/{job_id}").json()["percent"] == 100.0
    response = client.post(f"{API}/jobs/{job_id}/cancel")
    assert response.status_code == 409 and response.json()["error"]["code"] == "JOB_NOT_CANCELLABLE"
    assert client.post(f"{API}/surveys").status_code == 202


def _drain(ws: object) -> tuple[list[dict[str, object]], int | None]:
    received: list[dict[str, object]] = []
    try:
        while True:
            received.append(ws.receive_json())  # type: ignore[attr-defined]
    except WebSocketDisconnect as exc:
        return received, exc.code


def test_websocket_replay_resume_ping_and_unknown_job(client: TestClient) -> None:
    _, job_id = _ids(client)
    with client.websocket_connect(f"/ws/jobs/{job_id}") as ws:
        received, code = _drain(ws)
    assert code == 1000
    assert received[0]["type"] == "progress" and received[-1]["type"] == "done"
    assert [e["seq"] for e in received] == list(range(1, len(received) + 1))
    assert {e["type"] for e in received} >= {"progress", "track", "detection", "done"}
    done = received[-1]
    assert sorted(done["report_urls"]) == ["csv", "geojson", "json", "kml"]  # type: ignore[arg-type]
    with client.websocket_connect(f"/ws/jobs/{job_id}") as ws:
        ws.send_json({"type": "resume", "after_seq": len(received) - 2})
        tail, _ = _drain(ws)
    assert [e["seq"] for e in tail] == [len(received) - 1, len(received)]
    with client.websocket_connect(f"/ws/jobs/{job_id}") as ws:
        ws.send_json({"type": "ping"})
        with_pong, _ = _drain(ws)
    assert with_pong[0]["type"] == "pong" and "seq" not in with_pong[0]
    with client.websocket_connect("/ws/jobs/JOB-nope") as ws:
        error, code = _drain(ws)
    assert error[0]["code"] == "NOT_FOUND" and code == 4404
