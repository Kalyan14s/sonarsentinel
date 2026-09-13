"""Upload validation (pipeline stage S0): extension, size and magic-byte checks.

See ``docs/architecture/02-data-pipeline.md`` (S0 · Validate).
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from sonarsentinel.errors import CorruptHeaderError, FileTooLargeError, UnsupportedFormatError

SourceFormat = Literal["xtf", "geotiff", "png", "jpeg", "csv"]

#: First byte of an XTF file header (``FileFormat`` field) is always 123 (0x7B).
XTF_FILE_FORMAT_BYTE = 0x7B

_EXTENSIONS: dict[str, SourceFormat] = {
    ".xtf": "xtf",
    ".tif": "geotiff",
    ".tiff": "geotiff",
    ".png": "png",
    ".jpg": "jpeg",
    ".jpeg": "jpeg",
    ".csv": "csv",
}
_TIFF_MAGIC = (b"II*\x00", b"MM\x00*", b"II+\x00", b"MM\x00+")  # classic TIFF and BigTIFF
_PNG_MAGIC = b"\x89PNG\r\n\x1a\n"
_JPEG_MAGIC = b"\xff\xd8\xff"


@dataclass(frozen=True)
class FileCheck:
    """Result of a successful file check."""

    path: Path
    source_format: SourceFormat
    size_bytes: int


def check_file(path: str | Path, max_bytes: int) -> FileCheck:
    """Validate an uploaded file by extension, size and header bytes.

    Args:
        path: File to check.
        max_bytes: Maximum allowed size in bytes.

    Returns:
        The detected format and size.

    Raises:
        UnsupportedFormatError: Extension is not supported.
        FileTooLargeError: File is larger than ``max_bytes``.
        CorruptHeaderError: Content doesn't match the format implied by the extension.
    """
    p = Path(path)
    ext = p.suffix.lower()
    fmt = _EXTENSIONS.get(ext)
    if fmt is None:
        raise UnsupportedFormatError(
            f"File type {ext or '(none)'} is not supported", filename=p.name
        )
    size = p.stat().st_size
    if size > max_bytes:
        raise FileTooLargeError(
            f"{p.name} is {size} bytes; the limit is {max_bytes} bytes",
            filename=p.name,
            size_bytes=size,
            max_bytes=max_bytes,
        )
    with p.open("rb") as fh:
        head = fh.read(8)
    if not _magic_matches(fmt, head):
        raise CorruptHeaderError(f"{p.name} does not look like a valid {fmt} file", filename=p.name)
    return FileCheck(path=p, source_format=fmt, size_bytes=size)


def _magic_matches(fmt: SourceFormat, head: bytes) -> bool:
    if fmt == "xtf":
        return len(head) >= 1 and head[0] == XTF_FILE_FORMAT_BYTE
    if fmt == "geotiff":
        return head[:4] in _TIFF_MAGIC
    if fmt == "png":
        return head == _PNG_MAGIC
    if fmt == "jpeg":
        return head[:3] == _JPEG_MAGIC
    return b"\x00" not in head  # csv: plain text, no NUL bytes
