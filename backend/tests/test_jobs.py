"""ST-082/083: job worker — completed jobs are persisted and end with ``done`` (report links),
cancel stops within one chunk and ends with ``done`` (status cancelled), failures emit ``error``,
and jobs left over from a stopped server are failed on start-up."""

from __future__ import annotations

import json
from collections.abc import Iterator
from importlib import resources
from pathlib import Path
from typing import Any

import pytest

pytest.importorskip("sqlalchemy")
pytest.importorskip("pyxtf")
pytest.importorskip("scipy")
pytest.importorskip("cv2")
jsonschema = pytest.importorskip("jsonschema")

from sqlalchemy import func, select  # noqa: E402
from tools.make_synthetic_xtf import write_synthetic_xtf  # noqa: E402

from sonarsentinel.config import load_config  # noqa: E402
from sonarsentinel.errors import JobNotCancellableError, NotFoundError  # noqa: E402
from sonarsentinel.jobs.manager import JobManager, JobRequest  # noqa: E402
from sonarsentinel.storage import repository as repo  # noqa: E402
from sonarsentinel.storage.db import Database  # noqa: E402
from sonarsentinel.storage.models import Detection, Job, Report  # noqa: E402

OPTIONS = {"detector_model": "classical", "anomaly_scan": False, "allow_no_gps": False}
N_PINGS = 600


@pytest.fixture(scope="module")
def survey_file(tmp_path_factory: pytest.TempPathFactory) -> Path:
    path = tmp_path_factory.mktemp("jobs") / "line_jobs.xtf"
    survey = write_synthetic_xtf(
        path,
        n_pings=N_PINGS,
        samples_per_side=400,
        step_m=0.1,
        targets=[(150, "starboard", 250), (430, "port", 300)],
        target_extent=(12, 30),
    )
    return Path(survey.path)


@pytest.fixture
def config() -> dict[str, Any]:
    cfg = load_config()
    cfg["chunking"] = {"pings_per_chunk": 150, "overlap_pings": 30}
    return cfg


@pytest.fixture
def db(tmp_path: Path) -> Iterator[Database]:
    database = Database(tmp_path / "jobs.db")
    yield database
    database.dispose()


def _queue(
    db: Database,
    manager: JobManager,
    sources: list[Path],
    job_id: str = "JOB-0000test",
    survey_id: str = "SRV-20260913-001",
) -> JobRequest:
    with db.session() as session, session.begin():
        repo.create_survey(
            session,
            survey_id=survey_id,
            job_id=job_id,
            name="jobs test",
            project=None,
            options=OPTIONS,
            files=[
                {"filename": p.name, "format": "xtf", "size_bytes": 1, "sha256": "0" * 64}
                for p in sources
            ],
        )
    request = JobRequest(job_id, survey_id, list(sources), dict(OPTIONS))
    manager.submit(request)
    return request


def _events(data_dir: Path, survey_id: str) -> list[dict[str, Any]]:
    log = data_dir / "results" / survey_id / "job.log.jsonl"
    return [json.loads(line) for line in log.read_text("utf-8").splitlines()]


def _schema() -> Any:
    text = resources.files("sonarsentinel.report").joinpath("schema", "report-1.0.schema.json")
    return jsonschema.Draft202012Validator(json.loads(text.read_text("utf-8")))


def test_job_completes_and_is_persisted(
    tmp_path: Path, db: Database, config: dict[str, Any], survey_file: Path
) -> None:
    manager = JobManager(db, config, tmp_path)
    seen: list[dict[str, Any]] = []
    manager.add_listener(seen.append)
    manager.start()
    try:
        request = _queue(db, manager, [survey_file])
        body = manager.wait(request.job_id, timeout=120)
    finally:
        manager.stop()

    # The rule-based detector adds RULE_BASED_DETECTOR, so the job ends with warnings.
    assert body["status"] == "completed_with_warnings", body
    assert body["percent"] == 100.0 and body["pings_total"] == N_PINGS
    assert "detect" in body["stage_timings_ms"] and body["finished_utc"]
    results = tmp_path / "results" / request.survey_id
    report = json.loads((results / "report.json").read_text("utf-8"))
    assert _schema().is_valid(report) and report["survey"]["survey_id"] == request.survey_id
    assert all((results / f"report.{fmt}").is_file() for fmt in ("csv", "geojson", "kml"))
    with db.session() as session:
        stored = session.scalar(select(func.count()).select_from(Detection))
        assert stored == report["summary"]["total_detections"]
        formats = {r.format for r in session.scalars(select(Report))}
        assert formats == {"json", "csv", "geojson", "kml"}
    events = _events(tmp_path, request.survey_id)
    assert all(e["job_id"] == request.job_id for e in events)
    assert [e["seq"] for e in events] == list(range(1, len(events) + 1))
    done = events[-1]
    assert done["type"] == "done" and sum(e["type"] == "done" for e in events) == 1
    assert done["status"] == "completed_with_warnings" and done["summary"] == report["summary"]
    assert done["report_urls"]["kml"].endswith(f"/surveys/{request.survey_id}/report?format=kml")
    assert len(manager.events[request.job_id]) == len(events) and seen == events
    assert manager.replay(request.job_id, len(events) - 2) == events[-2:]
    assert not (tmp_path / "work" / request.survey_id).exists()


def test_cancel_running_job_stops_within_one_chunk(
    tmp_path: Path, db: Database, config: dict[str, Any], survey_file: Path
) -> None:
    """TC-API-006 at the worker level: cancel after the first chunk, the rest never runs."""
    manager = JobManager(db, config, tmp_path)
    replies: list[str] = []

    def cancel_after_first_chunk(event: dict[str, Any]) -> None:
        if event["type"] == "progress" and event.get("stage") == "detect" and not replies:
            replies.append(manager.cancel(event["job_id"]))

    manager.add_listener(cancel_after_first_chunk)
    manager.start()
    try:
        request = _queue(db, manager, [survey_file])
        body = manager.wait(request.job_id, timeout=120)
    finally:
        manager.stop()

    assert replies == ["cancelling"] and body["status"] == "cancelled"
    events = _events(tmp_path, request.survey_id)
    chunks = [e for e in events if e["type"] == "progress" and e.get("stage") == "detect"]
    assert len(chunks) == 1
    assert events[-1]["type"] == "done" and events[-1]["status"] == "cancelled"
    assert events[-1]["report_urls"] == {} and events[-1]["seq"] == len(events)
    with db.session() as session:
        # Detections stream per file after it finishes, so none exist yet in the first chunk.
        assert session.scalar(select(func.count()).select_from(Detection)) == 0
    with pytest.raises(JobNotCancellableError):
        manager.cancel(request.job_id)


def test_cancel_keeps_detections_found_so_far(
    tmp_path: Path, db: Database, config: dict[str, Any], survey_file: Path
) -> None:
    """ADR-018 §2: a cancelled job persists the detections already streamed (second file)."""
    manager = JobManager(db, config, tmp_path)
    replies: list[str] = []

    def cancel_in_second_file(event: dict[str, Any]) -> None:
        if event["type"] == "detection" and not replies:
            replies.append(manager.cancel(event["job_id"]))

    manager.add_listener(cancel_in_second_file)
    manager.start()
    try:
        request = _queue(db, manager, [survey_file, survey_file])
        body = manager.wait(request.job_id, timeout=120)
    finally:
        manager.stop()
    assert body["status"] == "cancelled"
    events = _events(tmp_path, request.survey_id)
    streamed = {e["detection"]["detection_id"] for e in events if e["type"] == "detection"}
    assert streamed
    with db.session() as session:
        stored = set(session.scalars(select(Detection.detection_id)))
    assert stored == streamed
    assert events[-1]["summary"]["total_detections"] == len(streamed)


def test_cancel_queued_job(
    tmp_path: Path, db: Database, config: dict[str, Any], survey_file: Path
) -> None:
    manager = JobManager(db, config, tmp_path)  # worker not started yet: the job stays queued
    request = _queue(db, manager, [survey_file])
    assert manager.cancel(request.job_id) == "cancelled"
    manager.start()
    try:
        body = manager.wait(request.job_id, timeout=10)
    finally:
        manager.stop()
    assert body["status"] == "cancelled"
    assert not (tmp_path / "results" / request.survey_id / "job.log.jsonl").exists()
    assert manager.replay(request.job_id) == []
    with pytest.raises(NotFoundError):
        manager.cancel("JOB-deadbeef")


def test_failed_job_and_recovery(tmp_path: Path, db: Database, config: dict[str, Any]) -> None:
    corrupt = tmp_path / "corrupt.xtf"
    corrupt.write_bytes(bytes(2048))
    manager = JobManager(db, config, tmp_path)
    seen: list[dict[str, Any]] = []
    manager.add_listener(seen.append)
    manager.start()
    try:
        request = _queue(db, manager, [corrupt])
        body = manager.wait(request.job_id, timeout=60)
    finally:
        manager.stop()
    assert body["status"] == "failed" and body["error"]["code"] == "CORRUPT_HEADER"
    last = _events(tmp_path, request.survey_id)[-1]
    assert last["type"] == "error" and last["code"] == "CORRUPT_HEADER"
    assert seen and seen[-1] == last  # listeners get the error event too

    # A job still "running" when the server stopped is failed when the next server starts.
    orphan = JobManager(db, config, tmp_path)
    _queue(db, orphan, [corrupt], job_id="JOB-00000002", survey_id="SRV-20260913-002")
    with db.session() as session, session.begin():
        job = session.get(Job, "JOB-00000002")
        assert job is not None
        job.status = "running"
    assert JobManager(db, config, tmp_path).recover() == 1
    with db.session() as session:
        job = session.get(Job, "JOB-00000002")
        assert job is not None
        payload = repo.job_payload(job)
    assert payload["status"] == "failed" and payload["error"]["code"] == "INTERNAL_ERROR"
