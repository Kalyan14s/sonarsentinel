"""Internal data contracts shared by every ingest adapter (ST-020).

All format readers (XTF, GeoTIFF, image + navigation CSV, ...) return a :class:`SonarLog`; later
pipeline stages only depend on these structures. See ``docs/architecture/02-data-pipeline.md`` §2.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

import numpy as np
import numpy.typing as npt
import pandas as pd

from sonarsentinel.errors import ValidationError

SourceFormat = Literal["xtf", "jsf", "sl2", "sl3", "geotiff", "image_nav", "image_only"]
ChannelLayout = Literal["port_stbd", "port_only", "stbd_only"]
NavSource = Literal["sensor", "ship", "csv", "interpolated"]

#: One row per ping. Values may be NaN when a format doesn't provide a field.
NAV_COLUMNS: tuple[str, ...] = (
    "ping",
    "time_utc",
    "lat",
    "lon",
    "heading_deg",
    "altitude_m",
    "sensor_depth_m",
    "speed_mps",
    "roll_deg",
    "pitch_deg",
    "slant_range_m",
    "cable_out_m",
    "layback_m",
    "nav_source",
)

#: Formats whose data is a ping-by-ping waterfall (as opposed to a georeferenced mosaic).
WATERFALL_FORMATS: frozenset[str] = frozenset(
    {"xtf", "jsf", "sl2", "sl3", "image_nav", "image_only"}
)

# Warning codes collected in ``SonarLog.warnings`` (docs/architecture/02-data-pipeline.md §5 and
# 06-data-models.md §2.2).
TRUNCATED_FILE = "TRUNCATED_FILE"
NO_NAVIGATION = "NO_NAVIGATION"
NOT_GEOTAGGED = "NOT_GEOTAGGED"
GPS_INTERPOLATED = "GPS_INTERPOLATED"
HEADING_FROM_COG = "HEADING_FROM_COG"
SHIP_POSITION_ONLY = "SHIP_POSITION_ONLY"


@dataclass(frozen=True)
class SonarInfo:
    """Sonar hardware and channel description."""

    make: str | None
    model: str | None
    frequency_khz: float | None
    samples_per_channel: int
    channel_layout: ChannelLayout


def empty_nav(n_pings: int = 0) -> pd.DataFrame:
    """Return a navigation table with all :data:`NAV_COLUMNS` and ``n_pings`` rows of NaN."""
    nav = pd.DataFrame({name: [np.nan] * n_pings for name in NAV_COLUMNS})
    nav["ping"] = np.arange(n_pings, dtype=np.int64)
    nav["time_utc"] = pd.Series(pd.NaT, index=nav.index, dtype="datetime64[ns, UTC]")
    nav["nav_source"] = pd.Series([None] * n_pings, index=nav.index, dtype=object)
    return nav


@dataclass
class SonarLog:
    """A sonar recording normalised into the common internal representation.

    Attributes:
        source_file: Name of the file the data came from.
        source_format: Input format.
        sonar: Sonar hardware and channel layout.
        nav: Navigation table, one row per ping, with every column in :data:`NAV_COLUMNS`.
        port: Port-side samples ``(n_pings, n_samples)``; sample 0 is nearest to nadir.
        starboard: Starboard-side samples ``(n_pings, n_samples)``; sample 0 is nearest to nadir.
        image: The raster as read, ``(rows, cols)``: GeoTIFF band 1, or the waterfall image for
            image inputs (port on the left, starboard on the right). ``None`` for XTF.
        ground_range_corrected: True if across-track samples are already ground range.
        crs_hint: CRS of the navigation coordinates if known, e.g. ``"EPSG:4326"``.
        geotransform: GDAL-order affine geotransform for georeferenced rasters (GeoTIFF only).
        warnings: Machine-readable warning codes collected while reading.
    """

    source_file: str
    source_format: SourceFormat
    sonar: SonarInfo
    nav: pd.DataFrame
    port: npt.NDArray[Any] | None = None
    starboard: npt.NDArray[Any] | None = None
    image: npt.NDArray[Any] | None = None
    ground_range_corrected: bool = False
    crs_hint: str | None = None
    geotransform: tuple[float, float, float, float, float, float] | None = None
    warnings: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.validate()

    @property
    def n_pings(self) -> int:
        """Number of pings (navigation rows)."""
        return int(len(self.nav))

    @property
    def has_navigation(self) -> bool:
        """True if at least one ping has a finite latitude and longitude."""
        if self.n_pings == 0:
            return False
        lat = pd.to_numeric(self.nav["lat"], errors="coerce")
        lon = pd.to_numeric(self.nav["lon"], errors="coerce")
        return bool((np.isfinite(lat) & np.isfinite(lon)).any())

    def add_warning(self, code: str) -> None:
        """Record a warning code once."""
        if code not in self.warnings:
            self.warnings.append(code)

    def validate(self) -> None:
        """Check the contract; raise :class:`ValidationError` describing the first problem."""
        missing = [c for c in NAV_COLUMNS if c not in self.nav.columns]
        if missing:
            raise ValidationError("Navigation table is missing columns", missing=missing)

        if self.source_format in WATERFALL_FORMATS:
            self._validate_channels()
        elif self.source_format == "geotiff":
            if self.geotransform is None:
                raise ValidationError("GeoTIFF input requires a geotransform")
            if self.image is None or self.image.ndim != 2:
                raise ValidationError("GeoTIFF input requires a 2-D image")

    def _validate_channels(self) -> None:
        layout = self.sonar.channel_layout
        channels = {"port": self.port, "starboard": self.starboard}
        expected = {
            "port": layout in ("port_stbd", "port_only"),
            "starboard": layout in ("port_stbd", "stbd_only"),
        }
        for name, array in channels.items():
            if expected[name] and array is None:
                raise ValidationError(f"{name} channel required by layout {layout}", channel=name)
            if not expected[name] and array is not None:
                raise ValidationError(
                    f"{name} channel not allowed by layout {layout}", channel=name
                )
        for name, array in channels.items():
            if array is None:
                continue
            if array.ndim != 2:
                raise ValidationError(
                    f"{name} channel must be 2-D (pings, samples)", shape=array.shape
                )
            if array.shape[0] != self.n_pings:
                raise ValidationError(
                    f"{name} channel has {array.shape[0]} pings but navigation has {self.n_pings}",
                    channel=name,
                )
            if array.shape[1] != self.sonar.samples_per_channel:
                raise ValidationError(
                    f"{name} channel has {array.shape[1]} samples, expected "
                    f"{self.sonar.samples_per_channel}",
                    channel=name,
                )
