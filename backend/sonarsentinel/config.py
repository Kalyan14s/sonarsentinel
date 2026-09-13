"""Pipeline configuration loading and hashing.

The config hash is stored with every job and report so results are reproducible (NFR-16).
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import yaml

from sonarsentinel.errors import ValidationError

DEFAULT_CONFIG_PATH = Path(__file__).resolve().parents[1] / "configs" / "pipeline.yaml"


def load_config(path: str | Path | None = None) -> dict[str, Any]:
    """Load the pipeline YAML configuration.

    Args:
        path: Config file. Defaults to ``backend/configs/pipeline.yaml``.

    Returns:
        The parsed configuration mapping.

    Raises:
        ValidationError: If the file is missing or its root is not a mapping.
    """
    config_path = Path(path) if path is not None else DEFAULT_CONFIG_PATH
    if not config_path.is_file():
        raise ValidationError(f"Config file not found: {config_path}", path=str(config_path))
    with config_path.open(encoding="utf-8") as fh:
        data = yaml.safe_load(fh)
    if not isinstance(data, dict):
        raise ValidationError("Config root must be a mapping", path=str(config_path))
    return data


def config_hash(config: dict[str, Any]) -> str:
    """Return a stable ``sha256:<hex>`` hash of a configuration, independent of key order."""
    canonical = json.dumps(config, sort_keys=True, separators=(",", ":"), default=str)
    return "sha256:" + hashlib.sha256(canonical.encode("utf-8")).hexdigest()
