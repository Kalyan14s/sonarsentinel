"""Settings endpoints (ST-098, ADR-019): ``GET /settings`` and partial ``PUT /settings``."""

from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, Request
from fastapi.concurrency import run_in_threadpool

from sonarsentinel import __version__
from sonarsentinel.api.context import ApiContext, get_context
from sonarsentinel.api.system import available_runtimes, list_models
from sonarsentinel.api.tiles import tiles_readable
from sonarsentinel.errors import ValidationError
from sonarsentinel.settings import load_settings, merge_update, save_settings, validate_settings

router = APIRouter()


def system_info(context: ApiContext) -> dict[str, Any]:
    """The read-only ``system`` block of the settings."""
    api = context.config.get("api", {})
    return {
        "data_dir": str(context.data_dir),
        "max_upload_gb": float(context.config.get("ingest", {}).get("max_upload_gb", 2)),
        "keep_work_files": bool(api.get("keep_work_files", False)),
        "offline_tiles_available": tiles_readable(context.offline_tiles),
        "runtimes_available": available_runtimes(),
        "version": __version__,
    }


def _save(context: ApiContext, body: Any) -> dict[str, Any]:
    current = load_settings(context.data_dir, context.config)
    settings = validate_settings(
        merge_update(current, body),
        model_ids=[m["id"] for m in list_models(context.config)],
        tiles_available=tiles_readable(context.offline_tiles),
    )
    save_settings(context.data_dir, settings)
    return settings


@router.get("/settings", tags=["system"], summary="Settings for new jobs and the dashboard")
def get_settings(request: Request) -> dict[str, Any]:
    context = get_context(request.app)
    return load_settings(context.data_dir, context.config) | {"system": system_info(context)}


@router.put(
    "/settings",
    tags=["system"],
    summary="Update settings (partial); applies to jobs started afterwards",
)
async def put_settings(request: Request) -> dict[str, Any]:
    try:
        body = await request.json()
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise ValidationError("Send the settings as a JSON object", field="body") from exc
    context = get_context(request.app)
    settings: dict[str, Any] = await run_in_threadpool(_save, context, body)
    return settings | {"system": system_info(context)}
