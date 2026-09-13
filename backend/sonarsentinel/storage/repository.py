"""Queries and conversions between report objects and database rows (ST-085, ST-084, ST-086)."""

from __future__ import annotations

import json
import re
import secrets
from collections.abc import Iterable
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from sonarsentinel.errors import NotFoundError
from sonarsentinel.report.builder import now_utc
from sonarsentinel.storage.models import (
    Detection,
    Job,
    ModelVersion,
    Project,
    QualityEvent,
    Report,
    Review,
    SourceFile,
    Survey,
    TrackSegment,
)

FINISHED_STATUSES = frozenset({"completed", "completed_with_warnings", "failed", "cancelled"})
_NUMBER = r"-?\d+(?:\.\d+)?(?:[eE][-+]?\d+)?"


def next_survey_id(session: Session, day: str) -> str:
    """``SRV-<day>-NNN`` with the next free number for that day (``day`` is ``YYYYMMDD``)."""
    prefix = f"SRV-{day}-"
    ids = session.scalars(select(Survey.survey_id).where(Survey.survey_id.like(f"{prefix}%")))
    numbers = [int(i[len(prefix) :]) for i in ids if i[len(prefix) :].isdigit()]
    return f"{prefix}{max(numbers, default=0) + 1:03d}"


def new_job_id() -> str:
    return f"JOB-{secrets.token_hex(4)}"


def project_id_for(name: str) -> str:
    slug = re.sub(r"[^A-Za-z0-9]+", "-", name).strip("-").lower()
    return slug or "default"


def create_survey(
    session: Session,
    *,
    survey_id: str,
    job_id: str,
    name: str,
    project: str | None,
    options: dict[str, Any],
    files: list[dict[str, Any]],
) -> Job:
    """Survey, source file and queued job rows for a new upload."""
    # The tables have foreign keys but no ORM relationships, so the unit of work doesn't order
    # inserts by dependency: flush parents before adding children.
    now = now_utc()
    project_id = None
    if project:
        project_id = project_id_for(project)
        if session.get(Project, project_id) is None:
            session.add(Project(project_id=project_id, name=project, created_utc=now))
            session.flush()
    session.add(
        Survey(
            survey_id=survey_id,
            project_id=project_id,
            name=name,
            status="queued",
            start_utc=None,
            end_utc=None,
            track_length_km=None,
            bbox_wkt=None,
            options_json=json.dumps(options, sort_keys=True),
            config_hash=None,
            created_utc=now,
        )
    )
    session.flush()
    for i, info in enumerate(files, start=1):
        session.add(
            SourceFile(
                file_id=f"{survey_id}-F{i:02d}",
                survey_id=survey_id,
                filename=info["filename"],
                format=info["format"],
                size_bytes=int(info["size_bytes"]),
                pings=info.get("pings"),
                sonar_json=json.dumps(info["sonar"]) if info.get("sonar") else None,
                sha256=info["sha256"],
            )
        )
    job = Job(
        job_id=job_id,
        survey_id=survey_id,
        status="queued",
        stage=None,
        percent=0.0,
        pings_done=None,
        pings_total=None,
        stage_timings_json="{}",
        warnings_json="[]",
        error_json=None,
        created_utc=now,
        started_utc=None,
        finished_utc=None,
    )
    session.add(job)
    return job


def bbox_wkt(bbox: list[float] | None) -> str | None:
    """``[minLon, minLat, maxLon, maxLat]`` as a WKT polygon."""
    if not bbox:
        return None
    x1, y1, x2, y2 = bbox
    return f"POLYGON(({x1} {y1}, {x2} {y1}, {x2} {y2}, {x1} {y2}, {x1} {y1}))"


def _wkt_pairs(wkt: str | None) -> list[tuple[float, float]]:
    if not wkt:
        return []
    numbers = [float(n) for n in re.findall(_NUMBER, wkt)]
    return list(zip(numbers[0::2], numbers[1::2], strict=False))


def parse_bbox_wkt(wkt: str | None) -> list[float] | None:
    """WKT polygon from :func:`bbox_wkt` → ``[minLon, minLat, maxLon, maxLat]``."""
    pairs = _wkt_pairs(wkt)
    if not pairs:
        return None
    lons = [p[0] for p in pairs]
    lats = [p[1] for p in pairs]
    return [min(lons), min(lats), max(lons), max(lats)]


def linestring_points(wkt: str | None) -> list[list[float]]:
    """``LINESTRING(lon lat, ...)`` → ``[[lat, lon], ...]``."""
    return [[lat, lon] for lon, lat in _wkt_pairs(wkt)]


def footprint_wkt(footprint: list[list[float]] | None) -> str | None:
    """Report footprint (``[[lat, lon], …]``) as a closed WKT polygon in lon/lat order."""
    if not footprint:
        return None
    ring = [*footprint, footprint[0]]
    return "POLYGON((" + ", ".join(f"{lon} {lat}" for lat, lon in ring) + "))"


def detection_record(
    det: dict[str, Any], survey_id: str, model_version_id: str | None
) -> Detection:
    """Report detection → ``detection`` row (the full object is kept in ``detection_json``)."""
    position = det.get("position") or {}
    dims = det.get("dimensions") or {}
    ref = det.get("sonar_ref") or {}
    return Detection(
        detection_id=det["detection_id"],
        survey_id=survey_id,
        model_version_id=model_version_id,
        cls=det["class"],
        confidence=float(det["confidence"]),
        alert_tier=det["alert_tier"],
        lat=position.get("lat"),
        lon=position.get("lon"),
        footprint_wkt=footprint_wkt(det.get("footprint")),
        depth_m=position.get("depth_m"),
        uncertainty_m=position.get("uncertainty_m"),
        length_m=dims.get("length_m"),
        width_m=dims.get("width_m"),
        area_m2=dims.get("area_m2"),
        height_m=dims.get("height_m"),
        orientation_deg=det.get("orientation_deg"),
        side=ref.get("side"),
        ping_start=ref.get("ping_start"),
        ping_end=ref.get("ping_end"),
        ground_range_m=ref.get("ground_range_m"),
        scores_json=json.dumps(det.get("scores", {}), sort_keys=True),
        quality_flags=";".join(det.get("quality_flags", [])),
        n_views=int(det.get("n_views", 1)),
        review_status=(det.get("review") or {}).get("status", "pending"),
        chip_path=None,
        mask_rle=None,
        detection_json=json.dumps(det, ensure_ascii=False),
    )


def ensure_model_version(session: Session, kind: str, version_id: str) -> str:
    """Row for ``name@x.y.z`` of a model kind; returns its key ``kind:name@x.y.z``."""
    key = f"{kind}:{version_id}"
    if session.get(ModelVersion, key) is None:
        name, _, version = version_id.partition("@")
        session.add(
            ModelVersion(
                model_version_id=key, kind=kind, name=name, version=version, metrics_json=None
            )
        )
        session.flush()
    return key


def save_detections(session: Session, survey_id: str, detections: Iterable[dict[str, Any]]) -> int:
    """Insert detection rows (with their detector model versions)."""
    count = 0
    for det in detections:
        model_key = ensure_model_version(session, "detector", det["model_version"])
        session.add(detection_record(det, survey_id, model_key))
        count += 1
    return count


def save_results(
    session: Session,
    survey_id: str,
    report: dict[str, Any],
    report_paths: dict[str, str],
    *,
    status: str,
    quality_events: list[dict[str, Any]] | None = None,
    track_segments: list[dict[str, Any]] | None = None,
) -> int:
    """Persist a finished job's report: survey fields, models, detections, files, events."""
    survey = session.get(Survey, survey_id)
    if survey is None:
        raise NotFoundError(f"Survey {survey_id} not found", survey_id=survey_id)
    section = report["survey"]
    survey.status = status
    survey.start_utc = section.get("start_utc")
    survey.end_utc = section.get("end_utc")
    survey.track_length_km = section.get("track_length_km")
    survey.bbox_wkt = bbox_wkt(section.get("bbox"))
    survey.config_hash = report["processing"].get("config_hash")

    for kind, version_id in report["processing"].get("models", {}).items():
        if version_id:
            ensure_model_version(session, kind, version_id)
    save_detections(session, survey_id, report["detections"])

    now = now_utc()
    for fmt, path in sorted(report_paths.items()):
        session.add(Report(survey_id=survey_id, format=fmt, path=str(path), created_utc=now))
    save_track(session, survey_id, quality_events, track_segments)
    return len(report["detections"])


def save_track(
    session: Session,
    survey_id: str,
    quality_events: list[dict[str, Any]] | None,
    track_segments: list[dict[str, Any]] | None,
) -> None:
    """Quality events and track segments of a job."""
    for item in quality_events or []:
        session.add(
            QualityEvent(
                survey_id=survey_id,
                code=str(item["code"]),
                ping_start=item.get("ping_start"),
                ping_end=item.get("ping_end"),
                message=item.get("message"),
            )
        )
    for segment in track_segments or []:
        points = segment.get("points") or []
        if len(points) < 2:
            continue
        line = "LINESTRING(" + ", ".join(f"{lon} {lat}" for lat, lon in points) + ")"
        session.add(
            TrackSegment(
                survey_id=survey_id,
                ping_start=segment.get("ping_start"),
                ping_end=segment.get("ping_end"),
                line_wkt=line,
            )
        )


# -- read side (ST-084) ---------------------------------------------------------------------------


def require_survey(session: Session, survey_id: str) -> Survey:
    survey = session.get(Survey, survey_id)
    if survey is None:
        raise NotFoundError(f"Survey {survey_id} not found", survey_id=survey_id)
    return survey


def require_detection(session: Session, detection_id: str) -> Detection:
    detection = session.get(Detection, detection_id)
    if detection is None:
        raise NotFoundError(f"Detection {detection_id} not found", detection_id=detection_id)
    return detection


def job_for_survey(session: Session, survey_id: str) -> Job | None:
    return session.scalar(select(Job).where(Job.survey_id == survey_id))


def list_surveys(session: Session, *, limit: int, offset: int) -> tuple[int, list[Survey]]:
    """Newest surveys first."""
    total = int(session.scalar(select(func.count()).select_from(Survey)) or 0)
    rows = session.scalars(
        select(Survey)
        .order_by(Survey.created_utc.desc(), Survey.survey_id.desc())
        .limit(limit)
        .offset(offset)
    ).all()
    return total, list(rows)


def source_filenames(session: Session, survey_id: str) -> list[str]:
    rows = session.scalars(
        select(SourceFile.filename)
        .where(SourceFile.survey_id == survey_id)
        .order_by(SourceFile.file_id)
    )
    return list(rows)


def detection_counts(session: Session, survey_id: str) -> dict[str, Any]:
    """Report ``summary`` counts from the detection columns (reflects reclassifications)."""
    by_class: dict[str, int] = {}
    for cls, count in session.execute(
        select(Detection.cls, func.count())
        .where(Detection.survey_id == survey_id)
        .group_by(Detection.cls)
    ).all():
        by_class[str(cls)] = int(count)
    by_tier: dict[str, int] = {}
    for tier, count in session.execute(
        select(Detection.alert_tier, func.count())
        .where(Detection.survey_id == survey_id)
        .group_by(Detection.alert_tier)
    ).all():
        by_tier[str(tier)] = int(count)
    return {
        "total_detections": sum(by_class.values()),
        "by_class": dict(sorted(by_class.items())),
        "by_tier": dict(sorted(by_tier.items())),
    }


def has_geotagged_detections(session: Session, survey_id: str) -> bool:
    count = session.scalar(
        select(func.count())
        .select_from(Detection)
        .where(Detection.survey_id == survey_id, Detection.lat.is_not(None))
    )
    return bool(count)


def survey_detections(session: Session, survey_id: str) -> list[dict[str, Any]]:
    """Stored report detections in ID (ping) order."""
    rows = session.scalars(
        select(Detection.detection_json)
        .where(Detection.survey_id == survey_id)
        .order_by(Detection.detection_id)
    )
    return [json.loads(text) for text in rows]


def report_file(session: Session, survey_id: str, fmt: str) -> str | None:
    """Path of the newest report file of a format, if one was written."""
    return session.scalar(
        select(Report.path)
        .where(Report.survey_id == survey_id, Report.format == fmt)
        .order_by(Report.report_id.desc())
        .limit(1)
    )


def track_segments(session: Session, survey_id: str) -> list[dict[str, Any]]:
    rows = session.scalars(
        select(TrackSegment)
        .where(TrackSegment.survey_id == survey_id)
        .order_by(TrackSegment.ping_start, TrackSegment.segment_id)
    )
    return [
        {
            "points": linestring_points(row.line_wkt),
            "ping_start": row.ping_start,
            "ping_end": row.ping_end,
        }
        for row in rows
    ]


def quality_events(session: Session, survey_id: str) -> list[dict[str, Any]]:
    rows = session.scalars(
        select(QualityEvent)
        .where(QualityEvent.survey_id == survey_id)
        .order_by(QualityEvent.ping_start, QualityEvent.event_id)
    )
    return [
        {
            "code": row.code,
            "ping_start": row.ping_start,
            "ping_end": row.ping_end,
            "message": row.message,
        }
        for row in rows
    ]


def record_review(
    session: Session,
    row: Detection,
    updated: dict[str, Any],
    *,
    old_cls: str,
    created_utc: str,
) -> None:
    """Store a review decision on the detection and append it to the ``review`` history."""
    review = updated["review"]
    row.detection_json = json.dumps(updated, ensure_ascii=False)
    row.cls = updated["class"]
    row.review_status = review["status"]
    session.add(
        Review(
            detection_id=row.detection_id,
            reviewer=review.get("reviewer"),
            action=review["status"],
            old_cls=old_cls,
            new_cls=updated["class"],
            reject_reason=review.get("reject_reason"),
            note=review.get("note"),
            created_utc=created_utc,
        )
    )


def _parse_utc(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def job_duration_s(job: Job | None) -> float | None:
    if job is None or not job.started_utc or not job.finished_utc:
        return None
    return round((_parse_utc(job.finished_utc) - _parse_utc(job.started_utc)).total_seconds(), 2)


def job_payload(job: Job, now: datetime | None = None) -> dict[str, Any]:
    """``GET /jobs/{job_id}`` body (API spec §2.7) plus survey id, times and any error."""
    eta_s = None
    if job.status == "running" and job.started_utc and 0.0 < job.percent < 100.0:
        elapsed = ((now or datetime.now(UTC)) - _parse_utc(job.started_utc)).total_seconds()
        eta_s = max(0, round(elapsed * (100.0 - job.percent) / job.percent))
    payload: dict[str, Any] = {
        "job_id": job.job_id,
        "survey_id": job.survey_id,
        "status": job.status,
        "stage": job.stage,
        "percent": job.percent,
        "eta_s": eta_s,
        "pings_done": job.pings_done,
        "pings_total": job.pings_total,
        "stage_timings_ms": json.loads(job.stage_timings_json or "{}"),
        "warnings": json.loads(job.warnings_json or "[]"),
        "created_utc": job.created_utc,
        "started_utc": job.started_utc,
        "finished_utc": job.finished_utc,
    }
    if job.error_json:
        payload["error"] = json.loads(job.error_json).get("error")
    return payload
