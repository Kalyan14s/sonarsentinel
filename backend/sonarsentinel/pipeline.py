"""Processing orchestrator (ST-075): sonar files → schema-valid report.

Stages ``validate → parse → preprocess → detect → score → geotag → merge → report``
(``docs/architecture/01-system-architecture.md`` §6). Waterfall inputs are processed chunk by
chunk (layback → preprocess → tiles → detector → in-chunk merge → measurement, shadow, features,
quality flags and chips), then duplicates from chunk overlaps are removed and detections are
scored and numbered in ping order. :func:`run_survey` combines several lines and clusters objects
seen on more than one line (ST-038). Events (``progress``, ``track``, ``warning``, ``detection``,
``detection_update``, ``detection_removed``, ``done``) go to ``on_event`` in the WebSocket message
shape of the API spec §3.

Scoring (ST-060…065, ADR-017): ``fused`` is the weighted mean of the detector, anomaly, shadow,
FP-filter and persistence scores that are available, minus dropout and motion penalties;
``confidence = 100 × calibrator(fused)`` when an isotonic calibrator is configured (identity
otherwise). Same input and configuration give the same report apart from ``generated_utc`` and
``duration_s`` (NFR-16).
"""

from __future__ import annotations

import math
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass, replace
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
from sonarsentinel.geo.cluster import cluster_detections, persistence_score
from sonarsentinel.geo.georef import raster_pixels_to_latlon
from sonarsentinel.geo.layback import LAYBACK_ESTIMATED, resolve_layback
from sonarsentinel.geo.measure import ImageGeometry, measure_mask, order_clockwise
from sonarsentinel.geo.track import track_bbox, track_length_km, valid_fixes
from sonarsentinel.ingest.chunking import chunk_ranges
from sonarsentinel.ingest.models import NOT_GEOTAGGED, SHIP_POSITION_ONLY, SonarLog
from sonarsentinel.ingest.reader import read_source
from sonarsentinel.preprocess.bottom import NO_ALTITUDE_BOTTOM_TRACKED
from sonarsentinel.preprocess.channels import to_three_channel
from sonarsentinel.preprocess.pipeline import preprocess_log
from sonarsentinel.preprocess.tiling import Tile, iter_tiles, row_col_mask
from sonarsentinel.report.builder import alert_tier, build_report, iso_utc
from sonarsentinel.report.chips import chip_url, remove_chips, rename_chips, write_chips
from sonarsentinel.scoring.features import detection_features
from sonarsentinel.scoring.fusion import (
    IDENTITY_CALIBRATOR,
    FpFilter,
    IsotonicCalibrator,
    fuse,
    load_calibrator,
    load_fp_filter,
)
from sonarsentinel.scoring.shadow import ShadowResult, shadow_score

EventCallback = Callable[[dict[str, Any]], None]
CALIBRATOR_VERSION = IDENTITY_CALIBRATOR
BATCH_TILES = 8


class PipelineCancelled(Exception):  # noqa: N818 - name is part of the jobs contract
    """Raised when ``should_cancel()`` returns True at a progress checkpoint (ST-082)."""


class _Events:
    """Numbered job events; ``progress`` events double as cancellation checkpoints.

    Waterfall inputs emit a ``progress`` event after every chunk, so a cancel request stops the
    job within one chunk.
    """

    def __init__(
        self, callback: EventCallback | None, should_cancel: Callable[[], bool] | None = None
    ) -> None:
        self.callback = callback
        self.should_cancel = should_cancel
        self.seq = 0

    def __call__(self, kind: str, **payload: Any) -> None:
        if self.callback is not None:
            self.seq += 1
            ts = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
            self.callback({"type": kind, "seq": self.seq, "ts": ts, **payload})
        if kind == "progress" and self.should_cancel is not None and self.should_cancel():
            raise PipelineCancelled("Job cancelled")


@dataclass
class _Scoring:
    """Fusion weights, penalties, tiers and the optional calibrator and FP filter."""

    weights: dict[str, float]
    penalties: dict[str, float]
    tiers: dict[str, float]
    anomaly_threshold: float
    calibrator: IsotonicCalibrator | None
    fp_filter: FpFilter | None

    @classmethod
    def from_config(cls, cfg: dict[str, Any]) -> _Scoring:
        scoring = cfg["scoring"]
        return cls(
            weights={k: float(v) for k, v in scoring["weights"].items()},
            penalties={k: float(v) for k, v in scoring["penalties"].items()},
            tiers={k: float(v) for k, v in scoring["tiers"].items()},
            anomaly_threshold=float(cfg.get("anomaly", {}).get("threshold", 0.5)),
            calibrator=load_calibrator(cfg),
            fp_filter=load_fp_filter(cfg),
        )

    @property
    def calibrator_version(self) -> str:
        return self.calibrator.describe() if self.calibrator is not None else IDENTITY_CALIBRATOR

    def apply(self, det: dict[str, Any]) -> None:
        """Set ``scores.fused``, ``confidence`` and ``alert_tier`` from the score breakdown."""
        scores = det["scores"]
        fused = fuse(
            scores,
            self.weights,
            dropout_penalty=float(scores.get("dropout_penalty", 0.0)),
            motion_penalty=float(scores.get("motion_penalty", 0.0)),
        )
        scores["fused"] = round(fused, 6)
        calibrated = self.calibrator(fused) if self.calibrator is not None else fused
        det["confidence"] = round(100.0 * calibrated, 1)
        det["alert_tier"] = alert_tier(
            det["confidence"],
            self.tiers,
            anomaly_score=scores.get("anomaly"),
            anomaly_threshold=self.anomaly_threshold,
        )


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
    should_cancel: Callable[[], bool] | None = None,
    work_dir: str | Path | None = None,
    results_dir: str | Path | None = None,
    apply_layback: str | bool | None = None,
    manual_layback_m: float | None = None,
    first_detection_number: int = 1,
) -> dict[str, Any]:
    """Process one file and return the report dictionary (schema ``report-1.0``).

    Args:
        should_cancel: Polled at every progress event; True stops the run with
            :class:`PipelineCancelled`.
        results_dir: When given, detection chips are written to
            ``<results_dir>/<survey_id>/chips/`` and ``chip_url`` is filled.
        apply_layback: Overrides ``navigation.apply_layback`` (``auto`` | ``true`` | ``false``).
        manual_layback_m: Operator layback in metres; wins over file values and estimates.
        first_detection_number: Number of the first detection ID (surveys with several lines).
    """
    cfg = config if config is not None else load_config()
    started = time.perf_counter()
    model: Detector = detector if detector is not None else BrightTargetDetector()
    scoring = _Scoring.from_config(cfg)
    emit = _Events(on_event, should_cancel)
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
    layback_estimated = _apply_layback(log, cfg, apply_layback, manual_layback_m)
    emit("progress", stage="parse", percent=5.0, pings_done=0, pings_total=log.n_pings)
    sid = survey_id or _survey_id(log)
    chips_dir = Path(results_dir) / sid / "chips" if results_dir is not None else None

    if log.source_format == "geotiff":
        found, quality = _detect_geotiff(log, cfg, model, chips_dir)
    else:
        found, quality = _detect_waterfall(
            log, cfg, model, emit, anomaly_model, chips_dir, layback_estimated
        )

    emit("progress", stage="merge", percent=90.0)
    unique = dedupe_across_chunks(found)
    if chips_dir is not None:
        kept = {sd.extra.get("chip_key") for sd in unique}
        for sd in found:
            key = sd.extra.get("chip_key")
            if key and key not in kept:
                remove_chips(chips_dir, key)
    detections = _finalise(
        unique,
        log,
        sid,
        min_conf,
        describe(model),
        scoring,
        chips_dir,
        first_detection_number,
    )
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
                "fp_filter": scoring.fp_filter.describe() if scoring.fp_filter else None,
                "calibrator": scoring.calibrator_version,
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


def run_survey(
    sources: Sequence[str | Path],
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
    should_cancel: Callable[[], bool] | None = None,
    work_dir: str | Path | None = None,
    results_dir: str | Path | None = None,
    apply_layback: str | bool | None = None,
    manual_layback_m: float | None = None,
) -> dict[str, Any]:
    """Process every line of one survey into one report (API uploads, ST-081/082).

    Files run through :func:`run_pipeline` in upload order with survey-wide detection numbers.
    Survey and quality sections are combined, and events keep one ``seq`` sequence with
    ``percent`` spread over the files. Afterwards the same object seen on several lines is merged
    (ST-038): a ``detection_removed`` event names each merged-away detection and a
    ``detection_update`` event carries the kept one with its new ``n_views`` and confidence.
    ``nav_csv`` applies to image inputs only.
    """
    from sonarsentinel.errors import ValidationError

    paths = [Path(s) for s in sources]
    if not paths:
        raise ValidationError("No input files", field="files")
    cfg = config if config is not None else load_config()
    started = time.perf_counter()
    emit = _Events(on_event, should_cancel)
    reports: list[dict[str, Any]] = []
    detections: list[dict[str, Any]] = []
    sid = survey_id

    for index, path in enumerate(paths):

        def relay(event: dict[str, Any], index: int = index) -> None:
            if event["type"] == "done":
                return  # one done event for the whole survey
            payload = {k: v for k, v in event.items() if k not in ("type", "seq", "ts")}
            if event["type"] == "progress":
                share = float(payload.get("percent", 0.0)) / 100.0
                payload["percent"] = round(100.0 * (index + share) / len(paths), 1)
            emit(event["type"], **payload)

        report = run_pipeline(
            path,
            config=cfg,
            nav_csv=None if path.suffix.lower() == ".xtf" else nav_csv,
            epsg=epsg,
            allow_no_gps=allow_no_gps,
            detector=detector,
            anomaly_model=anomaly_model,
            survey_id=sid,
            survey_name=survey_name,
            min_conf=min_conf,
            on_event=relay,
            should_cancel=should_cancel,
            work_dir=work_dir,
            results_dir=results_dir,
            apply_layback=apply_layback,
            manual_layback_m=manual_layback_m,
            first_detection_number=len(detections) + 1,
        )
        sid = report["survey"]["survey_id"]
        detections.extend(report["detections"])
        reports.append(report)

    scoring = _Scoring.from_config(cfg)
    radius = float(cfg.get("geo", {}).get("cluster_radius_m", 5.0))
    clustered = cluster_detections(detections, radius_m=radius)
    for removed_id, kept_id in clustered.removed.items():
        if results_dir is not None and sid:
            remove_chips(Path(results_dir) / sid / "chips", removed_id)
        emit("detection_removed", detection_id=removed_id, merged_into=kept_id)
    for det in clustered.detections:
        if det["n_views"] > 1:
            scoring.apply(det)
            emit("detection_update", detection=det)

    report = build_report(
        survey=_combine_surveys([r["survey"] for r in reports]),
        processing=_combine_processing(
            [r["processing"] for r in reports], round(time.perf_counter() - started, 2)
        ),
        detections=clustered.detections,
    )
    status = (
        "completed_with_warnings" if report["processing"]["quality"]["warnings"] else "completed"
    )
    emit("done", status=status, summary=report["summary"])
    return report


def _sum_or_none(values: list[float | None]) -> float | None:
    present = [v for v in values if v is not None]
    return round(sum(present), 4) if present else None


def _combine_surveys(sections: list[dict[str, Any]]) -> dict[str, Any]:
    survey = dict(sections[0])
    survey["source_files"] = [f for s in sections for f in s["source_files"]]
    starts = [s["start_utc"] for s in sections if s["start_utc"]]
    ends = [s["end_utc"] for s in sections if s["end_utc"]]
    survey["start_utc"] = min(starts) if starts else None  # ISO 8601 UTC strings sort in time order
    survey["end_utc"] = max(ends) if ends else None
    survey["track_length_km"] = _sum_or_none([s["track_length_km"] for s in sections])
    survey["area_covered_km2"] = _sum_or_none([s["area_covered_km2"] for s in sections])
    boxes = [s["bbox"] for s in sections if s["bbox"]]
    survey["bbox"] = (
        [
            min(b[0] for b in boxes),
            min(b[1] for b in boxes),
            max(b[2] for b in boxes),
            max(b[3] for b in boxes),
        ]
        if boxes
        else None
    )
    return survey


def _combine_processing(sections: list[dict[str, Any]], duration_s: float) -> dict[str, Any]:
    processing = dict(sections[0])
    quality = [s["quality"] for s in sections]
    processing["duration_s"] = duration_s
    processing["quality"] = {
        "dropout_pings": sum(q["dropout_pings"] for q in quality),
        "high_motion_pings": sum(q["high_motion_pings"] for q in quality),
        "bottom_tracked": any(q["bottom_tracked"] for q in quality),
        "layback_estimated": any(q["layback_estimated"] for q in quality),
        "warnings": sorted({w for q in quality for w in q["warnings"]}),
    }
    return processing


def _survey_id(log: SonarLog) -> str:
    times = log.nav["time_utc"].dropna()
    day = times.min().strftime("%Y%m%d") if len(times) else datetime.now(UTC).strftime("%Y%m%d")
    return f"SRV-{day}-001"


def _apply_layback(
    log: SonarLog, cfg: dict[str, Any], mode: str | bool | None, manual_m: float | None
) -> bool:
    """Move ship positions to the towfish (ST-034); True when the layback was estimated."""
    if log.source_format == "geotiff" or not log.has_navigation or not len(log.nav):
        return False
    nav_cfg = cfg.get("navigation", {})
    manual = manual_m if manual_m is not None else nav_cfg.get("manual_layback_m")
    result = resolve_layback(
        log.nav,
        mode=mode if mode is not None else nav_cfg.get("apply_layback", "auto"),
        manual_layback_m=float(manual) if manual is not None else None,
        ship_position_only=SHIP_POSITION_ONLY in log.warnings,
        tow_point_height_m=float(nav_cfg.get("tow_point_height_m", 0.0)),
        antenna_to_tow_point_m=float(nav_cfg.get("antenna_to_tow_point_m", 0.0)),
    )
    if not result.applied:
        return False
    nav = log.nav.copy()
    nav["lat"] = result.lat
    nav["lon"] = result.lon
    log.nav = nav
    return result.estimated


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


def _anomaly_stats(
    heat: npt.NDArray[np.float32] | None, det: RawDetection, pixel_threshold: float
) -> tuple[float | None, float | None]:
    """Mean and max heat inside the mask relative to twice the pixel threshold (0–1)."""
    if heat is None or pixel_threshold <= 0:
        return None, None
    x1, y1, x2, y2 = det.box
    values = heat[y1:y2, x1:x2][det.full_mask()]
    if not values.size:
        return None, None
    scale = 2.0 * pixel_threshold
    return (
        round(float(np.clip(values.mean() / scale, 0.0, 1.0)), 4),
        round(float(np.clip(values.max() / scale, 0.0, 1.0)), 4),
    )


def _detect_waterfall(
    log: SonarLog,
    cfg: dict[str, Any],
    model: Detector,
    emit: _Events,
    anomaly_model: Any | None = None,
    chips_dir: Path | None = None,
    layback_estimated: bool = False,
) -> tuple[list[SurveyDetection], dict[str, Any]]:
    tiling = cfg["tiling"]
    min_raw = float(cfg["detection"]["min_raw_score"])
    chip_px = int(cfg.get("report", {}).get("chip_size_px", 256))
    pixel_threshold = float(getattr(anomaly_model, "pixel_threshold", 0.0) or 0.0)
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
                pixel_threshold,
                min_area_px=min_px,
                exclude_boxes=[d.box for d in merged],
            )

        geometry = chunk.image_geometry()
        n_local = len(chunk.nav)
        chunk_range = (chunk.ping_offset, chunk.ping_offset + n_local - 1)
        nav_source = chunk.nav["nav_source"].to_numpy(dtype=object)
        headings = chunk.nav["heading_deg"].to_numpy(np.float64)
        texture = chunk.image_3ch[..., 2]
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
            mask = det.full_mask()
            m = measure_mask(mask, geometry, row0=y1, col0=x1)
            local = chunk.row_to_ping[y1:y2] - chunk.ping_offset
            flags = []
            if chunk.masks["dropout"][y1:y2].any():
                flags.append("DROPOUT")
            if chunk.masks["motion"][y1:y2].any():
                flags.append("HIGH_MOTION")
            altitude = chunk.altitude_m[local]
            finite_altitude = altitude[np.isfinite(altitude)]
            altitude_m = float(np.median(finite_altitude)) if finite_altitude.size else None
            if altitude_m is not None and m.ground_range_m < 0.3 * altitude_m:
                flags.append("NEAR_NADIR")
            if (nav_source[local] == "interpolated").any():
                flags.append("GPS_INTERPOLATED")
            if NO_ALTITUDE_BOTTOM_TRACKED in chunk.warnings:
                flags.append(NO_ALTITUDE_BOTTOM_TRACKED)
            if not chunk.geotagged:
                flags.append(NOT_GEOTAGGED)
            if x1 <= 0 or x2 >= width:
                flags.append("TILE_EDGE")  # cut by the swath edge (ADR-017 §5)
            if layback_estimated:
                flags.append(LAYBACK_ESTIMATED)

            dropout_fraction = float(chunk.masks["dropout"][y1:y2].mean())
            shadow = shadow_score(
                chunk.image,
                mask,
                det.box,
                nadir_col=chunk.nadir_col,
                ground_res_m=chunk.ground_res_m,
                altitude_m=altitude_m,
            )
            anomaly_mean, anomaly_max = _anomaly_stats(heat, det, pixel_threshold)
            features = detection_features(
                chunk.image,
                mask,
                det.box,
                cls=det.cls,
                detector_score=float(det.score),
                shadow=shadow,
                length_m=m.length_m,
                width_m=m.width_m,
                area_m2=m.area_m2,
                orientation_deg=m.orientation_deg,
                heading_deg=float(headings[m.ping - chunk.ping_offset]),
                anomaly_mean=anomaly_mean,
                anomaly_max=anomaly_max,
                texture=texture,
                dropout_fraction=dropout_fraction,
                motion="HIGH_MOTION" in flags,
                near_nadir="NEAR_NADIR" in flags,
                ground_range_m=m.ground_range_m,
            )
            chip_key = None
            if chips_dir is not None:
                chip_key = f"_tmp_{chunk.chunk_id}_{len(found)}"
                write_chips(
                    chips_dir,
                    chip_key,
                    chunk.image,
                    det.box,
                    mask,
                    size_px=chip_px,
                    heat=heat,
                    heat_scale=2.0 * pixel_threshold if pixel_threshold > 0 else 1.0,
                    shadow_band=shadow.band,
                )
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
                        "dropout_fraction": dropout_fraction,
                        "time_utc": iso_utc(chunk.nav["time_utc"].iloc[m.ping - chunk.ping_offset]),
                        "pixel_bbox": [int(x1), int(y1), int(x2), int(y2)],
                        "side": m.side,
                        "anomaly_score": anomaly_mean,
                        "shadow": shadow,
                        "features": features,
                        "chip_key": chip_key,
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
        "layback_estimated": layback_estimated,
        "warnings": sorted(warnings),
    }
    return found, quality


def _detect_geotiff(
    log: SonarLog, cfg: dict[str, Any], model: Detector, chips_dir: Path | None = None
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
    chip_px = int(cfg.get("report", {}).get("chip_size_px", 256))
    found: list[SurveyDetection] = []
    min_raw = float(cfg["detection"]["min_raw_score"])
    for det in merged:
        if det.score < min_raw:
            continue
        x1, y1, x2, y2 = det.box
        mask = det.full_mask()
        m = measure_mask(mask, geometry, row0=y1, col0=x1)
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
        chip_key = None
        if chips_dir is not None:
            chip_key = f"_tmp_g_{len(found)}"
            write_chips(chips_dir, chip_key, u8, det.box, mask, size_px=chip_px)
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
                    "anomaly_score": None,
                    "shadow": None,
                    "features": None,
                    "chip_key": chip_key,
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
    survey_id: str,
    min_conf: float | None,
    model_version: str,
    scoring: _Scoring,
    chips_dir: Path | None,
    first_number: int = 1,
) -> list[dict[str, Any]]:
    """Score, filter, number and serialise detections in ping order."""
    ordered = sorted(unique, key=lambda d: (d.ping_start, d.across_start_m, d.detection.cls))
    fp_scores: list[float | None] = [None] * len(ordered)
    if scoring.fp_filter is not None:
        with_features = [i for i, sd in enumerate(ordered) if sd.extra.get("features")]
        predicted = scoring.fp_filter.predict([ordered[i].extra["features"] for i in with_features])
        for i, value in zip(with_features, predicted, strict=True):
            fp_scores[i] = value

    detections: list[dict[str, Any]] = []
    for sd, fp_score in zip(ordered, fp_scores, strict=True):
        flags = sorted(set(sd.extra["flags"]))
        shadow: ShadowResult | None = sd.extra.get("shadow")
        scores: dict[str, float] = {"detector": round(float(sd.detection.score), 4)}
        if sd.extra.get("anomaly_score") is not None:
            scores["anomaly"] = float(sd.extra["anomaly_score"])
        if shadow is not None:
            scores["shadow"] = shadow.score
        if fp_score is not None:
            scores["fp_filter"] = fp_score
        scores["persistence"] = persistence_score(1)
        scores["dropout_penalty"] = round(
            scoring.penalties["dropout"] * float(sd.extra["dropout_fraction"]), 4
        )
        scores["motion_penalty"] = scoring.penalties["motion"] if "HIGH_MOTION" in flags else 0.0

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
        det: dict[str, Any] = {
            "detection_id": "",
            "class": sd.detection.cls,
            "confidence": 0.0,
            "alert_tier": "hidden",
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
                "height_m": shadow.height_m if shadow is not None else None,
            },
            "orientation_deg": m.orientation_deg,
            "sonar_ref": sonar_ref,
            "scores": scores,
            "quality_flags": flags,
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
        scoring.apply(det)
        key = sd.extra.get("chip_key")
        if min_conf is not None and det["confidence"] < min_conf:
            if chips_dir is not None and key:
                remove_chips(chips_dir, key)
            continue
        det["detection_id"] = f"{survey_id}-D{first_number + len(detections):04d}"
        if chips_dir is not None and key and rename_chips(chips_dir, key, det["detection_id"]):
            det["chip_url"] = chip_url(det["detection_id"])
        detections.append(det)
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
