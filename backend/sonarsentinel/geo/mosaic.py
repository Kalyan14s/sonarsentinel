"""Georeferenced mosaic of processed chunks (ST-036, FR-GEO-07).

``docs/architecture/04-geotagging-engine.md`` §7, implemented with rasterio (which bundles GDAL)
instead of ``osgeo.gdal`` (ADR-018): for each ground-range chunk, ground control points are placed
every ``step_rows`` rows at columns ``(0, nadir_col, width − 1)`` with
:func:`sonarsentinel.geo.georef.pixels_to_latlon`, and the chunk is warped to EPSG:4326 with a
thin-plate-spline GCP transform (GDAL ``SRC_METHOD=GCP_TPS``), which follows curved tracks. Chunks
merge by maximum with nodata 0.

Memory: each chunk is stored downsampled to the output resolution (default 0.25 m, so a 0.10 m
chunk shrinks about 6×), and the output grid is capped at ``max_pixels`` (default 25 million
uint8 pixels ≈ 25 MB) by coarsening the output resolution; :class:`MosaicResult` reports the
resolution used.

Residual check: pixels halfway between GCP rows at quarter-swath columns are projected with the
same TPS transform the warp uses and compared with their :func:`pixels_to_latlon` positions.
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import numpy.typing as npt
from pyproj import Geod

from sonarsentinel.errors import ValidationError
from sonarsentinel.geo.georef import GeoFrame, pixels_to_latlon

GEOD: Any = Geod(ellps="WGS84")
METRES_PER_DEGREE_LAT = 111_320.0


@dataclass(frozen=True)
class MosaicResult:
    tif: Path
    png: Path
    bounds_json: Path
    bounds: tuple[tuple[float, float], tuple[float, float]]  # ((south, west), (north, east))
    gcp_residual_m: float  # mean over check pixels
    gcp_residual_max_m: float
    ground_res_m: float  # output resolution actually used
    shape: tuple[int, int]  # (rows, cols)


@dataclass
class _Chunk:
    image: npt.NDArray[np.uint8]
    gcps: list[Any]
    residuals: npt.NDArray[np.float64]
    lats: npt.NDArray[np.float64]
    lons: npt.NDArray[np.float64]


def _downsample(image: npt.NDArray[np.uint8], factor: int) -> npt.NDArray[np.uint8]:
    if factor <= 1:
        return image
    import cv2

    size = (max(1, image.shape[1] // factor), max(1, image.shape[0] // factor))
    return np.asarray(cv2.resize(image, size, interpolation=cv2.INTER_AREA), dtype=np.uint8)


class MosaicBuilder:
    """Collect processed chunks and write a north-up EPSG:4326 mosaic."""

    def __init__(self, ground_res_m_out: float = 0.25, *, max_pixels: int = 25_000_000) -> None:
        if ground_res_m_out <= 0:
            raise ValidationError("ground_res_m_out must be > 0", ground_res_m_out=ground_res_m_out)
        self.ground_res_m_out = float(ground_res_m_out)
        self.max_pixels = int(max_pixels)
        self._chunks: list[_Chunk] = []

    def add(self, image_u8: npt.NDArray[np.uint8], frame: GeoFrame, *, step_rows: int = 50) -> None:
        """Add one ground-range chunk (rows follow ``frame.row_to_ping``, 0 = no data)."""
        from rasterio.control import GroundControlPoint
        from rasterio.transform import GCPTransformer

        height, width = image_u8.shape
        if height < 2 or width < 2 or len(frame.row_to_ping) != height:
            raise ValidationError("Chunk image and frame rows don't match", rows=height)
        rows = sorted({*range(0, height, max(1, step_rows)), height - 1})
        cols = sorted({0, min(max(frame.nadir_col, 0), width - 1), width - 1})
        grid_r, grid_c = np.meshgrid(rows, cols, indexing="ij")
        lat, lon = pixels_to_latlon(grid_r.ravel(), grid_c.ravel(), frame)
        factor = max(1, round(self.ground_res_m_out / frame.ground_res_m))
        small = _downsample(np.ascontiguousarray(image_u8, dtype=np.uint8), factor)
        sy, sx = small.shape[0] / height, small.shape[1] / width
        full_gcps = []
        small_gcps = []
        for r, c, y, x in zip(grid_r.ravel(), grid_c.ravel(), lat, lon, strict=True):
            full_gcps.append(GroundControlPoint(row=r + 0.5, col=c + 0.5, x=float(x), y=float(y)))
            small_gcps.append(
                GroundControlPoint(row=(r + 0.5) * sy, col=(c + 0.5) * sx, x=float(x), y=float(y))
            )

        check_r = np.array(
            [min(r + step_rows // 2, height - 1) for r in rows[:-1]] or [height // 2]
        )
        nadir = cols[len(cols) // 2]
        check_c = np.array(sorted({nadir // 2, nadir + (width - 1 - nadir) // 2}))
        cr, cc = np.meshgrid(check_r, check_c, indexing="ij")
        true_lat, true_lon = pixels_to_latlon(cr.ravel(), cc.ravel(), frame)
        with GCPTransformer(full_gcps, tps=True) as transformer:
            xs, ys = transformer.xy(cr.ravel().tolist(), cc.ravel().tolist(), offset="center")
        _, _, distance = GEOD.inv(
            np.asarray(xs, dtype=np.float64), np.asarray(ys, dtype=np.float64), true_lon, true_lat
        )
        self._chunks.append(
            _Chunk(
                image=small,
                gcps=small_gcps,
                residuals=np.abs(np.asarray(distance, dtype=np.float64)),
                lats=np.asarray(lat, dtype=np.float64),
                lons=np.asarray(lon, dtype=np.float64),
            )
        )

    def finish(self, out_dir: str | Path) -> MosaicResult:
        """Warp every chunk onto one grid and write ``mosaic.tif``, ``.png`` and bounds JSON."""
        import cv2
        import rasterio
        from rasterio.transform import from_origin
        from rasterio.warp import Resampling, reproject

        if not self._chunks:
            raise ValidationError("No chunks were added to the mosaic")
        lats = np.concatenate([c.lats for c in self._chunks])
        lons = np.concatenate([c.lons for c in self._chunks])
        lat0 = float(np.mean(lats))
        res = self.ground_res_m_out
        dlat = res / METRES_PER_DEGREE_LAT
        dlon = res / (METRES_PER_DEGREE_LAT * max(math.cos(math.radians(lat0)), 1e-6))
        west, east = float(lons.min()) - dlon, float(lons.max()) + dlon
        south, north = float(lats.min()) - dlat, float(lats.max()) + dlat
        cols = math.ceil((east - west) / dlon) + 1
        rows = math.ceil((north - south) / dlat) + 1
        if rows * cols > self.max_pixels:
            scale = math.sqrt(rows * cols / self.max_pixels)
            res, dlat, dlon = res * scale, dlat * scale, dlon * scale
            cols = math.ceil((east - west) / dlon) + 1
            rows = math.ceil((north - south) / dlat) + 1
        transform = from_origin(west, north, dlon, dlat)

        canvas = np.zeros((rows, cols), dtype=np.uint8)
        for chunk in self._chunks:
            warped = np.zeros_like(canvas)
            reproject(
                source=chunk.image,
                destination=warped,
                gcps=chunk.gcps,
                src_crs="EPSG:4326",
                src_nodata=0,
                dst_transform=transform,
                dst_crs="EPSG:4326",
                dst_nodata=0,
                resampling=Resampling.bilinear,
                SRC_METHOD="GCP_TPS",
            )
            np.maximum(canvas, warped, out=canvas)

        folder = Path(out_dir)
        folder.mkdir(parents=True, exist_ok=True)
        tif, png, bounds_json = (
            folder / "mosaic.tif",
            folder / "mosaic.png",
            folder / "mosaic_bounds.json",
        )
        with rasterio.open(
            tif,
            "w",
            driver="GTiff",
            height=rows,
            width=cols,
            count=1,
            dtype="uint8",
            crs="EPSG:4326",
            transform=transform,
            nodata=0,
            compress="deflate",
        ) as dataset:
            dataset.write(canvas, 1)
        alpha = np.where(canvas > 0, 255, 0).astype(np.uint8)
        if not cv2.imwrite(str(png), np.dstack([canvas, canvas, canvas, alpha])):
            raise OSError(f"Could not write {png}")
        bounds = (
            (round(north - rows * dlat, 7), round(west, 7)),
            (round(north, 7), round(west + cols * dlon, 7)),
        )
        residuals = np.concatenate([c.residuals for c in self._chunks])
        bounds_json.write_text(
            json.dumps(
                {
                    "bounds": [list(bounds[0]), list(bounds[1])],
                    "crs": "EPSG:4326",
                    "ground_res_m": round(res, 4),
                    "gcp_residual_m": round(float(residuals.mean()), 3),
                    "gcp_residual_max_m": round(float(residuals.max()), 3),
                },
                indent=2,
            ),
            encoding="utf-8",
        )
        return MosaicResult(
            tif=tif,
            png=png,
            bounds_json=bounds_json,
            bounds=bounds,
            gcp_residual_m=round(float(residuals.mean()), 3),
            gcp_residual_max_m=round(float(residuals.max()), 3),
            ground_res_m=round(res, 4),
            shape=(rows, cols),
        )
