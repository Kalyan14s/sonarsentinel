"""Coordinate formatting for reports and the dashboard (TC-GEO-014)."""

from __future__ import annotations

from typing import Literal

from sonarsentinel.errors import ValidationError

Axis = Literal["lat", "lon"]


def format_decimal(value: float, decimals: int = 6) -> str:
    """Decimal degrees with a fixed number of decimals (default 6 ≈ 0.11 m)."""
    return f"{value:.{decimals}f}"


def to_dms(value: float, axis: Axis) -> str:
    """Format degrees as ``DD° MM' SS.SS" H``, e.g. ``13° 05' 02.83" N``."""
    limit = 90.0 if axis == "lat" else 180.0
    if not -limit <= value <= limit:
        raise ValidationError(f"{axis} out of range", value=value)
    hemisphere = ("N" if value >= 0 else "S") if axis == "lat" else ("E" if value >= 0 else "W")
    total_hundredths = round(abs(value) * 3600 * 100)  # integer maths avoids 59.999… rounding
    degrees, rest = divmod(total_hundredths, 3600 * 100)
    minutes, hundredths = divmod(rest, 60 * 100)
    seconds = hundredths / 100
    return f"{degrees}° {minutes:02d}' {seconds:05.2f}\" {hemisphere}"
