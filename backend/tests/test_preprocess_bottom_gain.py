"""TC-PRE-001 (bottom tracking), TC-PRE-005 (gain flatness), TC-PRE-006 (per-side balance)."""

import numpy as np
import pytest

pytest.importorskip("scipy")
pytest.importorskip("pyxtf")

from tools.make_synthetic_xtf import write_synthetic_xtf  # noqa: E402

from sonarsentinel.ingest.xtf_reader import read_xtf  # noqa: E402
from sonarsentinel.preprocess.bottom import (  # noqa: E402
    resolve_altitude,
    track_bottom,
    water_column_mask,
)
from sonarsentinel.preprocess.gain import flatten_across_track, normalize_gain  # noqa: E402


def test_bottom_tracking_recovers_altitude(tmp_path) -> None:  # type: ignore[no-untyped-def]
    """TC-PRE-001: altitude removed from TD-01 is re-estimated within 10%."""
    survey = write_synthetic_xtf(tmp_path / "td01.xtf", n_pings=300, altitude_m=8.0)
    log = read_xtf(survey.path)
    track = track_bottom(log.port, log.starboard, log.nav["slant_range_m"])
    assert np.all(np.abs(track.altitude_m - 8.0) <= 0.8)
    assert np.median(np.abs(track.altitude_m - 8.0)) < 0.2


def test_resolve_altitude_modes() -> None:
    recorded = np.array([8.0, 40.0, np.nan, 8.1])
    tracked = np.array([8.2, 3.0, 7.9, np.nan])
    alt, used = resolve_altitude(recorded, tracked, mode="auto")
    assert alt.tolist() == [8.0, 3.0, 7.9, 8.1]
    assert used.tolist() == [False, True, True, False]
    alt, used = resolve_altitude(recorded, tracked, mode=True)
    assert used.tolist() == [True, True, True, False]
    alt, used = resolve_altitude(recorded, tracked, mode=False)
    assert not used.any() and np.isnan(alt[2])


def test_water_column_mask() -> None:
    mask = water_column_mask([2, np.nan, 0], 4)
    assert mask.tolist() == [
        [True, True, False, False],
        [False, False, False, False],
        [False, False, False, False],
    ]


def _attenuated(rng: np.random.Generator, gain: float = 1.0) -> np.ndarray:
    decay = np.exp(-3.0 * np.arange(512) / 512)
    return (gain * 3000.0 * decay[None, :] * rng.gamma(4.0, 0.25, (1500, 512))).astype(np.uint16)


def test_across_track_profile_is_flat() -> None:
    """TC-PRE-005: column means within ±10% of their median after normalisation."""
    rng = np.random.default_rng(0)
    raw = _attenuated(rng)
    before = raw.mean(axis=0)
    assert before.max() / before.min() > 10  # strong range loss before
    flat = flatten_across_track(raw, 200)
    cols = flat.mean(axis=0)
    assert np.all(np.abs(cols / np.median(cols) - 1) < 0.10)
    out = normalize_gain(raw, raw.copy())
    assert out.port is not None and out.port.dtype == np.uint8
    means = out.port.astype(np.float64).mean(axis=0)
    assert np.all(np.abs(means / np.median(means) - 1) < 0.10)


def test_port_and_starboard_are_balanced() -> None:
    """TC-PRE-006: a side twice as bright (roll imbalance) ends up within 5% of the other."""
    rng = np.random.default_rng(1)
    out = normalize_gain(_attenuated(rng, 1.0), _attenuated(rng, 2.0))
    assert out.port is not None and out.starboard is not None
    port_med = float(np.median(out.port))
    stbd_med = float(np.median(out.starboard))
    assert abs(port_med - stbd_med) / max(port_med, stbd_med) < 0.05
    unbalanced = normalize_gain(_attenuated(rng, 1.0), _attenuated(rng, 4.0), per_side=False,
                                along_track_window_pings=1_000_000)  # fmt: skip
    assert unbalanced.port is not None
