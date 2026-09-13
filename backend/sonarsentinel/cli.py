"""Command-line interface: ``sonarsentinel``."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

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


@app.command()
def detect(
    source: Annotated[Path, typer.Argument(help="Sonar log to analyse.")],
) -> None:
    """Run detection on a sonar log (planned: Sprint 3, ST-074/ST-075)."""
    typer.echo(f"detect is not implemented yet ({source.name}): planned for Sprint 3.", err=True)
    raise typer.Exit(code=2)


@app.command()
def serve(
    host: Annotated[str, typer.Option(help="Bind address.")] = "127.0.0.1",
    port: Annotated[int, typer.Option(help="Port.")] = 8000,
) -> None:
    """Start the API server (planned: Sprint 3-4, ST-080+)."""
    typer.echo(f"serve is not implemented yet ({host}:{port}): planned for Sprint 3.", err=True)
    raise typer.Exit(code=2)
