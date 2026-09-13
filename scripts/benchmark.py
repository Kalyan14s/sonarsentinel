"""ST-112 performance benchmark (Test Plan §6.5; NFR-01, 02, 04, 05, 06, 07).

Runs ``run_pipeline`` on one sonar file ``--runs`` times, each run in its own subprocess so memory
is isolated, and reports:

* wall-clock median / min / max and seconds per km of track (NFR-01 GPU, NFR-02 CPU);
* time spent per stage, from the ``progress`` events;
* first ``detection`` event latency (NFR-04) and the largest gap between progress events (NFR-05);
* peak resident memory of the run, sampled every 100 ms (NFR-07);
* model file sizes (NFR-06) and the hardware/software environment.

    python scripts/benchmark.py --synthetic-km 1.0 --runs 3 --out benchmark.json
    python scripts/benchmark.py --input line.xtf --runs 1 --detector auto --out usgs.json

Results go to ``--out`` (JSON) and the same name with ``.md`` (table).
"""

from __future__ import annotations

import argparse
import importlib.metadata
import json
import os
import platform
import statistics
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
sys.path.insert(0, str(ROOT / "backend" / "tests"))
os.environ.setdefault("KMP_DUPLICATE_LIB_OK", "TRUE")

TARGETS = {
    "NFR-02 CPU s per km": 300.0,
    "NFR-04 first detection s": 15.0,
    "NFR-05 max progress gap s": 5.0,
    "NFR-06 detector FP32 MB": 25.0,
    "NFR-07 peak RSS MB": 8192.0,
}


# --- pure helpers (unit-tested) -------------------------------------------------------------


def summary_stats(values: list[float]) -> dict[str, float | None]:
    """Median, minimum and maximum rounded to milliseconds (``None`` for no values)."""
    if not values:
        return {"median": None, "min": None, "max": None}
    return {
        "median": round(statistics.median(values), 3),
        "min": round(min(values), 3),
        "max": round(max(values), 3),
    }


def event_metrics(events: list[dict[str, Any]]) -> dict[str, Any]:
    """First-detection latency, largest progress gap and seconds per stage.

    ``events`` carry ``type``, ``t`` (seconds since the run started) and, for progress events,
    ``stage``. A stage lasts from its first progress event until the next event of another stage
    (or the ``done`` event).
    """
    progress = [e for e in events if e.get("type") == "progress"]
    times = [float(e["t"]) for e in progress]
    gaps = [b - a for a, b in zip(times, times[1:], strict=False)]
    first_detection = next((float(e["t"]) for e in events if e.get("type") == "detection"), None)
    end = next((float(e["t"]) for e in events if e.get("type") == "done"), None)
    if end is None and events:
        end = float(events[-1]["t"])
    stages: dict[str, float] = {}
    for i, current in enumerate(progress):
        following = progress[i + 1] if i + 1 < len(progress) else None
        stop = float(following["t"]) if following is not None else (end or float(current["t"]))
        stage = str(current.get("stage"))
        stages[stage] = round(stages.get(stage, 0.0) + stop - float(current["t"]), 3)
    return {
        "first_detection_s": round(first_detection, 3) if first_detection is not None else None,
        "max_progress_gap_s": round(max(gaps), 3) if gaps else None,
        "stage_s": stages,
        "progress_events": len(progress),
    }


def seconds_per_km(seconds: float | None, track_km: float | None) -> float | None:
    if seconds is None or not track_km:
        return None
    return round(seconds / track_km, 1)


def file_size_mb(path: Path) -> float | None:
    if path.is_dir():
        total = sum(p.stat().st_size for p in path.rglob("*") if p.is_file())
        return round(total / 2**20, 2)
    return round(path.stat().st_size / 2**20, 2) if path.is_file() else None


def markdown_table(result: dict[str, Any]) -> str:
    rows = [
        ("Runs", result["runs"], ""),
        ("Wall time median / min / max (s)", _triple(result["wall_s"]), ""),
        ("Track length (km)", result.get("track_length_km"), ""),
        (
            "Seconds per km (median)",
            result.get("s_per_km"),
            f"≤ {TARGETS['NFR-02 CPU s per km']:g}",
        ),
        ("First detection (s, median)", result.get("first_detection_s"), "≤ 15"),
        ("Max progress gap (s, worst run)", result.get("max_progress_gap_s"), "≤ 5"),
        ("Peak RSS (MB, worst run)", result.get("peak_rss_mb"), "≤ 8192"),
        ("Detections (last run)", result.get("detections"), ""),
        ("Runtime / detector", f"{result.get('runtime')} / {result.get('detector')}", ""),
    ]
    for name, size in (result.get("model_sizes_mb") or {}).items():
        rows.append(
            (f"Model size: {name} (MB)", size, "FP32 ≤ 25" if name == "detector_pt" else "")
        )
    lines = ["| Metric | Value | Target |", "|---|---|---|"]
    lines += [f"| {name} | {value} | {target} |" for name, value, target in rows]
    stages = result.get("stage_s") or {}
    if stages:
        lines += ["", "| Stage | Seconds (median run) |", "|---|---|"]
        lines += [f"| {stage} | {seconds} |" for stage, seconds in stages.items()]
    return "\n".join(lines) + "\n"


def _triple(stats: dict[str, float | None]) -> str:
    return f"{stats['median']} / {stats['min']} / {stats['max']}"


# --- child process: one pipeline run ---------------------------------------------------------


def child(args: argparse.Namespace) -> None:
    from sonarsentinel.cli import build_anomaly, build_detector
    from sonarsentinel.config import load_config
    from sonarsentinel.pipeline import run_pipeline

    cfg = load_config()
    detector = build_detector(args.detector, None, cfg)
    anomaly = None if args.no_anomaly else build_anomaly(cfg, False)
    events: list[dict[str, Any]] = []
    started = time.perf_counter()

    def on_event(event: dict[str, Any]) -> None:
        events.append(
            {"type": event["type"], "t": time.perf_counter() - started, "stage": event.get("stage")}
        )

    report = run_pipeline(
        args.input,
        config=cfg,
        detector=detector,
        anomaly_model=anomaly,
        on_event=on_event,
        results_dir=args.results_dir,
    )
    payload = {
        "duration_s": round(time.perf_counter() - started, 3),
        "events": events,
        "track_length_km": report["survey"]["track_length_km"],
        "detections": report["summary"]["total_detections"],
        "runtime": report["processing"]["runtime"],
        "models": report["processing"]["models"],
        "warnings": report["processing"]["quality"]["warnings"],
    }
    Path(args.child_out).write_text(json.dumps(payload), encoding="utf-8")


# --- parent: runs, memory sampling, summary --------------------------------------------------


def run_once(args: argparse.Namespace, source: Path, work: Path, index: int) -> dict[str, Any]:
    import psutil

    child_out = work / f"run{index}.json"
    command = [
        sys.executable,
        str(Path(__file__).resolve()),
        "--child",
        "--input",
        str(source),
        "--detector",
        args.detector,
        "--child-out",
        str(child_out),
        "--results-dir",
        str(work / f"results{index}"),
    ]
    if args.no_anomaly:
        command.append("--no-anomaly")
    started = time.perf_counter()
    proc = subprocess.Popen(command, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True)
    peak = 0
    handle = psutil.Process(proc.pid)
    while proc.poll() is None:
        try:
            rss = handle.memory_info().rss + sum(
                c.memory_info().rss for c in handle.children(recursive=True)
            )
            peak = max(peak, rss)
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass
        time.sleep(0.1)
    wall = time.perf_counter() - started
    stderr = proc.stderr.read() if proc.stderr else ""
    if proc.returncode != 0 or not child_out.is_file():
        raise SystemExit(f"Run {index} failed ({proc.returncode}):\n{stderr[-2000:]}")
    payload: dict[str, Any] = json.loads(child_out.read_text(encoding="utf-8"))
    payload["wall_s"] = round(wall, 3)
    payload["peak_rss_mb"] = round(peak / 2**20, 1)
    payload |= event_metrics(payload["events"])
    return payload


def environment() -> dict[str, Any]:
    import psutil

    versions = {}
    for package in ("numpy", "torch", "onnxruntime", "ultralytics", "lightgbm", "opencv-python"):
        try:
            versions[package] = importlib.metadata.version(package)
        except importlib.metadata.PackageNotFoundError:
            versions[package] = None
    return {
        "platform": platform.platform(),
        "processor": platform.processor(),
        "physical_cores": psutil.cpu_count(logical=False),
        "logical_cores": psutil.cpu_count(logical=True),
        "ram_gb": round(psutil.virtual_memory().total / 2**30, 1),
        "python": platform.python_version(),
        "packages": versions,
    }


def model_sizes() -> dict[str, float | None]:
    from sonarsentinel.config import load_config
    from sonarsentinel.scoring.fusion import repo_path

    cfg = load_config()
    weights = repo_path(cfg["detection"]["model"])
    return {
        "detector_pt": file_size_mb(weights.with_suffix(".pt")),
        "detector_onnx": file_size_mb(weights.with_suffix(".onnx")),
        "anomaly_bank": file_size_mb(repo_path(cfg["anomaly"]["model"])),
        "fp_filter": file_size_mb(repo_path(cfg["scoring"]["fp_filter_model"])),
        "calibrator": file_size_mb(repo_path(cfg["scoring"]["calibrator"])),
    }


def synthetic_line(folder: Path, km: float) -> Path:
    from tools.make_synthetic_xtf import write_synthetic_xtf

    n_pings = round(km * 1000 / 0.10)
    targets = [
        (int(n_pings * f), "starboard" if i % 2 else "port", 300 + 100 * (i % 5))
        for i, f in enumerate([0.1, 0.25, 0.4, 0.55, 0.7, 0.85])
    ]
    path = folder / f"synthetic_{km:g}km.xtf"
    write_synthetic_xtf(
        path,
        n_pings=n_pings,
        samples_per_side=1000,
        slant_range_m=50.0,
        step_m=0.10,
        targets=targets,
        target_extent=(12, 30),
    )
    return path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--input", type=Path, default=None)
    parser.add_argument("--synthetic-km", type=float, default=None)
    parser.add_argument("--runs", type=int, default=3)
    parser.add_argument("--detector", default="auto", choices=["auto", "classical", "yolo"])
    parser.add_argument("--no-anomaly", action="store_true")
    parser.add_argument("--out", type=Path, default=Path("benchmark.json"))
    parser.add_argument("--child", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--child-out", default=None, help=argparse.SUPPRESS)
    parser.add_argument("--results-dir", default=None, help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.child:
        child(args)
        return
    if (args.input is None) == (args.synthetic_km is None):
        parser.error("give exactly one of --input or --synthetic-km")

    with tempfile.TemporaryDirectory(prefix="ss_bench_") as tmp:
        work = Path(tmp)
        source = args.input or synthetic_line(work, float(args.synthetic_km))
        runs = [run_once(args, source, work, i) for i in range(args.runs)]

    walls = [r["duration_s"] for r in runs]
    median_run = sorted(runs, key=lambda r: r["duration_s"])[len(runs) // 2]
    first = [r["first_detection_s"] for r in runs if r["first_detection_s"] is not None]
    gaps = [r["max_progress_gap_s"] for r in runs if r["max_progress_gap_s"] is not None]
    result: dict[str, Any] = {
        "input": str(args.input) if args.input else f"synthetic {args.synthetic_km:g} km",
        "runs": len(runs),
        "detector": median_run["models"].get("detector"),
        "runtime": median_run["runtime"],
        "anomaly": median_run["models"].get("anomaly"),
        "wall_s": summary_stats(walls),
        "process_wall_s": summary_stats([r["wall_s"] for r in runs]),
        "track_length_km": median_run["track_length_km"],
        "s_per_km": seconds_per_km(statistics.median(walls), median_run["track_length_km"]),
        "first_detection_s": summary_stats(first)["median"],
        "max_progress_gap_s": max(gaps) if gaps else None,
        "peak_rss_mb": max(r["peak_rss_mb"] for r in runs),
        "detections": median_run["detections"],
        "warnings": median_run["warnings"],
        "stage_s": median_run["stage_s"],
        "model_sizes_mb": model_sizes(),
        "environment": environment(),
        "measured_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, indent=2), encoding="utf-8")
    args.out.with_suffix(".md").write_text(markdown_table(result), encoding="utf-8")
    print(json.dumps({k: v for k, v in result.items() if k != "environment"}, indent=2))


if __name__ == "__main__":
    main()
