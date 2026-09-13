"""Processing orchestrator (ST-075): one sonar file → schema-valid report.

Stages ``validate → parse → preprocess → detect → score → geotag → merge → report``
(``docs/architecture/01-system-architecture.md`` §6). Waterfall inputs are processed chunk by
chunk (preprocess → tiles → detector → in-chunk merge → measurement and quality flags), then
duplicates from chunk overlaps are removed and detections are scored and numbered in ping order.
Events (``progress``, ``track``, ``warning``, ``detection``, ``done``) go to ``on_event`` in the
WebSocket message shape of the API spec §3.

Scoring here is the Sprint 3 thin slice: fused = detector score − dropout/motion penalties, with an
identity calibrator (``identity@0.1.0``). Shadow, FP filter, anomaly and isotonic calibration arrive
in Sprint 4 (ST-060…065). Same input and configuration give the same report apart from
``generated_utc`` and ``duration_s`` (NFR-16).
"""

from __future__ import annotations

import math
import time
from collections.abc import Callable
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np
import numpy.typing as npt

from sonarsentinel.config import config_hash, load_config
from sonarsentinel.detect.anomaly import heat_regions
from sonarsentinel.detect.base import Detector, RawDetection, describe
from sonarsentinel.detect.classical import BrightTargetDetector
from sonarsentinel.detect.merge import (
    SurveyDetection,
    dedupe_across_chunks,
    merge_detections,
    tiles_to_image,
    to_survey,
)
from sonarsentinel.geo.georef import raster_pixels_to_latlon
from sonarsentinel.geo.measure import ImageGeometry, measure_mask, order_clockwise
from sonarsentinel.geo.track import track_bbox, track_length_km, valid_fixes
from sonarsentinel.ingest.chunking import chunk_ranges
from sonarsentinel.ingest.models import NOT_GEOTAGGED, SonarLog
from sonarsentinel.ingest.reader import read_source
from sonarsentinel.preprocess.bottom import NO_ALTITUDE_BOTTOM_TRACKED
from sonarsentinel.preprocess.channels import to_three_channel
from sonarsentinel.preprocess.pipeline import preprocess_log
from sonarsentinel.preprocess.tiling import Tile, iter_tiles, row_col_mask
from sonarsentinel.report.builder import alert_tier, build_report, iso_utc

EventCallback = Callable[[dict[str, Any]], None]
CALIBRATOR_VERSION = "identity@0.1.0"
BATCH_TILES = 8


class _Events:
    def __init__(self, callback: EventCallback | None) -> None:
        self.callback = callback
        self.seq = 0

    def __call__(self, kind: str, **payload: Any) -> None:
        if self.callback is None:
            return
        self.seq += 1
        ts = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
        self.callback({"type": kind, "seq": self.seq, "ts": ts, **payload})


def run_pipeline(
    source: str | Path,
    *,
    config: dict[str, Any] | None = None,
    nav_csv: str | Path | None = None,
    epsg: int | str | None = None,
    allow_no_gps: bool = False,
    detector: Detector | None = None,
    anomaly_model: Any | None = None,
    survey_id: str | None = None,
    survey_name: str | None = None,
    min_conf: float | None = None,
    on_event: EventCallback | None = None,
    work_dir: str | Path | None = None,
) -> dict[str, Any]:
    """Process one file and return the report dictionary (schema ``report-1.0``)."""
    cfg = config if config is not None else load_config()
    started = time.perf_counter()
    model: Detector = detector if detector is not None else BrightTargetDetector()
    emit = _Events(on_event)
    path = Path(source)

    emit("progress", stage="validate", percent=0.0)
    log = read_source(
        path,
        nav_csv=nav_csv,
        epsg=epsg,
        layout=cfg["ingest"]["image_layout"],
        allow_no_gps=allow_no_gps,
        work_dir=work_dir,
    )
    emit("progress", stage="parse", percent=5.0, pings_done=0, pings_total=log.n_pings)
    sid = survey_id or _survey_id(log)

    if log.source_format == "geotiff":
        found, quality = _detect_geotiff(log, cfg, model)
    else:
        found, quality = _detect_waterfall(log, cfg, model, emit, anomaly_model)

    emit("progress", stage="merge", percent=90.0)
    unique = dedupe_across_chunks(found)
    detections = _finalise(unique, log, cfg, sid, min_conf, describe(model))
    for det in detections:
        emit("detection", detection=det)

    if describe(model).startswith("classical-"):
        # The rule-based stand-in floods real seabed texture with detections (USGS Grand Bay test:
        # 3,785 on one line); make that visible in every report it produces.
        quality["warnings"] = sorted({*quality["warnings"], "RULE_BASED_DETECTOR"})

    emit("progress", stage="report", percent=95.0)
    report = build_report(
        survey=_survey_section(log, cfg, sid, survey_name or path.stem),
        processing={
            "pipeline_version": str(cfg.get("pipeline_version", "0.0.0")),
            "models": {
                "detector": describe(model),
                "anomaly": (
                    describe(anomaly_model)
                    if anomaly_model is not None and log.source_format != "geotiff"
                    else None
                ),
                "fp_filter": None,
                "calibrator": CALIBRATOR_VERSION,
            },
            "config_hash": config_hash(cfg),
            "runtime": str(getattr(model, "runtime", "cpu")),
            "duration_s": round(time.perf_counter() - started, 2),
            "quality": quality,
        },
        detections=detections,
    )
    status = "completed_with_warnings" if quality["warnings"] else "completed"
    emit("done", status=status, summary=report["summary"])
    return report


def _survey_id(log: SonarLog) -> str:
    times = log.nav["time_utc"].dropna()
    day = times.min().strftime("%Y%m%d") if len(times) else datetime.now(UTC).strftime("%Y%m%d")
    return f"SRV-{day}-001"


def _anomaly_heat(
    model: Any, pixels: list[Any], tiles: list[Tile], shape: tuple[int, int]
) -> npt.NDArray[np.float32]:
    """Chunk-sized anomaly heatmap: tile heatmaps resized to the tile, max where they overlap."""
    import cv2

    heat = np.zeros(shape, dtype=np.float32)
    for start in range(0, len(pixels), BATCH_TILES):
        result = model.score(pixels[start : start + BATCH_TILES])
        for tile, tile_heat in zip(
            tiles[start : start + BATCH_TILES], result.heatmaps, strict=True
        ):
            up = cv2.resize(
                np.asarray(tile_heat, np.float32),
                (tile.size, tile.size),
                interpolation=cv2.INTER_LINEAR,
            )
            h = min(tile.size, shape[0] - tile.row)
            w = min(tile.size, shape[1] - tile.col)
            region = heat[tile.row : tile.row + h, tile.col : tile.col + w]
            np.maximum(region, up[:h, :w], out=region)
    return heat


def _anomaly_score(
    heat: npt.NDArray[np.float32] | None, det: RawDetection, model: Any
) -> float | None:
    """Mean heat inside the detection mask relative to twice the pixel threshold (0–1)."""
    threshold = getattr(model, "pixel_threshold", None)
    if heat is None or not threshold:
        return None
    x1, y1, x2, y2 = det.box
    values = heat[y1:y2, x1:x2][det.full_mask()]
    if not values.size:
        return None
    return round(float(np.clip(values.mean() / (2.0 * threshold), 0.0, 1.0)), 4)


def _detect_waterfall(
    log: SonarLog,
    cfg: dict[str, Any],
    model: Detector,
    emit: _Events,
    anomaly_model: Any | None = None,
) -> tuple[list[SurveyDetection], dict[str, Any]]:
    tiling = cfg["tiling"]
    min_raw = float(cfg["detection"]["min_raw_score"])
    warnings: set[str] = set(log.warnings)
    dropout = np.zeros(log.n_pings, dtype=bool)
    motion = np.zeros(log.n_pings, dtype=bool)
    bottom_tracked = False
    found: list[SurveyDetection] = []
    n_chunks = max(
        len(
            chunk_ranges(
                log.n_pings, cfg["chunking"]["pings_per_chunk"], cfg["chunking"]["overlap_pings"]
            )
        ),
        1,
    )

    for chunk in preprocess_log(log, cfg):
        warnings |= set(chunk.warnings)
        bottom_tracked |= NO_ALTITUDE_BOTTOM_TRACKED in chunk.warnings
        for event in chunk.quality_events:
            target = dropout if event["code"] == "DROPOUT" else motion
            target[event["ping_start"] : event["ping_end"] + 1] = True
            emit(
                "warning",
                code=event["code"],
                message=f"{event['code']} pings",
                ping_start=event["ping_start"],
                ping_end=event["ping_end"],
            )

        height, width = chunk.image.shape
        skip = row_col_mask((height, width), rows=chunk.masks["dropout"])
        tiles, pixels = [], []
        for tile, px in iter_tiles(
            chunk.image_3ch,
            mask=skip,
            size=tiling["size_px"],
            overlap=tiling["overlap"],
            skip_if_masked_fraction_gt=tiling["skip_if_masked_fraction_gt"],
        ):
            tiles.append(tile)
            pixels.append(px)
        per_tile: list[list[RawDetection]] = []
        for start in range(0, len(pixels), BATCH_TILES):
            per_tile += model.predict(pixels[start : start + BATCH_TILES])
        merged = merge_detections(tiles_to_image(per_tile, tiles, (height, width)))

        heat = None
        if anomaly_model is not None and pixels:
            heat = _anomaly_heat(anomaly_model, pixels, tiles, (height, width))
            min_px = max(1, round(float(cfg["anomaly"]["min_region_m2"]) / chunk.ground_res_m**2))
            merged += heat_regions(
                heat,
                float(anomaly_model.pixel_threshold),
                min_area_px=min_px,
                exclude_boxes=[d.box for d in merged],
            )

        geometry = chunk.image_geometry()
        n_local = len(chunk.nav)
        chunk_range = (chunk.ping_offset, chunk.ping_offset + n_local - 1)
        nav_source = chunk.nav["nav_source"].to_numpy(dtype=object)
        # The despeckle/texture/median filters mirror the image at its borders, so the first and
        # last rows of the *line* are noisier than the rest; chunk borders inside the line are
        # covered by the overlap and are not affected.
        edge = int(cfg["preprocess"]["local_std_window"])
        line_start = chunk_range[0] == 0
        line_end = chunk_range[1] >= log.n_pings - 1
        for det in merged:
            if det.score < min_raw:
                continue
            x1, y1, x2, y2 = det.box
            if (line_start and y1 < edge) or (line_end and y2 > height - edge):
                continue
            m = measure_mask(det.full_mask(), geometry, row0=y1, col0=x1)
            local = chunk.row_to_ping[y1:y2] - chunk.ping_offset
            flags = []
            if chunk.masks["dropout"][y1:y2].any():
                flags.append("DROPOUT")
            if chunk.masks["motion"][y1:y2].any():
                flags.append("HIGH_MOTION")
            altitude = chunk.altitude_m[local]
            if np.isfinite(altitude).any() and m.ground_range_m < 0.3 * np.nanmedian(altitude):
                flags.append("NEAR_NADIR")
            if (nav_source[local] == "interpolated").any():
                flags.append("GPS_INTERPOLATED")
            if NO_ALTITUDE_BOTTOM_TRACKED in chunk.warnings:
                flags.append(NO_ALTITUDE_BOTTOM_TRACKED)
            if not chunk.geotagged:
                flags.append(NOT_GEOTAGGED)
            found.append(
                to_survey(
                    det,
                    row_to_ping=chunk.row_to_ping,
                    nadir_col=chunk.nadir_col,
                    ground_res_m=chunk.ground_res_m,
                    chunk_id=chunk.chunk_id,
                    chunk_ping_range=chunk_range,
                    extra={
                        "measurement": m,
                        "flags": flags,
                        "dropout_fraction": float(chunk.masks["dropout"][y1:y2].mean()),
                        "time_utc": iso_utc(chunk.nav["time_utc"].iloc[m.ping - chunk.ping_offset]),
                        "pixel_bbox": [int(x1), int(y1), int(x2), int(y2)],
                        "side": m.side,
                        "anomaly_score": _anomaly_score(heat, det, anomaly_model),
                    },
                )
            )

        if chunk.geotagged:
            step = max(1, n_local // 100)
            lat = chunk.nav["lat"].to_numpy(np.float64)[::step]
            lon = chunk.nav["lon"].to_numpy(np.float64)[::step]
            emit(
                "track",
                points=[
                    [round(float(a), 6), round(float(b), 6)] for a, b in zip(lat, lon, strict=True)
                ],
                ping_start=chunk_range[0],
                ping_end=chunk_range[1],
            )
        done = min(chunk_range[1] + 1, log.n_pings)
        emit(
            "progress",
            stage="detect",
            percent=round(10.0 + 80.0 * (chunk.chunk_id + 1) / n_chunks, 1),
            pings_done=done,
            pings_total=log.n_pings,
        )

    quality = {
        "dropout_pings": int(dropout.sum()),
        "high_motion_pings": int(motion.sum()),
        "bottom_tracked": bottom_tracked,
        "layback_estimated": False,
        "warnings": sorted(warnings),
    }
    return found, quality


def _detect_geotiff(
    log: SonarLog, cfg: dict[str, Any], model: Detector
) -> tuple[list[SurveyDetection], dict[str, Any]]:
    """Mosaic path: no pings, positions straight from the raster geotransform."""
    from pyproj import CRS

    assert log.image is not None and log.geotransform is not None and log.crs_hint is not None
    image = np.asarray(log.image, dtype=np.float64)
    finite = image[np.isfinite(image)]
    lo, hi = np.percentile(finite, [1, 99.5]) if finite.size else (0.0, 1.0)
    u8 = np.clip((image - lo) / max(hi - lo, 1e-9) * 255, 0, 255).astype(np.uint8)
    three = to_three_channel(u8)
    tiling = cfg["tiling"]
    tiles, pixels = [], []
    for tile, px in iter_tiles(three, size=tiling["size_px"], overlap=tiling["overlap"]):
        tiles.append(tile)
        pixels.append(px)
    per_tile: list[list[RawDetection]] = []
    for start in range(0, len(pixels), BATCH_TILES):
        per_tile += model.predict(pixels[start : start + BATCH_TILES])
    merged = merge_detections(tiles_to_image(per_tile, tiles, u8.shape))

    gt = log.geotransform
    pixel = math.sqrt(abs(gt[1] * gt[5]))
    crs = CRS.from_user_input(log.crs_hint)
    if crs.is_geographic:
        lat0 = gt[3] + gt[5] * u8.shape[0] / 2
        pixel *= 111_320.0 * math.cos(math.radians(lat0))
    rows_all = np.arange(u8.shape[0], dtype=np.int64)
    geometry = ImageGeometry(ground_res_m=pixel, nadir_col=0, row_to_ping=rows_all)
    found = []
    min_raw = float(cfg["detection"]["min_raw_score"])
    for det in merged:
        if det.score < min_raw:
            continue
        x1, y1, x2, y2 = det.box
        m = measure_mask(det.full_mask(), geometry, row0=y1, col0=x1)
        c_lat, c_lon = raster_pixels_to_latlon([m.centroid_row], [m.centroid_col], gt, log.crs_hint)
        corners = np.array(m.rect_corners_rc)
        f_lat, f_lon = raster_pixels_to_latlon(corners[:, 0], corners[:, 1], gt, log.crs_hint)
        footprint = order_clockwise(
            [[round(float(a), 6), round(float(b), 6)] for a, b in zip(f_lat, f_lon, strict=True)]
        )
        m = replace(
            m,
            lat=round(float(c_lat[0]), 6),
            lon=round(float(c_lon[0]), 6),
            footprint=footprint,
            orientation_deg=None,
            ground_range_m=0.0,
        )
        found.append(
            to_survey(
                det,
                row_to_ping=rows_all,
                nadir_col=0,
                ground_res_m=pixel,
                chunk_id=0,
                chunk_ping_range=(0, u8.shape[0] - 1),
                extra={
                    "measurement": m,
                    "flags": [],
                    "dropout_fraction": 0.0,
                    "time_utc": None,
                    "pixel_bbox": [x1, y1, x2, y2],
                    "side": "n/a",
                },
            )
        )
    quality = {
        "dropout_pings": 0,
        "high_motion_pings": 0,
        "bottom_tracked": False,
        "layback_estimated": False,
        "warnings": sorted(set(log.warnings)),
    }
    return found, quality


def _finalise(
    unique: list[SurveyDetection],
    log: SonarLog,
    cfg: dict[str, Any],
    survey_id: str,
    min_conf: float | None,
    model_version: str,
) -> list[dict[str, Any]]:
    penalties = cfg["scoring"]["penalties"]
    tiers = cfg["scoring"]["tiers"]
    rows = []
    ordered = sorted(unique, key=lambda d: (d.ping_start, d.across_start_m, d.detection.cls))
    for sd in ordered:
        raw = float(sd.detection.score)
        anomaly = sd.extra.get("anomaly_score")
        is_anomaly = sd.detection.cls == "unknown_anomaly"
        base = anomaly if is_anomaly and anomaly is not None else raw
        flags = list(sd.extra["flags"])
        dropout_penalty = round(float(penalties["dropout"]) * sd.extra["dropout_fraction"], 4)
        motion_penalty = float(penalties["motion"]) if "HIGH_MOTION" in flags else 0.0
        fused = min(max(base - dropout_penalty - motion_penalty, 0.0), 1.0)
        confidence = round(100.0 * fused, 1)
        if min_conf is not None and confidence < min_conf:
            continue
        rows.append((sd, raw, anomaly, flags, dropout_penalty, motion_penalty, fused, confidence))

    detections = []
    for i, (
        sd,
        raw,
        anomaly,
        flags,
        dropout_penalty,
        motion_penalty,
        fused,
        confidence,
    ) in enumerate(rows, start=1):
        tier_anomaly = anomaly if sd.detection.cls == "unknown_anomaly" else None
        scores: dict[str, float] = {"detector": round(raw, 4)}
        if anomaly is not None:
            scores["anomaly"] = anomaly
        scores |= {
            "dropout_penalty": dropout_penalty,
            "motion_penalty": motion_penalty,
            "fused": round(fused, 4),
        }
        m = sd.extra["measurement"]
        geotagged = NOT_GEOTAGGED not in flags
        sonar_ref: dict[str, Any] = {
            "source_file": log.source_file,
            "side": sd.extra["side"],
            "ping_start": sd.ping_start if log.source_format != "geotiff" else None,
            "ping_end": sd.ping_end if log.source_format != "geotiff" else None,
            "ground_range_m": m.ground_range_m if log.source_format != "geotiff" else None,
            "time_utc": sd.extra["time_utc"],
        }
        if not geotagged:
            sonar_ref["pixel_bbox"] = sd.extra["pixel_bbox"]
        detections.append(
            {
                "detection_id": f"{survey_id}-D{i:04d}",
                "class": sd.detection.cls,
                "confidence": confidence,
                "alert_tier": alert_tier(confidence, tiers, anomaly_score=tier_anomaly),
                "position": {
                    "lat": m.lat if geotagged else None,
                    "lon": m.lon if geotagged else None,
                    "depth_m": m.depth_m,
                    "uncertainty_m": None,
                },
                "footprint": m.footprint if geotagged else None,
                "dimensions": {
                    "length_m": m.length_m,
                    "width_m": m.width_m,
                    "area_m2": m.area_m2,
                    "height_m": None,
                },
                "orientation_deg": m.orientation_deg,
                "sonar_ref": sonar_ref,
                "scores": scores,
                "quality_flags": sorted(set(flags)),
                "n_views": 1,
                "review": {
                    "status": "pending",
                    "reviewer": None,
                    "reject_reason": None,
                    "note": None,
                    "updated_utc": None,
                },
                "model_version": model_version,
                "chip_url": None,
            }
        )
    return detections


def _survey_section(
    log: SonarLog, cfg: dict[str, Any], survey_id: str, name: str
) -> dict[str, Any]:
    slant = log.nav["slant_range_m"].to_numpy(np.float64) if log.n_pings else np.array([])
    range_m = float(np.nanmedian(slant)) if np.isfinite(slant).any() else None
    times = log.nav["time_utc"].dropna()
    freq = log.sonar.frequency_khz
    section: dict[str, Any] = {
        "survey_id": survey_id,
        "name": name,
        "project": None,
        "source_files": [log.source_file],
        "source_format": log.source_format,
        "sonar": {
            "make": log.sonar.make,
            "model": log.sonar.model,
            "frequency_khz": freq if freq and freq > 0 else None,
            "range_m": round(range_m, 2) if range_m and range_m > 0 else None,
        },
        "start_utc": iso_utc(times.min()) if len(times) else None,
        "end_utc": iso_utc(times.max()) if len(times) else None,
        "track_length_km": None,
        "area_covered_km2": None,
        "datum": "WGS84",
        "ground_resolution_m": float(cfg["preprocess"]["ground_resolution_m"]),
        "bbox": None,
    }
    if log.source_format == "geotiff":
        assert log.image is not None and log.geotransform is not None and log.crs_hint is not None
        h, w = log.image.shape
        lat, lon = raster_pixels_to_latlon(
            [0, 0, h - 1, h - 1], [0, w - 1, 0, w - 1], log.geotransform, log.crs_hint
        )
        section["bbox"] = [
            round(float(lon.min()), 6),
            round(float(lat.min()), 6),
            round(float(lon.max()), 6),
            round(float(lat.max()), 6),
        ]
    elif log.has_navigation and len(valid_fixes(log)[0]):
        length = track_length_km(log)
        section["track_length_km"] = round(length, 3)
        if range_m:
            section["area_covered_km2"] = round(length * 2 * range_m / 1000.0, 4)
        section["bbox"] = track_bbox(log)
    return section
