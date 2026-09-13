"""Sonar geometry to WGS84 positions (ST-031).

A processed chunk is a ground-range image: rows map to original pings through ``row_to_ping``,
the nadir line is column ``nadir_col``, starboard is to the right and port to the left, and each
pixel is ``ground_res_m`` metres. See ``docs/architecture/04-geotagging-engine.md`` §2.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Literal

import numpy as np
import numpy.typing as npt
from pyproj import Geod

from sonarsentinel.errors import ValidationError

if TYPE_CHECKING:
    from sonarsentinel.ingest.models import SonarLog

FloatArray = npt.NDArray[np.float64]
Side = Literal["port", "starboard"]

GEOD: Any = Geod(ellps="WGS84")


def slant_to_ground_range(slant_range_m: npt.ArrayLike, altitude_m: npt.ArrayLike) -> FloatArray:
    """Horizontal ground range from slant range and sonar altitude: ``sqrt(max(s² − h², 0))``."""
    s = np.asarray(slant_range_m, dtype=np.float64)
    h = np.asarray(altitude_m, dtype=np.float64)
    return np.asarray(np.sqrt(np.maximum(s**2 - h**2, 0.0)), dtype=np.float64)


def side_bearing_deg(heading_deg: npt.ArrayLike, side: Side | npt.ArrayLike) -> FloatArray:
    """Bearing from the sonar towards a seabed point on the given side (heading ± 90°)."""
    heading = np.asarray(heading_deg, dtype=np.float64)
    sides = np.asarray(side)
    offset = np.where(sides == "starboard", 90.0, -90.0)
    return np.asarray(np.mod(heading + offset, 360.0), dtype=np.float64)


def offset_position(
    lat: float, lon: float, heading_deg: float, side: Side, ground_range_m: float
) -> tuple[float, float]:
    """Position of a seabed point ``ground_range_m`` to the side of the sonar.

    Returns:
        ``(lat, lon)`` in decimal degrees (WGS84).
    """
    if ground_range_m < 0:
        raise ValidationError("ground_range_m must be >= 0", ground_range_m=ground_range_m)
    bearing = float(side_bearing_deg(heading_deg, side))
    lon2, lat2, _ = GEOD.fwd(lon, lat, bearing, ground_range_m)
    return float(lat2), float(lon2)


@dataclass(frozen=True)
class GeoFrame:
    """Navigation and image geometry needed to georeference a ground-range chunk.

    Attributes:
        lat: Sonar latitude per original ping (degrees).
        lon: Sonar longitude per original ping (degrees).
        heading_deg: Sonar heading per original ping (degrees true).
        row_to_ping: Original ping index for each image row.
        nadir_col: Column of the nadir line.
        ground_res_m: Across-track size of one pixel in metres.
    """

    lat: FloatArray
    lon: FloatArray
    heading_deg: FloatArray
    row_to_ping: npt.NDArray[np.int64]
    nadir_col: int
    ground_res_m: float

    def __post_init__(self) -> None:
        n = len(self.lat)
        if not (len(self.lon) == len(self.heading_deg) == n):
            raise ValidationError("lat, lon and heading_deg must have the same length")
        if self.ground_res_m <= 0:
            raise ValidationError("ground_res_m must be > 0", ground_res_m=self.ground_res_m)
        if self.nadir_col < 0:
            raise ValidationError("nadir_col must be >= 0", nadir_col=self.nadir_col)
        if len(self.row_to_ping) and (self.row_to_ping.min() < 0 or self.row_to_ping.max() >= n):
            raise ValidationError("row_to_ping refers to pings outside the navigation table")


def pixels_to_latlon(
    rows: npt.ArrayLike, cols: npt.ArrayLike, frame: GeoFrame
) -> tuple[FloatArray, FloatArray]:
    """Vectorised pixel → WGS84 conversion.

    Returns:
        ``(lat, lon)`` arrays with the shape of ``rows``.
    """
    r = np.asarray(rows, dtype=np.int64)
    c = np.asarray(cols, dtype=np.int64)
    if r.shape != c.shape:
        raise ValidationError("rows and cols must have the same shape")
    if r.size and (r.min() < 0 or r.max() >= len(frame.row_to_ping)):
        raise ValidationError("row index out of range", rows=int(len(frame.row_to_ping)))
    ping = frame.row_to_ping[r]
    offset = c - frame.nadir_col
    side = np.where(offset >= 0, "starboard", "port")
    bearing = side_bearing_deg(frame.heading_deg[ping], side)
    distance = np.abs(offset).astype(np.float64) * frame.ground_res_m
    lon2, lat2, _ = GEOD.fwd(frame.lon[ping], frame.lat[ping], bearing, distance)
    return np.asarray(lat2, dtype=np.float64), np.asarray(lon2, dtype=np.float64)


def pixel_to_latlon(row: int, col: int, frame: GeoFrame) -> tuple[float, float]:
    """Convert one pixel of a processed chunk to WGS84 ``(lat, lon)``."""
    lat, lon = pixels_to_latlon(np.array([row]), np.array([col]), frame)
    return float(lat[0]), float(lon[0])


def slant_samples_to_latlon(
    pings: npt.ArrayLike,
    sides: npt.ArrayLike,
    samples: npt.ArrayLike,
    log: SonarLog,
) -> tuple[FloatArray, FloatArray]:
    """Raw across-track samples of a waterfall log → WGS84 (unprocessed images, §2.1).

    ``slant = sample / samples_per_channel × slant_range_m`` and ``ground = sqrt(slant² − alt²)``
    unless the log is already ground-range corrected. Missing altitude is treated as 0; pings
    without navigation give NaN.

    Args:
        pings: Ping (row) indices into ``log.nav``.
        sides: ``"port"`` or ``"starboard"`` per sample.
        samples: Sample index from nadir (0 = nadir).
        log: The sonar log the samples come from.
    """
    p = np.asarray(pings, dtype=np.int64)
    s = np.asarray(samples, dtype=np.float64)
    sd = np.broadcast_to(np.asarray(sides), p.shape)
    if p.shape != s.shape:
        raise ValidationError("pings and samples must have the same shape")
    if p.size and (p.min() < 0 or p.max() >= log.n_pings):
        raise ValidationError("ping index out of range", n_pings=log.n_pings)
    nav = log.nav
    slant = s / log.sonar.samples_per_channel * nav["slant_range_m"].to_numpy(np.float64)[p]
    if log.ground_range_corrected:
        ground = slant
    else:
        altitude = np.nan_to_num(nav["altitude_m"].to_numpy(np.float64)[p], nan=0.0)
        ground = slant_to_ground_range(slant, altitude)
    bearing = side_bearing_deg(nav["heading_deg"].to_numpy(np.float64)[p], sd)
    lon2, lat2, _ = GEOD.fwd(
        nav["lon"].to_numpy(np.float64)[p], nav["lat"].to_numpy(np.float64)[p], bearing, ground
    )
    return np.asarray(lat2, dtype=np.float64), np.asarray(lon2, dtype=np.float64)


def raster_pixels_to_latlon(
    rows: npt.ArrayLike,
    cols: npt.ArrayLike,
    geotransform: tuple[float, float, float, float, float, float],
    crs: str,
) -> tuple[FloatArray, FloatArray]:
    """Pixel centres of a georeferenced raster (GeoTIFF) → WGS84 ``(lat, lon)``.

    Args:
        rows: Pixel rows.
        cols: Pixel columns.
        geotransform: GDAL-order geotransform ``(x0, dx, rx, y0, ry, dy)``.
        crs: CRS of the raster, e.g. ``"EPSG:32644"``.
    """
    from pyproj import Transformer

    r = np.asarray(rows, dtype=np.float64) + 0.5
    c = np.asarray(cols, dtype=np.float64) + 0.5
    if r.shape != c.shape:
        raise ValidationError("rows and cols must have the same shape")
    x0, dx, rx, y0, ry, dy = geotransform
    x = x0 + c * dx + r * rx
    y = y0 + c * ry + r * dy
    transformer: Any = Transformer.from_crs(crs, "EPSG:4326", always_xy=True)
    lon, lat = transformer.transform(x, y)
    return np.asarray(lat, dtype=np.float64), np.asarray(lon, dtype=np.float64)
