"""Job manager and worker (ST-082, ST-083): run uploaded surveys, store results, publish events.

Lifecycle (``docs/architecture/01-system-architecture.md``): ``queued → running → completed |
completed_with_warnings | failed``, and ``queued | running → cancelled``. One background thread
runs one job at a time; this is the prototype worker, and ADR-001's worker processes remain the
path for heavier deployments. Cancellation is cooperative: the pipeline polls ``should_cancel`` at
every ``progress`` event, which waterfall inputs emit after each chunk, so a running job stops
within one chunk.

Events (ADR-018 §1–2): every pipeline event gets the ``job_id``, goes to
``results/<survey_id>/job.log.jsonl``, to an in-memory buffer (last 1,000 per job) and to the
registered listeners (the WebSocket endpoint). The terminal event comes from the manager *after*
the results are saved: ``done`` with ``report_urls`` for finished and cancelled jobs, ``error`` for
failed ones, continuing the pipeline's ``seq``.
"""

from __future__ import annotations

import copy
import json
import logging
import queue
import shutil
import threading
import time
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from sonarsentinel.errors import JobNotCancellableError, NotFoundError, SonarSentinelError
from sonarsentinel.report.builder import now_utc
from sonarsentinel.storage import repository as repo
from sonarsentinel.storage.db import Database
from sonarsentinel.storage.models import Job, Survey

logger = logging.getLogger(__name__)

EVENT_BUFFER = 1000
PROGRESS_WRITE_INTERVAL_S = 1.0
REPORT_FORMATS = ("json", "csv", "geojson", "kml")
API_PREFIX = "/api/v1"

Event = dict[str, Any]
EventListener = Callable[[Event], None]
Runner = Callable[..., dict[str, Any]]


def report_url(survey_id: str, fmt: str) -> str:
    return f"{API_PREFIX}/surveys/{survey_id}/report?format={fmt}"


@dataclass
class JobRequest:
    """Everything the worker needs to process one uploaded survey."""

    job_id: str
    survey_id: str
    sources: list[Path]
    options: dict[str, Any] = field(default_factory=dict)
    nav_csv: Path | None = None


@dataclass
class _JobState:
    log_path: Path
    stage: str | None = None
    stage_started: float = field(default_factory=time.monotonic)
    timings_ms: dict[str, int] = field(default_factory=dict)
    warnings: list[dict[str, Any]] = field(default_factory=list)
    quality_events: list[dict[str, Any]] = field(default_factory=list)
    track: list[dict[str, Any]] = field(default_factory=list)
    detections: dict[str, dict[str, Any]] = field(default_factory=dict)
    last_write: float = 0.0
    last_seq: int = 0

    def enter_stage(self, stage: str | None) -> None:
        """Add the time spent in the current stage and switch to ``stage``."""
        now = time.monotonic()
        if self.stage is not None:
            spent = int((now - self.stage_started) * 1000)
            self.timings_ms[self.stage] = self.timings_ms.get(self.stage, 0) + spent
        self.stage = stage
        self.stage_started = now


def error_body(code: str, message: str, **details: Any) -> dict[str, Any]:
    """The API error shape for failures that are not :class:`SonarSentinelError`."""
    return {"error": {"code": code, "message": message, "details": details}}


class JobManager:
    """Queue, run, cancel and persist processing jobs; publish their events."""

    def __init__(
        self,
        database: Database,
        config: dict[str, Any],
        data_dir: str | Path,
        *,
        runner: Runner | None = None,
    ) -> None:
        self.database = database
        self.config = config
        self.data_dir = Path(data_dir)
        self._runner = runner
        self._queue: queue.Queue[JobRequest | None] = queue.Queue()
        self._cancel: dict[str, threading.Event] = {}
        self._lock = threading.Lock()
        self._events_lock = threading.Lock()
        self._thread: threading.Thread | None = None
        self._listeners: list[EventListener] = []
        self._survey_of: dict[str, str] = {}
        self.events: dict[str, deque[Event]] = {}

    @property
    def results_dir(self) -> Path:
        return self.data_dir / "results"

    def add_listener(self, listener: EventListener) -> None:
        """Call ``listener(event)`` for every job event (on the worker thread, after logging)."""
        with self._events_lock:
            self._listeners.append(listener)

    def remove_listener(self, listener: EventListener) -> None:
        with self._events_lock:
            if listener in self._listeners:
                self._listeners.remove(listener)

    def start(self) -> None:
        with self._lock:
            if self._thread is not None and self._thread.is_alive():
                return
            self._thread = threading.Thread(
                target=self._loop, name="sonarsentinel-jobs", daemon=True
            )
            self._thread.start()

    def stop(self, timeout: float = 30.0) -> None:
        """Cancel running work at its next chunk and stop the worker thread."""
        thread = self._thread
        if thread is None:
            return
        for flag in list(self._cancel.values()):
            flag.set()
        self._queue.put(None)
        thread.join(timeout)
        self._thread = None

    def recover(self) -> int:
        """Mark jobs left ``queued``/``running`` by a previous server process as failed."""
        with self.database.session() as session, session.begin():
            stale = session.scalars(select(Job).where(Job.status.in_(("queued", "running")))).all()
            for job in stale:
                error = error_body(
                    "INTERNAL_ERROR",
                    "The server stopped before this job finished; upload the survey again",
                    job_id=job.job_id,
                )
                self._mark_finished(session, job, "failed", error)
            return len(stale)

    def submit(self, request: JobRequest) -> None:
        self._cancel.setdefault(request.job_id, threading.Event())
        with self._events_lock:
            self.events.setdefault(request.job_id, deque(maxlen=EVENT_BUFFER))
            self._survey_of[request.job_id] = request.survey_id
        self._queue.put(request)

    def cancel(self, job_id: str) -> str:
        """``"cancelled"`` for a queued job, ``"cancelling"`` for a running one.

        Raises:
            NotFoundError: Unknown job.
            JobNotCancellableError: The job has already finished.
        """
        with self._lock, self.database.session() as session, session.begin():
            job = session.get(Job, job_id)
            if job is None:
                raise NotFoundError(f"Job {job_id} not found", job_id=job_id)
            if job.status in repo.FINISHED_STATUSES:
                raise JobNotCancellableError(
                    f"Job {job_id} has already finished ({job.status})",
                    job_id=job_id,
                    status=job.status,
                )
            self._cancel.setdefault(job_id, threading.Event()).set()
            if job.status == "queued":
                self._mark_finished(session, job, "cancelled")
                return "cancelled"
            return "cancelling"

    def wait(self, job_id: str, timeout: float = 60.0, poll_s: float = 0.05) -> dict[str, Any]:
        """Block until the job has finished (or ``timeout``); returns the job payload."""
        deadline = time.monotonic() + timeout
        while True:
            with self.database.session() as session:
                job = session.get(Job, job_id)
                if job is None:
                    raise NotFoundError(f"Job {job_id} not found", job_id=job_id)
                if job.status in repo.FINISHED_STATUSES or time.monotonic() >= deadline:
                    return repo.job_payload(job)
            time.sleep(poll_s)

    def replay(self, job_id: str, after_seq: int = 0) -> list[Event]:
        """Events with ``seq > after_seq``: from the buffer, or the job log when it is older."""
        with self._events_lock:
            buffered = list(self.events.get(job_id, ()))
            survey_id = self._survey_of.get(job_id)
        if buffered and int(buffered[0]["seq"]) <= after_seq + 1:
            return [e for e in buffered if int(e["seq"]) > after_seq]
        if survey_id is None:
            with self.database.session() as session:
                job = session.get(Job, job_id)
                survey_id = job.survey_id if job is not None else None
        log = self.results_dir / survey_id / "job.log.jsonl" if survey_id else None
        if log is None or not log.is_file():
            return [e for e in buffered if int(e["seq"]) > after_seq]
        events: list[Event] = []
        for line in log.read_text(encoding="utf-8").splitlines():
            try:
                event = json.loads(line)
            except json.JSONDecodeError:  # a line being written right now
                continue
            if int(event.get("seq", 0)) > after_seq:
                events.append(event)
        return events

    # -- worker ---------------------------------------------------------------------------------

    def _loop(self) -> None:
        while True:
            request = self._queue.get()
            if request is None:
                return
            try:
                self._run(request)
            except Exception:  # one broken job must not stop the worker
                logger.exception("Job %s crashed the worker loop", request.job_id)

    def _run(self, request: JobRequest) -> None:
        from sonarsentinel.pipeline import PipelineCancelled, run_survey
        from sonarsentinel.report.export import report_is_geotagged, track_coords, write_reports

        flag = self._cancel.setdefault(request.job_id, threading.Event())
        with self._lock, self.database.session() as session, session.begin():
            job = session.get(Job, request.job_id)
            if job is None or job.status != "queued" or flag.is_set():
                return
            job.status = "running"
            job.started_utc = now_utc()
            survey = session.get(Survey, request.survey_id)
            if survey is not None:
                survey.status = "running"

        log_path = self.results_dir / request.survey_id / "job.log.jsonl"
        log_path.parent.mkdir(parents=True, exist_ok=True)
        state = _JobState(log_path=log_path)
        work_dir = self.data_dir / "work" / request.survey_id
        runner = self._runner or run_survey
        try:
            config, kwargs = self._prepare(request)
            report = runner(
                request.sources,
                config=config,
                survey_id=request.survey_id,
                on_event=lambda event: self._on_event(request, state, event),
                should_cancel=flag.is_set,
                work_dir=work_dir,
                results_dir=self.results_dir,  # chips under results/<survey_id>/chips (ST-073)
                **kwargs,
            )
            formats = [
                f for f in REPORT_FORMATS if f in ("json", "csv") or report_is_geotagged(report)
            ]
            paths = write_reports(
                report, self.results_dir, formats, track=track_coords(state.track)
            )
            warned = bool(report["processing"]["quality"]["warnings"])
            status = "completed_with_warnings" if warned else "completed"
            self._finish(
                request,
                state,
                status,
                report=report,
                paths={fmt: str(path) for fmt, path in paths.items()},
            )
        except PipelineCancelled:
            self._finish(request, state, "cancelled")
        except SonarSentinelError as exc:
            self._finish(request, state, "failed", error=exc.to_dict())
        except Exception as exc:
            logger.exception("Job %s failed", request.job_id)
            error = error_body(
                "INTERNAL_ERROR",
                f"Unexpected failure ({type(exc).__name__}); see the job log",
                job_id=request.job_id,
            )
            self._finish(request, state, "failed", error=error)
        finally:
            self._cancel.pop(request.job_id, None)
            shutil.rmtree(work_dir, ignore_errors=True)

    def _prepare(self, request: JobRequest) -> tuple[dict[str, Any], dict[str, Any]]:
        """Job configuration and pipeline arguments from the upload options."""
        from sonarsentinel.cli import build_anomaly, build_detector

        options = request.options
        config = copy.deepcopy(self.config)
        if options.get("ground_resolution_m") is not None:
            preprocess = config.setdefault("preprocess", {})
            preprocess["ground_resolution_m"] = float(options["ground_resolution_m"])
        if options.get("image_layout"):
            config.setdefault("ingest", {})["image_layout"] = options["image_layout"]
        if options.get("apply_layback") is not None:
            config.setdefault("navigation", {})["apply_layback"] = options["apply_layback"]
        if options.get("manual_layback_m") is not None:
            navigation = config.setdefault("navigation", {})
            navigation["manual_layback_m"] = float(options["manual_layback_m"])
        epsg = options.get("utm_epsg", "auto")
        kwargs: dict[str, Any] = {
            "nav_csv": request.nav_csv,
            "epsg": None if epsg in (None, "auto") else epsg,
            "allow_no_gps": bool(options.get("allow_no_gps", False)),
            "detector": build_detector(str(options.get("detector_model") or "auto"), None, config),
            "anomaly_model": build_anomaly(config, not options.get("anomaly_scan", True)),
            "survey_name": options.get("name"),
            "min_conf": options.get("min_conf"),
        }
        return config, kwargs

    def _publish(self, request: JobRequest, state: _JobState, event: Event) -> None:
        """Log, buffer and hand an event to the listeners (in that order)."""
        with self._events_lock:
            with state.log_path.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(event, ensure_ascii=False, default=str) + "\n")
            self.events.setdefault(request.job_id, deque(maxlen=EVENT_BUFFER)).append(event)
            self._survey_of[request.job_id] = request.survey_id
            listeners = list(self._listeners)
        for listener in listeners:
            try:
                listener(event)
            except Exception:
                logger.exception("Job event listener failed")

    def _emit(self, request: JobRequest, state: _JobState, kind: str, **payload: Any) -> None:
        """A manager event that continues the pipeline's ``seq``."""
        state.last_seq += 1
        event = {
            "type": kind,
            "job_id": request.job_id,
            "seq": state.last_seq,
            "ts": now_utc(),
            **payload,
        }
        self._publish(request, state, event)

    def _on_event(self, request: JobRequest, state: _JobState, event: Event) -> None:
        kind = event.get("type")
        if kind == "done":
            return  # the manager emits ``done`` once the results are saved (ADR-018 §2)
        event = {**event, "job_id": request.job_id}
        state.last_seq = max(state.last_seq, int(event.get("seq", 0)))
        if kind == "detection" or kind == "detection_update":
            detection = event.get("detection") or {}
            if detection.get("detection_id"):
                state.detections[detection["detection_id"]] = detection
        elif kind == "detection_removed":
            state.detections.pop(str(event.get("detection_id")), None)
        elif kind == "warning":
            state.warnings.append({k: event.get(k) for k in ("code", "ping_start", "ping_end")})
            state.quality_events.append(
                {k: event.get(k) for k in ("code", "ping_start", "ping_end", "message")}
            )
        elif kind == "track":
            state.track.append({k: event.get(k) for k in ("points", "ping_start", "ping_end")})
        elif kind == "progress":
            stage = event.get("stage")
            changed = stage != state.stage
            if changed:
                state.enter_stage(stage)
            now = time.monotonic()
            if changed or now - state.last_write >= PROGRESS_WRITE_INTERVAL_S:
                self._write_progress(request.job_id, event, state)
                state.last_write = now
        self._publish(request, state, event)

    def _write_progress(self, job_id: str, event: Event, state: _JobState) -> None:
        with self.database.session() as session, session.begin():
            job = session.get(Job, job_id)
            if job is None:
                return
            job.stage = event.get("stage") or job.stage
            if event.get("percent") is not None:
                job.percent = float(event["percent"])
            if event.get("pings_done") is not None:
                job.pings_done = int(event["pings_done"])
            if event.get("pings_total") is not None:
                job.pings_total = int(event["pings_total"])
            job.stage_timings_json = json.dumps(state.timings_ms)
            job.warnings_json = json.dumps(state.warnings, default=str)

    def _finish(
        self,
        request: JobRequest,
        state: _JobState,
        status: str,
        *,
        report: dict[str, Any] | None = None,
        paths: dict[str, str] | None = None,
        error: dict[str, Any] | None = None,
    ) -> None:
        from sonarsentinel.api.filters import summarize

        state.enter_stage(None)
        partial = list(state.detections.values())
        with self.database.session() as session, session.begin():
            job = session.get(Job, request.job_id)
            if job is not None:
                job.stage_timings_json = json.dumps(state.timings_ms)
                job.warnings_json = json.dumps(state.warnings, default=str)
                if report is not None and paths is not None:
                    job.percent = 100.0
                    repo.save_results(
                        session,
                        request.survey_id,
                        report,
                        paths,
                        status=status,
                        quality_events=state.quality_events,
                        track_segments=state.track,
                    )
                elif status == "cancelled":
                    # Detections found so far are kept (S-02 Stop dialog); no report files.
                    repo.save_detections(session, request.survey_id, partial)
                    repo.save_track(session, request.survey_id, state.quality_events, state.track)
                self._mark_finished(session, job, status, error)

        if error is not None:
            detail = error.get("error", {})
            self._emit(
                request, state, "error", code=detail.get("code"), message=detail.get("message")
            )
        elif report is not None and paths is not None:
            bounds_path = self.results_dir / request.survey_id / "mosaic_bounds.json"
            mosaic = (
                {
                    "url": f"{API_PREFIX}/surveys/{request.survey_id}/mosaic.png",
                    "bounds": json.loads(bounds_path.read_text(encoding="utf-8"))["bounds"],
                }
                if bounds_path.is_file()
                else None
            )
            self._emit(
                request,
                state,
                "done",
                status=status,
                summary=report["summary"],
                report_urls={fmt: report_url(request.survey_id, fmt) for fmt in paths},
                mosaic=mosaic,
            )
        else:
            self._emit(
                request,
                state,
                "done",
                status=status,
                summary=summarize(partial),
                report_urls={},
                mosaic=None,
            )

    @staticmethod
    def _mark_finished(
        session: Session, job: Job, status: str, error: dict[str, Any] | None = None
    ) -> None:
        job.status = status
        job.finished_utc = now_utc()
        if error is not None:
            job.error_json = json.dumps(error, default=str)
        survey = session.get(Survey, job.survey_id)
        if survey is not None:
            survey.status = status
