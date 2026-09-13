"""Pick the right ingest adapter for a file and summarise the result (pipeline stage S1).

The summary has the shape of one entry of ``POST /surveys/validate``
(``docs/architecture/05-api-specification.md`` §2.2).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from sonarsentinel.errors import UnsupportedFormatError, ValidationError
from sonarsentinel.geo.track import track_bbox, track_length_km
from sonarsentinel.ingest.models import NOT_GEOTAGGED, ChannelLayout, SonarLog
from sonarsentinel.ingest.validators import check_file

DEFAULT_MAX_BYTES = 2 * 1024**3


def read_source(
    path: str | Path,
    *,
    nav_csv: str | Path | None = None,
    epsg: int | str | None = None,
    layout: ChannelLayout = "port_stbd",
    allow_no_gps: bool = False,
    work_dir: str | Path | None = None,
    max_bytes: int = DEFAULT_MAX_BYTES,
) -> SonarLog:
    """Validate a file (S0) and read it with the matching adapter (S1).

    Args:
        path: ``.xtf``, ``.tif``/``.tiff`` (GeoTIFF), ``.png`` or ``.jpg`` file.
        nav_csv: Navigation CSV for image inputs.
        epsg: CRS for projected navigation, or ``"auto"``/``None``.
        layout: Channel layout of image inputs.
        allow_no_gps: Continue without navigation (flag ``NOT_GEOTAGGED``) instead of failing.
        work_dir: Directory for memory-mapped XTF samples.
        max_bytes: Size limit.

    Raises:
        ValidationError: The file has no navigation and ``allow_no_gps`` is False.
        SonarSentinelError: Any validation or parsing error from the adapters.
    """
    checked = check_file(path, max_bytes=max_bytes)
    epsg_value = None if epsg in (None, "auto") else epsg

    if checked.source_format == "xtf":
        from sonarsentinel.ingest.xtf_reader import read_xtf

        log = read_xtf(checked.path, epsg=epsg_value, work_dir=work_dir)
    elif checked.source_format == "geotiff":
        from sonarsentinel.ingest.geotiff_reader import read_geotiff

        return read_geotiff(checked.path, epsg=epsg_value)
    elif checked.source_format in ("png", "jpeg"):
        from sonarsentinel.ingest.image_nav_reader import read_image_nav, read_image_only

        if nav_csv is not None:
            check_file(nav_csv, max_bytes=max_bytes)
            log = read_image_nav(checked.path, nav_csv, layout=layout, epsg=epsg_value)
        else:
            log = read_image_only(checked.path, layout=layout)
    else:
        raise UnsupportedFormatError(
            f"{checked.path.name}: a navigation CSV can't be processed on its own",
            filename=checked.path.name,
        )

    if not log.has_navigation:
        if not allow_no_gps:
            raise ValidationError(
                f"{checked.path.name} has no navigation: attach a navigation CSV or allow "
                "processing without GPS",
                filename=checked.path.name,
                hint="allow_no_gps",
            )
        log.add_warning(NOT_GEOTAGGED)
    return log


def summarize(log: SonarLog, size_bytes: int | None = None) -> dict[str, Any]:
    """Describe a log like one file entry of the validate endpoint."""
    fmt = log.source_format
    summary: dict[str, Any] = {
        "filename": log.source_file,
        "valid": True,
        "format": fmt,
        "size_bytes": size_bytes,
        "has_navigation": log.has_navigation,
        "warnings": list(log.warnings),
    }
    if fmt == "geotiff":
        assert log.image is not None
        summary.update(
            height=int(log.image.shape[0]), width=int(log.image.shape[1]), crs=log.crs_hint
        )
        return summary

    channels = sum(a is not None for a in (log.port, log.starboard))
    summary["sonar"] = {
        "make": log.sonar.make,
        "model": log.sonar.model,
        "channels": channels,
        "frequency_khz": log.sonar.frequency_khz,
        "samples_per_channel": log.sonar.samples_per_channel,
    }
    summary["pings"] = log.n_pings
    times = log.nav["time_utc"].dropna()
    summary["start_utc"] = _iso(times.min()) if len(times) else None
    summary["end_utc"] = _iso(times.max()) if len(times) else None
    if log.has_navigation:
        summary["bbox"] = track_bbox(log)
        summary["track_length_km"] = round(track_length_km(log), 3)
    return summary


def _iso(ts: Any) -> str:
    return str(ts.strftime("%Y-%m-%dT%H:%M:%S.%f")[:-4] + "Z")
