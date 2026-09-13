"""TC-PRE-008 (dropouts) and TC-PRE-009 (motion flags): ST-043 and ST-044."""

import numpy as np
import pytest

from sonarsentinel.errors import ValidationError
from sonarsentinel.ingest.models import empty_nav
from sonarsentinel.preprocess.dropout import detect_dropouts, repair_dropouts
from sonarsentinel.preprocess.motion import flag_segments, motion_flags, yaw_rate_deg_per_ping


def test_motion_flags_match_thresholds() -> None:
    """TC-PRE-009: a ±10° roll segment is flagged exactly on the pings over 5°."""
    nav = empty_nav(100)
    roll = np.zeros(100)
    roll[40:60] = 10.0 * np.sin(np.linspace(0, np.pi, 20))
    nav["roll_deg"] = roll
    nav["pitch_deg"] = 0.0
    nav["pitch_deg"] = nav["pitch_deg"].where(nav.index != 10, -5.5)
    nav["heading_deg"] = 90.0
    nav.loc[80, "heading_deg"] = 94.0
    flags = motion_flags(nav)
    assert np.array_equal(flags.roll, np.abs(roll) > 5.0)
    assert np.flatnonzero(flags.pitch).tolist() == [10]
    assert np.flatnonzero(flags.yaw_rate).tolist() == [80, 81]
    assert flags.any.sum() == flags.roll.sum() + 3


def test_exact_threshold_is_not_flagged_and_nan_is_ignored() -> None:
    nav = empty_nav(3)
    nav["roll_deg"] = [5.0, np.nan, -5.0001]
    flags = motion_flags(nav)
    assert flags.roll.tolist() == [False, False, True]


def test_yaw_rate_wraps() -> None:
    assert yaw_rate_deg_per_ping([359.0, 1.0, 358.0]).tolist() == pytest.approx([0.0, 2.0, 3.0])


def test_flag_segments() -> None:
    assert flag_segments([0, 1, 1, 0, 1]) == [(1, 2), (4, 4)]
    assert flag_segments([False, False]) == []


def _image(rng: np.random.Generator, n: int = 1000, samples: int = 300) -> np.ndarray:
    return rng.gamma(4.0, 50.0, (n, samples)).astype(np.uint16)


def test_injected_dropouts_are_found() -> None:
    """TC-PRE-008: ≥ 95% of injected zeroed or frozen pings are detected."""
    rng = np.random.default_rng(3)
    port, stbd = _image(rng), _image(rng)
    injected = np.zeros(1000, dtype=bool)
    injected[rng.choice(1000, 100, replace=False)] = True
    frozen = np.flatnonzero(injected)[::4]
    for i in np.flatnonzero(injected):
        if i in frozen and i > 0:
            port[i], stbd[i] = port[i - 1], stbd[i - 1]
        else:
            port[i], stbd[i] = 0, 0
    found = detect_dropouts(port, stbd)
    assert (found & injected).sum() / injected.sum() >= 0.95
    assert (found & ~injected).sum() <= 5


def test_flat_rows_and_invalid_nav() -> None:
    rng = np.random.default_rng(1)
    port = _image(rng, 50)
    port[7] = 200  # constant, non-zero row
    invalid = np.zeros(50, dtype=bool)
    invalid[30] = True
    found = detect_dropouts(port, None, invalid_nav=invalid)
    assert np.flatnonzero(found).tolist() == [7, 30]
    with pytest.raises(ValidationError):
        detect_dropouts(None)


def test_short_gaps_inpainted_long_gaps_masked() -> None:
    port = np.tile(np.arange(10, dtype=np.uint16) * 10, (20, 1))
    port[5] = 0
    port[6] = 0
    port[7] = 0
    port[12:16] = 0
    port[19] = 0
    stbd = port.copy()
    dropout = port.sum(axis=1) == 0
    port[4] = 100
    port[8] = 40
    repaired = repair_dropouts(port, stbd, dropout, max_gap=3)
    assert np.flatnonzero(repaired.inpainted).tolist() == [5, 6, 7]
    assert np.flatnonzero(repaired.masked).tolist() == [12, 13, 14, 15, 19]
    assert repaired.port is not None
    assert repaired.port[6, 0] == 70  # halfway between 100 and 40
    assert repaired.port.dtype == np.uint16
    assert port[6, 0] == 0  # input untouched
