from pathlib import Path

import pytest

from sonarsentinel.errors import CorruptHeaderError, FileTooLargeError, UnsupportedFormatError
from sonarsentinel.ingest.validators import check_file

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 16


@pytest.mark.parametrize(
    ("name", "content", "expected"),
    [
        ("line.xtf", bytes([0x7B, 0x01, 0x00, 0x00]), "xtf"),
        ("mosaic.tif", b"II*\x00" + b"\x00" * 8, "geotiff"),
        ("mosaic.TIFF", b"MM\x00*" + b"\x00" * 8, "geotiff"),
        ("waterfall.png", PNG, "png"),
        ("waterfall.jpg", b"\xff\xd8\xff\xe0" + b"\x00" * 8, "jpeg"),
        ("nav.csv", b"ping,lat,lon\n", "csv"),
    ],
)
def test_supported_files_are_detected(
    tmp_path: Path, name: str, content: bytes, expected: str
) -> None:
    f = tmp_path / name
    f.write_bytes(content)
    result = check_file(f, max_bytes=1024)
    assert result.source_format == expected
    assert result.size_bytes == len(content)


def test_unsupported_extension_is_rejected(tmp_path: Path) -> None:
    f = tmp_path / "scan.bmp"
    f.write_bytes(b"BM")
    with pytest.raises(UnsupportedFormatError) as exc_info:
        check_file(f, max_bytes=1024)
    assert exc_info.value.to_dict()["error"] == {
        "code": "UNSUPPORTED_FORMAT",
        "message": "File type .bmp is not supported",
        "details": {"filename": "scan.bmp"},
    }


def test_spoofed_extension_is_rejected(tmp_path: Path) -> None:
    """TC-SEC-002: a PNG renamed to .xtf fails the header check."""
    f = tmp_path / "evil.xtf"
    f.write_bytes(PNG)
    with pytest.raises(CorruptHeaderError):
        check_file(f, max_bytes=1024)


def test_binary_csv_is_rejected(tmp_path: Path) -> None:
    f = tmp_path / "nav.csv"
    f.write_bytes(b"ping\x00lat")
    with pytest.raises(CorruptHeaderError):
        check_file(f, max_bytes=1024)


def test_oversize_file_is_rejected(tmp_path: Path) -> None:
    f = tmp_path / "big.xtf"
    f.write_bytes(bytes([0x7B]) + b"\x00" * 99)
    with pytest.raises(FileTooLargeError) as exc_info:
        check_file(f, max_bytes=50)
    assert exc_info.value.http_status == 413
    assert exc_info.value.details["size_bytes"] == 100
