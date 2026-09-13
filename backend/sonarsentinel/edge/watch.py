"""Edge ``watch`` mode (ST-103, ``docs/architecture/07-deployment.md`` §4).

The folder is polled every ``interval`` seconds. A sonar file counts as closed once its
modification time is at least ``stable_seconds`` old; it is then processed once with
:func:`sonarsentinel.pipeline.run_pipeline`, and its reports (and chips) are written under
``out``. Progress survives restarts in ``out/.watch_state.json``, keyed by path with size and
mtime, so a restart does not reprocess finished files; a file that changes afterwards is processed
again. A file that fails is recorded with its error and skipped until it changes.

Inputs: ``.xtf``, ``.tif``/``.tiff`` and ``.png``/``.jpg`` images that have a ``<stem>_nav.csv``
next to them. Detections at or above ``alerts_min_conf`` produce one compact alert line each,
``SS1|survey|Dxxxx|class|conf|lat|lon|LxW|depth|UTC`` (≤ 256 bytes), printed and appended to
``out/alerts.log``.

Not implemented: tailing a file that is still being written chunk by chunk (named in 07 §4);
files are processed after they are closed.
"""

from __future__ import annotations

import json
import os
import time
from collections.abc import Callable, Sequence
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from sonarsentinel.errors import SonarSentinelError

WATCH_STATE = ".watch_state.json"
ALERTS_LOG = "alerts.log"
ALERT_MAX_BYTES = 256
SONAR_EXTENSIONS = (".xtf", ".tif", ".tiff")
IMAGE_EXTENSIONS = (".png", ".jpg", ".jpeg")

Processor = Callable[[Path, Path | None], dict[str, Any]]
Echo = Callable[[str], None]


@dataclass
class FileRecord:
    """What the watcher knows about one input file."""

    size: int
    mtime: float
    status: str = "pending"  # pending | done | failed
    survey_id: str | None = None
    error: str | None = None
    reports: list[str] = field(default_factory=list)
    alerts: int = 0
    processed_utc: str | None = None


@dataclass
class WatchState:
    files: dict[str, FileRecord] = field(default_factory=dict)

    @classmethod
    def load(cls, out: Path) -> WatchState:
        path = out / WATCH_STATE
        if not path.is_file():
            return cls()
        data = json.loads(path.read_text(encoding="utf-8"))
        return cls({key: FileRecord(**value) for key, value in data.get("files", {}).items()})

    def save(self, out: Path) -> None:
        out.mkdir(parents=True, exist_ok=True)
        path = out / WATCH_STATE
        tmp = path.with_suffix(".tmp")
        payload = {"files": {key: asdict(value) for key, value in sorted(self.files.items())}}
        tmp.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        tmp.replace(path)


def find_inputs(folder: Path) -> list[tuple[Path, Path | None]]:
    """Supported files in ``folder`` (not recursive) with their navigation CSV, if any."""
    found: list[tuple[Path, Path | None]] = []
    for path in sorted(folder.iterdir()):
        if not path.is_file() or path.name.startswith("."):
            continue
        suffix = path.suffix.lower()
        if suffix in SONAR_EXTENSIONS:
            found.append((path, None))
        elif suffix in IMAGE_EXTENSIONS:
            nav = path.with_name(f"{path.stem}_nav.csv")
            if nav.is_file():
                found.append((path, nav))
    return found


def _field(value: Any, fmt: str) -> str:
    return "" if value is None else format(value, fmt)


def alert_line(detection: dict[str, Any], survey_id: str) -> str:
    """Compact alert (FR-OPS-06 format), truncated to :data:`ALERT_MAX_BYTES` bytes."""
    position = detection.get("position") or {}
    dims = detection.get("dimensions") or {}
    ref = detection.get("sonar_ref") or {}
    short_id = str(detection.get("detection_id", "")).rsplit("-", 1)[-1]
    size = ""
    if dims.get("length_m") is not None and dims.get("width_m") is not None:
        size = f"{dims['length_m']:.1f}x{dims['width_m']:.1f}"
    line = "|".join(
        [
            "SS1",
            survey_id,
            short_id,
            str(detection.get("class", "")),
            _field(detection.get("confidence"), ".0f"),
            _field(position.get("lat"), ".6f"),
            _field(position.get("lon"), ".6f"),
            size,
            _field(position.get("depth_m"), ".1f"),
            str(ref.get("time_utc") or ""),
        ]
    )
    encoded = line.encode("utf-8")
    if len(encoded) <= ALERT_MAX_BYTES:
        return line
    return encoded[:ALERT_MAX_BYTES].decode("utf-8", errors="ignore")


def alert_lines(report: dict[str, Any], min_conf: float) -> list[str]:
    survey_id = report["survey"]["survey_id"]
    return [
        alert_line(det, survey_id)
        for det in report["detections"]
        if float(det.get("confidence") or 0.0) >= min_conf
    ]


def _now_utc() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def scan_once(
    folder: Path,
    out: Path,
    state: WatchState,
    *,
    process: Processor,
    formats: Sequence[str] = ("json", "csv"),
    stable_seconds: float = 10.0,
    alerts_min_conf: float | None = 80.0,
    now: float | None = None,
    echo: Echo = print,
) -> list[Path]:
    """Process every new or changed file that is stable; returns the files attempted."""
    from sonarsentinel.report.export import write_reports

    current = time.time() if now is None else now
    attempted: list[Path] = []
    for path, nav in find_inputs(folder):
        stat = path.stat()
        key = str(path.resolve())
        record = state.files.get(key)
        unchanged = (
            record is not None and record.size == stat.st_size and record.mtime == stat.st_mtime
        )
        if unchanged and record is not None and record.status in ("done", "failed"):
            continue
        if current - stat.st_mtime < stable_seconds:
            state.files[key] = FileRecord(size=stat.st_size, mtime=stat.st_mtime)
            continue  # still being written (or just copied): wait until it is stable

        attempted.append(path)
        record = FileRecord(size=stat.st_size, mtime=stat.st_mtime)
        state.files[key] = record
        try:
            report = process(path, nav)
            paths = write_reports(report, out, list(formats))
        except SonarSentinelError as exc:
            record.status, record.error = "failed", f"{exc.code}: {exc.message}"
        except Exception as exc:  # the watcher keeps running whatever one file does
            record.status, record.error = "failed", f"INTERNAL_ERROR: {exc!r}"
        else:
            record.status = "done"
            record.survey_id = report["survey"]["survey_id"]
            record.reports = [str(p) for p in paths.values()]
            lines = alert_lines(report, alerts_min_conf) if alerts_min_conf is not None else []
            record.alerts = len(lines)
            if lines:
                with (out / ALERTS_LOG).open("a", encoding="utf-8") as log:
                    log.write("\n".join(lines) + "\n")
            for line in lines:
                echo(line)
        record.processed_utc = _now_utc()
        state.save(out)
        if record.status == "done":
            summary = report["summary"]
            echo(
                f"[ok] {path.name}: {record.survey_id} {summary['total_detections']} detections, "
                f"{record.alerts} alerts"
            )
        else:
            echo(f"[X] {path.name}: {record.error}")
    state.save(out)
    return attempted


def make_processor(
    config: dict[str, Any], detector: Any, anomaly_model: Any | None, results_dir: Path
) -> Processor:
    """A :data:`Processor` that runs the full pipeline with one detector for every file."""
    from sonarsentinel.pipeline import run_pipeline

    def process(path: Path, nav: Path | None) -> dict[str, Any]:
        return run_pipeline(
            path,
            config=config,
            nav_csv=nav,
            detector=detector,
            anomaly_model=anomaly_model,
            results_dir=results_dir,
        )

    return process


def watch(
    folder: Path,
    out: Path,
    *,
    process: Processor,
    interval: float = 5.0,
    once: bool = False,
    sleep: Callable[[float], None] = time.sleep,
    **scan_options: Any,
) -> WatchState:
    """Scan until interrupted (``once``: a single scan)."""
    out.mkdir(parents=True, exist_ok=True)
    state = WatchState.load(out)
    while True:
        scan_once(folder, out, state, process=process, **scan_options)
        if once:
            return state
        sleep(interval)


def touch_old(path: Path, age_seconds: float) -> None:
    """Set a file's modification time into the past (used by tests and the ``--once`` demo)."""
    stamp = time.time() - age_seconds
    os.utime(path, (stamp, stamp))
