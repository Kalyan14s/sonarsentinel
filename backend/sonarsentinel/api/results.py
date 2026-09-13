"""Survey, detection, track, report and chip endpoints and review decisions (ST-084, ST-086).

Shapes follow ``docs/architecture/05-api-specification.md`` §2.3–2.6 with the decisions of
ADR-018: detection queries share :mod:`sonarsentinel.api.filters` with filtered exports, and every
export is built from the stored detections, so review changes appear in all downloads.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Query, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import FileResponse, Response
from sqlalchemy.orm import Session

from sonarsentinel.api.context import ApiContext, get_context
from sonarsentinel.api.filters import (
    MAX_LIMIT,
    parse_query,
    query_detections,
    select_scope,
    summarize,
)
from sonarsentinel.api.review import (
    apply_review,
    label_record,
    parse_review,
    remove_labels,
    write_label,
)
from sonarsentinel.errors import NotFoundError, ValidationError
from sonarsentinel.jobs.manager import report_url
from sonarsentinel.report.builder import now_utc
from sonarsentinel.report.chips import OVERLAYS, chip_filename
from sonarsentinel.report.export import (
    GEO_FORMATS,
    MEDIA_TYPES,
    SUPPORTED_FORMATS,
    report_is_geotagged,
    serialize,
    track_coords,
    track_feature_collection,
)
from sonarsentinel.storage import repository as repo
from sonarsentinel.storage.models import Survey

router = APIRouter()


class NotGeotaggedError(ValidationError):
    """GeoJSON or KML requested for a survey without positions (ADR-018 §8)."""

    http_status = 409


def _survey_summary(session: Session, survey: Survey) -> dict[str, Any]:
    job = repo.job_for_survey(session, survey.survey_id)
    return {
        "survey_id": survey.survey_id,
        "name": survey.name,
        "project": survey.project_id,
        "status": survey.status,
        "created_utc": survey.created_utc,
        "start_utc": survey.start_utc,
        "end_utc": survey.end_utc,
        "source_files": repo.source_filenames(session, survey.survey_id),
        "job": {
            "job_id": job.job_id if job is not None else None,
            "status": job.status if job is not None else survey.status,
            "duration_s": repo.job_duration_s(job),
        },
        "bbox": repo.parse_bbox_wkt(survey.bbox_wkt),
        "track_length_km": survey.track_length_km,
        "summary": repo.detection_counts(session, survey.survey_id),
    }


def _report_urls(session: Session, survey: Survey) -> dict[str, str]:
    if repo.report_file(session, survey.survey_id, "json") is None:
        return {}
    geotagged = survey.bbox_wkt is not None or repo.has_geotagged_detections(
        session, survey.survey_id
    )
    return {
        fmt: report_url(survey.survey_id, fmt)
        for fmt in SUPPORTED_FORMATS
        if geotagged or fmt not in GEO_FORMATS
    }


@router.get("/surveys", tags=["surveys"], summary="Surveys, newest first")
def list_surveys(
    request: Request,
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
) -> dict[str, Any]:
    context = get_context(request.app)
    with context.database.session() as session:
        total, rows = repo.list_surveys(session, limit=limit, offset=offset)
        return {"total": total, "items": [_survey_summary(session, s) for s in rows]}


@router.get("/surveys/{survey_id}", tags=["surveys"], summary="Survey metadata and report links")
def get_survey(survey_id: str, request: Request) -> dict[str, Any]:
    context = get_context(request.app)
    with context.database.session() as session:
        survey = repo.require_survey(session, survey_id)
        detail = _survey_summary(session, survey) | {"report_urls": _report_urls(session, survey)}
    bounds_path = context.jobs.results_dir / survey_id / "mosaic_bounds.json"
    detail["mosaic"] = (
        {
            "url": f"/api/v1/surveys/{survey_id}/mosaic.png",
            "bounds": json.loads(bounds_path.read_text(encoding="utf-8"))["bounds"],
        }
        if bounds_path.is_file()
        else None
    )
    return detail


@router.get(
    "/surveys/{survey_id}/detections",
    tags=["detections"],
    summary="Filtered, sorted and paged detections",
)
def list_detections(
    survey_id: str,
    request: Request,
    cls: str | None = Query(None, alias="class"),
    min_conf: float | None = None,
    max_conf: float | None = None,
    tier: str | None = None,
    review_status: str | None = None,
    flags: str | None = None,
    bbox: str | None = None,
    include_rejected: bool = True,
    sort: str | None = None,
    limit: int = Query(100, ge=1, le=MAX_LIMIT),
    offset: int = Query(0, ge=0),
) -> dict[str, Any]:
    query = parse_query(
        cls=cls,
        min_conf=min_conf,
        max_conf=max_conf,
        tier=tier,
        review_status=review_status,
        flags=flags,
        bbox=bbox,
        include_rejected=include_rejected,
        sort=sort,
    )
    context = get_context(request.app)
    with context.database.session() as session:
        repo.require_survey(session, survey_id)
        items = repo.survey_detections(session, survey_id)
    selected = query_detections(items, query)
    return {"total": len(selected), "items": selected[offset : offset + limit]}


@router.get(
    "/surveys/{survey_id}/track",
    tags=["surveys"],
    summary="Track LineString and quality segments (GeoJSON)",
)
def get_track(survey_id: str, request: Request) -> dict[str, Any]:
    context = get_context(request.app)
    with context.database.session() as session:
        repo.require_survey(session, survey_id)
        return track_feature_collection(
            repo.track_segments(session, survey_id), repo.quality_events(session, survey_id)
        )


@router.get(
    "/surveys/{survey_id}/report",
    tags=["reports"],
    summary="Download the report as JSON, CSV, GeoJSON or KML",
)
def download_report(
    survey_id: str,
    request: Request,
    format: str = "json",  # noqa: A002 - API parameter name
    scope: str = "all",
    include_rejected: bool = False,
    cls: str | None = Query(None, alias="class"),
    min_conf: float | None = None,
    max_conf: float | None = None,
    tier: str | None = None,
    review_status: str | None = None,
    flags: str | None = None,
    bbox: str | None = None,
) -> Response:
    fmt = format.lower()
    if fmt not in SUPPORTED_FORMATS:
        raise ValidationError(
            f"Unsupported report format: {format}",
            field="format",
            supported=list(SUPPORTED_FORMATS),
        )
    query = parse_query(
        cls=cls,
        min_conf=min_conf,
        max_conf=max_conf,
        tier=tier,
        review_status=review_status,
        flags=flags,
        bbox=bbox,
        include_rejected=include_rejected,
    )
    context = get_context(request.app)
    with context.database.session() as session:
        survey = repo.require_survey(session, survey_id)
        path = repo.report_file(session, survey_id, "json")
        if path is None or not Path(path).is_file():
            raise NotFoundError(
                f"The report for {survey_id} is not available (status {survey.status})",
                survey_id=survey_id,
                status=survey.status,
            )
        stored = repo.survey_detections(session, survey_id)
        segments = repo.track_segments(session, survey_id)
    base: dict[str, Any] = json.loads(Path(path).read_text(encoding="utf-8"))
    if fmt in GEO_FORMATS and not report_is_geotagged(base | {"detections": stored}):
        raise NotGeotaggedError("Survey is not geotagged", survey_id=survey_id, format=fmt)
    detections = select_scope(stored, scope, query, include_rejected=include_rejected)
    report = base | {"summary": summarize(detections), "detections": detections}
    content = serialize(report, fmt, track=track_coords(segments))
    return Response(
        content,
        media_type=MEDIA_TYPES[fmt],
        headers={"Content-Disposition": f'attachment; filename="{survey_id}_report.{fmt}"'},
    )


@router.get("/detections/{detection_id}", tags=["detections"], summary="One detection")
def get_detection(detection_id: str, request: Request) -> dict[str, Any]:
    context = get_context(request.app)
    with context.database.session() as session:
        row = repo.require_detection(session, detection_id)
        detection: dict[str, Any] = json.loads(row.detection_json)
        return detection


@router.get(
    "/detections/{detection_id}/chip.png",
    tags=["detections"],
    summary="Detection chip (PNG) with a mask, shadow, anomaly or no overlay",
    response_class=FileResponse,
)
def get_chip(detection_id: str, request: Request, overlay: str = "mask") -> FileResponse:
    if overlay not in OVERLAYS:
        raise ValidationError(
            f"Unknown overlay: {overlay}", field="overlay", supported=list(OVERLAYS)
        )
    context = get_context(request.app)
    with context.database.session() as session:
        survey_id = repo.require_detection(session, detection_id).survey_id
    path = context.jobs.results_dir / survey_id / "chips" / chip_filename(detection_id, overlay)
    if not path.is_file():
        raise NotFoundError(
            f"No {overlay} chip for detection {detection_id}",
            detection_id=detection_id,
            overlay=overlay,
        )
    return FileResponse(path, media_type="image/png")


@router.get(
    "/surveys/{survey_id}/mosaic.png",
    tags=["surveys"],
    summary="Georeferenced mosaic (PNG, EPSG:4326); bounds in the survey detail and done event",
    response_class=FileResponse,
)
def get_mosaic(survey_id: str, request: Request) -> FileResponse:
    context = get_context(request.app)
    with context.database.session() as session:
        repo.require_survey(session, survey_id)
    path = context.jobs.results_dir / survey_id / "mosaic.png"
    if not path.is_file():
        raise NotFoundError(f"No mosaic for survey {survey_id}", survey_id=survey_id)
    return FileResponse(path, media_type="image/png")


def _review(context: ApiContext, detection_id: str, body: Any) -> dict[str, Any]:
    created = now_utc()
    with context.database.session() as session, session.begin():
        row = repo.require_detection(session, detection_id)
        before: dict[str, Any] = json.loads(row.detection_json)
        decision = parse_review(body, before["class"])
        after = apply_review(before, decision, created)
        repo.record_review(session, row, after, old_cls=before["class"], created_utc=created)
        survey_id = row.survey_id
    labels = context.data_dir / "labels"
    remove_labels(labels, detection_id)
    if decision.status != "pending":
        chip = context.jobs.results_dir / survey_id / "chips" / chip_filename(detection_id, "mask")
        write_label(labels, label_record(before, after, survey_id, created), chip)
    return after


@router.patch(
    "/detections/{detection_id}",
    tags=["detections"],
    summary="Confirm, reject (with a reason), reclassify or undo a review",
)
async def review_detection(detection_id: str, request: Request) -> dict[str, Any]:
    try:
        body = await request.json()
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise ValidationError("Send the review as a JSON object", field="body") from exc
    context = get_context(request.app)
    result: dict[str, Any] = await run_in_threadpool(_review, context, detection_id, body)
    return result
