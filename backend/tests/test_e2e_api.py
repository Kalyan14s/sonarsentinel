"""End to end through the API (no browser): TC-E2E-001 (XTF upload → events → detail → CSV with the
same coordinates as JSON), TC-E2E-002 (image + sparse nav CSV → GPS_INTERPOLATED) and TC-E2E-003
(image without GPS → NOT_GEOTAGGED, no geographic exports)."""

from __future__ import annotations

import csv
import io
import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import pytest

pytest.importorskip("fastapi")
pytest.importorskip("httpx")
pytest.importorskip("sqlalchemy")
pytest.importorskip("pyxtf")
pytest.importorskip("scipy")
cv2 = pytest.importorskip("cv2")

from fastapi.testclient import TestClient  # noqa: E402
from pyproj import Geod  # noqa: E402
from starlette.websockets import WebSocketDisconnect  # noqa: E402
from tools.make_synthetic_xtf import write_synthetic_xtf  # noqa: E402

from sonarsentinel.api.main import API_PREFIX, create_app  # noqa: E402
from sonarsentinel.config import load_config  # noqa: E402

API = API_PREFIX
OPTIONS: dict[str, Any] = {"detector_model": "classical", "anomaly_scan": False}


@pytest.fixture
def client(tmp_path: Path) -> Iterator[TestClient]:
    cfg = load_config()
    cfg["chunking"] = {"pings_per_chunk": 200, "overlap_pings": 40}
    with TestClient(create_app(cfg, data_dir=tmp_path / "data")) as test_client:
        yield test_client


def _run(
    client: TestClient,
    files: list[tuple[str, str, bytes]],
    options: dict[str, Any],
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    response = client.post(
        f"{API}/surveys",
        files=[
            (field, (name, content, "application/octet-stream")) for field, name, content in files
        ],
        data={"options": json.dumps(options)},
    )
    assert response.status_code == 202, response.text
    body: dict[str, Any] = response.json()
    events: list[dict[str, Any]] = []
    with client.websocket_connect(body["ws_url"]) as ws:
        try:
            while True:
                events.append(ws.receive_json())
        except WebSocketDisconnect:
            pass
    return body, events


def _image(path: Path, rows: int = 400, cols: int = 800) -> bytes:
    rng = np.random.default_rng(0)
    image = np.clip(rng.normal(110, 12, (rows, cols)), 0, 255).astype(np.uint8)
    image[180:195, 600:640] = 250
    ok, png = cv2.imencode(".png", image)
    assert ok
    path.write_bytes(png.tobytes())
    return png.tobytes()


def test_xtf_upload_to_csv(client: TestClient, tmp_path: Path) -> None:
    """TC-E2E-001: AC-01 through the API."""
    survey = write_synthetic_xtf(
        tmp_path / "line_e2e.xtf",
        n_pings=600,
        samples_per_side=400,
        step_m=0.1,
        targets=[(150, "starboard", 250), (430, "port", 300)],
        target_extent=(12, 30),
    )
    body, events = _run(
        client, [("files", "line_e2e.xtf", Path(survey.path).read_bytes())], OPTIONS
    )
    kinds = [e["type"] for e in events]
    assert "track" in kinds and "detection" in kinds and kinds[-1] == "done"
    assert kinds.index("detection") < kinds.index("done")

    sid = body["survey_id"]
    detail = client.get(f"{API}/surveys/{sid}").json()
    assert detail["summary"]["total_detections"] == events[-1]["summary"]["total_detections"] > 0
    detections = client.get(f"{API}/surveys/{sid}/detections", params={"limit": 5000}).json()
    by_id = {d["detection_id"]: d for d in detections["items"]}
    assert len(by_id) == detections["total"]
    for det in by_id.values():
        lat, lon = det["position"]["lat"], det["position"]["lon"]
        assert lat is not None and round(lat, 6) == lat and round(lon, 6) == lon

    csv_text = client.get(detail["report_urls"]["csv"]).text
    rows = list(csv.DictReader(io.StringIO(csv_text)))
    assert {r["detection_id"] for r in rows} == set(by_id)
    for row in rows:
        det = by_id[row["detection_id"]]
        assert row["lat"] == f"{det['position']['lat']:.6f}"
        assert row["lon"] == f"{det['position']['lon']:.6f}"
    track = client.get(f"{API}/surveys/{sid}/track").json()["features"][0]["geometry"]
    assert track["type"] == "LineString" and len(track["coordinates"]) >= 2


def test_image_with_sparse_nav_is_geotagged_and_interpolated(
    client: TestClient, tmp_path: Path
) -> None:
    """TC-E2E-002: image + nav CSV with fewer rows than pings → positions, GPS_INTERPOLATED."""
    rows = 400
    png = _image(tmp_path / "harbour.png", rows=rows)
    pings = np.arange(0, rows, 25)
    geod = Geod(ellps="WGS84")
    lon, lat, _ = geod.fwd(
        np.full(rows, 80.3071), np.full(rows, 13.0802), np.full(rows, 62.4), np.arange(rows) * 0.1
    )
    nav = pd.DataFrame(
        {
            "ping": pings,
            "time_utc": pd.to_datetime("2026-09-12T05:10:02Z") + pd.to_timedelta(pings * 0.1, "s"),
            "lat": np.asarray(lat)[pings],
            "lon": np.asarray(lon)[pings],
            "heading_deg": 62.4,
            "slant_range_m": 40.0,
            "altitude_m": 8.0,
        }
    ).to_csv(index=False)
    body, events = _run(
        client,
        [("files", "harbour.png", png), ("nav_csv", "harbour_nav.csv", nav.encode())],
        OPTIONS,
    )
    assert events[-1]["type"] == "done", events[-1]
    detections = client.get(
        f"{API}/surveys/{body['survey_id']}/detections", params={"limit": 5000}
    ).json()["items"]
    assert detections, "bright patch should be detected"
    assert all(d["position"]["lat"] is not None for d in detections)
    assert any("GPS_INTERPOLATED" in d["quality_flags"] for d in detections)


def test_image_without_gps_is_not_geotagged(client: TestClient, tmp_path: Path) -> None:
    """TC-E2E-003: AC-02 through the API; GeoJSON/KML are refused with 409."""
    png = _image(tmp_path / "harbour.png")
    body, events = _run(client, [("files", "harbour.png", png)], OPTIONS | {"allow_no_gps": True})
    done = events[-1]
    assert done["type"] == "done" and sorted(done["report_urls"]) == ["csv", "json"]
    sid = body["survey_id"]
    detections = client.get(f"{API}/surveys/{sid}/detections", params={"limit": 5000}).json()[
        "items"
    ]
    assert detections
    for det in detections:
        assert det["position"]["lat"] is None and det["position"]["lon"] is None
        assert "NOT_GEOTAGGED" in det["quality_flags"] and len(det["sonar_ref"]["pixel_bbox"]) == 4
    assert sorted(client.get(f"{API}/surveys/{sid}").json()["report_urls"]) == ["csv", "json"]
    for fmt in ("geojson", "kml"):
        refused = client.get(f"{API}/surveys/{sid}/report", params={"format": fmt})
        assert refused.status_code == 409 and refused.json()["error"]["code"] == "VALIDATION_ERROR"
    assert client.get(f"{API}/surveys/{sid}/report", params={"format": "csv"}).status_code == 200
