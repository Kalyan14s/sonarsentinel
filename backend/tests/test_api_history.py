"""ST-098 history: ``GET /surveys`` filters and fields, ``DELETE /surveys/{id}`` (ADR-019)."""

from __future__ import annotations

import json
import time
from collections.abc import Iterator, Sequence
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

from sonarsentinel.api.main import API_PREFIX, create_app  # noqa: E402
from sonarsentinel.api.mock import create_mock_app  # noqa: E402
from sonarsentinel.config import load_config  # noqa: E402
from sonarsentinel.storage import repository as repo  # noqa: E402
from sonarsentinel.storage.models import (  # noqa: E402
    Detection,
    Job,
    QualityEvent,
    Report,
    Review,
    SourceFile,
    Survey,
    TrackSegment,
)

OPTIONS: dict[str, Any] = {"detector_model": "classical", "anomaly_scan": False}
URL = f"{API_PREFIX}/surveys"
FINISHED = {"completed", "completed_with_warnings", "failed", "cancelled"}


@pytest.fixture
def config() -> dict[str, Any]:
    cfg = load_config()
    cfg["chunking"] = {"pings_per_chunk": 150, "overlap_pings": 30}
    return cfg


@pytest.fixture
def client(tmp_path: Path, config: dict[str, Any]) -> Iterator[TestClient]:
    with TestClient(create_app(config, data_dir=tmp_path / "data")) as test_client:
        yield test_client


def _add_survey(
    client: TestClient,
    survey_id: str,
    *,
    name: str,
    project: str | None,
    files: Sequence[tuple[str, int]],
    created: str,
    status: str,
    warnings: int = 0,
) -> None:
    context = client.app.state.context  # type: ignore[attr-defined]
    job_id = survey_id.replace("SRV-", "JOB-")
    with context.database.session() as session, session.begin():
        repo.create_survey(
            session,
            survey_id=survey_id,
            job_id=job_id,
            name=name,
            project=project,
            options=OPTIONS,
            files=[
                {"filename": f, "format": "xtf", "size_bytes": size, "sha256": "0" * 64}
                for f, size in files
            ],
        )
    with context.database.session() as session, session.begin():
        survey = session.get(Survey, survey_id)
        job = session.get(Job, job_id)
        assert survey is not None and job is not None
        survey.created_utc = created
        survey.status = job.status = status
        job.warnings_json = json.dumps([{"code": "GPS_GAP"}] * warnings)


def _ids(client: TestClient, **params: Any) -> list[str]:
    response = client.get(URL, params=params)
    assert response.status_code == 200, response.text
    return [item["survey_id"] for item in response.json()["items"]]


@pytest.fixture
def history(client: TestClient) -> TestClient:
    _add_survey(
        client,
        "SRV-20260910-001",
        name="Harbour line 1",
        project="NIOT",
        files=[("harbour_01.xtf", 1000)],
        created="2026-09-10T08:00:00Z",
        status="completed",
    )
    _add_survey(
        client,
        "SRV-20260912-001",
        name="Pipeline check",
        project="ONGC",
        files=[("PIPE_route.xtf", 2000), ("nav.csv", 500)],
        created="2026-09-12T12:00:00Z",
        status="completed_with_warnings",
        warnings=2,
    )
    _add_survey(
        client,
        "SRV-20260914-001",
        name="Night run",
        project=None,
        files=[("night.xtf", 300)],
        created="2026-09-14T23:30:00Z",
        status="failed",
    )
    return client


def test_list_items_and_filters(history: TestClient) -> None:
    body = history.get(URL).json()
    assert body["total"] == 3
    assert _ids(history) == ["SRV-20260914-001", "SRV-20260912-001", "SRV-20260910-001"]
    pipeline = body["items"][1]
    assert pipeline["project"] == repo.project_id_for("ONGC")
    assert pipeline["status"] == "completed_with_warnings" and pipeline["warning_count"] == 2
    assert pipeline["size_bytes"] == 2500
    assert {"by_class", "by_tier", "total_detections"} <= set(pipeline["summary"])

    assert _ids(history, q="HARBOUR") == ["SRV-20260910-001"]
    assert _ids(history, q="pipe_ROUTE") == ["SRV-20260912-001"]  # source file name
    assert _ids(history, q="_") == ["SRV-20260912-001", "SRV-20260910-001"]  # literal "_"
    assert _ids(history, q="%") == []
    assert _ids(history, project="ONGC") == ["SRV-20260912-001"]
    assert _ids(history, status="failed,completed") == ["SRV-20260914-001", "SRV-20260910-001"]
    assert _ids(history, **{"from": "2026-09-12"}) == ["SRV-20260914-001", "SRV-20260912-001"]
    assert _ids(history, to="2026-09-12") == ["SRV-20260912-001", "SRV-20260910-001"]
    assert _ids(history, **{"from": "2026-09-11", "to": "2026-09-13"}) == ["SRV-20260912-001"]
    assert _ids(history, **{"from": "2026-09-14T23:00:00Z"}) == ["SRV-20260914-001"]

    page = history.get(URL, params={"status": "completed,completed_with_warnings", "limit": 1})
    assert page.json()["total"] == 2 and len(page.json()["items"]) == 1
    assert _ids(history, limit=1, offset=1) == ["SRV-20260912-001"]


@pytest.mark.parametrize(
    "params",
    [
        {"status": "done"},
        {"from": "yesterday"},
        {"from": "2026-09-13", "to": "2026-09-12"},
        {"limit": 0},
    ],
)
def test_invalid_filters(client: TestClient, params: dict[str, Any]) -> None:
    response = client.get(URL, params=params)
    assert response.status_code == 400 and response.json()["error"]["code"] == "VALIDATION_ERROR"


def test_delete_refuses_unfinished_and_unknown_surveys(client: TestClient) -> None:
    for survey_id, status in (("SRV-20260913-001", "queued"), ("SRV-20260913-002", "running")):
        _add_survey(
            client,
            survey_id,
            name="busy",
            project=None,
            files=[("busy.xtf", 10)],
            created="2026-09-13T10:00:00Z",
            status=status,
        )
        response = client.delete(f"{URL}/{survey_id}")
        assert response.status_code == 409, response.text
        error = response.json()["error"]
        assert error["code"] == "JOB_NOT_CANCELLABLE" and error["message"] == "Cancel the job first"
    assert client.get(URL).json()["total"] == 2

    missing = client.delete(f"{URL}/SRV-20000101-001")
    assert missing.status_code == 404 and missing.json()["error"]["code"] == "NOT_FOUND"


def _files(root: Path) -> list[Path]:
    return sorted(p for p in root.rglob("*") if p.is_file()) if root.exists() else []


def test_delete_removes_rows_and_files_but_keeps_labels(client: TestClient, tmp_path: Path) -> None:
    source = write_synthetic_xtf(
        tmp_path / "line.xtf",
        n_pings=450,
        samples_per_side=300,
        step_m=0.1,
        targets=[(200, "starboard", 150)],
        target_extent=(12, 30),
    )
    data = tmp_path / "data"
    created = client.post(
        URL,
        files=[("files", ("line.xtf", Path(source.path).read_bytes(), "application/octet-stream"))],
        data={"options": json.dumps(OPTIONS)},
    )
    assert created.status_code == 202, created.text
    survey_id, job_id = created.json()["survey_id"], created.json()["job_id"]
    deadline = time.monotonic() + 120
    while client.get(f"{API_PREFIX}/jobs/{job_id}").json()["status"] not in FINISHED:
        assert time.monotonic() < deadline
        time.sleep(0.1)

    detections = client.get(f"{URL}/{survey_id}/detections").json()["items"]
    assert detections
    review = client.patch(
        f"{API_PREFIX}/detections/{detections[0]['detection_id']}",
        json={"review_status": "confirmed", "reviewer": "analyst-02"},
    )
    assert review.status_code == 200, review.text
    other_label = data / "labels" / "2026-09" / "DET-other" / "label.json"
    other_label.parent.mkdir(parents=True, exist_ok=True)
    other_label.write_text("{}", encoding="utf-8")
    (data / "work" / survey_id).mkdir(parents=True, exist_ok=True)
    (data / "work" / survey_id / "left_over.npy").write_bytes(b"x")
    labels = _files(data / "labels")
    assert (data / "uploads" / survey_id).is_dir() and (data / "results" / survey_id).is_dir()

    response = client.delete(f"{URL}/{survey_id}")
    assert response.status_code == 204 and response.content == b""
    for folder in ("results", "uploads", "work"):
        assert not (data / folder / survey_id).exists()
    assert _files(data / "labels") == labels
    context = client.app.state.context  # type: ignore[attr-defined]
    with context.database.session() as session:
        for model in (
            Survey,
            Job,
            SourceFile,
            Detection,
            Review,
            TrackSegment,
            QualityEvent,
            Report,
        ):
            assert session.scalar(select(func.count()).select_from(model)) == 0, model
    assert client.get(f"{URL}/{survey_id}").status_code == 404
    assert client.get(URL).json() == {"total": 0, "items": []}
    assert client.delete(f"{URL}/{survey_id}").status_code == 404


def test_mock_history_filters_and_delete() -> None:
    mock = TestClient(create_mock_app(event_delay_s=0.0))
    item = mock.get(URL).json()["items"][0]
    assert {"project", "status", "warning_count", "size_bytes"} <= set(item)
    assert mock.get(URL, params={"q": item["name"][:3].upper()}).json()["total"] == 1
    assert mock.get(URL, params={"q": "no such survey"}).json()["total"] == 0
    assert mock.get(URL, params={"status": "failed"}).json()["total"] == 0
    assert mock.get(URL, params={"status": "bogus"}).status_code == 400

    survey_id = item["survey_id"]
    assert mock.delete(f"{URL}/{survey_id}").status_code == 204
    assert mock.get(URL).json() == {"total": 0, "items": []}
    assert mock.get(f"{URL}/{survey_id}").status_code == 404
    assert mock.delete(f"{URL}/{survey_id}").status_code == 404
