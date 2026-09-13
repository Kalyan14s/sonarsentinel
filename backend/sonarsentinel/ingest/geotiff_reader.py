"""GeoTIFF mosaic reader (ST-022, FR-ING-02).

A GeoTIFF is a single georeferenced raster with no ping structure: the reader keeps band 1, the
GDAL geotransform and the CRS. Pixel positions are converted with
:func:`sonarsentinel.geo.georef.raster_pixels_to_latlon`.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from sonarsentinel.errors import CorruptHeaderError, CrsRequiredError
from sonarsentinel.ingest.models import SonarInfo, SonarLog, empty_nav


def read_geotiff(path: str | Path, *, epsg: int | str | None = None) -> SonarLog:
    """Read a side-scan mosaic GeoTIFF.

    Args:
        path: GeoTIFF file.
        epsg: CRS to use when the file has none (e.g. ``32644``); ignored if the file has a CRS.

    Raises:
        CorruptHeaderError: The file can't be opened as a raster or has no geotransform.
        CrsRequiredError: The file has no CRS and ``epsg`` wasn't given.
    """
    import rasterio
    from rasterio.errors import RasterioIOError

    p = Path(path)
    try:
        ds: Any = rasterio.open(p)
    except RasterioIOError as exc:
        raise CorruptHeaderError(f"{p.name} can't be read as a GeoTIFF", filename=p.name) from exc

    with ds:
        if ds.transform.is_identity:
            raise CorruptHeaderError(f"{p.name} has no geotransform", filename=p.name)
        if ds.crs is not None:
            epsg_code = ds.crs.to_epsg()
            crs = f"EPSG:{epsg_code}" if epsg_code else ds.crs.to_wkt()
        elif epsg is not None and epsg != "auto":
            crs = f"EPSG:{epsg}" if isinstance(epsg, int) else str(epsg)
        else:
            raise CrsRequiredError(
                f"{p.name} has no coordinate reference system; provide an EPSG code",
                filename=p.name,
                hint="utm_epsg",
            )
        image = ds.read(1)
        geotransform = tuple(float(v) for v in ds.transform.to_gdal())

    return SonarLog(
        source_file=p.name,
        source_format="geotiff",
        sonar=SonarInfo(
            make=None,
            model=None,
            frequency_khz=None,
            samples_per_channel=int(image.shape[1]),
            channel_layout="port_stbd",
        ),
        nav=empty_nav(0),
        image=image,
        ground_range_corrected=True,
        crs_hint=crs,
        geotransform=geotransform,  # type: ignore[arg-type]
    )
