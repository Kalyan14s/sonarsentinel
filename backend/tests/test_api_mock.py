"""ST-087 mock API: TC-API-004 (filters), TC-API-005 (review), TC-API-006 (cancel finished),
TC-API-007 (report download) and WebSocket replay with resume — against the canned fixtures."""

import csv
import io
import json
from importlib import resources

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("httpx")
jsonschema = pytest.importorskip("jsonschema")
from fastapi.testclient import TestClient  # noqa: E402

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
    ordered = client.get(f"{API}/surveys/{sid}/detections", params={"sort": "-confidence"}).json()[
        "items"
    ]
    assert [d["confidence"] for d in ordered] == sorted(
        (d["confidence"] for d in ordered), reverse=True
    )
    page = client.get(f"{API}/surveys/{sid}/detections", params={"limit": 2, "offset": 1}).json()
    assert page["total"] == total and len(page["items"]) == min(2, total - 1)
    lat = ordered[0]["position"]["lat"]
    lon = ordered[0]["position"]["lon"]
    box = f"{lon - 1e-5},{lat - 1e-5},{lon + 1e-5},{lat + 1e-5}"
    inside = client.get(f"{API}/surveys/{sid}/detections", params={"bbox": box}).json()
    assert ordered[0]["detection_id"] in {d["detection_id"] for d in inside["items"]}
    assert (
        client.get(f"{API}/surveys/{sid}/detections", params={"sort": "bogus"}).status_code == 400
    )
    assert (
        client.get(f"{API}/surveys/SRV-19990101-001/detections").json()["error"]["code"]
        == "NOT_FOUND"
    )


def test_review_update(client: TestClient) -> None:
    """TC-API-005 (mock part): confirm, reject needs a reason, reclassify."""
    sid, _ = _ids(client)
    det_id = client.get(f"{API}/surveys/{sid}/detections").json()["items"][0]["detection_id"]
    url = f"{API}/detections/{det_id}"
    assert (
        client.patch(url, json={"review_status": "confirmed", "reviewer": "analyst-02"}).json()[
            "review"
        ]["status"]
        == "confirmed"
    )
    bad = client.patch(url, json={"review_status": "rejected"})
    assert bad.status_code == 400 and bad.json()["error"]["code"] == "VALIDATION_ERROR"
    rejected = client.patch(url, json={"review_status": "rejected", "reject_reason": "rock"}).json()
    assert rejected["review"]["reject_reason"] == "rock"
    moved = client.patch(
        url, json={"review_status": "reclassified", "class": "debris_other"}
    ).json()
    assert moved["class"] == "debris_other"
    assert client.get(url).json()["review"]["status"] == "reclassified"
    assert (
        client.patch(f"{API}/detections/nope", json={"review_status": "confirmed"}).status_code
        == 404
    )


def test_report_download_and_track(client: TestClient) -> None:
    """TC-API-007 (json/csv)."""
    sid, _ = _ids(client)
    response = client.get(f"{API}/surveys/{sid}/report", params={"format": "csv"})
    assert response.status_code == 200 and response.headers["content-type"].startswith("text/csv")
    assert f'filename="{sid}_report.csv"' in response.headers["content-disposition"]
    rows = list(csv.DictReader(io.StringIO(response.text)))
    assert len(rows) == client.get(f"{API}/surveys/{sid}").json()["summary"]["total_detections"]
    assert (
        client.get(f"{API}/surveys/{sid}/report", params={"format": "json"}).json()[
            "report_version"
        ]
        == "1.0"
    )
    assert client.get(f"{API}/surveys/{sid}/report", params={"format": "kml"}).status_code == 400
    line = client.get(f"{API}/surveys/{sid}/track").json()["features"][0]["geometry"]
    assert line["type"] == "LineString" and len(line["coordinates"]) > 10


def test_jobs_and_cancel(client: TestClient) -> None:
    """TC-API-006 (finished job → 409)."""
    _, job_id = _ids(client)
    assert client.get(f"{API}/jobs/{job_id}").json()["percent"] == 100.0
    response = client.post(f"{API}/jobs/{job_id}/cancel")
    assert response.status_code == 409 and response.json()["error"]["code"] == "JOB_NOT_CANCELLABLE"
    assert client.post(f"{API}/surveys").status_code == 202


def test_websocket_replay_and_resume(client: TestClient) -> None:
    _, job_id = _ids(client)
    with client.websocket_connect(f"/ws/jobs/{job_id}") as ws:
        received = []
        try:
            while True:
                received.append(ws.receive_json())
        except Exception:  # server closes after the last event
            pass
    assert received[0]["type"] == "progress" and received[-1]["type"] == "done"
    assert [e["seq"] for e in received] == list(range(1, len(received) + 1))
    assert {e["type"] for e in received} >= {"progress", "track", "detection", "done"}
    with client.websocket_connect(f"/ws/jobs/{job_id}") as ws:
        ws.send_json({"type": "resume", "after_seq": len(received) - 2})
        tail = []
        try:
            while True:
                tail.append(ws.receive_json())
        except Exception:
            pass
    assert [e["seq"] for e in tail] == [len(received) - 1, len(received)]
