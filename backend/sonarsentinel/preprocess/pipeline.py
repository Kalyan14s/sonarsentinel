"""Preprocessing stages S2–S7 for one chunk of a waterfall log.

``SonarLog`` chunk → navigation cleaning (S2) → dropout repair + bottom tracking (S3, S6) → gain
(S4) → slant-range correction and along-track resampling (S5) → quality masks (S6) → 3-channel
image (S7). Parameters come from ``pipeline.yaml``. See ``docs/architecture/02-data-pipeline.md``.
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass, field
from typing import Any

import numpy as np
import numpy.typing as npt
import pandas as pd

from sonarsentinel.errors import ValidationError
from sonarsentinel.geo.georef import GeoFrame
from sonarsentinel.geo.navigation import clean_navigation
from sonarsentinel.ingest.chunking import iter_chunks
from sonarsentinel.ingest.models import SonarLog
from sonarsentinel.preprocess.bottom import (
    NO_ALTITUDE_BOTTOM_TRACKED,
    resolve_altitude,
    track_bottom,
)
from sonarsentinel.preprocess.channels import to_three_channel
from sonarsentinel.preprocess.dropout import DROPOUT, detect_dropouts, repair_dropouts
from sonarsentinel.preprocess.gain import normalize_gain
from sonarsentinel.preprocess.geometry import (
    along_track_rows,
    build_ground_image,
    ground_bins,
    near_nadir_columns,
    slant_to_ground,
)
from sonarsentinel.preprocess.motion import HIGH_MOTION, flag_segments, motion_flags


@dataclass
class ProcessedChunk:
    """Output of stages S2–S7 for one chunk (``docs/architecture/02-data-pipeline.md`` §2)."""

    chunk_id: int
    ping_offset: int
    image: npt.NDArray[np.uint8]
    image_3ch: npt.NDArray[np.uint8]
    row_to_ping: npt.NDArray[np.int64]  # global ping index per image row
    ground_res_m: float
    nadir_col: int
    masks: dict[str, npt.NDArray[np.bool_]]  # "dropout"/"motion" per row, "near_nadir" per column
    nav: pd.DataFrame  # cleaned navigation for this chunk's pings
    altitude_m: npt.NDArray[np.float64]
    geotagged: bool
    warnings: list[str] = field(default_factory=list)
    quality_events: list[dict[str, Any]] = field(default_factory=list)

    def geo_frame(self) -> GeoFrame:
        """Geometry for :func:`sonarsentinel.geo.georef.pixels_to_latlon` on this image."""
        if not self.geotagged:
            raise ValidationError("Chunk has no navigation (NOT_GEOTAGGED)")
        return GeoFrame(
            lat=self.nav["lat"].to_numpy(np.float64),
            lon=self.nav["lon"].to_numpy(np.float64),
            heading_deg=self.nav["heading_deg"].to_numpy(np.float64),
            row_to_ping=self.row_to_ping - self.ping_offset,
            nadir_col=self.nadir_col,
            ground_res_m=self.ground_res_m,
        )


def _add(warnings: list[str], codes: list[str] | str) -> None:
    for code in [codes] if isinstance(codes, str) else codes:
        if code not in warnings:
            warnings.append(code)


def preprocess_chunk(
    log: SonarLog, config: dict[str, Any], *, chunk_id: int = 0, ping_offset: int = 0
) -> ProcessedChunk:
    """Run stages S2–S7 on a waterfall log (usually one chunk from :func:`iter_chunks`)."""
    if log.port is None and log.starboard is None:
        raise ValidationError("Preprocessing needs a waterfall log with port/starboard channels")
    pre = config["preprocess"]
    navcfg = config["navigation"]
    res = float(pre["ground_resolution_m"])
    warnings = list(log.warnings)
    n = log.n_pings

    nav = log.nav
    geotagged = log.has_navigation
    if geotagged:
        cleaned = clean_navigation(
            nav,
            max_speed_mps=navcfg["max_speed_mps"],
            smoothing_window=navcfg["smoothing_window_pings"],
            heading_window=navcfg["heading_smoothing_window_pings"],
        )
        nav = cleaned.nav
        _add(warnings, cleaned.warnings)

    motion = motion_flags(nav, **pre["motion"])
    dropout = detect_dropouts(
        log.port, log.starboard, min_row_std_ratio=pre["dropout"]["min_row_std_ratio"]
    )
    repaired = repair_dropouts(
        log.port, log.starboard, dropout, max_gap=pre["dropout"]["max_inpaint_gap_pings"]
    )

    slant = nav["slant_range_m"].to_numpy(np.float64)
    has_geometry = np.isfinite(slant).any() and not log.ground_range_corrected
    altitude = nav["altitude_m"].to_numpy(np.float64)
    if has_geometry:
        slant = np.where(np.isfinite(slant), slant, np.nanmedian(slant))
        bt = pre["bottom_tracking"]
        track = track_bottom(
            repaired.port,
            repaired.starboard,
            slant,
            threshold_k=bt["threshold_k"],
            median_window=bt["median_window"],
        )
        altitude, used_tracking = resolve_altitude(altitude, track.altitude_m, mode=bt["enabled"])
        if used_tracking.any():
            _add(warnings, NO_ALTITUDE_BOTTOM_TRACKED)

    gain = normalize_gain(
        repaired.port,
        repaired.starboard,
        along_track_window_pings=pre["gain"]["along_track_window_pings"],
        per_side=pre["gain"]["per_side"],
        clip_percentiles=pre["gain"]["clip_percentiles"],
    )

    if has_geometry:
        n_ground = ground_bins(slant, altitude, res) + 1
        sides = [
            None
            if s is None
            else slant_to_ground(s, slant, altitude, ground_res_m=res, n_ground=n_ground)
            for s in (gain.port, gain.starboard)
        ]
        local_rows = along_track_rows(nav["lat"], nav["lon"], res) if geotagged else np.arange(n)
        image_f, nadir_col = build_ground_image(sides[0], sides[1], local_rows)
        image = np.asarray(np.clip(np.rint(image_f), 0, 255), dtype=np.uint8)
    else:
        local_rows = np.arange(n, dtype=np.int64)
        width = max(s.shape[1] for s in (gain.port, gain.starboard) if s is not None)
        image = np.zeros((n, 2 * width), dtype=np.uint8)
        if gain.port is not None:
            image[:, : gain.port.shape[1]][:, ::-1] = gain.port
        if gain.starboard is not None:
            image[:, width : width + gain.starboard.shape[1]] = gain.starboard
        nadir_col = width

    median_alt = float(np.nanmedian(altitude)) if np.isfinite(altitude).any() else 0.0
    masks = {
        "dropout": repaired.masked[local_rows],
        "motion": motion.any[local_rows],
        "near_nadir": near_nadir_columns(image.shape[1], nadir_col, res, median_alt),
    }
    events: list[dict[str, Any]] = []
    for code, flags in ((DROPOUT, repaired.masked), (HIGH_MOTION, motion.any)):
        segments = flag_segments(flags)
        if segments:
            _add(warnings, code)
        events += [
            {"code": code, "ping_start": s + ping_offset, "ping_end": e + ping_offset}
            for s, e in segments
        ]

    return ProcessedChunk(
        chunk_id=chunk_id,
        ping_offset=ping_offset,
        image=image,
        image_3ch=to_three_channel(
            image, lee_window=pre["despeckle"]["window"], std_window=pre["local_std_window"]
        ),
        row_to_ping=np.asarray(local_rows, dtype=np.int64) + ping_offset,
        ground_res_m=res,
        nadir_col=int(nadir_col),
        masks=masks,
        nav=nav,
        altitude_m=np.asarray(altitude, dtype=np.float64),
        geotagged=geotagged,
        warnings=warnings,
        quality_events=events,
    )


def preprocess_log(log: SonarLog, config: dict[str, Any]) -> Iterator[ProcessedChunk]:
    """Split a log into overlapping chunks (``chunking`` config) and preprocess each one."""
    chunking = config["chunking"]
    for i, (offset, chunk) in enumerate(
        iter_chunks(log, chunking["pings_per_chunk"], chunking["overlap_pings"])
    ):
        yield preprocess_chunk(chunk, config, chunk_id=i, ping_offset=offset)
