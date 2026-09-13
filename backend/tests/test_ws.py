"""ST-083 WebSocket job events: TC-WS-001 (order, seq, done), TC-WS-004 (resume without duplicates
or gaps, also from the job log), TC-WS-005 (cross-line merge events), TC-WS-006 (error event),
unknown job (close 4404) and ping/pong."""

from __future__ import annotations

import json
import time
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
from starlette.websockets import WebSocketDisconnect  # noqa: E402
from tools.make_synthetic_xtf import write_synthetic_xtf  # noqa: E402

from sonarsentinel.api.main import API_PREFIX, create_app  # noqa: E402
from sonarsentinel.config import load_config  # noqa: E402

OPTIONS = {"detector_model": "classical", "anomaly_scan": False}
FINISHED = {"completed", "completed_with_warnings", "failed", "cancelled"}


@pytest.fixture(scope="module")
def xtf_bytes(tmp_path_factory: pytest.TempPathFactory) -> bytes:
    survey = write_synthetic_xtf(
        tmp_path_factory.mktemp("ws") / "line_ws.xtf",
        n_pings=600,
        samples_per_side=400,
        step_m=0.1,
        targets=[(150, "starboard", 250), (430, "port", 300)],
        target_extent=(12, 30),
    )
    return Path(survey.path).read_bytes()


def _config() -> dict[str, Any]:
    cfg = load_config()
    cfg["chunking"] = {"pings_per_chunk": 150, "overlap_pings": 30}
    return cfg


@pytest.fixture
def client(tmp_path: Path) -> Iterator[TestClient]:
    with TestClient(create_app(_config(), data_dir=tmp_path / "data")) as test_client:
        yield test_client


def _upload(
    client: TestClient, files: list[tuple[str, bytes]], options: dict[str, Any] | None = None
) -> dict[str, Any]:
    response = client.post(
        f"{API_PREFIX}/surveys",
        files=[("files", (name, content, "application/octet-stream")) for name, content in files],
        data={"options": json.dumps(options or OPTIONS)},
    )
    assert response.status_code == 202, response.text
    body: dict[str, Any] = response.json()
    return body


def _drain(ws: Any) -> tuple[list[dict[str, Any]], int | None]:
    events: list[dict[str, Any]] = []
    try:
        while True:
            events.append(ws.receive_json())
    except WebSocketDisconnect as exc:
        return events, exc.code


def _wait(client: TestClient, job_id: str, timeout: float = 120.0) -> dict[str, Any]:
    deadline = time.monotonic() + timeout
    while True:
        body: dict[str, Any] = client.get(f"{API_PREFIX}/jobs/{job_id}").json()
        if body["status"] in FINISHED or time.monotonic() > deadline:
            return body
        time.sleep(0.1)


def test_event_order_seq_and_done(client: TestClient, xtf_bytes: bytes) -> None:
    """TC-WS-001: progress first, increasing seq, done last with report links, close 1000."""
    job = _upload(client, [("line_ws.xtf", xtf_bytes)])
    with client.websocket_connect(job["ws_url"]) as ws:
        events, code = _drain(ws)
    assert code == 1000
    seqs = [e["seq"] for e in events]
    assert seqs == list(range(1, len(events) + 1))
    assert events[0]["type"] == "progress" and all(e["job_id"] == job["job_id"] for e in events)
    assert {"track", "detection"} <= {e["type"] for e in events}
    done = events[-1]
    assert done["type"] == "done" and done["status"] in {"completed", "completed_with_warnings"}
    assert sorted(done["report_urls"]) == ["csv", "geojson", "json", "kml"]
    mosaic = done["mosaic"]  # ST-036: the geotagged job writes a mosaic next to the report
    assert mosaic["url"] == f"{API_PREFIX}/surveys/{job['survey_id']}/mosaic.png"
    assert len(mosaic["bounds"]) == 2
    assert done["summary"]["total_detections"] == sum(e["type"] == "detection" for e in events)
    # The results are saved before ``done``: the report download works right away.
    survey_id = job["survey_id"]
    assert client.get(done["report_urls"]["csv"]).status_code == 200
    assert client.get(f"{API_PREFIX}/surveys/{survey_id}").json()["job"]["status"] == done["status"]


def test_resume_has_no_duplicates_or_gaps(client: TestClient, xtf_bytes: bytes) -> None:
    """TC-WS-004: drop the connection, resume after the last seq; also replay from the job log."""
    job = _upload(client, [("line_ws.xtf", xtf_bytes)])
    first: list[dict[str, Any]] = []
    with client.websocket_connect(job["ws_url"]) as ws:
        for _ in range(3):
            first.append(ws.receive_json())
    last = first[-1]["seq"]
    with client.websocket_connect(job["ws_url"]) as ws:
        ws.send_json({"type": "resume", "after_seq": last})
        rest, code = _drain(ws)
    assert code == 1000
    combined = [e["seq"] for e in first + rest]
    assert combined == list(range(1, len(combined) + 1))
    assert rest[-1]["type"] == "done"

    # Server restart: the in-memory buffer is gone, the job log still replays everything.
    context = client.app.state.context  # type: ignore[attr-defined]
    context.jobs.events.pop(job["job_id"], None)
    context.jobs._survey_of.pop(job["job_id"], None)
    with client.websocket_connect(job["ws_url"]) as ws:
        ws.send_json({"type": "resume", "after_seq": 2})
        replayed, code = _drain(ws)
    assert code == 1000 and [e["seq"] for e in replayed] == list(range(3, len(combined) + 1))


def test_two_lines_emit_merge_events(client: TestClient, xtf_bytes: bytes) -> None:
    """TC-WS-005: the same object on two lines → detection_removed with merged_into + update."""
    job = _upload(client, [("line_a.xtf", xtf_bytes), ("line_b.xtf", xtf_bytes)])
    with client.websocket_connect(job["ws_url"]) as ws:
        events, _ = _drain(ws)
    detections = {e["detection"]["detection_id"] for e in events if e["type"] == "detection"}
    removed = [e for e in events if e["type"] == "detection_removed"]
    updated = [e for e in events if e["type"] == "detection_update"]
    assert removed and updated
    assert all(e["merged_into"] in detections and e["detection_id"] in detections for e in removed)
    assert {e["detection"]["detection_id"] for e in updated} == {e["merged_into"] for e in removed}
    assert all(e["detection"]["n_views"] == 2 for e in updated)
    done = events[-1]
    assert done["type"] == "done"
    assert done["summary"]["total_detections"] == len(detections) - len(removed)
    stored = client.get(
        f"{API_PREFIX}/surveys/{job['survey_id']}/detections", params={"limit": 5000}
    ).json()
    assert stored["total"] == len(detections) - len(removed)


def test_failed_job_emits_error_event(tmp_path: Path, xtf_bytes: bytes) -> None:
    """TC-WS-006: a missing model file → ``error`` event with a code, job ``failed``."""
    cfg = _config()
    cfg["detection"]["model"] = str(tmp_path / "missing" / "best.pt")
    with TestClient(create_app(cfg, data_dir=tmp_path / "data")) as client:
        job = _upload(client, [("line_ws.xtf", xtf_bytes)], OPTIONS | {"detector_model": "yolo"})
        with client.websocket_connect(job["ws_url"]) as ws:
            events, code = _drain(ws)
        assert code == 1000
        assert events[-1]["type"] == "error" and events[-1]["code"] == "MODELS_NOT_LOADED"
        assert events[-1]["message"] and events[-1]["seq"] == len(events)
        status = _wait(client, job["job_id"])
        assert status["status"] == "failed" and status["error"]["code"] == "MODELS_NOT_LOADED"


def test_unknown_job_and_ping(client: TestClient, xtf_bytes: bytes) -> None:
    with client.websocket_connect("/ws/jobs/JOB-deadbeef") as ws:
        message = ws.receive_json()
        with pytest.raises(WebSocketDisconnect) as closed:
            ws.receive_json()
    assert message["type"] == "error" and message["code"] == "NOT_FOUND"
    assert closed.value.code == 4404

    job = _upload(client, [("line_ws.xtf", xtf_bytes)])
    assert _wait(client, job["job_id"])["status"] in {"completed", "completed_with_warnings"}
    with client.websocket_connect(job["ws_url"]) as ws:
        ws.send_json({"type": "ping"})
        events, code = _drain(ws)
    assert events[0]["type"] == "pong" and "seq" not in events[0]
    assert events[0]["job_id"] == job["job_id"] and events[-1]["type"] == "done" and code == 1000
