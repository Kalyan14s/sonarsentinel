"""ST-060 shadow consistency score and height (TC-CONF-004, TC-CONF-006)."""

import numpy as np
import pytest

from sonarsentinel.scoring.shadow import shadow_score

RES = 0.1
NADIR = 400


def _seabed(seed: int = 0) -> np.ndarray:
    rng = np.random.default_rng(seed)
    return np.clip(rng.normal(100, 8, (600, 801)), 1, 255).astype(np.uint8)


def _object(
    image: np.ndarray,
    *,
    row: int,
    col: int,
    rows: int = 30,
    cols: int = 20,
    shadow_px: int = 22,
    starboard: bool = True,
) -> tuple[tuple[int, int, int, int], np.ndarray]:
    """Bright block at columns ``col:col+cols`` with a dark shadow on the far side."""
    image[row : row + rows, col : col + cols] = 200
    if starboard:
        image[row : row + rows, col + cols : col + cols + shadow_px] = 25
    else:
        image[row : row + rows, col - shadow_px : col] = 25
    box = (col, row, col + cols, row + rows)
    return box, np.ones((rows, cols), dtype=bool)


def test_object_scores_well_above_shadow_only_patch() -> None:
    """TC-CONF-004: object with shadow beats a shadow-only patch by ≥ 0.3."""
    image = _seabed()
    box, mask = _object(image, row=100, col=NADIR + 180)
    image[300:330, NADIR + 150 : NADIR + 190] = 25  # shadow-only patch, no highlight
    dark_box = (NADIR + 150, 300, NADIR + 190, 330)
    dark_mask = np.ones((30, 40), dtype=bool)

    obj = shadow_score(image, mask, box, nadir_col=NADIR, ground_res_m=RES, altitude_m=10.0)
    dark = shadow_score(
        image, dark_mask, dark_box, nadir_col=NADIR, ground_res_m=RES, altitude_m=10.0
    )
    assert obj.score - dark.score >= 0.3
    assert dark.score == 0.0 and dark.contrast == 0.0
    assert obj.coverage == pytest.approx(1.0) and obj.band is not None


@pytest.mark.parametrize("starboard", [True, False])
def test_height_of_one_metre_object_within_30_percent(starboard: bool) -> None:
    """TC-CONF-006: Ls = h·r/(H−h) for h = 1 m, H = 10 m, far edge at r = 20 m → h ± 30%."""
    altitude, height, far_range = 10.0, 1.0, 20.0
    shadow_px = round(height * far_range / (altitude - height) / RES)
    image = _seabed(1)
    cols = 20
    far_col = round(far_range / RES)
    col = NADIR + far_col - cols if starboard else NADIR - far_col
    box, mask = _object(
        image, row=200, col=col, cols=cols, shadow_px=shadow_px, starboard=starboard
    )
    result = shadow_score(image, mask, box, nadir_col=NADIR, ground_res_m=RES, altitude_m=altitude)
    assert result.height_m is not None
    assert result.height_m == pytest.approx(height, rel=0.3)
    assert result.shadow_length_m == pytest.approx(shadow_px * RES, abs=0.2)


def test_no_shadow_no_height_and_low_score() -> None:
    image = _seabed(2)
    image[100:130, NADIR + 100 : NADIR + 120] = 200  # flat bright patch, no shadow
    box = (NADIR + 100, 100, NADIR + 120, 130)
    result = shadow_score(
        image, np.ones((30, 20), bool), box, nadir_col=NADIR, ground_res_m=RES, altitude_m=8.0
    )
    assert result.score == 0.0 and result.height_m is None and result.contrast > 0.5


def test_missing_altitude_gives_no_height_but_keeps_score() -> None:
    image = _seabed(3)
    box, mask = _object(image, row=50, col=NADIR + 150)
    result = shadow_score(image, mask, box, nadir_col=NADIR, ground_res_m=RES, altitude_m=None)
    assert result.height_m is None and result.score > 0.5


def test_empty_mask_scores_zero() -> None:
    image = _seabed(4)
    box = (NADIR + 10, 10, NADIR + 20, 20)
    result = shadow_score(
        image, np.zeros((10, 10), bool), box, nadir_col=NADIR, ground_res_m=RES, altitude_m=5.0
    )
    assert result.score == 0.0 and result.band is None
