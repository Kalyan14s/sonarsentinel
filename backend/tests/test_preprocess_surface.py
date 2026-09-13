"""ST-047 surface-return band mask (TC-PRE-012)."""

import numpy as np

from sonarsentinel.preprocess.surface import (
    in_surface_band,
    suppress_surface_detection,
    surface_band_mask,
)

RES = 0.1
NADIR = 100
WIDTH = 201


def test_band_matches_analytic_ground_range_on_both_sides() -> None:
    """TC-PRE-012: depth 5 m, altitude 3 m → band at g = sqrt(s² − H²) for s = 5 ± 0.5 m."""
    mask = surface_band_mask(5.0, 3.0, NADIR, WIDTH, RES)
    assert mask.shape == (1, WIDTH)
    near = np.sqrt(4.5**2 - 3.0**2)
    far = np.sqrt(5.5**2 - 3.0**2)
    ground = np.abs(np.arange(WIDTH) - NADIR) * RES
    expected = (ground >= near) & (ground <= far)
    assert np.array_equal(mask[0], expected)
    starboard = np.flatnonzero(mask[0] & (np.arange(WIDTH) >= NADIR))
    port = np.flatnonzero(mask[0] & (np.arange(WIDTH) < NADIR))
    assert starboard.min() - NADIR == NADIR - port.max()  # symmetric about nadir
    assert np.sqrt(5.0**2 - 3.0**2) / RES + NADIR in range(starboard.min(), starboard.max() + 1)


def test_rows_vectorised_and_no_band_when_sensor_above_altitude() -> None:
    depth = np.array([5.0, 2.0, 5.0, np.nan])
    altitude = np.array([3.0, 3.0, np.nan, 3.0])
    mask = surface_band_mask(depth, altitude, NADIR, WIDTH, RES)
    assert mask.shape == (4, WIDTH)
    assert mask[0].any()
    assert not mask[1:].any()


def test_box_in_band_and_suppression_rules() -> None:
    mask = np.repeat(surface_band_mask(5.0, 3.0, NADIR, WIDTH, RES), 50, axis=0)
    band_cols = np.flatnonzero(mask[0] & (np.arange(WIDTH) >= NADIR))
    inside = (int(band_cols.min()), 10, int(band_cols.max()) + 1, 40)
    outside = (180, 10, 195, 40)
    assert in_surface_band(inside, mask)
    assert not in_surface_band(outside, mask)
    assert not in_surface_band((0, 0, 0, 0), mask)

    assert suppress_surface_detection(
        True, length_m=8.0, width_m=1.0, orientation_rel_track_deg=5.0
    )
    assert suppress_surface_detection(True, 8.0, 1.0, 172.0)  # 8° from the track, other direction
    assert not suppress_surface_detection(True, 8.0, 1.0, 40.0)  # not parallel to the track
    assert not suppress_surface_detection(True, 3.0, 1.0, 0.0)  # not linear
    assert not suppress_surface_detection(False, 8.0, 1.0, 0.0)  # outside the band
    assert not suppress_surface_detection(True, 8.0, 0.0, 0.0)
    assert not suppress_surface_detection(True, 8.0, 1.0, None)
