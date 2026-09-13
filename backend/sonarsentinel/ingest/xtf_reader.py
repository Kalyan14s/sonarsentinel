"""XTF reader (ST-021) with optional memory-mapped sample storage (ST-026).

Reading happens in two passes so the whole file never has to be in memory:

1. :func:`scan_xtf` walks packet headers only, records the file offset of every complete sonar
   ping and the largest sample count per channel, and detects a truncated tail.
2. :func:`read_xtf` allocates the port/starboard arrays (``numpy.memmap`` files in ``work_dir``
   when given) and fills them ping by ping, collecting navigation into ``NAV_COLUMNS``.

Conventions (XTF rev. X26/X42): ``NavUnits`` 0 = metres (projected), 3 = lat/lon; ``SensorSpeed``
is in knots. The specification says odd-numbered side-scan channels have their sample order
reversed, which in practice means the port channel is stored far range first (confirmed on USGS
Klein 3900 files). Writers differ, so by default the order is detected by correlating the port and
starboard range profiles (:func:`detect_port_order`); pass ``port_order`` to override. Output
arrays always have sample 0 at nadir. See ``docs/architecture/02-data-pipeline.md`` S1.
"""

from __future__ import annotations

import ctypes
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, BinaryIO, Literal

import numpy as np
import numpy.typing as npt
import pandas as pd

from sonarsentinel.errors import CorruptHeaderError
from sonarsentinel.geo.units import to_wgs84
from sonarsentinel.ingest.models import (
    NO_NAVIGATION,
    SHIP_POSITION_ONLY,
    TRUNCATED_FILE,
    ChannelLayout,
    SonarInfo,
    SonarLog,
    empty_nav,
)

XTF_FILE_FORMAT = 0x7B
XTF_MAGIC = 0xFACE
HEADER_TYPE_SONAR = 0
CHANNEL_TYPE_PORT = 1
CHANNEL_TYPE_STBD = 2
KNOTS_TO_MPS = 1852.0 / 3600.0

#: Warning added when the port sample order couldn't be detected and the default was used.
PORT_ORDER_ASSUMED = "PORT_ORDER_ASSUMED"

PortOrder = Literal["auto", "far_first", "nadir_first"]

_SAMPLE_FORMAT_DTYPE: dict[int, Any] = {2: np.uint32, 3: np.uint16, 5: np.float32, 8: np.uint8}
_BYTES_DTYPE: dict[int, Any] = {1: np.uint8, 2: np.uint16, 4: np.uint32}
_NAV_FIELDS = (
    "sensor_x",
    "sensor_y",
    "ship_x",
    "ship_y",
    "heading_deg",
    "altitude_m",
    "sensor_depth_m",
    "speed_kn",
    "roll_deg",
    "pitch_deg",
    "slant_range_m",
    "cable_out_m",
    "layback_m",
)


@dataclass(frozen=True)
class _Types:
    """pyxtf ctypes structures and their sizes (pyxtf is in the ``geo`` extra)."""

    file_header: Any
    packet_start: Any
    ping_header: Any
    chan_header: Any

    @property
    def ping_size(self) -> int:
        return ctypes.sizeof(self.ping_header)

    @property
    def chan_size(self) -> int:
        return ctypes.sizeof(self.chan_header)


def _types() -> _Types:
    from pyxtf import XTFFileHeader, XTFPacketStart, XTFPingChanHeader, XTFPingHeader

    return _Types(XTFFileHeader, XTFPacketStart, XTFPingHeader, XTFPingChanHeader)


@dataclass(frozen=True)
class ChannelSpec:
    """One side-scan channel as described in the file header."""

    index: int  # position within each ping's channel list
    side: str  # "port" | "starboard"
    bytes_per_sample: int
    dtype: Any
    frequency_khz: float | None
    name: str


@dataclass
class XtfScan:
    """Result of the header-only pass over an XTF file."""

    path: Path
    file_header: Any
    header_size: int
    nav_units: int
    sonar_name: str
    n_sonar_channels: int
    port: ChannelSpec | None
    starboard: ChannelSpec | None
    ping_offsets: npt.NDArray[np.int64]
    max_samples: dict[str, int] = field(default_factory=dict)
    truncated: bool = False

    @property
    def n_pings(self) -> int:
        return int(len(self.ping_offsets))

    @property
    def layout(self) -> ChannelLayout:
        if self.port and self.starboard:
            return "port_stbd"
        return "port_only" if self.port else "stbd_only"

    @property
    def channels(self) -> dict[int, ChannelSpec]:
        return {c.index: c for c in (self.port, self.starboard) if c is not None}


def _decode(raw: bytes) -> str:
    return raw.split(b"\x00", 1)[0].decode("ascii", errors="replace").strip()


def _read_exact(fh: BinaryIO, n: int) -> bytes:
    data = fh.read(n)
    return data if len(data) == n else b""


def _bytes_per_sample(header: Any, i: int) -> int:
    return int(header.ChanInfo[min(i, 5)].BytesPerSample) or 2


def _sample_count(chan: Any, header: Any, i: int) -> int:
    # NumSamples replaced ChanInfo.Reserved (old SamplesPerChannel); fall back for old files.
    return int(chan.NumSamples) or int(header.ChanInfo[min(i, 5)].Reserved)


def _channel_specs(
    header: Any, channels: tuple[int, int] | None
) -> tuple[ChannelSpec | None, ChannelSpec | None, int]:
    """Pick the port and starboard channels (lowest-numbered pair unless ``channels`` is given)."""
    n_sonar = int(header.NumberOfSonarChannels)
    infos = [header.ChanInfo[i] for i in range(min(n_sonar, 6))]

    def spec(i: int, side: str) -> ChannelSpec:
        info = infos[i]
        nbytes = int(info.BytesPerSample) or 2
        dtype = _SAMPLE_FORMAT_DTYPE.get(int(info.SampleFormat)) or _BYTES_DTYPE.get(nbytes)
        if dtype is None or np.dtype(dtype).itemsize != nbytes:
            raise CorruptHeaderError(
                f"Unsupported sample format in channel {i}",
                channel=i,
                bytes_per_sample=nbytes,
                sample_format=int(info.SampleFormat),
            )
        freq = float(info.Frequency)
        return ChannelSpec(
            index=i,
            side=side,
            bytes_per_sample=nbytes,
            dtype=dtype,
            frequency_khz=freq if freq > 0 else None,
            name=_decode(bytes(info.ChannelName)),
        )

    if channels is not None:
        for i in channels:
            if not 0 <= i < len(infos):
                raise CorruptHeaderError(f"Channel {i} is not in the file", channel=i)
        return spec(channels[0], "port"), spec(channels[1], "starboard"), n_sonar

    port_i = next((i for i, c in enumerate(infos) if c.TypeOfChannel == CHANNEL_TYPE_PORT), None)
    stbd_i = next((i for i, c in enumerate(infos) if c.TypeOfChannel == CHANNEL_TYPE_STBD), None)
    if port_i is None and stbd_i is None and len(infos) >= 2:
        port_i, stbd_i = 0, 1  # spec: channel 0 is typically port and 1 starboard
    port = spec(port_i, "port") if port_i is not None else None
    stbd = spec(stbd_i, "starboard") if stbd_i is not None else None
    return port, stbd, n_sonar


def scan_xtf(path: str | Path, *, channels: tuple[int, int] | None = None) -> XtfScan:
    """Read the file header and index all complete sonar pings without reading samples.

    Raises:
        CorruptHeaderError: The file header is invalid, there are no side-scan channels, or no
            readable sonar ping.
    """
    t = _types()
    p = Path(path)
    size = p.stat().st_size
    start_size = ctypes.sizeof(t.packet_start)

    with p.open("rb") as fh:
        raw = _read_exact(fh, ctypes.sizeof(t.file_header))
        if not raw or raw[0] != XTF_FILE_FORMAT:
            raise CorruptHeaderError(f"{p.name} has no valid XTF file header", filename=p.name)
        header = t.file_header.from_buffer_copy(raw)
        port, stbd, n_sonar = _channel_specs(header, channels)
        if port is None and stbd is None:
            raise CorruptHeaderError(f"{p.name} has no side-scan sonar channels", filename=p.name)
        header_size = 1024 if header.channel_count() <= 6 else 2048
        by_index = {c.index: c for c in (port, stbd) if c is not None}

        offsets: list[int] = []
        max_samples = {"port": 0, "starboard": 0}
        truncated = False
        pos = header_size
        while pos < size:
            fh.seek(pos)
            raw_start = _read_exact(fh, start_size)
            if not raw_start:
                truncated = True
                break
            start = t.packet_start.from_buffer_copy(raw_start)
            n_bytes = int(start.NumBytesThisRecord)
            if start.MagicNumber != XTF_MAGIC or n_bytes < start_size or pos + n_bytes > size:
                truncated = True
                break
            if start.HeaderType == HEADER_TYPE_SONAR:
                counts = _index_ping(fh, pos, n_bytes, int(start.NumChansToFollow), header, t)
                if counts is None:
                    truncated = True
                    break
                for i, count in counts.items():
                    if i in by_index:
                        side = by_index[i].side
                        max_samples[side] = max(max_samples[side], count)
                offsets.append(pos)
            pos += n_bytes

    if not offsets:
        raise CorruptHeaderError(f"{p.name} contains no readable sonar pings", filename=p.name)
    return XtfScan(
        path=p,
        file_header=header,
        header_size=header_size,
        nav_units=int(header.NavUnits),
        sonar_name=_decode(bytes(header.SonarName)),
        n_sonar_channels=n_sonar,
        port=port,
        starboard=stbd,
        ping_offsets=np.asarray(offsets, dtype=np.int64),
        max_samples=max_samples,
        truncated=truncated,
    )


def _index_ping(
    fh: BinaryIO, pos: int, n_bytes: int, n_chans: int, header: Any, t: _Types
) -> dict[int, int] | None:
    """Sample count per channel of one ping, or None if the packet is malformed."""
    offset = pos + t.ping_size
    end = pos + n_bytes
    counts: dict[int, int] = {}
    for i in range(n_chans):
        if offset + t.chan_size > end:
            return None
        fh.seek(offset)
        raw = _read_exact(fh, t.chan_size)
        if not raw:
            return None
        count = _sample_count(t.chan_header.from_buffer_copy(raw), header, i)
        offset += t.chan_size + count * _bytes_per_sample(header, i)
        if offset > end:
            return None
        counts[i] = count
    return counts


def _read_ping(
    fh: BinaryIO, pos: int, scan: XtfScan, t: _Types
) -> tuple[Any, dict[str, tuple[npt.NDArray[Any], Any]]]:
    """Read one sonar ping: its header and ``{side: (samples as stored, channel header)}``."""
    fh.seek(pos)
    ping = t.ping_header.from_buffer_copy(fh.read(t.ping_size))
    by_index = scan.channels
    out: dict[str, tuple[npt.NDArray[Any], Any]] = {}
    for i in range(int(ping.NumChansToFollow)):
        chan = t.chan_header.from_buffer_copy(fh.read(t.chan_size))
        count = _sample_count(chan, scan.file_header, i)
        spec = by_index.get(i)
        if spec is None:
            fh.seek(count * _bytes_per_sample(scan.file_header, i), 1)
            continue
        samples = np.frombuffer(fh.read(count * spec.bytes_per_sample), dtype=spec.dtype)
        out[spec.side] = (samples, chan)
    return ping, out


def detect_port_order(
    scan: XtfScan, max_pings: int = 200, bins: int = 256, margin: float = 0.2
) -> str | None:
    """Guess how port samples are stored by comparing their range profile with starboard.

    Starboard is stored nadir first. Both sides see the same range-dependent intensity (water
    column, grazing angle, attenuation), so the mean log-intensity profile of port-as-stored
    correlates with the starboard profile when port is nadir first and with the *reversed*
    starboard profile when it is far first. This works in deep water (dark band at nadir) and in
    shallow water (brightest at nadir), unlike a darkest-end rule.

    Returns:
        ``"far_first"``, ``"nadir_first"``, or ``None`` without a starboard channel or when the
        two correlations differ by less than ``margin``.
    """
    if scan.port is None or scan.starboard is None:
        return None
    t = _types()
    port_profile = np.zeros(bins)
    stbd_profile = np.zeros(bins)
    used = 0
    rows = np.unique(np.linspace(0, scan.n_pings - 1, min(max_pings, scan.n_pings)).astype(int))
    with scan.path.open("rb") as fh:
        for row in rows:
            _, chans = _read_ping(fh, int(scan.ping_offsets[row]), scan, t)
            if "port" not in chans or "starboard" not in chans:
                continue
            port, stbd = chans["port"][0], chans["starboard"][0]
            if min(len(port), len(stbd)) < bins:
                continue
            port_profile += _range_profile(port, bins)
            stbd_profile += _range_profile(stbd, bins)
            used += 1
    if used == 0:
        return None
    same = _correlation(port_profile, stbd_profile)
    flipped = _correlation(port_profile, stbd_profile[::-1])
    if abs(same - flipped) < margin:
        return None
    return "nadir_first" if same > flipped else "far_first"


def _range_profile(samples: npt.NDArray[Any], bins: int) -> npt.NDArray[np.float64]:
    """Mean log intensity in ``bins`` equal slices over the whole range (needs ≥ bins samples)."""
    x = np.log1p(samples.astype(np.float64))
    edges = np.linspace(0, len(x), bins + 1).astype(np.int64)
    sums = np.add.reduceat(x, edges[:-1])
    return np.asarray(sums / np.diff(edges), dtype=np.float64)


def _correlation(a: npt.NDArray[np.float64], b: npt.NDArray[np.float64]) -> float:
    a = a - a.mean()
    b = b - b.mean()
    denom = float(np.sqrt((a * a).sum() * (b * b).sum()))
    return float((a * b).sum()) / denom if denom > 0 else 0.0


def read_xtf(
    path: str | Path,
    *,
    epsg: int | str | None = None,
    work_dir: str | Path | None = None,
    channels: tuple[int, int] | None = None,
    port_order: PortOrder = "auto",
) -> SonarLog:
    """Read an XTF side-scan file into a :class:`SonarLog`.

    Args:
        path: XTF file.
        epsg: CRS for projected navigation (``NavUnits`` = 0), e.g. ``32644``.
        work_dir: If given, samples are written to memory-mapped ``.npy`` files here instead of
            being held in RAM (use for large files, ST-026).
        channels: ``(port_index, starboard_index)`` to override automatic channel selection,
            e.g. ``(2, 3)`` for the high-frequency pair of a dual-frequency sonar.
        port_order: How port samples are stored: ``auto`` (detect), ``far_first`` or
            ``nadir_first``.

    Raises:
        CorruptHeaderError: Invalid file header or no readable pings.
        CrsRequiredError: Navigation is projected and no ``epsg`` was given.
    """
    scan = scan_xtf(path, channels=channels)
    t = _types()
    n = scan.n_pings
    specs = [c for c in (scan.port, scan.starboard) if c is not None]
    n_samples = max(scan.max_samples[c.side] for c in specs)
    warnings: list[str] = []

    reverse_port = False
    if scan.port is not None:
        order = port_order if port_order != "auto" else detect_port_order(scan)
        if order is None:
            order = "far_first"
            warnings.append(PORT_ORDER_ASSUMED)
        reverse_port = order == "far_first"

    arrays = {spec.side: _allocate(scan, spec, n_samples, work_dir) for spec in specs}
    fields = {name: np.full(n, np.nan) for name in _NAV_FIELDS}
    time_parts = np.zeros((n, 7), dtype=np.int64)

    with scan.path.open("rb") as fh:
        for row, pos in enumerate(scan.ping_offsets):
            ping, chans = _read_ping(fh, int(pos), scan, t)
            time_parts[row] = (
                ping.Year,
                ping.Month,
                ping.Day,
                ping.Hour,
                ping.Minute,
                ping.Second,
                ping.HSeconds,
            )
            fields["sensor_x"][row] = ping.SensorXcoordinate
            fields["sensor_y"][row] = ping.SensorYcoordinate
            fields["ship_x"][row] = ping.ShipXcoordinate
            fields["ship_y"][row] = ping.ShipYcoordinate
            fields["heading_deg"][row] = ping.SensorHeading
            fields["altitude_m"][row] = ping.SensorPrimaryAltitude
            fields["sensor_depth_m"][row] = ping.SensorDepth
            fields["speed_kn"][row] = ping.SensorSpeed
            fields["roll_deg"][row] = ping.SensorRoll
            fields["pitch_deg"][row] = ping.SensorPitch
            fields["cable_out_m"][row] = ping.CableOut + ping.CableOutHundredths / 100.0
            fields["layback_m"][row] = ping.Layback

            for side, (samples, chan) in chans.items():
                if side == "port" and reverse_port:
                    samples = samples[::-1]
                arrays[side][row, : len(samples)] = samples
                if side == "port" or np.isnan(fields["slant_range_m"][row]):
                    fields["slant_range_m"][row] = chan.SlantRange

    for arr in arrays.values():
        if isinstance(arr, np.memmap):
            arr.flush()

    nav, nav_warnings = _build_nav(scan, fields, time_parts, epsg)
    warnings = nav_warnings + warnings
    if scan.truncated:
        warnings.append(TRUNCATED_FILE)
    freq = next((c.frequency_khz for c in specs if c.frequency_khz), None)
    return SonarLog(
        source_file=scan.path.name,
        source_format="xtf",
        sonar=SonarInfo(
            make=None,
            model=scan.sonar_name or None,
            frequency_khz=freq,
            samples_per_channel=n_samples,
            channel_layout=scan.layout,
        ),
        nav=nav,
        port=arrays.get("port"),
        starboard=arrays.get("starboard"),
        crs_hint="EPSG:4326",
        warnings=warnings,
    )


def _allocate(
    scan: XtfScan, spec: ChannelSpec, n_samples: int, work_dir: str | Path | None
) -> npt.NDArray[Any]:
    shape = (scan.n_pings, n_samples)
    if work_dir is None:
        return np.zeros(shape, dtype=spec.dtype)
    out = Path(work_dir)
    out.mkdir(parents=True, exist_ok=True)
    mm: npt.NDArray[Any] = np.lib.format.open_memmap(
        out / f"{scan.path.stem}_{spec.side}.npy", mode="w+", dtype=spec.dtype, shape=shape
    )
    return mm


def _build_nav(
    scan: XtfScan,
    fields: dict[str, npt.NDArray[np.float64]],
    time_parts: npt.NDArray[np.int64],
    epsg: int | str | None,
) -> tuple[pd.DataFrame, list[str]]:
    nav = empty_nav(scan.n_pings)
    warnings: list[str] = []

    sensor_ok = _valid_fix(fields["sensor_x"], fields["sensor_y"])
    ship_ok = _valid_fix(fields["ship_x"], fields["ship_y"])
    use_ship = ~sensor_ok & ship_ok
    x = np.where(sensor_ok, fields["sensor_x"], np.where(use_ship, fields["ship_x"], np.nan))
    y = np.where(sensor_ok, fields["sensor_y"], np.where(use_ship, fields["ship_y"], np.nan))

    if np.isfinite(x).any():
        lat, lon = to_wgs84(x, y, nav_units=scan.nav_units, epsg=epsg)
        nav["lat"], nav["lon"] = lat, lon
        source = np.full(scan.n_pings, None, dtype=object)
        source[use_ship] = "ship"
        source[sensor_ok] = "sensor"
        nav["nav_source"] = source
        if use_ship.any():
            warnings.append(SHIP_POSITION_ONLY)
    else:
        warnings.append(NO_NAVIGATION)

    for name in (
        "heading_deg",
        "sensor_depth_m",
        "roll_deg",
        "pitch_deg",
        "slant_range_m",
        "cable_out_m",
        "layback_m",
    ):
        nav[name] = fields[name]
    nav["altitude_m"] = np.where(fields["altitude_m"] > 0, fields["altitude_m"], np.nan)
    nav["speed_mps"] = fields["speed_kn"] * KNOTS_TO_MPS

    parts = pd.DataFrame(
        time_parts[:, :6], columns=["year", "month", "day", "hour", "minute", "second"]
    )
    times = pd.to_datetime(parts, errors="coerce", utc=True)
    nav["time_utc"] = times + pd.to_timedelta(time_parts[:, 6] * 10, unit="ms")
    return nav, warnings


def _valid_fix(x: npt.NDArray[np.float64], y: npt.NDArray[np.float64]) -> npt.NDArray[np.bool_]:
    return np.asarray(np.isfinite(x) & np.isfinite(y) & ~((x == 0) & (y == 0)), dtype=bool)
