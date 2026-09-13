import numpy as np
import pandas as pd
import pytest

from sonarsentinel.errors import ValidationError
from sonarsentinel.ingest.models import NAV_COLUMNS, SonarInfo, SonarLog, empty_nav


def _info(layout: str = "port_stbd", samples: int = 100) -> SonarInfo:
    return SonarInfo(
        make="EdgeTech",
        model="4200",
        frequency_khz=600.0,
        samples_per_channel=samples,
        channel_layout=layout,
    )  # type: ignore[arg-type]


def _log(**overrides: object) -> SonarLog:
    kwargs: dict[str, object] = {
        "source_file": "line_07.xtf",
        "source_format": "xtf",
        "sonar": _info(),
        "nav": empty_nav(5),
        "port": np.zeros((5, 100), dtype=np.float32),
        "starboard": np.zeros((5, 100), dtype=np.float32),
    }
    kwargs.update(overrides)
    return SonarLog(**kwargs)  # type: ignore[arg-type]


def test_empty_nav_has_all_columns() -> None:
    nav = empty_nav(3)
    assert tuple(nav.columns) == NAV_COLUMNS
    assert list(nav["ping"]) == [0, 1, 2]


def test_valid_waterfall_log() -> None:
    log = _log()
    assert log.n_pings == 5
    assert log.warnings == []


def test_missing_nav_column_is_rejected() -> None:
    with pytest.raises(ValidationError) as exc_info:
        _log(nav=empty_nav(5).drop(columns=["heading_deg"]))
    assert exc_info.value.details["missing"] == ["heading_deg"]


def test_ping_count_mismatch_is_rejected() -> None:
    with pytest.raises(ValidationError, match="pings but navigation has"):
        _log(nav=empty_nav(4))


def test_sample_count_mismatch_is_rejected() -> None:
    with pytest.raises(ValidationError, match="samples, expected"):
        _log(sonar=_info(samples=120))


def test_layout_must_match_channels() -> None:
    with pytest.raises(ValidationError, match="not allowed"):
        _log(sonar=_info(layout="port_only"))
    log = _log(sonar=_info(layout="port_only"), starboard=None)
    assert log.starboard is None


def test_channels_must_be_2d() -> None:
    with pytest.raises(ValidationError, match="2-D"):
        _log(port=np.zeros(5, dtype=np.float32))


def test_geotiff_requires_geotransform() -> None:
    nav = pd.DataFrame({c: [] for c in NAV_COLUMNS})
    with pytest.raises(ValidationError, match="geotransform"):
        SonarLog(source_file="m.tif", source_format="geotiff", sonar=_info(), nav=nav)
    with pytest.raises(ValidationError, match="2-D image"):
        SonarLog(
            source_file="m.tif",
            source_format="geotiff",
            sonar=_info(),
            nav=nav,
            geotransform=(80.30, 1e-6, 0.0, 13.09, 0.0, -1e-6),
        )
    log = SonarLog(
        source_file="m.tif",
        source_format="geotiff",
        sonar=_info(),
        nav=nav,
        image=np.zeros((4, 5), dtype=np.uint8),
        geotransform=(80.30, 1e-6, 0.0, 13.09, 0.0, -1e-6),
    )
    assert log.n_pings == 0
    assert not log.has_navigation


def test_add_warning_is_idempotent() -> None:
    log = _log()
    log.add_warning("TRUNCATED_FILE")
    log.add_warning("TRUNCATED_FILE")
    assert log.warnings == ["TRUNCATED_FILE"]
