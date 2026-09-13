"""ST-098: ``GET/PUT /settings`` — defaults, partial updates, validation, persistence and the
overlay on new jobs' configuration (ADR-019)."""

from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("httpx")
pytest.importorskip("sqlalchemy")
pytest.importorskip("scipy")
pytest.importorskip("cv2")

from fastapi.testclient import TestClient  # noqa: E402

from sonarsentinel.api.main import API_PREFIX, create_app  # noqa: E402
from sonarsentinel.api.mock import create_mock_app  # noqa: E402
from sonarsentinel.config import load_config  # noqa: E402
from sonarsentinel.jobs.manager import JobRequest  # noqa: E402
from sonarsentinel.settings import SETTINGS_FILENAME, detector_name  # noqa: E402

SECTIONS = {"detection", "anomaly", "tiers", "map", "processing", "geo", "system"}
CLASSICAL_ID = "classical-bright-target@0.1.0"
URL = f"{API_PREFIX}/settings"


@pytest.fixture(autouse=True)
def no_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in ("SS_OFFLINE_TILES", "SS_RUNTIME", "SS_MAX_UPLOAD_GB", "SS_KEEP_WORK_FILES"):
        monkeypatch.delenv(name, raising=False)


@pytest.fixture
def config() -> dict[str, Any]:
    return load_config()


@pytest.fixture
def client(tmp_path: Path, config: dict[str, Any]) -> Iterator[TestClient]:
    with TestClient(create_app(config, data_dir=tmp_path / "data")) as test_client:
        yield test_client


def test_defaults_come_from_the_config(
    client: TestClient, tmp_path: Path, config: dict[str, Any]
) -> None:
    body = client.get(URL).json()
    assert set(body) == SECTIONS
    detection = config["detection"]
    assert body["detection"] == {
        "model_id": "auto",
        "runtime": detection["runtime"],
        "min_raw_score": detection["min_raw_score"],
    }
    assert body["anomaly"] == {
        "enabled": config["anomaly"]["enabled"],
        "threshold": config["anomaly"]["threshold"],
    }
    assert body["tiers"] == {k: float(v) for k, v in config["scoring"]["tiers"].items()}
    assert body["map"] == {"min_conf_default": 30.0, "basemap": "online", "coordinates": "dd"}
    assert body["processing"] == {
        "ground_resolution_m": config["preprocess"]["ground_resolution_m"],
        "pings_per_chunk": config["chunking"]["pings_per_chunk"],
        "overlap_pings": config["chunking"]["overlap_pings"],
    }
    assert body["geo"] == {
        "apply_layback": config["navigation"]["apply_layback"],
        "cluster_radius_m": float(config["geo"]["cluster_radius_m"]),
    }
    system = body["system"]
    assert system["data_dir"] == str(tmp_path / "data")
    assert system["max_upload_gb"] == float(config["ingest"]["max_upload_gb"])
    assert system["keep_work_files"] is False and system["offline_tiles_available"] is False
    assert "auto" in system["runtimes_available"] and system["version"]
    assert not (tmp_path / "data" / SETTINGS_FILENAME).exists()


def test_partial_update_round_trip_and_restart(
    client: TestClient, tmp_path: Path, config: dict[str, Any]
) -> None:
    before = client.get(URL).json()
    update = {
        "tiers": {"hazard": 85},
        "map": {"coordinates": "dms"},
        "detection": {"model_id": CLASSICAL_ID},
        "system": {"data_dir": "ignored"},  # read-only
    }
    response = client.put(URL, json=update)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["tiers"] == before["tiers"] | {"hazard": 85.0}
    assert body["map"] == before["map"] | {"coordinates": "dms"}
    assert body["detection"] == before["detection"] | {"model_id": CLASSICAL_ID}
    assert body["processing"] == before["processing"] and body["system"] == before["system"]
    assert client.get(URL).json() == body

    saved = json.loads((tmp_path / "data" / SETTINGS_FILENAME).read_text("utf-8"))
    assert "system" not in saved and saved["tiers"]["hazard"] == 85.0
    with TestClient(create_app(config, data_dir=tmp_path / "data")) as restarted:
        assert restarted.get(URL).json() == body


@pytest.mark.parametrize(
    "update",
    [
        {"tiers": {"hazard": 40, "review": 50}},
        {"tiers": {"anomaly": 50}},
        {"tiers": {"hazard": 120}},
        {"anomaly": {"threshold": 1.5}},
        {"detection": {"min_raw_score": -0.1}},
        {"detection": {"runtime": "openvino"}},
        {"detection": {"model_id": "rcnn"}},
        {"processing": {"pings_per_chunk": 100, "overlap_pings": 100}},
        {"processing": {"pings_per_chunk": 0}},
        {"map": {"basemap": "offline"}},  # no MBTiles file configured
        {"map": {"coordinates": "utm"}},
        {"geo": {"apply_layback": "sometimes"}},
        {"colour": "red"},
        {"tiers": {"extreme": 95}},
        [],
    ],
)
def test_invalid_updates_are_rejected(client: TestClient, tmp_path: Path, update: Any) -> None:
    response = client.put(URL, json=update)
    assert response.status_code == 400, response.text
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"
    assert not (tmp_path / "data" / SETTINGS_FILENAME).exists()


def test_error_details_and_invalid_json(client: TestClient) -> None:
    unknown = client.put(URL, json={"tiers": {"extreme": 95}}).json()["error"]
    assert unknown["details"]["errors"][0]["field"] == "tiers.extreme"
    ordering = client.put(URL, json={"tiers": {"hazard": 40}}).json()["error"]
    assert "hazard > review > anomaly" in ordering["details"]["errors"][0]["message"]
    broken = client.put(URL, content=b"{not json", headers={"content-type": "application/json"})
    assert broken.status_code == 400 and broken.json()["error"]["code"] == "VALIDATION_ERROR"


def test_saved_settings_apply_to_new_jobs(tmp_path: Path, config: dict[str, Any]) -> None:
    """New jobs use the base config with the saved settings; upload options still win."""
    classical = {"detector_model": "classical", "anomaly_scan": False}
    with TestClient(create_app(config, data_dir=tmp_path / "data")) as client:
        jobs = client.app.state.context.jobs  # type: ignore[attr-defined]
        base = jobs.config
        request = JobRequest("JOB-00000001", "SRV-20260914-001", [], {"anomaly_scan": False})
        before, _ = jobs._prepare(JobRequest("JOB-00000000", "SRV-20260914-000", [], classical))
        update = {
            "tiers": {"hazard": 90, "review": 60, "anomaly": 40},
            "processing": {"pings_per_chunk": 500, "overlap_pings": 50, "ground_resolution_m": 0.2},
            "detection": {"model_id": CLASSICAL_ID, "min_raw_score": 0.3},
            "anomaly": {"threshold": 0.7},
            "geo": {"apply_layback": False, "cluster_radius_m": 8},
        }
        assert client.put(URL, json=update).status_code == 200
        after, kwargs = jobs._prepare(request)
        options = classical | {"ground_resolution_m": 0.05}
        upload, _ = jobs._prepare(JobRequest("JOB-00000002", "SRV-20260914-002", [], options))

    assert before["scoring"]["tiers"] == config["scoring"]["tiers"]
    assert after["scoring"]["tiers"] == {"hazard": 90.0, "review": 60.0, "anomaly": 40.0}
    assert (after["chunking"]["pings_per_chunk"], after["chunking"]["overlap_pings"]) == (500, 50)
    assert after["preprocess"]["ground_resolution_m"] == 0.2
    assert after["detection"]["min_raw_score"] == 0.3 and after["anomaly"]["threshold"] == 0.7
    assert after["navigation"]["apply_layback"] is False and after["geo"]["cluster_radius_m"] == 8.0
    assert type(kwargs["detector"]).__name__ == "BrightTargetDetector"  # model_id → classical
    assert upload["preprocess"]["ground_resolution_m"] == 0.05
    assert base["scoring"]["tiers"] == config["scoring"]["tiers"]  # the base config is unchanged


def test_model_id_maps_to_a_detector() -> None:
    assert detector_name("auto") == "auto"
    assert detector_name(CLASSICAL_ID) == "classical"
    assert detector_name("yolo:0.1.0") == "yolo"


def test_mock_settings_are_kept_in_memory() -> None:
    mock = TestClient(create_mock_app(event_delay_s=0.0))
    assert set(mock.get(URL).json()) == SECTIONS
    updated = mock.put(URL, json={"map": {"coordinates": "dms"}})
    assert updated.status_code == 200 and mock.get(URL).json()["map"]["coordinates"] == "dms"
    assert mock.put(URL, json={"tiers": {"hazard": 10}}).status_code == 400
    assert mock.put(URL, json={"map": {"basemap": "offline"}}).status_code == 400
