"""Pipeline configuration loading, environment overrides and hashing.

The config hash is stored with every job and report so results are reproducible (NFR-16).
Deployment settings come from ``SS_*`` environment variables
(``docs/architecture/07-deployment.md`` §6, ADR-019); :func:`apply_env` applies them on top of the
YAML file, and invalid values fail at start-up with :class:`ValidationError`.
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Any

import yaml

from sonarsentinel.errors import ValidationError

DEFAULT_CONFIG_PATH = Path(__file__).resolve().parents[1] / "configs" / "pipeline.yaml"
CONFIG_ENV = "SS_CONFIG"
RUNTIMES = ("auto", "torch", "onnxruntime", "tensorrt", "cuda")
LOG_LEVELS = ("DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL")
DEFAULT_JOB_TIMEOUT_S = 3600.0
MODEL_PATH_KEYS = (
    ("detection", "model"),
    ("anomaly", "model"),
    ("scoring", "fp_filter_model"),
    ("scoring", "calibrator"),
)
_TRUE = ("1", "true", "yes", "on")
_FALSE = ("0", "false", "no", "off")


def load_config(path: str | Path | None = None) -> dict[str, Any]:
    """Load the pipeline YAML configuration and apply the ``SS_*`` environment variables.

    Args:
        path: Config file. Defaults to ``SS_CONFIG``, else ``backend/configs/pipeline.yaml``.

    Returns:
        The parsed configuration mapping.

    Raises:
        ValidationError: If the file is missing, its root is not a mapping, or an environment
            variable has an invalid value.
    """
    if path is not None:
        config_path = Path(path)
    elif os.environ.get(CONFIG_ENV, "").strip():
        config_path = Path(os.environ[CONFIG_ENV].strip())
    else:
        config_path = DEFAULT_CONFIG_PATH
    if not config_path.is_file():
        raise ValidationError(f"Config file not found: {config_path}", path=str(config_path))
    with config_path.open(encoding="utf-8") as fh:
        data = yaml.safe_load(fh)
    if not isinstance(data, dict):
        raise ValidationError("Config root must be a mapping", path=str(config_path))
    return apply_env(data)


def _env(name: str) -> str | None:
    value = os.environ.get(name, "").strip()
    return value or None


def _number(name: str, value: str, *, integer: bool = False, minimum: float = 0.0) -> float:
    """Parse a number that must be greater than ``minimum`` (integers: at least ``minimum``)."""
    try:
        number: float = int(value) if integer else float(value)
    except ValueError as exc:
        kind = "a whole number" if integer else "a number"
        raise ValidationError(f"{name} must be {kind}, not {value!r}", field=name) from exc
    if (integer and number < minimum) or (not integer and number <= minimum):
        bound = "at least" if integer else "greater than"
        raise ValidationError(f"{name} must be {bound} {minimum:g}", field=name, value=value)
    return number


def _flag(name: str, value: str) -> bool:
    text = value.lower()
    if text in _TRUE:
        return True
    if text in _FALSE:
        return False
    raise ValidationError(f"{name} must be true or false, not {value!r}", field=name)


def apply_env(config: dict[str, Any]) -> dict[str, Any]:
    """Apply ``SS_*`` environment variables to ``config`` in place and return it.

    ============================  =====================================================
    ``SS_MODELS_DIR``             relative model paths resolve against this folder (a
                                  leading ``models/`` component is dropped)
    ``SS_RUNTIME``                ``detection.runtime``
    ``SS_MAX_UPLOAD_GB``          ``ingest.max_upload_gb``
    ``SS_OFFLINE_TILES``          ``api.offline_tiles`` (MBTiles file)
    ``SS_KEEP_WORK_FILES``        ``api.keep_work_files``
    ``SS_LOG_LEVEL``              ``api.log_level``
    ``SS_WORKERS``                ``api.workers`` (only 1 is supported)
    ``SS_JOB_TIMEOUT_S``          ``jobs.max_job_seconds``
    ============================  =====================================================

    ``SS_CONFIG`` (config path) is handled by :func:`load_config` and ``SS_DATA_DIR`` by the API.
    Applying it twice gives the same result.
    """
    models_dir = _env("SS_MODELS_DIR")
    if models_dir:
        root = Path(models_dir)
        for section, key in MODEL_PATH_KEYS:
            block = config.get(section)
            value = block.get(key) if isinstance(block, dict) else None
            if not value:
                continue
            path = Path(str(value))
            if path.is_absolute():
                continue
            parts = path.parts[1:] if path.parts and path.parts[0] == "models" else path.parts
            block[key] = str(root.joinpath(*parts))  # type: ignore[index]

    runtime = _env("SS_RUNTIME")
    if runtime:
        if runtime.lower() not in RUNTIMES:
            raise ValidationError(
                f"SS_RUNTIME must be one of {', '.join(RUNTIMES)}",
                field="SS_RUNTIME",
                value=runtime,
            )
        config.setdefault("detection", {})["runtime"] = runtime.lower()

    upload = _env("SS_MAX_UPLOAD_GB")
    if upload:
        config.setdefault("ingest", {})["max_upload_gb"] = _number("SS_MAX_UPLOAD_GB", upload)

    tiles = _env("SS_OFFLINE_TILES")
    if tiles:
        config.setdefault("api", {})["offline_tiles"] = tiles

    keep = _env("SS_KEEP_WORK_FILES")
    if keep:
        config.setdefault("api", {})["keep_work_files"] = _flag("SS_KEEP_WORK_FILES", keep)

    level = _env("SS_LOG_LEVEL")
    if level:
        if level.upper() not in LOG_LEVELS:
            raise ValidationError(
                f"SS_LOG_LEVEL must be one of {', '.join(LOG_LEVELS)}",
                field="SS_LOG_LEVEL",
                value=level,
            )
        config.setdefault("api", {})["log_level"] = level.upper()

    workers = _env("SS_WORKERS")
    if workers:
        count = _number("SS_WORKERS", workers, integer=True, minimum=1)
        config.setdefault("api", {})["workers"] = int(count)

    timeout = _env("SS_JOB_TIMEOUT_S")
    if timeout:
        config.setdefault("jobs", {})["max_job_seconds"] = _number("SS_JOB_TIMEOUT_S", timeout)
    return config


def config_hash(config: dict[str, Any]) -> str:
    """Return a stable ``sha256:<hex>`` hash of a configuration, independent of key order."""
    canonical = json.dumps(config, sort_keys=True, separators=(",", ":"), default=str)
    return "sha256:" + hashlib.sha256(canonical.encode("utf-8")).hexdigest()
