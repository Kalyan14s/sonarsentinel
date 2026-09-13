"""Object measurements, footprints and depth (ST-033, stage S10).

A detection mask in a processed ground-range image gives its centroid, minimum-area rectangle
(``cv2.minAreaRect``), length/width/area in metres, orientation of the long axis from true north
(0–180°), a clockwise 4-corner footprint in WGS84 and depth (sensor depth + altitude).
See ``docs/architecture/04-geotagging-engine.md`` §6.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
import numpy.typing as npt

from sonarsentinel.errors import ValidationError
from sonarsentinel.geo.georef import GeoFrame, pixels_to_latlon

FloatArray = npt.NDArray[np.float64]
IntArray = npt.NDArray[np.int64]


@dataclass(frozen=True)
class ImageGeometry:
    """What measuring needs to know about a processed chunk image.

    Attributes:
        ground_res_m: Pixel size in metres (across and along track).
        nadir_col: Column of the nadir line.
        row_to_ping: Local ping index (into the per-ping arrays below) for each image row.
        ping_offset: Global index of local ping 0.
        frame: Georeferencing frame, or ``None`` when the input is not geotagged.
        heading_deg: Heading per local ping (needed for orientation).
        sensor_depth_m: Sensor depth per local ping.
        altitude_m: Altitude per local ping.
    """

    ground_res_m: float
    nadir_col: int
    row_to_ping: IntArray
    ping_offset: int = 0
    frame: GeoFrame | None = None
    heading_deg: FloatArray | None = None
    sensor_depth_m: FloatArray | None = None
    altitude_m: FloatArray | None = None


@dataclass(frozen=True)
class Measurement:
    """Geometry of one detected object."""

    centroid_row: float
    centroid_col: float
    ping: int  # global ping at the centroid
    side: str  # "port" | "starboard"
    ground_range_m: float
    length_m: float
    width_m: float
    area_m2: float
    orientation_deg: float | None
    rect_corners_rc: tuple[tuple[float, float], ...]
    lat: float | None = None
    lon: float | None = None
    footprint: list[list[float]] | None = None  # 4 × [lat, lon], clockwise
    depth_m: float | None = None


def orientation_from_heading(d_col: float, d_row: float, heading_deg: float) -> float:
    """Long-axis direction ``(d_col, d_row)`` in the image → degrees from true north in [0, 180).

    Rows run forward along the track (the heading) and columns increase to starboard
    (heading + 90°), so the image vector's bearing is ``heading + atan2(d_col, d_row)``.
    """
    bearing = heading_deg + math.degrees(math.atan2(d_col, d_row))
    return bearing % 180.0


def order_clockwise(points: list[list[float]]) -> list[list[float]]:
    """Order ``[lat, lon]`` corners clockwise (as seen on a north-up map)."""
    lat0 = math.radians(sum(p[0] for p in points) / len(points))
    xy = [(p[1] * math.cos(lat0), p[0]) for p in points]
    cx = sum(x for x, _ in xy) / len(xy)
    cy = sum(y for _, y in xy) / len(xy)
    order = sorted(range(len(points)), key=lambda i: -math.atan2(xy[i][1] - cy, xy[i][0] - cx))
    return [points[i] for i in order]


def measure_mask(
    mask: npt.NDArray[np.bool_],
    geometry: ImageGeometry,
    *,
    row0: int = 0,
    col0: int = 0,
) -> Measurement:
    """Measure a boolean mask whose top-left pixel is at image ``(row0, col0)``.

    Raises:
        ValidationError: The mask is empty.
    """
    import cv2

    ys, xs = np.nonzero(np.asarray(mask, dtype=bool))
    if len(xs) == 0:
        raise ValidationError("Cannot measure an empty mask")
    rows = ys.astype(np.float64) + row0
    cols = xs.astype(np.float64) + col0
    cy, cx = float(rows.mean()), float(cols.mean())
    res = geometry.ground_res_m

    points = np.stack([cols, rows], axis=1).astype(np.float32)
    rect = cv2.minAreaRect(points)
    corners = cv2.boxPoints(rect)  # (col, row)
    side_a = corners[1] - corners[0]
    side_b = corners[2] - corners[1]
    len_a = float(np.hypot(*side_a)) + 1.0  # pixel centres → pixel extent
    len_b = float(np.hypot(*side_b)) + 1.0
    long_vec = side_a if len_a >= len_b else side_b

    n_rows = len(geometry.row_to_ping)
    r_idx = int(np.clip(round(cy), 0, n_rows - 1))
    local_ping = int(geometry.row_to_ping[r_idx])

    orientation = None
    if geometry.heading_deg is not None and np.isfinite(geometry.heading_deg[local_ping]):
        orientation = round(
            orientation_from_heading(
                float(long_vec[0]), float(long_vec[1]), float(geometry.heading_deg[local_ping])
            ),
            1,
        )

    lat = lon = None
    footprint = None
    if geometry.frame is not None:
        c_lat, c_lon = pixels_to_latlon(
            np.array([r_idx]), np.array([int(round(cx))]), geometry.frame
        )
        lat, lon = round(float(c_lat[0]), 6), round(float(c_lon[0]), 6)
        corner_rows = np.clip(np.rint(corners[:, 1]), 0, n_rows - 1).astype(np.int64)
        corner_cols = np.maximum(np.rint(corners[:, 0]), 0).astype(np.int64)
        f_lat, f_lon = pixels_to_latlon(corner_rows, corner_cols, geometry.frame)
        footprint = order_clockwise(
            [[round(float(a), 6), round(float(b), 6)] for a, b in zip(f_lat, f_lon, strict=True)]
        )

    depth = None
    if geometry.sensor_depth_m is not None and geometry.altitude_m is not None:
        value = float(geometry.sensor_depth_m[local_ping]) + float(geometry.altitude_m[local_ping])
        depth = round(value, 2) if math.isfinite(value) else None

    return Measurement(
        centroid_row=cy,
        centroid_col=cx,
        ping=local_ping + geometry.ping_offset,
        side="starboard" if cx >= geometry.nadir_col else "port",
        ground_range_m=round(abs(cx - geometry.nadir_col) * res, 2),
        length_m=round(max(len_a, len_b) * res, 2),
        width_m=round(min(len_a, len_b) * res, 2),
        area_m2=round(len(xs) * res * res, 2),
        orientation_deg=orientation,
        rect_corners_rc=tuple((float(r), float(c)) for c, r in corners),
        lat=lat,
        lon=lon,
        footprint=footprint,
        depth_m=depth,
    )
