"""Mock API server for frontend development (ST-087).

Serves one canned survey (``fixtures/mock_report.json``) and its recorded job events
(``fixtures/mock_events.json``) through the real endpoint shapes of
``docs/architecture/05-api-specification.md``: surveys, filtered detections, track, report
downloads, jobs, review ``PATCH`` and the ``/ws/jobs/{job_id}`` event stream with ``seq`` and
``resume``. State (reviews, cancellation) is in memory and resets on restart. Fixtures are
regenerated with ``scripts/make_mock_fixtures.py``.

    sonarsentinel serve --mock --port 8001
"""

from __future__ import annotations

import asyncio
import copy
import csv
import io
import json
from importlib import resources
from typing import Any

from fastapi import APIRouter, FastAPI, Query, Request, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response

from sonarsentinel import __version__
from sonarsentinel.errors import (
    JobNotCancellableError,
    NotFoundError,
    SonarSentinelError,
    ValidationError,
)
from sonarsentinel.report.export import to_csv

API = "/api/v1"
TIER_ORDER = {"hazard": 0, "review": 1, "anomaly": 2, "hidden": 3}
REJECT_REASONS = {"rock", "shadow", "ripples", "noise", "other"}


def _fixture(name: str) -> Any:
    text = resources.files("sonarsentinel.api").joinpath("fixtures", name).read_text("utf-8")
    return json.loads(text)


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

    def survey_summary(self) -> dict[str, Any]:
        survey = self.report["survey"]
        return {
            "survey_id": self.survey_id,
            "name": survey["name"],
            "created_utc": self.report["generated_utc"],
            "source_files": survey["source_files"],
            "job": {
                "job_id": self.job_id,
                "status": self.job_status,
                "duration_s": self.report["processing"]["duration_s"],
            },
            "bbox": survey["bbox"],
            "track_length_km": survey["track_length_km"],
            "summary": self.report["summary"],
        }


def _csv_param(value: str | None) -> set[str] | None:
    return {v.strip() for v in value.split(",") if v.strip()} if value else None


def filter_detections(
    items: list[dict[str, Any]],
    *,
    cls: str | None = None,
    min_conf: float | None = None,
    max_conf: float | None = None,
    tier: str | None = None,
    review_status: str | None = None,
    flags: str | None = None,
    bbox: str | None = None,
    sort: str | None = None,
) -> list[dict[str, Any]]:
    """The query semantics of ``GET /surveys/{id}/detections`` (API spec §2.4)."""
    classes, tiers, statuses, wanted_flags = map(_csv_param, (cls, tier, review_status, flags))
    box = None
    if bbox:
        try:
            box = [float(v) for v in bbox.split(",")]
            assert len(box) == 4
        except (ValueError, AssertionError) as exc:
            raise ValidationError("bbox must be minLon,minLat,maxLon,maxLat", bbox=bbox) from exc
    out = []
    for d in items:
        pos = d["position"]
        if classes and d["class"] not in classes:
            continue
        if min_conf is not None and d["confidence"] < min_conf:
            continue
        if max_conf is not None and d["confidence"] > max_conf:
            continue
        if tiers and d["alert_tier"] not in tiers:
            continue
        if statuses and d["review"]["status"] not in statuses:
            continue
        if wanted_flags and not wanted_flags & set(d["quality_flags"]):
            continue
        if box and (
            pos["lat"] is None
            or not (box[0] <= pos["lon"] <= box[2] and box[1] <= pos["lat"] <= box[3])
        ):
            continue
        out.append(d)
    keys = {
        "confidence": lambda d: d["confidence"],
        "-confidence": lambda d: -d["confidence"],
        "area": lambda d: d["dimensions"]["area_m2"] or 0.0,
        "ping": lambda d: d["sonar_ref"].get("ping_start") or 0,
    }
    if sort:
        if sort not in keys:
            raise ValidationError(f"Unknown sort: {sort}", supported=sorted(keys))
        out.sort(key=keys[sort])
    return out


def create_mock_app(event_delay_s: float = 0.05) -> FastAPI:
    state = MockState()
    app = FastAPI(title="SonarSentinel mock API", version=__version__, docs_url="/docs")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.exception_handler(SonarSentinelError)
    async def error(_: Request, exc: SonarSentinelError) -> JSONResponse:
        return JSONResponse(status_code=exc.http_status, content=exc.to_dict())

    def survey_or_404(survey_id: str) -> None:
        if survey_id != state.survey_id:
            raise NotFoundError(f"Survey {survey_id} not found", survey_id=survey_id)

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
    def surveys() -> dict[str, Any]:
        return {"total": 1, "items": [state.survey_summary()]}

    @r.get("/surveys/{survey_id}")
    def survey(survey_id: str) -> dict[str, Any]:
        survey_or_404(survey_id)
        base = f"{API}/surveys/{survey_id}/report?format="
        return state.survey_summary() | {"report_urls": {f: base + f for f in ("json", "csv")}}

    @r.get("/surveys/{survey_id}/track")
    def track(survey_id: str) -> dict[str, Any]:
        survey_or_404(survey_id)
        points = [p for e in state.events if e["type"] == "track" for p in e["points"]]
        return {
            "type": "FeatureCollection",
            "features": [
                {
                    "type": "Feature",
                    "properties": {"feature_kind": "track"},
                    "geometry": {
                        "type": "LineString",
                        "coordinates": [[lon, lat] for lat, lon in points],
                    },
                }
            ],
        }

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
        sort: str | None = None,
        limit: int = Query(100, ge=1, le=1000),
        offset: int = Query(0, ge=0),
    ) -> dict[str, Any]:
        survey_or_404(survey_id)
        items = filter_detections(
            list(state.detections.values()),
            cls=cls,
            min_conf=min_conf,
            max_conf=max_conf,
            tier=tier,
            review_status=review_status,
            flags=flags,
            bbox=bbox,
            sort=sort,
        )
        return {"total": len(items), "items": items[offset : offset + limit]}

    @r.get("/surveys/{survey_id}/report")
    def report(survey_id: str, format: str = "json") -> Response:  # noqa: A002
        survey_or_404(survey_id)
        current = copy.deepcopy(state.report) | {"detections": list(state.detections.values())}
        filename = f"{survey_id}_report.{format}"
        headers = {"Content-Disposition": f'attachment; filename="{filename}"'}
        if format == "json":
            return Response(
                json.dumps(current, indent=2), media_type="application/json", headers=headers
            )
        if format == "csv":
            return Response(to_csv(current), media_type="text/csv", headers=headers)
        raise ValidationError(
            f"Report format {format} is not available in the mock", supported=["json", "csv"]
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
            "status": state.job_status,
            "stage": "report",
            "percent": 100.0,
            "eta_s": 0,
            "pings_done": total,
            "pings_total": total,
            "stage_timings_ms": {},
            "warnings": [e for e in state.events if e["type"] == "warning"],
        }

    @r.post("/jobs/{job_id}/cancel")
    def cancel(job_id: str) -> dict[str, Any]:
        if job_id != state.job_id:
            raise NotFoundError(f"Job {job_id} not found", job_id=job_id)
        raise JobNotCancellableError("Job already finished", job_id=job_id, status=state.job_status)

    @r.get("/detections/{detection_id}")
    def detection(detection_id: str) -> dict[str, Any]:
        if detection_id not in state.detections:
            raise NotFoundError(f"Detection {detection_id} not found", detection_id=detection_id)
        return state.detections[detection_id]

    @r.patch("/detections/{detection_id}")
    async def review(detection_id: str, request: Request) -> dict[str, Any]:
        if detection_id not in state.detections:
            raise NotFoundError(f"Detection {detection_id} not found", detection_id=detection_id)
        body = await request.json()
        status = body.get("review_status")
        if status not in {"pending", "confirmed", "rejected", "reclassified"}:
            raise ValidationError(
                "review_status must be pending, confirmed, rejected or reclassified"
            )
        if status == "rejected" and body.get("reject_reason") not in REJECT_REASONS:
            raise ValidationError(
                "reject_reason is required for a rejection", allowed=sorted(REJECT_REASONS)
            )
        det = state.detections[detection_id]
        if status == "reclassified":
            if "class" not in body:
                raise ValidationError("class is required when reclassifying")
            det["class"] = body["class"]
        det["review"] = {
            "status": status,
            "reviewer": body.get("reviewer"),
            "reject_reason": body.get("reject_reason") if status == "rejected" else None,
            "note": body.get("note"),
            "updated_utc": "2026-09-13T12:00:00Z",
        }
        return det

    app.include_router(r)

    @app.websocket("/ws/jobs/{job_id}")
    async def job_events(websocket: WebSocket, job_id: str) -> None:
        await websocket.accept()
        if job_id != state.job_id:
            await websocket.send_json(
                {
                    "type": "error",
                    "job_id": job_id,
                    "seq": 1,
                    "code": "NOT_FOUND",
                    "message": "Job not found",
                }
            )
            await websocket.close()
            return
        after = 0
        try:
            first = await asyncio.wait_for(websocket.receive_json(), timeout=0.2)
            if first.get("type") == "resume":
                after = int(first.get("after_seq", 0))
        except TimeoutError:
            pass
        except WebSocketDisconnect:
            return
        for event in state.events:
            if event["seq"] <= after:
                continue
            await websocket.send_json(event | {"job_id": job_id})
            await asyncio.sleep(event_delay_s)
        await websocket.close()

    return app


app = create_mock_app()


def events_to_csv_rows(events: list[dict[str, Any]]) -> str:
    """Debug helper: one CSV row per event (type, seq)."""
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(["seq", "type"])
    for e in events:
        writer.writerow([e["seq"], e["type"]])
    return buffer.getvalue()
