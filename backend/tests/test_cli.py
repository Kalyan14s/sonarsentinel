from pathlib import Path

from typer.testing import CliRunner

from sonarsentinel import __version__
from sonarsentinel.cli import app

runner = CliRunner()


def test_version_prints_package_version() -> None:
    result = runner.invoke(app, ["version"])
    assert result.exit_code == 0
    assert __version__ in result.output


def test_validate_reports_ok_and_failures(tmp_path: Path) -> None:
    good = tmp_path / "line_07.xtf"
    good.write_bytes(bytes([0x7B, 0x01]) + b"\x00" * 1022)
    bad = tmp_path / "scan.bmp"
    bad.write_bytes(b"BM\x00\x00")

    result = runner.invoke(app, ["validate", str(good), str(bad)])

    assert result.exit_code == 1
    assert "[ok] line_07.xtf: xtf, 1024 bytes" in result.output
    assert "[X] scan.bmp: UNSUPPORTED_FORMAT" in result.output


def test_validate_all_ok_exits_zero(tmp_path: Path) -> None:
    nav = tmp_path / "nav.csv"
    nav.write_text("ping,lat,lon\n0,13.08,80.31\n", encoding="utf-8")
    result = runner.invoke(app, ["validate", str(nav)])
    assert result.exit_code == 0


def test_config_command_prints_hash() -> None:
    result = runner.invoke(app, ["config"])
    assert result.exit_code == 0
    assert "pipeline_version: 0.2.0" in result.output
    assert "config_hash: sha256:" in result.output


def test_detect_is_a_placeholder(tmp_path: Path) -> None:
    result = runner.invoke(app, ["detect", str(tmp_path / "line.xtf")])
    assert result.exit_code == 2
