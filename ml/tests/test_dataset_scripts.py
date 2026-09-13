"""Unit tests for the ST-010/011/012 dataset preparation scripts on small synthetic inputs."""

import csv
import io
import json
import zipfile
from pathlib import Path

import numpy as np
import pytest

cv2 = pytest.importorskip("cv2")

from build_normal_pool import build, is_usable, tile_grid  # noqa: E402
from convert_ai4shipwrecks import convert as convert_ai4  # noqa: E402
from convert_ai4shipwrecks import site_id  # noqa: E402
from convert_mine_sss import convert as convert_mine  # noqa: E402
from convert_mine_sss import convert_boxes, parse_labels  # noqa: E402
from yolo_seg import box_to_polygon, format_polygon, mask_to_polygons  # noqa: E402


def _jpg(image: np.ndarray) -> bytes:
    ok, buf = cv2.imencode(".jpg", image)
    assert ok
    return buf.tobytes()


def test_box_to_polygon_clips_and_orders() -> None:
    assert box_to_polygon(0.5, 0.5, 0.2, 0.4) == [(0.4, 0.3), (0.6, 0.3), (0.6, 0.7), (0.4, 0.7)]
    assert box_to_polygon(0.05, 0.5, 0.2, 0.2)[0][0] == 0.0
    assert format_polygon(2, [(0.1, 0.2)], decimals=2) == "2 0.10 0.20"


def test_mask_to_polygons_finds_rectangle() -> None:
    mask = np.zeros((100, 200), np.uint8)
    mask[20:60, 50:150] = 255
    mask[90:92, 0:2] = 1  # below min area
    (poly,) = mask_to_polygons(mask)
    xs, ys = zip(*poly, strict=True)
    assert min(xs) == pytest.approx(0.25) and max(xs) == pytest.approx(149 / 200)
    assert min(ys) == pytest.approx(0.2) and max(ys) == pytest.approx(59 / 100)


def test_parse_and_map_mine_labels() -> None:
    boxes = parse_labels("0 0.5 0.5 0.1 0.1\n\n1 0.2 0.2 0.05 0.05\n")
    lines, nombo = convert_boxes(boxes)
    assert lines == [format_polygon(2, box_to_polygon(0.5, 0.5, 0.1, 0.1))]
    assert len(nombo) == 1 and nombo[0].source_class == 1
    with pytest.raises(ValueError, match="unknown class"):
        parse_labels("7 0.5 0.5 0.1 0.1")
    with pytest.raises(ValueError, match="expected 5"):
        parse_labels("0 0.5 0.5")


def _mine_zip(path: Path) -> None:
    rng = np.random.default_rng(0)
    image = rng.integers(40, 200, (1024, 1024, 3), dtype=np.uint8)
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr("2021/0001_2021.jpg", _jpg(image))
        zf.writestr("2021/0001_2021.txt", "0 0.5 0.5 0.05 0.05\n1 0.25 0.25 0.05 0.05\n")
        zf.writestr("2021/0002_2021.jpg", _jpg(image))
        zf.writestr("2021/0002_2021.txt", "")
        blank = np.zeros((1024, 1024, 3), np.uint8)
        zf.writestr("2021/0003_2021.jpg", _jpg(blank))
        zf.writestr("2021/0003_2021.txt", "")


def test_convert_mine_sss_end_to_end(tmp_path: Path) -> None:
    raw = tmp_path / "raw"
    raw.mkdir()
    _mine_zip(raw / "2021.zip")
    summary = convert_mine(raw, tmp_path / "out", n_overlays=5)
    assert summary["images"] == 3 and summary["milco_to_cylinder"] == 1
    assert summary["nombo_for_review"] == 1 and summary["images_without_objects"] == 2
    label = (tmp_path / "out/labels/2021/0001_2021.txt").read_text(encoding="utf-8")
    assert label.startswith("2 ") and len(label.split()) == 9
    rows = list(csv.DictReader(io.StringIO((tmp_path / "out/nombo_review.csv").read_text())))
    assert rows[0]["decision"] == "" and (tmp_path / "out" / rows[0]["crop"]).exists()
    assert len(list((tmp_path / "out/qa_overlays").iterdir())) == 1


def test_normal_pool_uses_only_empty_label_images(tmp_path: Path) -> None:
    raw = tmp_path / "raw"
    raw.mkdir()
    _mine_zip(raw / "2021.zip")
    summary = build(raw, tmp_path / "pool")
    assert summary["source_images"] == 2  # 0002 and the blank 0003; 0001 has objects
    assert summary["tiles"] == 4 and summary["rejected_blank"] == 4
    manifest = (tmp_path / "pool/manifest.csv").read_text(encoding="utf-8")
    assert "0001_2021" not in manifest
    assert (tmp_path / "pool/contact_sheet.png").exists()
    assert json.loads((tmp_path / "pool/summary.json").read_text())["tiles_2021"] == 4


def test_tile_helpers() -> None:
    assert tile_grid(1024, 1100, 512) == [(0, 0), (0, 512), (512, 0), (512, 512)]
    assert not is_usable(np.zeros((8, 8), np.uint8))
    assert is_usable(np.random.default_rng(1).integers(30, 200, (8, 8)).astype(np.uint8))


def test_convert_ai4shipwrecks(tmp_path: Path) -> None:
    (tmp_path / "img").mkdir()
    (tmp_path / "lbl").mkdir()
    cv2.imwrite(str(tmp_path / "img/Kyle_Spangler_03.png"), np.full((64, 64), 120, np.uint8))
    mask = np.zeros((64, 64), np.uint8)
    mask[10:30, 10:50] = 1
    cv2.imwrite(str(tmp_path / "lbl/Kyle_Spangler_03.png"), mask)
    summary = convert_ai4(tmp_path / "img", tmp_path / "lbl", tmp_path / "out")
    assert summary["images"] == 1 and summary["polygons"] == 1
    assert summary["site:kyle_spangler"] == 1
    assert site_id("Monohansett-12") == "monohansett"
