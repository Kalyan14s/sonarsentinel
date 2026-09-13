"""FastAPI application skeleton (ST-080): health, models, OpenAPI docs and the error model.

Endpoints follow ``docs/architecture/05-api-specification.md``; the survey/job routes arrive in
Sprint 4 (ST-081…085). Every :class:`~sonarsentinel.errors.SonarSentinelError` is returned in the
``{"error": {code, message, details}}`` shape with its HTTP status.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path
from typing import Any

from fastapi import APIRouter, FastAPI, Request
from fastapi.responses import JSONResponse

from sonarsentinel import __version__
from sonarsentinel.config import load_config
from sonarsentinel.errors import SonarSentinelError

API_PREFIX = "/api/v1"


def _gpu() -> dict[str, Any]:
    if importlib.util.find_spec("torch") is None:
        return {"available": False, "name": None}
    import torch

    if torch.cuda.is_available():
        return {"available": True, "name": torch.cuda.get_device_name(0)}
    return {"available": False, "name": None}


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


def create_app(config: dict[str, Any] | None = None) -> FastAPI:
    cfg = config if config is not None else load_config()
    app = FastAPI(
        title="SonarSentinel API",
        version=__version__,
        description="Marine debris and ghost-net detection in side-scan sonar.",
        docs_url="/docs",
        openapi_url="/openapi.json",
    )

    @app.exception_handler(SonarSentinelError)
    async def sonarsentinel_error(_: Request, exc: SonarSentinelError) -> JSONResponse:
        return JSONResponse(status_code=exc.http_status, content=exc.to_dict())

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
    return app


app = create_app()
