import hashlib
import importlib.util
import json
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "fetch_test_data.py"
_spec = importlib.util.spec_from_file_location("fetch_test_data", SCRIPT)
assert _spec is not None and _spec.loader is not None
fetch = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(fetch)


def _manifest(tmp_path: Path, source: Path, sha256: str | None) -> Path:
    manifest = tmp_path / "manifest.json"
    entry = {
        "name": "fixture",
        "url": source.as_uri(),
        "dest": "data/test/fixture.bin",
        "sha256": sha256,
    }
    manifest.write_text(json.dumps({"files": [entry]}), encoding="utf-8")
    return manifest


@pytest.fixture
def source(tmp_path: Path) -> Path:
    src = tmp_path / "source.bin"
    src.write_bytes(b"sonar-fixture-bytes")
    return src


def test_empty_manifest_is_ok(tmp_path: Path) -> None:
    manifest = tmp_path / "manifest.json"
    manifest.write_text('{"files": []}', encoding="utf-8")
    assert fetch.main(["--manifest", str(manifest), "--root", str(tmp_path)]) == 0


def test_unpinned_entry_requires_accept_new(tmp_path: Path, source: Path) -> None:
    manifest = _manifest(tmp_path, source, sha256=None)
    args = ["--manifest", str(manifest), "--root", str(tmp_path)]
    assert fetch.main(args) == 1
    assert fetch.main([*args, "--accept-new"]) == 0
    assert (tmp_path / "data/test/fixture.bin").read_bytes() == source.read_bytes()


def test_pinned_entry_downloads_then_skips(
    tmp_path: Path, source: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    digest = hashlib.sha256(source.read_bytes()).hexdigest()
    manifest = _manifest(tmp_path, source, sha256=digest)
    args = ["--manifest", str(manifest), "--root", str(tmp_path)]
    assert fetch.main(args) == 0
    assert fetch.main(args) == 0
    assert "[skip] fixture" in capsys.readouterr().out


def test_checksum_mismatch_fails_and_removes_file(tmp_path: Path, source: Path) -> None:
    manifest = _manifest(tmp_path, source, sha256="0" * 64)
    assert fetch.main(["--manifest", str(manifest), "--root", str(tmp_path)]) == 1
    assert not (tmp_path / "data/test/fixture.bin").exists()
