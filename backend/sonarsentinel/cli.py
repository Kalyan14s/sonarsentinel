"""Command-line interface: ``sonarsentinel``."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Annotated, Any

import typer

from sonarsentinel import __version__
from sonarsentinel.config import config_hash, load_config
from sonarsentinel.errors import SonarSentinelError
from sonarsentinel.ingest.validators import check_file

app = typer.Typer(
    help="SonarSentinel: marine debris and ghost-net detection in side-scan sonar imagery.",
    no_args_is_help=True,
    add_completion=False,
)

GIB = 1024**3

NavOption = Annotated[
    Path | None,
    typer.Option("--nav", exists=True, dir_okay=False, help="Navigation CSV for image inputs."),
]
EpsgOption = Annotated[
    str,
    typer.Option("--utm-epsg", help="EPSG code for projected navigation, e.g. 32644, or 'auto'."),
]
LayoutOption = Annotated[
    str, typer.Option(help="Image channel layout: port_stbd, port_only or stbd_only.")
]
NoGpsOption = Annotated[
    bool, typer.Option("--allow-no-gps", help="Continue without navigation (NOT_GEOTAGGED).")
]


@app.command()
def version() -> None:
    """Print the package version."""
    typer.echo(__version__)


@app.command()
def validate(
    files: Annotated[
        list[Path], typer.Argument(exists=True, dir_okay=False, help="Sonar files to check.")
    ],
    max_upload_gb: Annotated[float, typer.Option(help="Maximum file size in GiB.")] = 2.0,
) -> None:
    """Check file type, size and header bytes (pipeline stage S0)."""
    failed = False
    for f in files:
        try:
            result = check_file(f, max_bytes=int(max_upload_gb * GIB))
        except SonarSentinelError as exc:
            failed = True
            typer.echo(f"[X] {f.name}: {exc.code} - {exc.message}")
        else:
            typer.echo(f"[ok] {f.name}: {result.source_format}, {result.size_bytes} bytes")
    if failed:
        raise typer.Exit(code=1)


def _epsg(value: str) -> int | str | None:
    if value in ("", "auto"):
        return None
    return int(value) if value.isdigit() else value


def _read(source: Path, nav: Path | None, utm_epsg: str, layout: str, allow_no_gps: bool):  # type: ignore[no-untyped-def]
    from sonarsentinel.ingest.reader import read_source

    try:
        return read_source(
            source,
            nav_csv=nav,
            epsg=_epsg(utm_epsg),
            layout=layout,  # type: ignore[arg-type]
            allow_no_gps=allow_no_gps,
        )
    except SonarSentinelError as exc:
        typer.echo(json.dumps(exc.to_dict()), err=True)
        raise typer.Exit(code=1) from exc


@app.command()
def inspect(
    source: Annotated[Path, typer.Argument(exists=True, dir_okay=False, help="Sonar file.")],
    nav: NavOption = None,
    utm_epsg: EpsgOption = "auto",
    layout: LayoutOption = "port_stbd",
    allow_no_gps: NoGpsOption = False,
) -> None:
    """Read a sonar file (stage S1) and print a JSON summary: pings, times, track, warnings."""
    from sonarsentinel.ingest.reader import summarize

    log = _read(source, nav, utm_epsg, layout, allow_no_gps)
    typer.echo(json.dumps(summarize(log, source.stat().st_size), indent=2))


@app.command()
def track(
    source: Annotated[Path, typer.Argument(exists=True, dir_okay=False, help="Sonar file.")],
    out: Annotated[Path, typer.Option(help="Output GeoJSON file.")] = Path("track.geojson"),
    every: Annotated[int, typer.Option(help="Keep every Nth ping.")] = 1,
    nav: NavOption = None,
    utm_epsg: EpsgOption = "auto",
) -> None:
    """Export the sonar track as GeoJSON (open it in QGIS or geojson.io to check it on a map)."""
    from sonarsentinel.geo.track import track_geojson

    log = _read(source, nav, utm_epsg, "port_stbd", False)
    geojson = track_geojson(log, every=every)
    out.write_text(json.dumps(geojson), encoding="utf-8")
    n = len(geojson["features"][0]["geometry"]["coordinates"])
    typer.echo(f"[ok] wrote {out} ({n} points)")


@app.command("config")
def show_config(
    path: Annotated[
        Path | None, typer.Option(help="Pipeline YAML (default: backend/configs/pipeline.yaml).")
    ] = None,
) -> None:
    """Load the pipeline configuration and print its version and hash."""
    try:
        cfg = load_config(path)
    except SonarSentinelError as exc:
        typer.echo(f"[X] {exc.code} - {exc.message}")
        raise typer.Exit(code=1) from exc
    typer.echo(f"pipeline_version: {cfg.get('pipeline_version', 'unknown')}")
    typer.echo(f"config_hash: {config_hash(cfg)}")


def build_anomaly(cfg: dict[str, Any], disabled: bool) -> Any | None:
    """The configured PatchCore model, or ``None`` if disabled, untrained or torch is missing."""
    import importlib.util

    anomaly = cfg.get("anomaly", {})
    if disabled or not anomaly.get("enabled", False) or importlib.util.find_spec("torch") is None:
        return None
    folder = Path(anomaly["model"])
    if not folder.is_absolute():
        folder = Path(__file__).resolve().parents[2] / folder
    if not (folder / "memory_bank.pt").is_file():
        return None
    from sonarsentinel.detect.anomaly import PatchCoreModel

    return PatchCoreModel.load(folder)


def _repo_path(value: str | Path) -> Path:
    """Config paths are relative to the repository root."""
    path = Path(value)
    return path if path.is_absolute() else Path(__file__).resolve().parents[2] / path


def build_detector(name: str, model: Path | None, cfg: dict[str, Any]) -> Any:
    """Detector by CLI name.

    ``auto`` uses the trained YOLO11-seg weights when they exist and Ultralytics is installed,
    otherwise the rule-based stand-in; ``classical`` and ``yolo`` force one of them.
    """
    import importlib.util

    from sonarsentinel.errors import ValidationError

    if name not in ("auto", "classical", "yolo"):
        raise ValidationError(f"Unknown detector: {name}", supported=["auto", "classical", "yolo"])
    weights = model or _repo_path(cfg["detection"]["model"])
    has_yolo = weights.is_file() and importlib.util.find_spec("ultralytics") is not None
    if name == "yolo" or (name == "auto" and has_yolo):
        from sonarsentinel.detect.yolo import YoloDetector

        return YoloDetector(weights, sahi=bool(cfg["detection"].get("sahi", True)))
    from sonarsentinel.detect.classical import BrightTargetDetector

    return BrightTargetDetector()


@app.command()
def detect(
    source: Annotated[Path, typer.Argument(exists=True, dir_okay=False, help="Sonar file.")],
    out: Annotated[Path, typer.Option(help="Output folder (a subfolder per survey).")] = Path(
        "results"
    ),
    formats: Annotated[str, typer.Option(help="Comma-separated: json,csv.")] = "json,csv",
    nav: NavOption = None,
    utm_epsg: EpsgOption = "auto",
    min_conf: Annotated[
        float | None, typer.Option("--min-conf", help="Drop detections below this confidence.")
    ] = None,
    no_anomaly: Annotated[
        bool, typer.Option("--no-anomaly", help="Skip the PatchCore anomaly model.")
    ] = False,
    allow_no_gps: NoGpsOption = False,
    detector: Annotated[
        str, typer.Option(help="auto (trained YOLO if available), classical or yolo.")
    ] = "auto",
    model: Annotated[Path | None, typer.Option(help="Detector weights (yolo).")] = None,
    config: Annotated[Path | None, typer.Option(help="Pipeline YAML.")] = None,
    quiet: Annotated[bool, typer.Option(help="No progress output.")] = False,
) -> None:
    """Run the full pipeline on a sonar file and write the report (stages S0–S12)."""
    from sonarsentinel.pipeline import run_pipeline
    from sonarsentinel.report.export import write_reports

    def progress(event: dict[str, Any]) -> None:
        if not quiet and event["type"] in ("progress", "done"):
            detail = event.get("stage") or event.get("status")
            typer.echo(f"  {event['type']}: {detail} {event.get('percent', '')}", err=True)

    try:
        cfg = load_config(config)
        report = run_pipeline(
            source,
            config=cfg,
            nav_csv=nav,
            epsg=_epsg(utm_epsg),
            allow_no_gps=allow_no_gps,
            detector=build_detector(detector, model, cfg),
            anomaly_model=build_anomaly(cfg, no_anomaly),
            min_conf=min_conf,
            on_event=progress,
        )
        paths = write_reports(report, out, [f.strip() for f in formats.split(",") if f.strip()])
    except SonarSentinelError as exc:
        typer.echo(json.dumps(exc.to_dict()), err=True)
        raise typer.Exit(code=1) from exc
    summary = report["summary"]
    typer.echo(
        f"[ok] {report['survey']['survey_id']}: {summary['total_detections']} detections "
        f"{summary['by_tier']} -> " + ", ".join(str(p) for p in paths.values())
    )


@app.command()
def serve(
    host: Annotated[str, typer.Option(help="Bind address.")] = "127.0.0.1",
    port: Annotated[int, typer.Option(help="Port.")] = 8000,
    mock: Annotated[bool, typer.Option(help="Serve the mock API for frontend work.")] = False,
) -> None:
    """Start the API server (``--mock`` serves canned surveys and events, ST-087)."""
    import uvicorn

    target = "sonarsentinel.api.mock:app" if mock else "sonarsentinel.api.main:app"
    uvicorn.run(target, host=host, port=port)
