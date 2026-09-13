"""Sprint 5 pipeline outputs end to end: position uncertainty (ST-035) and mosaic (ST-036)."""

import json
from pathlib import Path
from typing import Any

import pytest

pytest.importorskip("pyxtf")
pytest.importorskip("scipy")
pytest.importorskip("cv2")
pytest.importorskip("rasterio")

from tools.make_synthetic_xtf import write_synthetic_xtf  # noqa: E402

from sonarsentinel.config import load_config  # noqa: E402
from sonarsentinel.detect.classical import BrightTargetDetector  # noqa: E402
from sonarsentinel.geo.uncertainty import uncertainty_config  # noqa: E402
from sonarsentinel.pipeline import run_pipeline  # noqa: E402


@pytest.fixture(scope="module")
def outputs(tmp_path_factory: pytest.TempPathFactory) -> tuple[dict[str, Any], Path]:
    root = tmp_path_factory.mktemp("geo_outputs")
    survey = write_synthetic_xtf(
        root / "line.xtf",
        n_pings=900,
        samples_per_side=1000,
        step_m=0.1,
        targets=[(250, "starboard", 400), (600, "port", 500)],
        target_extent=(12, 30),
    )
    results = root / "results"
    report = run_pipeline(
        survey.path, config=load_config(), detector=BrightTargetDetector(), results_dir=results
    )
    return report, results / report["survey"]["survey_id"]


def test_every_geotagged_detection_has_uncertainty(outputs: tuple[dict[str, Any], Path]) -> None:
    """TC-GEO-010 end to end: uncertainty_m filled from the config budget (≥ the GNSS term)."""
    report, _ = outputs
    gnss = uncertainty_config(load_config())["gnss_m"]
    assert report["detections"]
    for det in report["detections"]:
        value = det["position"]["uncertainty_m"]
        assert isinstance(value, float) and gnss <= value < 10.0


def test_mosaic_written_next_to_the_report(outputs: tuple[dict[str, Any], Path]) -> None:
    """ST-036: mosaic GeoTIFF, PNG and Leaflet bounds that contain every detection."""
    report, folder = outputs
    for name in ("mosaic.tif", "mosaic.png", "mosaic_bounds.json"):
        assert (folder / name).is_file(), name
    (south, west), (north, east) = json.loads((folder / "mosaic_bounds.json").read_text("utf-8"))[
        "bounds"
    ]
    for det in report["detections"]:
        assert south <= det["position"]["lat"] <= north
        assert west <= det["position"]["lon"] <= east
