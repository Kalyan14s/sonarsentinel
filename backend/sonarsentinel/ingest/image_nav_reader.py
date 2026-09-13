"""Waterfall image readers: image + navigation CSV (ST-023) and image only (ST-024).

The image is a waterfall: row 0 is the first ping, port on the left (far range at column 0) and
starboard on the right. The navigation CSV format is in ``docs/architecture/06-data-models.md`` §5.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
import numpy.typing as npt
import pandas as pd
from pyproj import Geod

from sonarsentinel.errors import CorruptHeaderError, NavCsvInvalidError
from sonarsentinel.geo.units import to_wgs84
from sonarsentinel.ingest.models import (
    GPS_INTERPOLATED,
    HEADING_FROM_COG,
    NOT_GEOTAGGED,
    ChannelLayout,
    SonarInfo,
    SonarLog,
    empty_nav,
)

FloatArray = npt.NDArray[np.float64]

#: Optional numeric columns copied (and interpolated) from the CSV when present.
OPTIONAL_NUMERIC = ("altitude_m", "sensor_depth_m", "speed_mps", "roll_deg", "pitch_deg")

_GEOD: Any = Geod(ellps="WGS84")


def load_waterfall_image(path: str | Path) -> npt.NDArray[Any]:
    """Read a PNG/JPEG/TIFF waterfall as a 2-D grayscale array."""
    import cv2

    p = Path(path)
    buffer = np.fromfile(p, dtype=np.uint8)  # works with non-ASCII paths on Windows
    image: Any = cv2.imdecode(buffer, cv2.IMREAD_UNCHANGED) if buffer.size else None
    if image is None:
        raise CorruptHeaderError(f"{p.name} can't be decoded as an image", filename=p.name)
    if image.ndim == 3:
        code = cv2.COLOR_BGRA2GRAY if image.shape[2] == 4 else cv2.COLOR_BGR2GRAY
        image = cv2.cvtColor(image, code)
    return np.asarray(image)


def split_channels(
    image: npt.NDArray[Any], layout: ChannelLayout
) -> tuple[npt.NDArray[Any] | None, npt.NDArray[Any] | None, int]:
    """Split a waterfall into ``(port, starboard, samples_per_channel)``, sample 0 at nadir.

    For ``port_stbd`` the nadir is the image centre; an odd centre column is dropped.
    """
    width = image.shape[1]
    if layout == "port_only":
        return image[:, ::-1], None, width
    if layout == "stbd_only":
        return None, image, width
    samples = width // 2
    return image[:, :samples][:, ::-1], image[:, width - samples :], samples


def _interp_extrap(x_new: FloatArray, x: FloatArray, y: FloatArray) -> FloatArray:
    """Linear interpolation that extrapolates linearly beyond the first and last points."""
    out = np.interp(x_new, x, y)
    if len(x) >= 2:
        lo, hi = x_new < x[0], x_new > x[-1]
        out[lo] = y[0] + (x_new[lo] - x[0]) * (y[1] - y[0]) / (x[1] - x[0])
        out[hi] = y[-1] + (x_new[hi] - x[-1]) * (y[-1] - y[-2]) / (x[-1] - x[-2])
    return np.asarray(out, dtype=np.float64)


def _interp_heading(x_new: FloatArray, x: FloatArray, heading: FloatArray) -> FloatArray:
    """Interpolate headings on the circle (359° → 1° passes through 0°, not 180°)."""
    rad = np.radians(heading)
    s = np.interp(x_new, x, np.sin(rad))
    c = np.interp(x_new, x, np.cos(rad))
    return np.asarray(np.mod(np.degrees(np.arctan2(s, c)), 360.0), dtype=np.float64)


def course_over_ground(lat: FloatArray, lon: FloatArray) -> FloatArray:
    """Heading of travel between consecutive fixes (degrees true); the last fix repeats."""
    if len(lat) < 2:
        return np.full(len(lat), np.nan)
    az, _, _ = _GEOD.inv(lon[:-1], lat[:-1], lon[1:], lat[1:])
    cog = np.mod(np.asarray(az, dtype=np.float64), 360.0)
    return np.append(cog, cog[-1])


def read_nav_csv(
    path: str | Path, n_rows: int, *, epsg: int | str | None = None
) -> tuple[pd.DataFrame, list[str], bool]:
    """Read a navigation CSV and expand it to one row per image row.

    Args:
        path: CSV file (``ping`` = image row).
        n_rows: Number of image rows.
        epsg: CRS for ``easting``/``northing`` columns.

    Returns:
        ``(nav, warnings, ground_range_corrected)``.

    Raises:
        NavCsvInvalidError: Required columns are missing or values are invalid.
        CrsRequiredError: Projected coordinates without an EPSG code.
    """
    p = Path(path)
    try:
        df = pd.read_csv(p)
    except (pd.errors.ParserError, pd.errors.EmptyDataError, UnicodeDecodeError) as exc:
        raise NavCsvInvalidError(f"{p.name} can't be parsed as CSV", filename=p.name) from exc
    df.columns = [str(c).strip() for c in df.columns]

    has_latlon = {"lat", "lon"} <= set(df.columns)
    has_utm = {"easting", "northing"} <= set(df.columns)
    missing = [c for c in ("ping", "slant_range_m") if c not in df.columns]
    if not (has_latlon or has_utm):
        missing += [c for c in ("lat", "lon") if c not in df.columns]
    if missing:
        raise NavCsvInvalidError(
            f"{p.name} is missing required columns: {', '.join(missing)}",
            filename=p.name,
            missing=missing,
        )
    if df.empty:
        raise NavCsvInvalidError(f"{p.name} has no rows", filename=p.name)

    x_col, y_col = ("lon", "lat") if has_latlon else ("easting", "northing")
    numeric = ["ping", "slant_range_m", x_col, y_col]
    if "heading_deg" in df.columns:
        numeric.append("heading_deg")
    numeric += [c for c in OPTIONAL_NUMERIC if c in df.columns]
    values = df[numeric].apply(pd.to_numeric, errors="coerce")
    bad = [c for c in ("ping", "slant_range_m", x_col, y_col) if values[c].isna().any()]
    if bad:
        raise NavCsvInvalidError(
            f"{p.name} has empty or non-numeric values in: {', '.join(bad)}",
            filename=p.name,
            columns=bad,
        )
    pings = values["ping"].to_numpy(dtype=np.float64)
    if np.any(pings != np.round(pings)) or pings.min() < 0 or pings.max() >= n_rows:
        raise NavCsvInvalidError(
            f"{p.name}: ping values must be whole numbers from 0 to {n_rows - 1}",
            filename=p.name,
            n_rows=n_rows,
        )
    if len(np.unique(pings)) != len(pings):
        raise NavCsvInvalidError(f"{p.name}: duplicate ping values", filename=p.name)
    if n_rows > 1 and len(pings) < 2:
        raise NavCsvInvalidError(f"{p.name}: at least two fixes are needed", filename=p.name)

    order = np.argsort(pings)
    values = values.iloc[order].reset_index(drop=True)
    source_rows = df.iloc[order].reset_index(drop=True)
    pings = pings[order]

    lat_fix, lon_fix = to_wgs84(
        values[x_col].to_numpy(), values[y_col].to_numpy(), epsg=None if has_latlon else epsg
    )
    if has_latlon and (np.any(np.abs(lat_fix) > 90) or np.any(np.abs(lon_fix) > 180)):
        raise NavCsvInvalidError(f"{p.name}: lat/lon out of range", filename=p.name)

    rows = np.arange(n_rows, dtype=np.float64)
    nav = empty_nav(n_rows)
    nav["lat"] = _interp_extrap(rows, pings, lat_fix)
    nav["lon"] = _interp_extrap(rows, pings, lon_fix)
    nav["slant_range_m"] = np.interp(rows, pings, values["slant_range_m"].to_numpy(np.float64))
    for col in OPTIONAL_NUMERIC:
        if col in values.columns and values[col].notna().sum() >= 1:
            known = values[col].notna().to_numpy()
            nav[col] = np.interp(rows, pings[known], values[col].to_numpy(np.float64)[known])

    warnings: list[str] = []
    if "heading_deg" in values.columns and values["heading_deg"].notna().all():
        nav["heading_deg"] = _interp_heading(rows, pings, values["heading_deg"].to_numpy())
    else:
        nav["heading_deg"] = course_over_ground(
            nav["lat"].to_numpy(np.float64), nav["lon"].to_numpy(np.float64)
        )
        warnings.append(HEADING_FROM_COG)

    if "time_utc" in source_rows.columns:
        times = pd.to_datetime(source_rows["time_utc"], utc=True, errors="coerce")
        if times.notna().sum() >= 2:
            known = times.notna().to_numpy()
            ns = times[known].dt.as_unit("ns").astype("int64").to_numpy(dtype=np.float64)
            nav["time_utc"] = pd.to_datetime(
                _interp_extrap(rows, pings[known], ns).astype(np.int64), unit="ns", utc=True
            )

    given = np.zeros(n_rows, dtype=bool)
    given[pings.astype(np.int64)] = True
    nav["nav_source"] = np.where(given, "csv", "interpolated")
    if not given.all():
        warnings.append(GPS_INTERPOLATED)

    ground_corrected = False
    if "ground_range_corrected" in source_rows.columns:
        flags = source_rows["ground_range_corrected"].astype(str).str.strip().str.lower()
        ground_corrected = bool(flags.isin(["true", "1", "yes"]).any())
    return nav, warnings, ground_corrected


def read_image_nav(
    image_path: str | Path,
    nav_csv: str | Path,
    *,
    layout: ChannelLayout = "port_stbd",
    epsg: int | str | None = None,
) -> SonarLog:
    """Read a waterfall image with its navigation CSV (FR-ING-03)."""
    p = Path(image_path)
    image = load_waterfall_image(p)
    nav, warnings, ground_corrected = read_nav_csv(nav_csv, image.shape[0], epsg=epsg)
    port, starboard, samples = split_channels(image, layout)
    return SonarLog(
        source_file=p.name,
        source_format="image_nav",
        sonar=SonarInfo(None, None, None, samples, layout),
        nav=nav,
        port=port,
        starboard=starboard,
        image=image,
        ground_range_corrected=ground_corrected,
        crs_hint="EPSG:4326",
        warnings=warnings,
    )


def read_image_only(image_path: str | Path, *, layout: ChannelLayout = "port_stbd") -> SonarLog:
    """Read a waterfall image without navigation (FR-ING-04): flagged ``NOT_GEOTAGGED``."""
    p = Path(image_path)
    image = load_waterfall_image(p)
    port, starboard, samples = split_channels(image, layout)
    return SonarLog(
        source_file=p.name,
        source_format="image_only",
        sonar=SonarInfo(None, None, None, samples, layout),
        nav=empty_nav(image.shape[0]),
        port=port,
        starboard=starboard,
        image=image,
        warnings=[NOT_GEOTAGGED],
    )
