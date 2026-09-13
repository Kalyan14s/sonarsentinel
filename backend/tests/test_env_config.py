"""ADR-019: ``SS_*`` environment variables (07-deployment §6) and the data-folder precedence."""

from __future__ import annotations

import copy
import logging
from pathlib import Path
from typing import Any

import pytest
import yaml

from sonarsentinel.config import DEFAULT_CONFIG_PATH, DEFAULT_JOB_TIMEOUT_S, apply_env, load_config
from sonarsentinel.errors import ValidationError

SS_VARS = (
    "SS_CONFIG",
    "SS_DATA_DIR",
    "SONARSENTINEL_DATA_DIR",
    "SS_MODELS_DIR",
    "SS_RUNTIME",
    "SS_MAX_UPLOAD_GB",
    "SS_OFFLINE_TILES",
    "SS_KEEP_WORK_FILES",
    "SS_LOG_LEVEL",
    "SS_WORKERS",
    "SS_JOB_TIMEOUT_S",
)


@pytest.fixture(autouse=True)
def clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in SS_VARS:
        monkeypatch.delenv(name, raising=False)


def _file_config() -> dict[str, Any]:
    data: dict[str, Any] = yaml.safe_load(DEFAULT_CONFIG_PATH.read_text(encoding="utf-8"))
    return data


def _write_yaml(tmp_path: Path, data: dict[str, Any]) -> Path:
    path = tmp_path / "pipeline.yaml"
    path.write_text(yaml.safe_dump(data), encoding="utf-8")
    return path


def test_no_variables_keeps_the_file() -> None:
    assert load_config() == _file_config()


def test_ss_config_sets_the_default_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    path = _write_yaml(tmp_path, {"pipeline_version": "9.9.9"})
    monkeypatch.setenv("SS_CONFIG", str(path))
    assert load_config()["pipeline_version"] == "9.9.9"
    assert load_config(DEFAULT_CONFIG_PATH)["pipeline_version"] != "9.9.9"  # argument wins
    monkeypatch.setenv("SS_CONFIG", str(tmp_path / "missing.yaml"))
    with pytest.raises(ValidationError):
        load_config()


def test_variables_override_the_config(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    models = tmp_path / "models"
    calibrator = str((tmp_path / "elsewhere" / "calibrator.pkl").resolve())
    path = _write_yaml(
        tmp_path,
        {
            "detection": {"model": "models/detector/yolo11s-seg/0.3.0/best.pt", "runtime": "auto"},
            "anomaly": {"model": "anomaly/patchcore"},
            "scoring": {"fp_filter_model": None, "calibrator": calibrator},
            "ingest": {"max_upload_gb": 2},
        },
    )
    values = {
        "SS_MODELS_DIR": str(models),
        "SS_RUNTIME": "ONNXRuntime",
        "SS_MAX_UPLOAD_GB": "0.5",
        "SS_OFFLINE_TILES": str(tmp_path / "world.mbtiles"),
        "SS_KEEP_WORK_FILES": "true",
        "SS_LOG_LEVEL": "debug",
        "SS_WORKERS": "1",
        "SS_JOB_TIMEOUT_S": "90",
    }
    for name, value in values.items():
        monkeypatch.setenv(name, value)
    cfg = load_config(path)

    assert (
        Path(cfg["detection"]["model"]) == models / "detector" / "yolo11s-seg" / "0.3.0" / "best.pt"
    )
    assert Path(cfg["anomaly"]["model"]) == models / "anomaly" / "patchcore"
    assert cfg["scoring"] == {"fp_filter_model": None, "calibrator": calibrator}  # absolute kept
    assert cfg["detection"]["runtime"] == "onnxruntime"
    assert cfg["ingest"]["max_upload_gb"] == 0.5
    assert cfg["api"] == {
        "offline_tiles": str(tmp_path / "world.mbtiles"),
        "keep_work_files": True,
        "log_level": "DEBUG",
        "workers": 1,
    }
    assert cfg["jobs"] == {"max_job_seconds": 90.0}
    assert apply_env(copy.deepcopy(cfg)) == cfg  # applying twice changes nothing

    monkeypatch.setenv("SS_KEEP_WORK_FILES", "0")
    assert load_config(path)["api"]["keep_work_files"] is False


@pytest.mark.parametrize(
    ("name", "value"),
    [
        ("SS_RUNTIME", "openvino"),
        ("SS_RUNTIME", "gpu"),
        ("SS_MAX_UPLOAD_GB", "lots"),
        ("SS_MAX_UPLOAD_GB", "0"),
        ("SS_KEEP_WORK_FILES", "maybe"),
        ("SS_LOG_LEVEL", "loud"),
        ("SS_WORKERS", "0"),
        ("SS_WORKERS", "1.5"),
        ("SS_JOB_TIMEOUT_S", "-5"),
    ],
)
def test_invalid_values_fail_at_startup(
    monkeypatch: pytest.MonkeyPatch, name: str, value: str
) -> None:
    monkeypatch.setenv(name, value)
    with pytest.raises(ValidationError) as info:
        load_config()
    assert info.value.details["field"] == name


def test_data_dir_precedence(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    pytest.importorskip("fastapi")
    from sonarsentinel.api.main import resolve_data_dir

    assert resolve_data_dir().parts[-2:] == ("data", "api")
    monkeypatch.setenv("SONARSENTINEL_DATA_DIR", str(tmp_path / "legacy"))
    assert resolve_data_dir() == tmp_path / "legacy"
    monkeypatch.setenv("SS_DATA_DIR", str(tmp_path / "ss"))
    assert resolve_data_dir() == tmp_path / "ss"
    assert resolve_data_dir(tmp_path / "explicit") == tmp_path / "explicit"


def test_create_app_applies_the_environment(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    pytest.importorskip("fastapi")
    pytest.importorskip("sqlalchemy")
    from sonarsentinel.api.main import create_app

    monkeypatch.setenv("SS_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("SS_MAX_UPLOAD_GB", "0.25")
    monkeypatch.setenv("SS_OFFLINE_TILES", str(tmp_path / "tiles.mbtiles"))
    monkeypatch.setenv("SS_WORKERS", "4")
    monkeypatch.setenv("SS_LOG_LEVEL", "WARNING")
    config = _file_config()
    package_logger = logging.getLogger("sonarsentinel")
    previous = package_logger.level
    try:
        with caplog.at_level(logging.WARNING, logger="sonarsentinel.api.main"):
            app = create_app(config)
        assert package_logger.level == logging.WARNING
    finally:
        package_logger.setLevel(previous)

    assert app.state.config["ingest"]["max_upload_gb"] == 0.25
    assert config == _file_config()  # the caller's mapping is not changed
    assert app.state.data_dir == tmp_path / "data"
    assert app.state.offline_tiles == tmp_path / "tiles.mbtiles"
    assert "SS_WORKERS=4" in caplog.text


def test_job_timeout_and_work_files_settings(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    pytest.importorskip("sqlalchemy")
    from sonarsentinel.jobs.manager import JobManager
    from sonarsentinel.storage.db import Database

    database = Database(tmp_path / "jobs.db")
    try:
        default = JobManager(database, load_config(), tmp_path)
        assert default.job_timeout_s == DEFAULT_JOB_TIMEOUT_S == 3600
        assert default.keep_work_files is False
        monkeypatch.setenv("SS_JOB_TIMEOUT_S", "12.5")
        monkeypatch.setenv("SS_KEEP_WORK_FILES", "yes")
        manager = JobManager(database, load_config(), tmp_path)
        assert manager.job_timeout_s == 12.5 and manager.keep_work_files is True
    finally:
        database.dispose()
