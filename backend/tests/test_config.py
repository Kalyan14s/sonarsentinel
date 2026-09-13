from pathlib import Path

import pytest

from sonarsentinel.config import config_hash, load_config
from sonarsentinel.errors import ValidationError


def test_default_config_matches_documented_defaults() -> None:
    cfg = load_config()
    assert cfg["pipeline_version"] == "0.2.0"
    assert cfg["preprocess"]["ground_resolution_m"] == 0.10
    assert cfg["tiling"] == {"size_px": 640, "overlap": 0.25, "skip_if_masked_fraction_gt": 0.8}
    assert cfg["scoring"]["tiers"] == {"hazard": 80, "review": 50, "anomaly": 30}
    weights = cfg["scoring"]["weights"]
    assert sum(weights.values()) == pytest.approx(1.0)


def test_config_hash_is_independent_of_key_order() -> None:
    a = {"x": 1, "y": {"b": 2, "a": [1, 2]}}
    b = {"y": {"a": [1, 2], "b": 2}, "x": 1}
    assert config_hash(a) == config_hash(b)
    assert config_hash(a).startswith("sha256:")
    assert config_hash(a) != config_hash({"x": 2, "y": {"b": 2, "a": [1, 2]}})


def test_missing_config_raises(tmp_path: Path) -> None:
    with pytest.raises(ValidationError):
        load_config(tmp_path / "nope.yaml")


def test_non_mapping_config_raises(tmp_path: Path) -> None:
    f = tmp_path / "list.yaml"
    f.write_text("- a\n- b\n", encoding="utf-8")
    with pytest.raises(ValidationError):
        load_config(f)
