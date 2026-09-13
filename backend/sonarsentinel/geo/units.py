"""Coordinate units and CRS handling (ST-030).

See ``docs/architecture/04-geotagging-engine.md`` §3.
"""

from __future__ import annotations

from typing import Any

import numpy as np
import numpy.typing as npt
from pyproj import CRS, Transformer

from sonarsentinel.errors import CrsRequiredError, ValidationError

FloatArray = npt.NDArray[np.float64]

#: XTF file header ``NavUnits`` values.
XTF_NAV_UNITS_METERS = 0
XTF_NAV_UNITS_LATLON = 3


def looks_geographic(x: npt.ArrayLike, y: npt.ArrayLike) -> bool:
    """Return True if all valid coordinates fit longitude/latitude ranges.

    ``(0, 0)`` fixes and non-finite values are ignored; if nothing valid remains, returns False.
    """
    xs = np.asarray(x, dtype=np.float64)
    ys = np.asarray(y, dtype=np.float64)
    valid = np.isfinite(xs) & np.isfinite(ys) & ~((xs == 0) & (ys == 0))
    if not valid.any():
        return False
    return bool(np.all(np.abs(xs[valid]) <= 180.0) and np.all(np.abs(ys[valid]) <= 90.0))


def utm_epsg_for(lon: float, lat: float) -> int:
    """Return the WGS84 / UTM EPSG code (326xx north, 327xx south) for a position."""
    if not (-180.0 <= lon <= 180.0 and -80.0 <= lat <= 84.0):
        raise ValidationError("Position outside the UTM range", lon=lon, lat=lat)
    zone = min(int((lon + 180.0) // 6.0) + 1, 60)
    return (32600 if lat >= 0 else 32700) + zone


def _parse_crs(epsg: int | str) -> CRS:
    try:
        return CRS.from_user_input(f"EPSG:{epsg}" if isinstance(epsg, int) else epsg)
    except Exception as exc:  # pyproj raises CRSError subclasses
        raise ValidationError(f"Unknown CRS: {epsg}", crs=str(epsg)) from exc


def to_wgs84(
    x: npt.ArrayLike,
    y: npt.ArrayLike,
    *,
    nav_units: int | None = None,
    epsg: int | str | None = None,
) -> tuple[FloatArray, FloatArray]:
    """Convert navigation coordinates to WGS84 latitude/longitude.

    Args:
        x: Longitudes or eastings.
        y: Latitudes or northings.
        nav_units: XTF ``NavUnits`` header value if known (0 = metres, 3 = lat/lon).
        epsg: CRS of projected coordinates, e.g. ``32644`` or ``"EPSG:32644"``; ``"auto"`` or
            ``None`` means unknown.

    Returns:
        ``(lat, lon)`` arrays in decimal degrees.

    Raises:
        CrsRequiredError: Coordinates are projected but no CRS was given.
        ValidationError: The CRS is unknown or not projected.
    """
    xs = np.atleast_1d(np.asarray(x, dtype=np.float64))
    ys = np.atleast_1d(np.asarray(y, dtype=np.float64))
    if xs.shape != ys.shape:
        raise ValidationError(
            "x and y must have the same shape", x_shape=xs.shape, y_shape=ys.shape
        )

    if nav_units == XTF_NAV_UNITS_LATLON:
        geographic = True
    elif nav_units == XTF_NAV_UNITS_METERS:
        geographic = False
    else:
        geographic = looks_geographic(xs, ys)

    if geographic:
        return ys.copy(), xs.copy()

    if epsg is None or epsg == "auto":
        raise CrsRequiredError(
            "Projected coordinates found but no EPSG code is known; provide the UTM zone",
            hint="utm_epsg",
        )
    crs = _parse_crs(epsg)
    if not crs.is_projected:
        raise ValidationError("Coordinates look projected but the given CRS is not", crs=str(epsg))
    transformer: Any = Transformer.from_crs(crs, "EPSG:4326", always_xy=True)
    lon, lat = transformer.transform(xs, ys)
    return np.asarray(lat, dtype=np.float64), np.asarray(lon, dtype=np.float64)
