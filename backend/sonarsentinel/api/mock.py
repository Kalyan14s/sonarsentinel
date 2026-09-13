"""Mock API server for frontend development (ST-087; routes of ST-083/084/086/072, ADR-018).

Serves one canned survey (``fixtures/mock_report.json``) and its recorded job events
(``fixtures/mock_events.json``) through the same endpoint shapes as the real API: surveys, filtered
detections, track with quality segments, report downloads in four formats and scopes, chips
(placeholder PNGs), jobs, review ``PATCH`` and the ``/ws/jobs/{job_id}`` event stream with ``seq``,
``resume`` and ``ping``. Filtering, review validation and exports use the real modules. State
(reviews) is in memory and resets on restart. Fixtures come from ``scripts/make_mock_fixtures.py``.

    sonarsentinel serve --mock --port 8001
"""

from __future__ import annotations

import asyncio
import copy
import json
import struct
import zlib
from importlib import resources
from typing import Any

from fastapi import APIRouter, FastAPI, Query, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import Response

from sonarsentinel import __version__
from sonarsentinel.api.filters import (
    MAX_LIMIT,
    parse_query,
    query_detections,
    select_scope,
    summarize,
)
from sonarsentinel.api.handlers import install_handlers
from sonarsentinel.api.history import parse_survey_filters, survey_matches
from sonarsentinel.api.review import apply_review, parse_review
from sonarsentinel.api.ws import (
    CLOSE_NORMAL,
    CLOSE_NOT_FOUND,
    TERMINAL_EVENTS,
    first_message,
    pong,
    resume_after,
)
from sonarsentinel.config import load_config
from sonarsentinel.errors import JobNotCancellableError, NotFoundError, ValidationError
from sonarsentinel.report.builder import now_utc
from sonarsentinel.report.chips import OVERLAYS
from sonarsentinel.report.export import (
    GEO_FORMATS,
    MEDIA_TYPES,
    SUPPORTED_FORMATS,
    report_is_geotagged,
    serialize,
    track_coords,
    track_feature_collection,
)
from sonarsentinel.settings import default_settings, merge_update, validate_settings

API = "/api/v1"


def _fixture(name: str) -> Any:
    text = resources.files("sonarsentinel.api").joinpath("fixtures", name).read_text("utf-8")
    return json.loads(text)


def placeholder_png(size: int = 256, grey: int = 96) -> bytes:
    """A plain grey 8-bit greyscale PNG (no image library needed)."""

    def chunk(tag: bytes, data: bytes) -> bytes:
        crc = zlib.crc32(tag + data) & 0xFFFFFFFF
        return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", crc)

    rows = b"".join(b"\x00" + bytes([grey]) * size for _ in range(size))
    header = struct.pack(">IIBBBBB", size, size, 8, 0, 0, 0, 0)
    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", header)
        + chunk(b"IDAT", zlib.compress(rows))
        + chunk(b"IEND", b"")
    )


class MockState:
    def __init__(self) -> None:
        self.report: dict[str, Any] = _fixture("mock_report.json")
        self.events: list[dict[str, Any]] = _fixture("mock_events.json")
        self.survey_id: str = self.report["survey"]["survey_id"]
        self.job_id = self.survey_id.replace("SRV-", "JOB-")
        self.job_status = (
            "completed_with_warnings"
            if self.report["processing"]["quality"]["warnings"]
            else "completed"
        )
        self.detections: dict[str, dict[str, Any]] = {
            d["detection_id"]: d for d in self.report["detections"]
        }
        self.track = [
            {k: e.get(k) for k in ("points", "ping_start", "ping_end")}
            for e in self.events
            if e["type"] == "track"
        ]
        self.quality = [
            {k: e.get(k) for k in ("code", "ping_start", "ping_end", "message")}
            for e in self.events
            if e["type"] == "warning"
        ]
        self.deleted = False
        self.settings: dict[str, Any] = default_settings(load_config())

    def report_urls(self) -> dict[str, str]:
        geotagged = report_is_geotagged(self.report)
        return {
            fmt: f"{API}/surveys/{self.survey_id}/report?format={fmt}"
            for fmt in SUPPORTED_FORMATS
            if geotagged or fmt not in GEO_FORMATS
        }

    def survey_summary(self) -> dict[str, Any]:
        survey = self.report["survey"]
        return {
            "survey_id": self.survey_id,
            "name": survey["name"],
            "project": survey.get("project"),
            "status": self.job_status,
            "created_utc": self.report["generated_utc"],
            "start_utc": survey.get("start_utc"),
            "end_utc": survey.get("end_utc"),
            "source_files": survey["source_files"],
            "job": {
                "job_id": self.job_id,
                "status": self.job_status,
                "duration_s": self.report["processing"]["duration_s"],
            },
            "bbox": survey["bbox"],
            "track_length_km": survey["track_length_km"],
            "warning_count": len(self.quality),
            "size_bytes": 0,
            "summary": summarize(self.detections.values()),
        }

    def stream(self) -> list[dict[str, Any]]:
        """Recorded events with the manager's ``done`` fields (ADR-018 §2)."""
        events = []
        for event in self.events:
            item = event | {"job_id": self.job_id}
            if item["type"] == "done":
                item |= {"report_urls": self.report_urls(), "mosaic": None}
            events.append(item)
        return events


def create_mock_app(event_delay_s: float = 0.05) -> FastAPI:
    state = MockState()
    app = FastAPI(title="SonarSentinel mock API", version=__version__, docs_url="/docs")
    install_handlers(app)

    def survey_or_404(survey_id: str) -> None:
        if survey_id != state.survey_id or state.deleted:
            raise NotFoundError(f"Survey {survey_id} not found", survey_id=survey_id)

    def detection_or_404(detection_id: str) -> dict[str, Any]:
        if detection_id not in state.detections:
            raise NotFoundError(f"Detection {detection_id} not found", detection_id=detection_id)
        return state.detections[detection_id]

    r = APIRouter(prefix=API)

    @r.get("/health")
    def health() -> dict[str, Any]:
        return {
            "status": "ok",
            "version": __version__,
            "gpu": {"available": False, "name": None},
            "runtime": "mock",
            "models_loaded": True,
            "offline_tiles": False,
        }

    @r.get("/models")
    def models() -> dict[str, Any]:
        detector = state.report["processing"]["models"]["detector"]
        return {"total": 1, "items": [{"kind": "detector", "id": detector, "available": True}]}

    @r.post("/surveys/validate")
    async def validate(request: Request) -> dict[str, Any]:
        form = await request.form()
        files = []
        for upload in form.getlist("files"):
            name = getattr(upload, "filename", str(upload))
            is_image = name.lower().endswith((".png", ".jpg", ".jpeg"))
            files.append(
                {
                    "filename": name,
                    "valid": True,
                    "format": "image_only" if is_image else "xtf",
                    "has_navigation": not is_image,
                    "warnings": ["NO_NAVIGATION: attach a navigation CSV or continue without GPS"]
                    if is_image
                    else [],
                }
            )
        return {"files": files}

    @r.post("/surveys", status_code=202)
    def create_survey() -> dict[str, Any]:
        return {
            "survey_id": state.survey_id,
            "job_id": state.job_id,
            "status": "queued",
            "ws_url": f"/ws/jobs/{state.job_id}",
        }

    @r.get("/surveys")
    def surveys(
        q: str | None = None,
        project: str | None = None,
        status: str | None = None,
        date_from: str | None = Query(None, alias="from"),
        date_to: str | None = Query(None, alias="to"),
        limit: int = Query(50, ge=1, le=500),
        offset: int = Query(0, ge=0),
    ) -> dict[str, Any]:
        filters = parse_survey_filters(
            q=q, project=project, status=status, date_from=date_from, date_to=date_to
        )
        summaries = [] if state.deleted else [state.survey_summary()]
        items = [s for s in summaries if survey_matches(s, filters)]
        return {"total": len(items), "items": items[offset : offset + limit]}

    @r.delete("/surveys/{survey_id}", status_code=204, response_class=Response)
    def delete_survey(survey_id: str) -> Response:
        survey_or_404(survey_id)
        state.deleted = True
        return Response(status_code=204)

    def mock_system() -> dict[str, Any]:
        return {
            "data_dir": "mock",
            "max_upload_gb": 2.0,
            "keep_work_files": False,
            "offline_tiles_available": False,
            "runtimes_available": ["auto"],
            "version": __version__,
        }

    @r.get("/settings")
    def get_settings() -> dict[str, Any]:
        return state.settings | {"system": mock_system()}

    @r.put("/settings")
    async def put_settings(request: Request) -> dict[str, Any]:
        try:
            body = await request.json()
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            raise ValidationError("Send the settings as a JSON object", field="body") from exc
        detector = state.report["processing"]["models"]["detector"]
        state.settings = validate_settings(
            merge_update(state.settings, body), model_ids=[detector], tiles_available=False
        )
        return state.settings | {"system": mock_system()}

    @r.get("/tiles/{z}/{x}/{y}.png")
    def tile(z: int, x: int, y: int) -> Response:
        raise NotFoundError("The mock has no offline tiles", z=z, x=x, y=y)

    @r.get("/surveys/{survey_id}")
    def survey(survey_id: str) -> dict[str, Any]:
        survey_or_404(survey_id)
        return state.survey_summary() | {"report_urls": state.report_urls()}

    @r.get("/surveys/{survey_id}/track")
    def track(survey_id: str) -> dict[str, Any]:
        survey_or_404(survey_id)
        return track_feature_collection(state.track, state.quality)

    @r.get("/surveys/{survey_id}/detections")
    def detections(
        survey_id: str,
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
        survey_or_404(survey_id)
        items = query_detections(state.detections.values(), query)
        return {"total": len(items), "items": items[offset : offset + limit]}

    @r.get("/surveys/{survey_id}/report")
    def report(
        survey_id: str,
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
        survey_or_404(survey_id)
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
        stored = list(state.detections.values())
        selected = select_scope(stored, scope, query, include_rejected=include_rejected)
        current = copy.deepcopy(state.report) | {
            "summary": summarize(selected),
            "detections": selected,
        }
        content = serialize(current, fmt, track=track_coords(state.track))
        return Response(
            content,
            media_type=MEDIA_TYPES[fmt],
            headers={"Content-Disposition": f'attachment; filename="{survey_id}_report.{fmt}"'},
        )

    @r.get("/jobs/{job_id}")
    def job(job_id: str) -> dict[str, Any]:
        if job_id != state.job_id:
            raise NotFoundError(f"Job {job_id} not found", job_id=job_id)
        total = (
            state.report["detections"][-1]["sonar_ref"]["ping_end"]
            if state.report["detections"]
            else 0
        )
        return {
            "job_id": job_id,
            "survey_id": state.survey_id,
            "status": state.job_status,
            "stage": "report",
            "percent": 100.0,
            "eta_s": 0,
            "pings_done": total,
            "pings_total": total,
            "stage_timings_ms": {},
            "warnings": [
                {k: e.get(k) for k in ("code", "ping_start", "ping_end")} for e in state.quality
            ],
        }

    @r.post("/jobs/{job_id}/cancel")
    def cancel(job_id: str) -> dict[str, Any]:
        if job_id != state.job_id:
            raise NotFoundError(f"Job {job_id} not found", job_id=job_id)
        raise JobNotCancellableError("Job already finished", job_id=job_id, status=state.job_status)

    @r.get("/detections/{detection_id}")
    def detection(detection_id: str) -> dict[str, Any]:
        return detection_or_404(detection_id)

    @r.get("/detections/{detection_id}/chip.png")
    def chip(detection_id: str, overlay: str = "mask") -> Response:
        if overlay not in OVERLAYS:
            raise ValidationError(
                f"Unknown overlay: {overlay}", field="overlay", supported=list(OVERLAYS)
            )
        detection_or_404(detection_id)
        grey = 96 + 24 * OVERLAYS.index(overlay)
        return Response(placeholder_png(grey=grey), media_type="image/png")

    @r.patch("/detections/{detection_id}")
    async def review(detection_id: str, request: Request) -> dict[str, Any]:
        det = detection_or_404(detection_id)
        try:
            body = await request.json()
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            raise ValidationError("Send the review as a JSON object", field="body") from exc
        decision = parse_review(body, det["class"])
        updated = apply_review(det, decision, now_utc())
        state.detections[detection_id] = updated
        return updated

    app.include_router(r)

    @app.websocket("/ws/jobs/{job_id}")
    async def job_events(websocket: WebSocket, job_id: str) -> None:
        await websocket.accept()
        if job_id != state.job_id:
            await websocket.send_json(
                {
                    "type": "error",
                    "job_id": job_id,
                    "ts": now_utc(),
                    "code": "NOT_FOUND",
                    "message": f"Job {job_id} not found",
                }
            )
            await websocket.close(code=CLOSE_NOT_FOUND)
            return
        try:
            opening = await first_message(websocket)
            if opening is not None and opening.get("type") == "ping":
                await websocket.send_json(pong(job_id))
            after = resume_after(opening)
            for event in state.stream():
                if event["seq"] <= after:
                    continue
                await websocket.send_json(event)
                if event["type"] in TERMINAL_EVENTS:
                    break
                await asyncio.sleep(event_delay_s)
            await websocket.close(code=CLOSE_NORMAL)
        except WebSocketDisconnect:
            return

    return app


app = create_mock_app()
