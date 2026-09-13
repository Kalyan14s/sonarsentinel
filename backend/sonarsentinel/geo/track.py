"""Survey track geometry: length, bounding box and GeoJSON export.

The GeoJSON follows RFC 7946 (``[lon, lat]`` order), matching the ``LineString`` track feature in
``docs/architecture/06-data-models.md`` §3.2.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import numpy as np
import numpy.typing as npt
from pyproj import Geod

if TYPE_CHECKING:
    from sonarsentinel.ingest.models import SonarLog

_GEOD: Any = Geod(ellps="WGS84")


def valid_fixes(log: SonarLog) -> tuple[npt.NDArray[np.float64], npt.NDArray[np.float64]]:
    """Latitudes and longitudes of pings with finite navigation."""
    lat = log.nav["lat"].to_numpy(np.float64)
    lon = log.nav["lon"].to_numpy(np.float64)
    ok = np.isfinite(lat) & np.isfinite(lon)
    return lat[ok], lon[ok]


def track_length_km(log: SonarLog) -> float:
    """Geodesic length of the sonar track in kilometres."""
    lat, lon = valid_fixes(log)
    if len(lat) < 2:
        return 0.0
    return float(_GEOD.line_length(lon, lat)) / 1000.0


def track_bbox(log: SonarLog) -> list[float] | None:
    """``[min_lon, min_lat, max_lon, max_lat]`` of the track, or None without navigation."""
    lat, lon = valid_fixes(log)
    if not len(lat):
        return None
    return [
        round(float(lon.min()), 6),
        round(float(lat.min()), 6),
        round(float(lon.max()), 6),
        round(float(lat.max()), 6),
    ]


def track_geojson(log: SonarLog, every: int = 1, decimals: int = 6) -> dict[str, Any]:
    """The track as a GeoJSON ``FeatureCollection`` with one ``LineString`` feature."""
    lat, lon = valid_fixes(log)
    step = max(every, 1)
    coords = [
        [round(float(x), decimals), round(float(y), decimals)]
        for x, y in zip(lon[::step], lat[::step], strict=True)
    ]
    if len(lon) and coords[-1] != [
        round(float(lon[-1]), decimals),
        round(float(lat[-1]), decimals),
    ]:
        coords.append([round(float(lon[-1]), decimals), round(float(lat[-1]), decimals)])
    return {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "geometry": {"type": "LineString", "coordinates": coords},
                "properties": {
                    "feature_kind": "track",
                    "source_file": log.source_file,
                    "pings": log.n_pings,
                    "track_length_km": round(track_length_km(log), 3),
                    "warnings": list(log.warnings),
                },
            }
        ],
    }
