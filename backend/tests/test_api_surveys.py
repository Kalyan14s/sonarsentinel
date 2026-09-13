"""ST-081/082 over HTTP: TC-API-001 (upload starts a job), TC-API-002 (validate), TC-API-003
(errors) and TC-API-006 (cancel)."""

from __future__ import annotations

import copy
import json
import re
import threading
import time
from collections.abc import Iterator
from importlib import resources
from pathlib import Path
from typing import Any

import numpy as np
import pytest

pytest.importorskip("fastapi")
pytest.importorskip("httpx")
pytest.importorskip("sqlalchemy")
pytest.importorskip("pyxtf")
pytest.importorskip("scipy")
cv2 = pytest.importorskip("cv2")
jsonschema = pytest.importorskip("jsonschema")

from fastapi.testclient import TestClient  # noqa: E402
from tools.make_synthetic_xtf import write_synthetic_xtf  # noqa: E402

from sonarsentinel.api.main import API_PREFIX, create_app  # noqa: E402
from sonarsentinel.config import load_config  # noqa: E402

OPTIONS: dict[str, Any] = {"detector_model": "classical", "anomaly_scan": False}
N_PINGS = 450
FINISHED = {"completed", "completed_with_warnings", "failed", "cancelled"}


@pytest.fixture(scope="module")
def xtf_bytes(tmp_path_factory: pytest.TempPathFactory) -> bytes:
    path = tmp_path_factory.mktemp("api") / "line.xtf"
    survey = write_synthetic_xtf(
        path,
        n_pings=N_PINGS,
        samples_per_side=300,
        step_m=0.1,
        targets=[(200, "starboard", 150)],
        target_extent=(12, 30),
    )
    return Path(survey.path).read_bytes()


@pytest.fixture
def config() -> dict[str, Any]:
    cfg = load_config()
    cfg["chunking"] = {"pings_per_chunk": 150, "overlap_pings": 30}
    return cfg


@pytest.fixture
def client(tmp_path: Path, config: dict[str, Any]) -> Iterator[TestClient]:
    with TestClient(create_app(config, data_dir=tmp_path / "data")) as test_client:
        yield test_client


def _post_survey(
    client: TestClient,
    content: bytes,
    *,
    name: str = "line 07.xtf",
    options: dict[str, Any] | None = None,
) -> Any:
    return client.post(
        f"{API_PREFIX}/surveys",
        files=[("files", (name, content, "application/octet-stream"))],
        data={"options": json.dumps(OPTIONS if options is None else options)},
    )


def _wait(client: TestClient, job_id: str, timeout: float = 120.0) -> dict[str, Any]:
    deadline = time.monotonic() + timeout
    while True:
        body: dict[str, Any] = client.get(f"{API_PREFIX}/jobs/{job_id}").json()
        if body["status"] in FINISHED or time.monotonic() > deadline:
            return body
        time.sleep(0.1)


def _log(data_dir: Path, survey_id: str) -> list[dict[str, Any]]:
    path = data_dir / "results" / survey_id / "job.log.jsonl"
    return [json.loads(line) for line in path.read_text("utf-8").splitlines()]


def test_upload_starts_a_job_that_writes_the_report(
    client: TestClient, xtf_bytes: bytes, tmp_path: Path
) -> None:
    """TC-API-001, and TC-API-006 for finished and queued jobs."""
    response = _post_survey(
        client, xtf_bytes, options=OPTIONS | {"name": "Line 07", "project": "NIOT"}
    )
    assert response.status_code == 202, response.text
    body = response.json()
    assert set(body) == {"survey_id", "job_id", "status", "ws_url"}
    assert re.fullmatch(r"SRV-\d{8}-001", body["survey_id"])
    assert re.fullmatch(r"JOB-[0-9a-f]{8}", body["job_id"])
    assert body["status"] == "queued" and body["ws_url"] == f"/ws/jobs/{body['job_id']}"

    job = _wait(client, body["job_id"])
    assert job["status"] == "completed_with_warnings", job
    assert job["survey_id"] == body["survey_id"] and job["percent"] == 100.0
    assert job["pings_total"] == N_PINGS and "detect" in job["stage_timings_ms"]

    data = tmp_path / "data"
    assert (data / "uploads" / body["survey_id"] / "line_07.xtf").is_file()
    report = json.loads((data / "results" / body["survey_id"] / "report.json").read_text("utf-8"))
    schema_text = resources.files("sonarsentinel.report").joinpath(
        "schema", "report-1.0.schema.json"
    )
    schema = jsonschema.Draft202012Validator(json.loads(schema_text.read_text("utf-8")))
    assert schema.is_valid(report) and report["survey"]["name"] == "Line 07"

    finished = client.post(f"{API_PREFIX}/jobs/{body['job_id']}/cancel")
    assert finished.status_code == 409 and finished.json()["error"]["code"] == "JOB_NOT_CANCELLABLE"

    second = _post_survey(client, xtf_bytes)
    assert second.status_code == 202 and second.json()["survey_id"].endswith("-002")
    cancel = client.post(f"{API_PREFIX}/jobs/{second.json()['job_id']}/cancel")
    assert (cancel.status_code, cancel.json()["status"]) in {
        (200, "cancelled"),
        (202, "cancelling"),
    }
    assert _wait(client, second.json()["job_id"])["status"] == "cancelled"


def test_cancel_running_job_over_http(client: TestClient, xtf_bytes: bytes, tmp_path: Path) -> None:
    """TC-API-006: a running job is cancelled within one chunk."""
    context = client.app.state.context  # type: ignore[attr-defined]
    in_detect, release = threading.Event(), threading.Event()

    def pause_after_first_chunk(event: dict[str, Any]) -> None:
        if (
            event["type"] == "progress"
            and event.get("stage") == "detect"
            and not in_detect.is_set()
        ):
            in_detect.set()
            release.wait(30)

    context.jobs.add_listener(pause_after_first_chunk)
    job_id = _post_survey(client, xtf_bytes).json()["job_id"]
    assert in_detect.wait(60)
    running = client.get(f"{API_PREFIX}/jobs/{job_id}").json()
    assert running["status"] == "running" and running["stage"] == "detect"
    response = client.post(f"{API_PREFIX}/jobs/{job_id}/cancel")
    release.set()
    assert response.status_code == 202
    assert response.json() == {"job_id": job_id, "status": "cancelling"}

    job = _wait(client, job_id)
    assert job["status"] == "cancelled"
    events = _log(tmp_path / "data", job["survey_id"])
    chunks = [e for e in events if e["type"] == "progress" and e.get("stage") == "detect"]
    assert len(chunks) == 1 and not any(e["type"] == "done" for e in events)


def test_validate_reports_metadata_without_processing(
    client: TestClient, xtf_bytes: bytes, tmp_path: Path
) -> None:
    """TC-API-002: XTF metadata; an image without navigation gets NO_NAVIGATION."""
    ok, png = cv2.imencode(".png", np.full((200, 400), 90, np.uint8))
    assert ok
    response = client.post(
        f"{API_PREFIX}/surveys/validate",
        files=[
            ("files", ("line_07.xtf", xtf_bytes, "application/octet-stream")),
            ("files", ("harbour_03.png", png.tobytes(), "image/png")),
            ("files", ("scan.bmp", b"BM" + bytes(64), "image/bmp")),
        ],
    )
    assert response.status_code == 200, response.text
    xtf, image, bmp = response.json()["files"]
    assert xtf["valid"] and xtf["format"] == "xtf" and xtf["filename"] == "line_07.xtf"
    assert xtf["pings"] == N_PINGS and xtf["has_navigation"] and xtf["sonar"]["channels"] == 2
    assert xtf["start_utc"] and xtf["size_bytes"] == len(xtf_bytes)
    assert image["valid"] and image["format"] == "image_only" and not image["has_navigation"]
    assert (image["width"], image["height"]) == (400, 200)
    assert image["warnings"][0].startswith("NO_NAVIGATION")
    assert not bmp["valid"] and bmp["error"]["code"] == "UNSUPPORTED_FORMAT"
    uploads = tmp_path / "data" / "uploads"
    assert not uploads.exists() or not any(uploads.iterdir())


def test_upload_errors(tmp_path: Path, config: dict[str, Any]) -> None:
    """TC-API-003: 400, 404, 413, 415 and 422 in the error model; nothing left on disk."""
    small = copy.deepcopy(config)
    small["ingest"]["max_upload_gb"] = 4096 / 1024**3
    tiny_xtf = b"\x7b" + bytes(10)
    with TestClient(create_app(small, data_dir=tmp_path / "data")) as client:

        def code(response: Any, status: int) -> str:
            assert response.status_code == status, response.text
            return str(response.json()["error"]["code"])

        assert code(_post_survey(client, b"\x7b" + bytes(10_000)), 413) == "FILE_TOO_LARGE"
        assert code(_post_survey(client, b"BM" + bytes(64), name="scan.bmp"), 415) == (
            "UNSUPPORTED_FORMAT"
        )
        assert code(_post_survey(client, bytes(100)), 422) == "CORRUPT_HEADER"

        bad_json = client.post(
            f"{API_PREFIX}/surveys",
            files=[("files", ("a.xtf", tiny_xtf, "application/octet-stream"))],
            data={"options": "{not json"},
        )
        assert code(bad_json, 400) == "VALIDATION_ERROR"
        unknown = _post_survey(client, tiny_xtf, options={"colour": "red"})
        assert code(unknown, 400) == "VALIDATION_ERROR"
        assert unknown.json()["error"]["details"]["errors"][0]["field"] == "colour"
        rcnn = _post_survey(client, tiny_xtf, options={"detector_model": "rcnn"})
        assert code(rcnn, 400) == "VALIDATION_ERROR"
        no_files = client.post(f"{API_PREFIX}/surveys", data={"options": "{}"})
        assert code(no_files, 400) == "VALIDATION_ERROR"
        ok, png = cv2.imencode(".png", np.zeros((10, 10), np.uint8))
        no_nav = _post_survey(client, png.tobytes(), name="harbour.png", options=OPTIONS)
        assert code(no_nav, 400) == "VALIDATION_ERROR"

        assert code(client.get(f"{API_PREFIX}/jobs/JOB-deadbeef"), 404) == "NOT_FOUND"
        assert code(client.post(f"{API_PREFIX}/jobs/JOB-deadbeef/cancel"), 404) == "NOT_FOUND"

    uploads = tmp_path / "data" / "uploads"
    assert not uploads.exists() or not any(uploads.iterdir())
