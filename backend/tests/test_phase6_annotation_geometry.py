from __future__ import annotations

import importlib.util
from pathlib import Path


def _mod():
    path = (
        Path(__file__).resolve().parents[1]
        / "app"
        / "drawing_annotation_geometry.py"
    )
    spec = importlib.util.spec_from_file_location(
        "drawing_annotation_geometry",
        path,
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_phase6_polygon_area_and_calibrated_square_meters():
    mod = _mod()
    payload = {
        "elements": [
            {
                "client_ref": "room-1",
                "page_no": 1,
                "element_type": "room",
                "geometry": {
                    "points": [
                        [0, 0],
                        [100, 0],
                        [100, 50],
                        [0, 50],
                    ]
                },
            }
        ]
    }
    page_dimensions = {
        "1": {
            "width": 1000,
            "height": 800,
            "calibration": {
                "method": "two_point",
                "point_a": [0, 0],
                "point_b": [100, 0],
                "reference_length_m": 2.0,
            },
        }
    }

    result, dims = mod.apply_geometry_metrics(
        payload,
        page_dimensions,
    )
    metrics = result["elements"][0]["derived_geometry"]

    assert metrics["area_px2"] == 5000.0
    assert metrics["perimeter_px"] == 300.0
    assert metrics["meters_per_pixel"] == 0.02
    assert metrics["area_m2"] == 2.0
    assert metrics["perimeter_m"] == 6.0
    assert metrics["calibration_status"] == "calibrated"
    assert dims["1"]["calibration"]["pixel_distance"] == 100.0


def test_phase6_geometry_edit_recalculates_area():
    mod = _mod()
    payload = {
        "elements": [
            {
                "client_ref": "room-1",
                "page_no": 1,
                "element_type": "room",
                "geometry": {
                    "points": [
                        [0, 0],
                        [200, 0],
                        [200, 50],
                        [0, 50],
                    ]
                },
                "derived_geometry": {
                    "area_px2": 999999,
                    "area_m2": 999999,
                },
            }
        ]
    }
    page_dimensions = {
        "1": {
            "width": 1000,
            "height": 800,
            "calibration": {
                "method": "two_point",
                "point_a": [0, 0],
                "point_b": [100, 0],
                "reference_length_m": 2.0,
            },
        }
    }

    result, _ = mod.apply_geometry_metrics(
        payload,
        page_dimensions,
    )
    metrics = result["elements"][0]["derived_geometry"]

    assert metrics["area_px2"] == 10000.0
    assert metrics["area_m2"] == 4.0


def test_phase6_uncalibrated_zone_keeps_px_area_and_null_square_meters():
    mod = _mod()
    payload = {
        "elements": [
            {
                "client_ref": "zone-1",
                "page_no": 1,
                "element_type": "zone",
                "geometry": {
                    "points": [
                        [0, 0],
                        [10, 0],
                        [10, 10],
                        [0, 10],
                    ]
                },
            }
        ]
    }

    result, _ = mod.apply_geometry_metrics(
        payload,
        {"1": {"width": 100, "height": 100}},
    )
    metrics = result["elements"][0]["derived_geometry"]

    assert metrics["area_px2"] == 100.0
    assert metrics["area_m2"] is None
    assert metrics["calibration_status"] == "uncalibrated"


def test_phase6_invalid_two_point_calibration_is_rejected():
    mod = _mod()
    payload = {"elements": []}
    bad = {
        "1": {
            "width": 100,
            "height": 100,
            "calibration": {
                "method": "two_point",
                "point_a": [10, 10],
                "point_b": [10, 10],
                "reference_length_m": 2.0,
            },
        }
    }

    try:
        mod.apply_geometry_metrics(payload, bad)
        assert False, "expected ValueError"
    except ValueError as exc:
        assert "points must differ" in str(exc)
