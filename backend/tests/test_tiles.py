"""ST-099: offline MBTiles basemap tiles; health ``offline_tiles`` and ``runtime`` (ADR-019)."""

from __future__ import annotations

import sqlite3
from contextlib import closing
from pathlib import Path
from typing import Any

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("httpx")
pytest.importorskip("sqlalchemy")

from fastapi.testclient import TestClient  # noqa: E402

from sonarsentinel.api import system  # noqa: E402
from sonarsentinel.api.main import API_PREFIX, create_app  # noqa: E402
from sonarsentinel.api.mock import create_mock_app, placeholder_png  # noqa: E402
from sonarsentinel.config import load_config  # noqa: E402

TILE_A = placeholder_png(4, 10)
TILE_B = placeholder_png(4, 200)


@pytest.fixture(autouse=True)
def no_tiles_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("SS_OFFLINE_TILES", raising=False)


@pytest.fixture
def config() -> dict[str, Any]:
    return load_config()


@pytest.fixture
def mbtiles(tmp_path: Path) -> Path:
    path = tmp_path / "harbour.mbtiles"
    with closing(sqlite3.connect(path)) as conn, conn:
        conn.execute("CREATE TABLE metadata (name TEXT, value TEXT)")
        conn.execute(
            "CREATE TABLE tiles (zoom_level INTEGER, tile_column INTEGER, tile_row INTEGER, "
            "tile_data BLOB)"
        )
        conn.executemany(
            "INSERT INTO metadata VALUES (?, ?)", [("name", "harbour"), ("format", "png")]
        )
        # TMS rows: XYZ 1/0/0 is row 2^1 - 1 - 0 = 1, XYZ 2/1/2 is row 2^2 - 1 - 2 = 1.
        conn.executemany(
            "INSERT INTO tiles VALUES (?, ?, ?, ?)", [(1, 0, 1, TILE_A), (2, 1, 1, TILE_B)]
        )
    return path


def _app(config: dict[str, Any], tmp_path: Path, **kwargs: Any) -> TestClient:
    return TestClient(create_app(config, data_dir=tmp_path / "data", **kwargs))


def test_tiles_are_served_with_the_tms_row_flip(
    config: dict[str, Any], tmp_path: Path, mbtiles: Path
) -> None:
    with _app(config, tmp_path, offline_tiles=mbtiles) as client:
        first = client.get(f"{API_PREFIX}/tiles/1/0/0.png")
        assert first.status_code == 200 and first.content == TILE_A
        assert first.headers["content-type"] == "image/png"
        assert first.headers["cache-control"] == "max-age=86400"
        assert client.get(f"{API_PREFIX}/tiles/2/1/2.png").content == TILE_B
        for missing in ("1/0/1", "2/1/1", "1/5/0", "30/0/0"):
            response = client.get(f"{API_PREFIX}/tiles/{missing}.png")
            assert response.status_code == 404 and response.json()["error"]["code"] == "NOT_FOUND"

        assert client.get(f"{API_PREFIX}/health").json()["offline_tiles"] is True
        settings = client.get(f"{API_PREFIX}/settings").json()
        assert settings["system"]["offline_tiles_available"] is True
        offline = client.put(f"{API_PREFIX}/settings", json={"map": {"basemap": "offline"}})
        assert offline.status_code == 200 and offline.json()["map"]["basemap"] == "offline"


def test_missing_or_unreadable_tiles(
    config: dict[str, Any], tmp_path: Path, mbtiles: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    broken = tmp_path / "broken.mbtiles"
    broken.write_bytes(b"not a database")
    for path in (None, tmp_path / "missing.mbtiles", broken):
        client = _app(config, tmp_path, offline_tiles=path)
        response = client.get(f"{API_PREFIX}/tiles/1/0/0.png")
        assert response.status_code == 404 and response.json()["error"]["code"] == "NOT_FOUND"
        assert client.get(f"{API_PREFIX}/health").json()["offline_tiles"] is False

    monkeypatch.setenv("SS_OFFLINE_TILES", str(mbtiles))
    assert _app(config, tmp_path).get(f"{API_PREFIX}/tiles/1/0/0.png").content == TILE_A

    mock = TestClient(create_mock_app(event_delay_s=0.0))
    assert mock.get(f"{API_PREFIX}/tiles/1/0/0.png").status_code == 404


def test_health_runtime_is_what_the_detector_would_use(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    weights = tmp_path / "best.pt"
    config: dict[str, Any] = {"detection": {"model": str(weights), "runtime": "auto"}}
    installed = {"ultralytics", "onnxruntime"}
    monkeypatch.setattr(system, "importable", lambda name: name in installed)
    cpu = {"available": False, "name": None}
    gpu = {"available": True, "name": "test GPU"}

    assert system.detector_runtime(config, gpu) == "classical"  # no trained weights
    weights.write_bytes(b"pt")
    assert system.detector_runtime(config, cpu) == "torch"
    weights.with_suffix(".onnx").write_bytes(b"onnx")
    assert system.detector_runtime(config, cpu) == "onnxruntime"
    assert system.detector_runtime(config, gpu) == "cuda"
    config["detection"]["runtime"] = "torch"
    assert system.detector_runtime(config, gpu) == "torch"
    config["detection"]["runtime"] = "cuda"
    installed.discard("onnxruntime")
    assert system.detector_runtime(config, cpu) == "torch"  # CPU fallback
    installed.discard("ultralytics")
    assert system.detector_runtime(config, gpu) == "classical"
