"""FastAPI application (ST-080…086): system, surveys, detections, reports, jobs and job events.

Endpoints follow ``docs/architecture/05-api-specification.md`` and ADR-018. Every error is returned
in the ``{"error": {code, message, details}}`` shape with its HTTP status, including invalid query
parameters (400 ``VALIDATION_ERROR``). Uploaded files, results, labels and the SQLite database live
under the data folder: ``create_app(data_dir=…)``, else the ``SONARSENTINEL_DATA_DIR`` environment
variable, else ``<repo>/data/api``.
"""

from __future__ import annotations

import importlib.util
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
from sonarsentinel.api.surveys import router as surveys_router
from sonarsentinel.api.ws import router as ws_router
from sonarsentinel.config import load_config

API_PREFIX = "/api/v1"
DATA_DIR_ENV = "SONARSENTINEL_DATA_DIR"


def _gpu() -> dict[str, Any]:
    if importlib.util.find_spec("torch") is None:
        return {"available": False, "name": None}
    import torch

    if torch.cuda.is_available():
        return {"available": True, "name": torch.cuda.get_device_name(0)}
    return {"available": False, "name": None}


def resolve_data_dir(data_dir: str | Path | None = None) -> Path:
    """Data folder for uploads, results, job logs, labels and the database."""
    if data_dir is not None:
        return Path(data_dir)
    if os.environ.get(DATA_DIR_ENV):
        return Path(os.environ[DATA_DIR_ENV])
    return Path(__file__).resolve().parents[3] / "data" / "api"


def list_models(config: dict[str, Any]) -> list[dict[str, Any]]:
    """Detector options: the rule-based stand-in (always) and the configured trained model."""
    from sonarsentinel.detect.classical import BrightTargetDetector

    weights = Path(config["detection"]["model"])
    if not weights.is_absolute():
        weights = Path(__file__).resolve().parents[3] / weights
    return [
        {
            "kind": "detector",
            "id": BrightTargetDetector.model_version,
            "available": True,
            "trained": False,
            "path": None,
        },
        {
            "kind": "detector",
            "id": f"yolo:{weights.parent.name}" if weights.parent.name else "yolo",
            "available": weights.is_file(),
            "trained": True,
            "path": str(weights),
        },
    ]


def create_app(
    config: dict[str, Any] | None = None, *, data_dir: str | Path | None = None
) -> FastAPI:
    cfg = config if config is not None else load_config()

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
    app.state.context = None
    install_handlers(app)

    router = APIRouter(prefix=API_PREFIX)

    @router.get("/health", tags=["system"], summary="Service, GPU and model status")
    def health() -> dict[str, Any]:
        models = list_models(cfg)
        gpu = _gpu()
        return {
            "status": "ok",
            "version": __version__,
            "pipeline_version": cfg.get("pipeline_version"),
            "gpu": gpu,
            "runtime": "cuda" if gpu["available"] else "cpu",
            "models_loaded": any(m["available"] and m["trained"] for m in models),
            "offline_tiles": False,
        }

    @router.get("/models", tags=["system"], summary="Available model versions")
    def models() -> dict[str, Any]:
        items = list_models(cfg)
        return {"total": len(items), "items": items}

    app.include_router(router)
    app.include_router(surveys_router, prefix=API_PREFIX)
    app.include_router(results_router, prefix=API_PREFIX)
    app.include_router(ws_router)
    return app


app = create_app()
