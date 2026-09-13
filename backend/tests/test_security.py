"""TC-SEC-001…003: upload path traversal, a PNG renamed to ``.xtf`` and an oversized stream; the
server binds to localhost by default."""

from __future__ import annotations

import inspect
import json
from pathlib import Path
from typing import Any

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("httpx")
pytest.importorskip("sqlalchemy")
pytest.importorskip("pyxtf")
pytest.importorskip("scipy")
pytest.importorskip("cv2")

from fastapi.testclient import TestClient  # noqa: E402
from tools.make_synthetic_xtf import write_synthetic_xtf  # noqa: E402

from sonarsentinel.api import surveys as surveys_api  # noqa: E402
from sonarsentinel.api.main import API_PREFIX, create_app  # noqa: E402
from sonarsentinel.api.mock import placeholder_png  # noqa: E402
from sonarsentinel.config import load_config  # noqa: E402

OPTIONS: dict[str, Any] = {"detector_model": "classical", "anomaly_scan": False}


@pytest.fixture(scope="module")
def xtf_bytes(tmp_path_factory: pytest.TempPathFactory) -> bytes:
    path = tmp_path_factory.mktemp("security") / "line.xtf"
    survey = write_synthetic_xtf(
        path,
        n_pings=80,
        samples_per_side=300,
        step_m=0.1,
        targets=[(40, "starboard", 150)],
        target_extent=(12, 30),
    )
    return Path(survey.path).read_bytes()


@pytest.fixture
def config(monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    monkeypatch.delenv("SS_MAX_UPLOAD_GB", raising=False)
    return load_config()


def _upload(client: TestClient, name: str, content: bytes) -> Any:
    return client.post(
        f"{API_PREFIX}/surveys",
        files=[("files", (name, content, "application/octet-stream"))],
        data={"options": json.dumps(OPTIONS)},
    )


def _files(root: Path) -> list[Path]:
    return [p for p in root.rglob("*") if p.is_file()] if root.exists() else []


def test_sec_001_traversal_names_stay_in_the_survey_upload_folder(
    tmp_path: Path, config: dict[str, Any], xtf_bytes: bytes
) -> None:
    data = tmp_path / "server" / "data"
    survey_ids = []
    with TestClient(create_app(config, data_dir=data)) as client:
        for name in ("../../evil.xtf", "..\\..\\evil.xtf"):
            response = _upload(client, name, xtf_bytes)
            assert response.status_code == 202, response.text
            body = response.json()
            survey_ids.append(body["survey_id"])
            client.post(f"{API_PREFIX}/jobs/{body['job_id']}/cancel")  # the content is irrelevant
            stored = _files(data / "uploads" / body["survey_id"])
            assert [p.name for p in stored] == ["evil.xtf"]

    evil = sorted(tmp_path.rglob("*evil*"))
    expected = sorted(data / "uploads" / sid / "evil.xtf" for sid in survey_ids)
    assert evil == expected
    assert not (data / "evil.xtf").exists() and not (tmp_path / "server" / "evil.xtf").exists()


def test_sec_002_png_named_xtf_is_rejected(tmp_path: Path, config: dict[str, Any]) -> None:
    png = placeholder_png(32)
    with TestClient(create_app(config, data_dir=tmp_path / "data")) as client:
        upload = _upload(client, "line_07.xtf", png)
        check = client.post(
            f"{API_PREFIX}/surveys/validate",
            files=[("files", ("line_07.xtf", png, "application/octet-stream"))],
        )
    # The extension is allowed, so the magic-byte check answers: 422 CORRUPT_HEADER (not 415).
    assert upload.status_code == 422, upload.text
    assert upload.json()["error"]["code"] == "CORRUPT_HEADER"
    result = check.json()["files"][0]
    assert not result["valid"] and result["error"]["code"] == "CORRUPT_HEADER"
    assert _files(tmp_path / "data" / "uploads") == []


def test_sec_003_oversized_stream_is_refused_without_writing_it(
    tmp_path: Path, config: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    config["ingest"]["max_upload_gb"] = 0.00001
    limit = int(0.00001 * 1024**3)  # 10 737 bytes
    size = 2 * 1024 * 1024
    written: list[int] = []

    class CountingHandle:
        def __init__(self, handle: Any) -> None:
            self.handle = handle

        def write(self, chunk: bytes) -> int:
            written.append(len(chunk))
            return int(self.handle.write(chunk))

        def close(self) -> None:
            self.handle.close()

    original = surveys_api._FormReader._headers_finished

    def counting_headers_finished(self: Any) -> None:
        original(self)
        if self._handle is not None:
            self._handle = CountingHandle(self._handle)

    monkeypatch.setattr(surveys_api._FormReader, "_headers_finished", counting_headers_finished)
    with TestClient(create_app(config, data_dir=tmp_path / "data")) as client:
        response = _upload(client, "huge.xtf", b"\x7b" + bytes(size - 1))

    assert response.status_code == 413, response.text
    assert response.json()["error"]["code"] == "FILE_TOO_LARGE"
    assert sum(written) <= limit < size  # writing stops at the limit (TestClient sends one chunk)
    assert _files(tmp_path / "data" / "uploads") == []


def test_serve_binds_localhost_by_default() -> None:
    pytest.importorskip("typer")
    from sonarsentinel import cli

    assert inspect.signature(cli.serve).parameters["host"].default == "127.0.0.1"
