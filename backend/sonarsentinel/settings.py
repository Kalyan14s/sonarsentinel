"""Operator settings (ST-098, ADR-019).

Defaults come from the pipeline configuration; ``PUT /settings`` saves validated overrides to
``<data_dir>/settings.json``. Saved settings apply to jobs started afterwards, never to running
jobs. ``detection.model_id`` is ``auto`` or one of the ``GET /models`` ids and maps to the
detector choice (``auto`` | ``classical`` | ``yolo``).
"""

from __future__ import annotations

import copy
import json
import logging
from collections.abc import Sequence
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator
from pydantic import ValidationError as PydanticValidationError

from sonarsentinel.errors import ValidationError

logger = logging.getLogger(__name__)

SETTINGS_FILENAME = "settings.json"
AUTO_MODEL = "auto"
SETTINGS_RUNTIMES = ("auto", "torch", "onnxruntime", "tensorrt", "cuda")


class _Section(BaseModel):
    model_config = ConfigDict(extra="forbid")


class DetectionSettings(_Section):
    model_id: str = AUTO_MODEL
    runtime: Literal["auto", "torch", "onnxruntime", "tensorrt", "cuda"] = "auto"
    min_raw_score: float = Field(0.20, ge=0, le=1)


class AnomalySettings(_Section):
    enabled: bool = True
    threshold: float = Field(0.50, ge=0, le=1)


class TierSettings(_Section):
    hazard: float = Field(80.0, ge=0, le=100)
    review: float = Field(50.0, ge=0, le=100)
    anomaly: float = Field(30.0, ge=0, le=100)

    @model_validator(mode="after")
    def _ordered(self) -> TierSettings:
        if not self.hazard > self.review > self.anomaly:
            raise ValueError("tiers must satisfy hazard > review > anomaly")
        return self


class MapSettings(_Section):
    min_conf_default: float = Field(30.0, ge=0, le=100)
    basemap: Literal["online", "offline"] = "online"
    coordinates: Literal["dd", "dms"] = "dd"


class ProcessingSettings(_Section):
    ground_resolution_m: float = Field(0.10, gt=0, le=10)
    pings_per_chunk: int = Field(2000, gt=0)
    overlap_pings: int = Field(200, ge=0)

    @model_validator(mode="after")
    def _overlap(self) -> ProcessingSettings:
        if self.overlap_pings >= self.pings_per_chunk:
            raise ValueError("overlap_pings must be smaller than pings_per_chunk")
        return self


class GeoSettings(_Section):
    apply_layback: Literal["auto"] | bool = "auto"
    cluster_radius_m: float = Field(5.0, gt=0, le=1000)


class Settings(_Section):
    detection: DetectionSettings
    anomaly: AnomalySettings
    tiers: TierSettings
    map: MapSettings
    processing: ProcessingSettings
    geo: GeoSettings


def default_settings(config: dict[str, Any]) -> dict[str, Any]:
    """Settings as they follow from the pipeline configuration alone."""
    detection = config.get("detection", {})
    anomaly = config.get("anomaly", {})
    tiers = config.get("scoring", {}).get("tiers", {})
    preprocess = config.get("preprocess", {})
    chunking = config.get("chunking", {})
    layback = config.get("navigation", {}).get("apply_layback", "auto")
    runtime = str(detection.get("runtime", "auto"))
    data = {
        "detection": {
            "model_id": AUTO_MODEL,
            "runtime": runtime if runtime in SETTINGS_RUNTIMES else "auto",
            "min_raw_score": float(detection.get("min_raw_score", 0.20)),
        },
        "anomaly": {
            "enabled": bool(anomaly.get("enabled", True)),
            "threshold": float(anomaly.get("threshold", 0.50)),
        },
        "tiers": {
            name: float(tiers.get(name, default))
            for name, default in (("hazard", 80.0), ("review", 50.0), ("anomaly", 30.0))
        },
        "map": {"min_conf_default": 30.0, "basemap": "online", "coordinates": "dd"},
        "processing": {
            "ground_resolution_m": float(preprocess.get("ground_resolution_m", 0.10)),
            "pings_per_chunk": int(chunking.get("pings_per_chunk", 2000)),
            "overlap_pings": int(chunking.get("overlap_pings", 200)),
        },
        "geo": {
            "apply_layback": layback if isinstance(layback, bool) else str(layback),
            "cluster_radius_m": float(config.get("geo", {}).get("cluster_radius_m", 5.0)),
        },
    }
    return validate_settings(data)


def validate_settings(
    data: Any,
    *,
    model_ids: Sequence[str] | None = None,
    tiles_available: bool | None = None,
) -> dict[str, Any]:
    """Validated settings as plain JSON types.

    Args:
        data: Complete settings (all sections).
        model_ids: Allowed ``detection.model_id`` values besides ``auto`` (``GET /models`` ids).
        tiles_available: When given, ``map.basemap = "offline"`` requires it to be True.

    Raises:
        ValidationError: Unknown keys, wrong types, out-of-range values or inconsistent tiers.
    """
    try:
        settings = Settings.model_validate(data)
    except PydanticValidationError as exc:
        errors = [
            {"field": ".".join(str(p) for p in err["loc"]) or "settings", "message": err["msg"]}
            for err in exc.errors()
        ]
        raise ValidationError("Invalid settings", field="settings", errors=errors) from exc
    if model_ids is not None and settings.detection.model_id not in (AUTO_MODEL, *model_ids):
        raise ValidationError(
            f"Unknown detection.model_id: {settings.detection.model_id}",
            field="detection.model_id",
            supported=[AUTO_MODEL, *model_ids],
        )
    if tiles_available is False and settings.map.basemap == "offline":
        raise ValidationError(
            "The offline basemap needs an MBTiles file (SS_OFFLINE_TILES)", field="map.basemap"
        )
    return settings.model_dump()


def merge_update(current: dict[str, Any], update: Any) -> dict[str, Any]:
    """Apply a partial update (per section) to complete settings; ``system`` is read-only."""
    if not isinstance(update, dict):
        raise ValidationError("Send the settings as a JSON object", field="body")
    merged = copy.deepcopy(current)
    for key, value in update.items():
        if key == "system":
            continue
        if isinstance(merged.get(key), dict) and isinstance(value, dict):
            merged[key] = {**merged[key], **value}
        else:
            merged[key] = value  # unknown sections and wrong types fail validation
    return merged


def settings_path(data_dir: str | Path) -> Path:
    return Path(data_dir) / SETTINGS_FILENAME


def saved_settings(data_dir: str | Path, config: dict[str, Any]) -> dict[str, Any] | None:
    """Saved settings completed with the defaults, or ``None`` when nothing was saved."""
    path = settings_path(data_dir)
    if not path.is_file():
        return None
    try:
        saved = json.loads(path.read_text(encoding="utf-8"))
        return validate_settings(merge_update(default_settings(config), saved))
    except (OSError, json.JSONDecodeError, ValidationError):
        logger.warning("Ignoring unreadable or invalid settings file %s", path)
        return None


def load_settings(data_dir: str | Path, config: dict[str, Any]) -> dict[str, Any]:
    """Current settings: the saved ones, else the defaults from the configuration."""
    return saved_settings(data_dir, config) or default_settings(config)


def save_settings(data_dir: str | Path, settings: dict[str, Any]) -> Path:
    """Write validated settings atomically."""
    path = settings_path(data_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(settings, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temporary.replace(path)
    return path


def detector_name(model_id: str) -> str:
    """``detection.model_id`` → detector choice for ``build_detector``."""
    if model_id == AUTO_MODEL:
        return "auto"
    return "classical" if model_id.startswith("classical") else "yolo"


def apply_settings(config: dict[str, Any], settings: dict[str, Any]) -> dict[str, Any]:
    """A copy of ``config`` with the settings that affect processing applied."""
    merged = copy.deepcopy(config)
    detection, anomaly = settings["detection"], settings["anomaly"]
    processing, geo = settings["processing"], settings["geo"]
    merged.setdefault("detection", {}).update(
        runtime=detection["runtime"], min_raw_score=detection["min_raw_score"]
    )
    merged.setdefault("anomaly", {}).update(
        enabled=anomaly["enabled"], threshold=anomaly["threshold"]
    )
    merged.setdefault("scoring", {})["tiers"] = dict(settings["tiers"])
    merged.setdefault("preprocess", {})["ground_resolution_m"] = processing["ground_resolution_m"]
    merged["chunking"] = {
        **merged.get("chunking", {}),
        "pings_per_chunk": processing["pings_per_chunk"],
        "overlap_pings": processing["overlap_pings"],
    }
    merged.setdefault("navigation", {})["apply_layback"] = geo["apply_layback"]
    merged.setdefault("geo", {})["cluster_radius_m"] = geo["cluster_radius_m"]
    return merged
