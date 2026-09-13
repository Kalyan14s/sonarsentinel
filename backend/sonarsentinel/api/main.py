"""FastAPI application (ST-080…086, ST-098, ST-099): system, settings, tiles, surveys, detections,
reports, jobs and job events.

Endpoints follow ``docs/architecture/05-api-specification.md``, ADR-018 and ADR-019. Every error is
returned in the ``{"error": {code, message, details}}`` shape with its HTTP status, including
invalid query parameters (400 ``VALIDATION_ERROR``). Uploaded files, results, labels, settings and
the SQLite database live under the data folder: ``create_app(data_dir=…)``, else ``SS_DATA_DIR``,
else ``SONARSENTINEL_DATA_DIR`` (older name), else ``<repo>/data/api``. ``SS_*`` environment
variables are applied to the configuration (:func:`sonarsentinel.config.apply_env`).
"""

from __future__ import annotations

import copy
import logging
import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import APIRouter, FastAPI

from sonarsentinel import __version__
from sonarsentinel.api.context import close_context, get_context
from sonarsentinel.api.handlers import install_handlers
from sonarsentinel.api.results import router as results_router
from sonarsentinel.api.settings import router as settings_router
from sonarsentinel.api.surveys import router as surveys_router
from sonarsentinel.api.system import detector_runtime, gpu_info, list_models
from sonarsentinel.api.tiles import router as tiles_router
from sonarsentinel.api.tiles import tiles_readable
from sonarsentinel.api.ws import router as ws_router
from sonarsentinel.config import apply_env, load_config

__all__ = ["API_PREFIX", "app", "create_app", "list_models", "resolve_data_dir"]

API_PREFIX = "/api/v1"
DATA_DIR_ENV = "SS_DATA_DIR"
LEGACY_DATA_DIR_ENV = "SONARSENTINEL_DATA_DIR"

logger = logging.getLogger(__name__)


def resolve_data_dir(data_dir: str | Path | None = None) -> Path:
    """Data folder for uploads, results, job logs, labels, settings and the database."""
    if data_dir is not None:
        return Path(data_dir)
    for name in (DATA_DIR_ENV, LEGACY_DATA_DIR_ENV):
        value = os.environ.get(name, "").strip()
        if value:
            return Path(value)
    return Path(__file__).resolve().parents[3] / "data" / "api"


def resolve_offline_tiles(
    config: dict[str, Any], offline_tiles: str | Path | None = None
) -> Path | None:
    """MBTiles file: the argument, else ``api.offline_tiles`` (``SS_OFFLINE_TILES``)."""
    value = (
        offline_tiles if offline_tiles is not None else config.get("api", {}).get("offline_tiles")
    )
    return Path(value) if value else None


def _configure_logging(config: dict[str, Any]) -> None:
    api = config.get("api", {})
    if api.get("log_level"):
        logging.getLogger("sonarsentinel").setLevel(str(api["log_level"]).upper())
    workers = int(api.get("workers", 1) or 1)
    if workers > 1:
        logger.warning("SS_WORKERS=%d requested; the prototype runs a single job worker", workers)


def create_app(
    config: dict[str, Any] | None = None,
    *,
    data_dir: str | Path | None = None,
    offline_tiles: str | Path | None = None,
) -> FastAPI:
    cfg = apply_env(copy.deepcopy(config)) if config is not None else load_config()
    _configure_logging(cfg)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        get_context(app)  # open the database and start the job worker
        try:
            yield
        finally:
            close_context(app)

    app = FastAPI(
        title="SonarSentinel API",
        version=__version__,
        description="Marine debris and ghost-net detection in side-scan sonar.",
        docs_url="/docs",
        openapi_url="/openapi.json",
        lifespan=lifespan,
    )
    app.state.config = cfg
    app.state.data_dir = resolve_data_dir(data_dir)
    app.state.offline_tiles = resolve_offline_tiles(cfg, offline_tiles)
    app.state.context = None
    install_handlers(app)

    router = APIRouter(prefix=API_PREFIX)

    @router.get("/health", tags=["system"], summary="Service, GPU, runtime and model status")
    def health() -> dict[str, Any]:
        models = list_models(cfg)
        gpu = gpu_info()
        return {
            "status": "ok",
            "version": __version__,
            "pipeline_version": cfg.get("pipeline_version"),
            "gpu": gpu,
            "runtime": detector_runtime(cfg, gpu),
            "models_loaded": any(m["available"] and m["trained"] for m in models),
            "offline_tiles": tiles_readable(app.state.offline_tiles),
        }

    @router.get("/models", tags=["system"], summary="Available model versions")
    def models() -> dict[str, Any]:
        items = list_models(cfg)
        return {"total": len(items), "items": items}

    app.include_router(router)
    app.include_router(settings_router, prefix=API_PREFIX)
    app.include_router(tiles_router, prefix=API_PREFIX)
    app.include_router(surveys_router, prefix=API_PREFIX)
    app.include_router(results_router, prefix=API_PREFIX)
    app.include_router(ws_router)
    return app


app = create_app()
