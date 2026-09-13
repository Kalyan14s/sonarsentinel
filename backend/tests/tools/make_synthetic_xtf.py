"""Synthetic XTF survey generator: test data TD-01 (and TD-05 variants).

Writes a dual-channel side-scan XTF file with a known track (straight or curved), altitude, heading
and bright point targets at known positions, and returns the ground truth. Used by the golden
geotagging and XTF reader tests; can also be run from the command line::

    python tests/tools/make_synthetic_xtf.py out.xtf --pings 2000 --track curved --utm-epsg 32644
"""

from __future__ import annotations

import argparse
import ctypes
import json
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Literal

import numpy as np
from pyproj import Geod, Transformer
from pyxtf import XTFFileHeader, XTFPingChanHeader, XTFPingHeader

GEOD = Geod(ellps="WGS84")
KNOTS_PER_MPS = 3600.0 / 1852.0

Track = Literal["straight", "curved"]
PortOrder = Literal["far_first", "nadir_first"]
Profile = Literal["water_column", "attenuation"]


@dataclass
class Target:
    """A point target placed on one side at a whole slant-range sample."""

    ping: int
    side: str
    sample: int
    slant_range_m: float = 0.0
    ground_range_m: float = 0.0
    lat: float = 0.0
    lon: float = 0.0


@dataclass
class SyntheticSurvey:
    """Ground truth for a generated file."""

    path: str
    n_pings: int
    samples_per_side: int
    slant_range_m: float
    altitude_m: float
    sensor_depth_m: float
    speed_mps: float
    nav_units: int
    utm_epsg: int | None
    port_order: str
    start_utc: str
    ping_interval_s: float
    lat: list[float] = field(default_factory=list)
    lon: list[float] = field(default_factory=list)
    heading_deg: list[float] = field(default_factory=list)
    targets: list[Target] = field(default_factory=list)
    background_level: int = 0
    target_level: int = 0

    def to_json(self) -> str:
        return json.dumps(asdict(self), indent=2)


def make_track(
    n_pings: int,
    track: Track = "straight",
    *,
    start: tuple[float, float] = (13.0802, 80.3071),
    heading_deg: float = 62.4,
    step_m: float = 0.1,
    turn_deg: float = 90.0,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Sensor positions and headings; ``curved`` turns ``turn_deg`` over the line."""
    if track == "straight":
        headings = np.full(n_pings, heading_deg)
    else:
        headings = np.mod(heading_deg + np.linspace(0.0, turn_deg, n_pings), 360.0)
    lats = np.empty(n_pings)
    lons = np.empty(n_pings)
    lats[0], lons[0] = start
    for i in range(1, n_pings):
        lons[i], lats[i], _ = GEOD.fwd(lons[i - 1], lats[i - 1], headings[i - 1], step_m)
    return lats, lons, headings


def write_synthetic_xtf(
    path: str | Path,
    *,
    n_pings: int = 400,
    samples_per_side: int = 1000,
    slant_range_m: float = 50.0,
    altitude_m: float = 8.0,
    sensor_depth_m: float = 10.2,
    step_m: float = 0.1,
    ping_interval_s: float = 0.1,
    track: Track = "straight",
    heading_deg: float = 62.4,
    utm_epsg: int | None = None,
    port_order: PortOrder = "far_first",
    profile: Profile = "water_column",
    targets: list[tuple[int, str, int]] | None = None,
    target_extent: tuple[int, int] = (1, 1),
    seed: int = 0,
    write_ship_position: bool = True,
    write_sensor_position: bool = True,
) -> SyntheticSurvey:
    """Write a synthetic XTF file and return its ground truth.

    Args:
        path: Output file.
        n_pings: Number of sonar pings.
        samples_per_side: Samples per channel (16-bit).
        slant_range_m: Range of each channel.
        altitude_m: Constant sonar altitude above the seabed.
        sensor_depth_m: Constant sensor depth.
        step_m: Distance travelled between pings.
        ping_interval_s: Time between pings.
        track: ``straight`` or ``curved``.
        heading_deg: Initial heading.
        utm_epsg: Write projected coordinates in this UTM zone (``NavUnits`` = 0), not lat/lon.
        port_order: Sample order of the port channel as stored in the file.
        profile: Across-track intensity: ``water_column`` (dark band next to nadir, flat beyond)
            or ``attenuation`` (shallow water: brightest at nadir, fading with range).
        targets: ``(ping, side, sample)`` point targets; defaults to a small set on both sides.
        target_extent: ``(pings, samples)`` size of each target, starting at its ping and sample.
        seed: Random seed for the speckle background.
        write_ship_position: Also fill ``ShipX/Ycoordinate`` (same as the sensor).
        write_sensor_position: Fill ``SensorX/Ycoordinate``.
    """
    rng = np.random.default_rng(seed)
    lats, lons, headings = make_track(n_pings, track, heading_deg=heading_deg, step_m=step_m)
    if targets is None:
        targets = [
            (n_pings // 4, "starboard", samples_per_side // 2),
            (n_pings // 2, "port", samples_per_side // 3),
            (3 * n_pings // 4, "starboard", 9 * samples_per_side // 10),
            (n_pings // 2, "starboard", samples_per_side // 5),
        ]

    xs, ys = lons, lats
    nav_units = 3
    if utm_epsg is not None:
        fwd = Transformer.from_crs("EPSG:4326", f"EPSG:{utm_epsg}", always_xy=True)
        xs, ys = fwd.transform(lons, lats)
        nav_units = 0

    header = XTFFileHeader()
    header.SonarName = b"SYNTH-SSS"
    header.NoteString = b"SonarSentinel TD-01 synthetic survey"
    header.ThisFileName = Path(path).name.encode()[:63]
    header.NavUnits = nav_units
    header.NumberOfSonarChannels = 2
    for i, (kind, name) in enumerate(((1, b"Port 600"), (2, b"Stbd 600"))):
        info = header.ChanInfo[i]
        info.TypeOfChannel = kind
        info.SubChannelNumber = i
        info.BytesPerSample = 2
        info.SampleFormat = 3
        info.Frequency = 600.0
        info.ChannelName = name
    assert ctypes.sizeof(header) == 1024

    background_level, target_level = 400, 60000
    start_time = datetime(2026, 9, 12, 5, 10, 2, tzinfo=UTC)
    truth: list[Target] = []
    lookup: dict[tuple[int, str], list[int]] = {}
    for ping, side, sample in targets:
        slant = sample / samples_per_side * slant_range_m
        ground = float(np.sqrt(max(slant**2 - altitude_m**2, 0.0)))
        bearing = headings[ping] + (90.0 if side == "starboard" else -90.0)
        lon2, lat2, _ = GEOD.fwd(lons[ping], lats[ping], bearing, ground)
        truth.append(Target(ping, side, sample, slant, ground, float(lat2), float(lon2)))
        for dp in range(target_extent[0]):
            lookup.setdefault((ping + dp, side), []).append(sample)

    chan_size = ctypes.sizeof(XTFPingChanHeader)
    ping_size = ctypes.sizeof(XTFPingHeader)
    record_size = ping_size + 2 * (chan_size + 2 * samples_per_side)

    with Path(path).open("wb") as fh:
        fh.write(header.to_bytes())
        for i in range(n_pings):
            t = start_time + timedelta(seconds=i * ping_interval_s)
            ping = XTFPingHeader()
            ping.NumChansToFollow = 2
            ping.NumBytesThisRecord = record_size
            ping.Year, ping.Month, ping.Day = t.year, t.month, t.day
            ping.Hour, ping.Minute, ping.Second = t.hour, t.minute, t.second
            ping.HSeconds = t.microsecond // 10_000
            ping.JulianDay = t.timetuple().tm_yday
            ping.PingNumber = i
            if write_sensor_position:
                ping.SensorXcoordinate, ping.SensorYcoordinate = float(xs[i]), float(ys[i])
            if write_ship_position:
                ping.ShipXcoordinate, ping.ShipYcoordinate = float(xs[i]), float(ys[i])
            ping.SensorHeading = float(headings[i])
            ping.SensorPrimaryAltitude = altitude_m
            ping.SensorDepth = sensor_depth_m
            ping.SensorSpeed = step_m / ping_interval_s * KNOTS_PER_MPS
            ping.SensorRoll, ping.SensorPitch = 0.5, -0.3
            ping.CableOut, ping.Layback = 25, 0.0

            chans, data = [], []
            for ch, side in enumerate(("port", "starboard")):
                chan = XTFPingChanHeader()
                chan.ChannelNumber = ch
                chan.SlantRange = slant_range_m
                chan.GroundRange = float(np.sqrt(slant_range_m**2 - altitude_m**2))
                chan.Frequency = 600
                chan.NumSamples = samples_per_side
                if profile == "attenuation":
                    decay = np.exp(-3.0 * np.arange(samples_per_side) / samples_per_side)
                    speckle = rng.gamma(4.0, 0.25, samples_per_side)
                    samples = (3000.0 * decay * speckle).clip(0, 65535).astype(np.uint16)
                else:
                    samples = rng.integers(
                        background_level - 100, background_level + 100, samples_per_side
                    ).astype(np.uint16)
                    water = int(altitude_m / slant_range_m * samples_per_side)
                    samples[:water] = 5  # dark water column next to nadir
                for s in lookup.get((i, side), []):
                    samples[s : s + target_extent[1]] = target_level
                if side == "port" and port_order == "far_first":
                    samples = samples[::-1].copy()
                chans.append(chan)
                data.append(samples)
            ping.ping_chan_headers = chans
            ping.data = data
            raw = ping.to_bytes()
            assert len(raw) == record_size
            fh.write(raw)

    return SyntheticSurvey(
        path=str(path),
        n_pings=n_pings,
        samples_per_side=samples_per_side,
        slant_range_m=slant_range_m,
        altitude_m=altitude_m,
        sensor_depth_m=sensor_depth_m,
        speed_mps=step_m / ping_interval_s,
        nav_units=nav_units,
        utm_epsg=utm_epsg,
        port_order=port_order,
        start_utc=start_time.isoformat(),
        ping_interval_s=ping_interval_s,
        lat=lats.tolist(),
        lon=lons.tolist(),
        heading_deg=headings.tolist(),
        targets=truth,
        background_level=background_level,
        target_level=target_level,
    )


def truncate(path: str | Path, out: str | Path, drop_bytes: int = 1000) -> Path:
    """TD-05: copy a file without its last ``drop_bytes`` bytes."""
    data = Path(path).read_bytes()
    Path(out).write_bytes(data[:-drop_bytes])
    return Path(out)


def corrupt_header(path: str | Path, out: str | Path) -> Path:
    """TD-05: copy a file with the XTF file-format byte overwritten."""
    data = bytearray(Path(path).read_bytes())
    data[0] = 0x00
    Path(out).write_bytes(bytes(data))
    return Path(out)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("out", type=Path)
    parser.add_argument("--pings", type=int, default=2000)
    parser.add_argument("--samples", type=int, default=1000)
    parser.add_argument("--track", choices=["straight", "curved"], default="straight")
    parser.add_argument("--utm-epsg", type=int, default=None)
    parser.add_argument("--truth", type=Path, help="Write ground truth JSON here")
    args = parser.parse_args()
    survey = write_synthetic_xtf(
        args.out,
        n_pings=args.pings,
        samples_per_side=args.samples,
        track=args.track,
        utm_epsg=args.utm_epsg,
    )
    if args.truth:
        args.truth.write_text(survey.to_json(), encoding="utf-8")
    print(f"wrote {args.out} ({args.out.stat().st_size} bytes, {survey.n_pings} pings)")


if __name__ == "__main__":
    main()
