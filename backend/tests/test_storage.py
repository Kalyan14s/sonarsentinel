"""ST-085: SQLite storage — idempotent migrations, ids, report persistence, job payload."""

from __future__ import annotations

import json
import re
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from importlib import resources
from pathlib import Path
from typing import Any

import pytest

pytest.importorskip("sqlalchemy")

from sqlalchemy import func, inspect, select, text  # noqa: E402

from sonarsentinel.storage import repository as repo  # noqa: E402
from sonarsentinel.storage.db import MIGRATIONS, SCHEMA_VERSION, Database, migrate  # noqa: E402
from sonarsentinel.storage.models import (  # noqa: E402
    Detection,
    Job,
    ModelVersion,
    QualityEvent,
    Report,
    Survey,
    TrackSegment,
)

TABLES = {
    "project",
    "survey",
    "source_file",
    "job",
    "detection",
    "review",
    "track_segment",
    "quality_event",
    "report",
    "model_version",
    "schema_version",
}


def _example() -> dict[str, Any]:
    path = resources.files("sonarsentinel.report").joinpath("schema", "example-report-1.0.json")
    data: dict[str, Any] = json.loads(path.read_text("utf-8"))
    return data


@pytest.fixture
def db(tmp_path: Path) -> Iterator[Database]:
    database = Database(tmp_path / "test.db")
    yield database
    database.dispose()


def _new_survey(db: Database, survey_id: str = "SRV-20260913-001") -> None:
    with db.session() as session, session.begin():
        repo.create_survey(
            session,
            survey_id=survey_id,
            job_id="JOB-0000abcd",
            name="Line 07",
            project="NIOT Cleanup 2026",
            options={"allow_no_gps": False},
            files=[
                {
                    "filename": "line_07.xtf",
                    "format": "xtf",
                    "size_bytes": 1024,
                    "sha256": "ab" * 32,
                }
            ],
        )


def test_migrations_are_idempotent(tmp_path: Path) -> None:
    path = tmp_path / "migrate.db"
    first = Database(path)
    assert first.version == SCHEMA_VERSION == MIGRATIONS[-1][0]
    assert migrate(first.engine) == SCHEMA_VERSION
    inspector = inspect(first.engine)
    assert set(inspector.get_table_names()) >= TABLES
    indexes = {index["name"] for index in inspector.get_indexes("detection")}
    assert {
        "ix_detection_survey_tier_confidence",
        "ix_detection_cls",
        "ix_detection_review_status",
    } <= indexes
    first.dispose()

    again = Database(path)
    with again.engine.connect() as conn:
        applied = conn.execute(text("SELECT COUNT(*) FROM schema_version")).scalar()
    assert again.version == SCHEMA_VERSION and applied == len(MIGRATIONS)
    again.dispose()


def test_survey_and_job_ids(db: Database) -> None:
    with db.session() as session:
        assert repo.next_survey_id(session, "20260913") == "SRV-20260913-001"
    _new_survey(db)
    with db.session() as session:
        assert repo.next_survey_id(session, "20260913") == "SRV-20260913-002"
        assert repo.next_survey_id(session, "20260914") == "SRV-20260914-001"
        job = session.get(Job, "JOB-0000abcd")
        survey = session.get(Survey, "SRV-20260913-001")
        assert job is not None and job.status == "queued" and job.percent == 0.0
        assert survey is not None and survey.project_id == "niot-cleanup-2026"
    assert re.fullmatch(r"JOB-[0-9a-f]{8}", repo.new_job_id())


def test_report_round_trip(db: Database) -> None:
    report = _example()
    survey_id = report["survey"]["survey_id"]
    _new_survey(db, survey_id)
    with db.session() as session, session.begin():
        saved = repo.save_results(
            session,
            survey_id,
            report,
            {"json": "results/report.json", "csv": "results/report.csv"},
            status="completed",
            quality_events=[{"code": "DROPOUT", "ping_start": 1, "ping_end": 5, "message": "5"}],
            track_segments=[
                {"points": [[13.08, 80.30], [13.09, 80.31]], "ping_start": 0, "ping_end": 99}
            ],
        )
    assert saved == len(report["detections"]) > 0
    with db.session() as session:
        stored = session.scalars(select(Detection.detection_id)).all()
        assert sorted(stored) == sorted(d["detection_id"] for d in report["detections"])
        first = report["detections"][0]
        row = session.get(Detection, first["detection_id"])
        assert row is not None and json.loads(row.detection_json) == first
        assert row.cls == first["class"] and row.confidence == first["confidence"]
        assert row.quality_flags == ";".join(first["quality_flags"])
        assert row.model_version_id == f"detector:{first['model_version']}"
        assert session.scalar(select(func.count()).select_from(Report)) == 2
        assert session.scalar(select(func.count()).select_from(QualityEvent)) == 1
        segment = session.scalars(select(TrackSegment)).one()
        assert segment.line_wkt == "LINESTRING(80.3 13.08, 80.31 13.09)"
        survey = session.get(Survey, survey_id)
        assert survey is not None and survey.status == "completed"
        if report["survey"]["bbox"]:
            assert survey.bbox_wkt is not None and survey.bbox_wkt.startswith("POLYGON((")
        assert "detector" in set(session.scalars(select(ModelVersion.kind)))


def test_job_payload_eta_and_error() -> None:
    job = Job(
        job_id="JOB-00000001",
        survey_id="SRV-20260913-001",
        status="running",
        stage="detect",
        percent=25.0,
        pings_done=10,
        pings_total=40,
        stage_timings_json='{"parse": 5}',
        warnings_json='[{"code": "HIGH_MOTION", "ping_start": 1, "ping_end": 2}]',
        error_json=None,
        created_utc="2026-09-13T09:59:59Z",
        started_utc="2026-09-13T10:00:00Z",
        finished_utc=None,
    )
    now = datetime(2026, 9, 13, 10, 0, 10, tzinfo=UTC)
    body = repo.job_payload(job, now=now)
    assert body["eta_s"] == 30 and body["stage_timings_ms"] == {"parse": 5}
    assert body["warnings"][0]["code"] == "HIGH_MOTION" and "error" not in body

    job.status, job.error_json = (
        "failed",
        json.dumps({"error": {"code": "CORRUPT_HEADER", "message": "bad", "details": {}}}),
    )
    failed = repo.job_payload(job, now=now + timedelta(seconds=5))
    assert failed["eta_s"] is None and failed["error"]["code"] == "CORRUPT_HEADER"
