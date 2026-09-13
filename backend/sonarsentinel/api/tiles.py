"""Offline basemap tiles (ST-099, ADR-019): ``GET /tiles/{z}/{x}/{y}.png`` from an MBTiles file.

MBTiles is a SQLite database that stores rows in the TMS scheme, so the XYZ ``y`` of Leaflet maps
to ``tile_row = 2^z − 1 − y``. The file comes from ``create_app(offline_tiles=…)`` or
``SS_OFFLINE_TILES``. Tiles must be rendered in-house: the OpenStreetMap tile policy forbids bulk
downloads for offline use.
"""

from __future__ import annotations

import sqlite3
from contextlib import closing
from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import Response

from sonarsentinel.errors import NotFoundError

router = APIRouter()

CACHE_CONTROL = "max-age=86400"
MAX_ZOOM = 24


def _connect(path: Path) -> sqlite3.Connection:
    return sqlite3.connect(f"{path.resolve().as_uri()}?mode=ro", uri=True)


def tiles_readable(path: Path | None) -> bool:
    """True when ``path`` is an MBTiles file with a readable ``tiles`` table."""
    if path is None or not path.is_file():
        return False
    try:
        with closing(_connect(path)) as conn:
            conn.execute("SELECT 1 FROM tiles LIMIT 1").fetchall()
    except sqlite3.Error:
        return False
    return True


def read_tile(path: Path, z: int, x: int, y: int) -> bytes | None:
    """Tile bytes for XYZ coordinates, or ``None`` when out of range or not in the file."""
    if not 0 <= z <= MAX_ZOOM:
        return None
    size = 1 << z
    if not (0 <= x < size and 0 <= y < size):
        return None
    with closing(_connect(path)) as conn:
        row = conn.execute(
            "SELECT tile_data FROM tiles WHERE zoom_level = ? AND tile_column = ? AND tile_row = ?",
            (z, x, size - 1 - y),
        ).fetchone()
    return bytes(row[0]) if row is not None else None


@router.get(
    "/tiles/{z}/{x}/{y}.png",
    tags=["system"],
    summary="Offline basemap tile from the configured MBTiles file",
    response_class=Response,
)
def get_tile(z: int, x: int, y: int, request: Request) -> Response:
    path: Path | None = getattr(request.app.state, "offline_tiles", None)
    if path is None or not tiles_readable(path):
        raise NotFoundError("Offline tiles are not configured (SS_OFFLINE_TILES)", z=z, x=x, y=y)
    try:
        data = read_tile(path, z, x, y)
    except sqlite3.Error as exc:
        raise NotFoundError("Offline tiles could not be read", z=z, x=x, y=y) from exc
    if data is None:
        raise NotFoundError(f"No tile {z}/{x}/{y}", z=z, x=x, y=y)
    return Response(data, media_type="image/png", headers={"Cache-Control": CACHE_CONTROL})
