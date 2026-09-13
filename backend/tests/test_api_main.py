"""ST-080: API skeleton. TC-API-008 (health) and the error model shape (TC-API-003 part)."""

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("httpx")
from fastapi.testclient import TestClient  # noqa: E402

from sonarsentinel import __version__  # noqa: E402
from sonarsentinel.api.main import API_PREFIX, create_app  # noqa: E402
from sonarsentinel.errors import UnsupportedFormatError  # noqa: E402


@pytest.fixture(scope="module")
def client() -> TestClient:
    app = create_app()

    @app.get("/boom")
    def boom() -> None:
        raise UnsupportedFormatError("File type .bmp is not supported", filename="scan.bmp")

    return TestClient(app)


def test_health(client: TestClient) -> None:
    """TC-API-008: version, GPU, runtime and model status."""
    body = client.get(f"{API_PREFIX}/health").json()
    assert body["status"] == "ok" and body["version"] == __version__
    assert set(body["gpu"]) == {"available", "name"}
    assert body["runtime"] in ("cpu", "cuda") and isinstance(body["models_loaded"], bool)


def test_models(client: TestClient) -> None:
    body = client.get(f"{API_PREFIX}/models").json()
    ids = [m["id"] for m in body["items"]]
    assert "classical-bright-target@0.1.0" in ids and body["total"] == len(ids)


def test_openapi_lists_endpoints(client: TestClient) -> None:
    spec = client.get("/openapi.json").json()
    assert {f"{API_PREFIX}/health", f"{API_PREFIX}/models"} <= set(spec["paths"])
    assert client.get("/docs").status_code == 200


def test_error_model(client: TestClient) -> None:
    response = client.get("/boom")
    assert response.status_code == 415
    assert response.json() == {
        "error": {
            "code": "UNSUPPORTED_FORMAT",
            "message": "File type .bmp is not supported",
            "details": {"filename": "scan.bmp"},
        }
    }
