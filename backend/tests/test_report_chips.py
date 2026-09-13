"""ST-073 detection chips (TC-REP-009: one chip per detection with mask/shadow/anomaly overlays)."""

from pathlib import Path

import numpy as np
import pytest

cv2 = pytest.importorskip("cv2")

from sonarsentinel.report.chips import (  # noqa: E402
    OVERLAYS,
    chip_filename,
    chip_url,
    remove_chips,
    rename_chips,
    render_chip,
    write_chips,
)


def _scene() -> tuple[np.ndarray, np.ndarray, tuple[int, int, int, int], np.ndarray]:
    rng = np.random.default_rng(0)
    image = np.clip(rng.normal(90, 10, (400, 600)), 0, 255).astype(np.uint8)
    image[100:130, 300:340] = 220
    heat = np.zeros(image.shape, dtype=np.float32)
    heat[90:140, 290:350] = 3.0
    return image, heat, (300, 100, 340, 130), np.ones((30, 40), dtype=bool)


def test_every_overlay_written_and_renamed(tmp_path: Path) -> None:
    image, heat, box, mask = _scene()
    paths = write_chips(
        tmp_path,
        "_tmp_0_1",
        image,
        box,
        mask,
        heat=heat,
        heat_scale=6.0,
        shadow_band=(340, 100, 360, 130),
    )
    assert [p.name for p in paths] == [chip_filename("_tmp_0_1", o) for o in OVERLAYS]
    for path in paths:
        chip = cv2.imread(str(path))
        assert chip.shape == (256, 256, 3)

    assert rename_chips(tmp_path, "_tmp_0_1", "SRV-20260912-001-D0001")
    names = sorted(p.name for p in tmp_path.iterdir())
    assert names == sorted(chip_filename("SRV-20260912-001-D0001", o) for o in OVERLAYS)
    remove_chips(tmp_path, "SRV-20260912-001-D0001")
    assert not any(tmp_path.iterdir())
    assert (
        chip_url("SRV-20260912-001-D0001") == "/api/v1/detections/SRV-20260912-001-D0001/chip.png"
    )


def test_overlays_differ_and_mask_outline_drawn() -> None:
    image, heat, box, mask = _scene()
    plain = render_chip(image, box, mask, overlay="none")
    outlined = render_chip(image, box, mask, overlay="mask")
    shadow = render_chip(image, box, mask, overlay="shadow", shadow_band=(340, 100, 360, 130))
    anomaly = render_chip(image, box, mask, overlay="anomaly", heat=heat, heat_scale=6.0)
    assert not np.array_equal(plain, outlined)
    assert not np.array_equal(outlined, shadow)
    assert not np.array_equal(plain, anomaly)
    assert np.array_equal(plain[..., 0], plain[..., 2])  # grey without overlay


def test_large_object_and_image_edge() -> None:
    rng = np.random.default_rng(1)
    image = np.clip(rng.normal(90, 10, (300, 300)), 0, 255).astype(np.uint8)
    big = render_chip(image, (0, 0, 290, 280), np.ones((280, 290), bool), overlay="mask")
    corner = render_chip(image, (0, 0, 5, 5), np.ones((5, 5), bool), overlay="mask", size_px=128)
    assert big.shape == (256, 256, 3) and corner.shape == (128, 128, 3)
    with pytest.raises(ValueError, match="Unknown overlay"):
        render_chip(image, (0, 0, 5, 5), np.ones((5, 5), bool), overlay="bogus")
