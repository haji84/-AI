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



def test_phase6_floor_summary_totals_calibrated_regions():
    mod = _mod()
    payload = {
        "elements": [
            {
                "client_ref": "room-a",
                "page_no": 1,
                "floor_number": 1,
                "element_type": "room",
                "label": "A",
                "geometry": {
                    "points": [[0, 0], [100, 0], [100, 50], [0, 50]]
                },
            },
            {
                "client_ref": "zone-b",
                "page_no": 1,
                "floor_number": 1,
                "element_type": "zone",
                "label": "B",
                "geometry": {
                    "points": [[100, 0], [200, 0], [200, 50], [100, 50]]
                },
            },
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

    result, _ = mod.apply_geometry_metrics(payload, page_dimensions)
    summary = result["geometry_summary"]

    assert summary["summary_version"] == "drawing-geometry-summary-v1"
    assert summary["region_count"] == 2
    assert summary["overlap_warning_count"] == 0

    floor = summary["floor_summaries"][0]
    assert floor["floor_number"] == 1
    assert floor["region_count"] == 2
    assert floor["room_count"] == 1
    assert floor["zone_count"] == 1
    assert floor["area_px2_total"] == 10000.0
    assert floor["area_m2_total"] == 4.0
    assert floor["calibrated_region_count"] == 2
    assert floor["uncalibrated_region_count"] == 0
    assert floor["metric_area_complete"] is True


def test_phase6_floor_summary_shared_boundary_is_not_overlap():
    mod = _mod()
    payload = {
        "elements": [
            {
                "client_ref": "left",
                "page_no": 1,
                "floor_number": 1,
                "element_type": "room",
                "label": "左",
                "geometry": {
                    "points": [[0, 0], [100, 0], [100, 100], [0, 100]]
                },
            },
            {
                "client_ref": "right",
                "page_no": 1,
                "floor_number": 1,
                "element_type": "room",
                "label": "右",
                "geometry": {
                    "points": [[100, 0], [200, 0], [200, 100], [100, 100]]
                },
            },
        ]
    }

    result, _ = mod.apply_geometry_metrics(
        payload,
        {"1": {"width": 300, "height": 200}},
    )

    assert result["geometry_summary"]["overlap_warning_count"] == 0


def test_phase6_floor_summary_detects_interior_overlap_but_not_other_floor():
    mod = _mod()
    payload = {
        "elements": [
            {
                "client_ref": "base",
                "page_no": 1,
                "floor_number": 1,
                "element_type": "room",
                "label": "基準",
                "geometry": {
                    "points": [[0, 0], [100, 0], [100, 100], [0, 100]]
                },
            },
            {
                "client_ref": "overlap",
                "page_no": 1,
                "floor_number": 1,
                "element_type": "zone",
                "label": "重複",
                "geometry": {
                    "points": [[50, 50], [150, 50], [150, 150], [50, 150]]
                },
            },
            {
                "client_ref": "floor-two",
                "page_no": 1,
                "floor_number": 2,
                "element_type": "room",
                "label": "2階",
                "geometry": {
                    "points": [[50, 50], [150, 50], [150, 150], [50, 150]]
                },
            },
        ]
    }

    result, _ = mod.apply_geometry_metrics(
        payload,
        {"1": {"width": 300, "height": 200}},
    )
    summary = result["geometry_summary"]

    assert summary["overlap_warning_count"] == 1
    warning = summary["overlap_warnings"][0]
    assert {warning["left_ref"], warning["right_ref"]} == {"base", "overlap"}
    assert warning["warning"] == "interior_overlap"


def test_phase6_floor_summary_marks_metric_total_incomplete_without_scale():
    mod = _mod()
    payload = {
        "elements": [
            {
                "client_ref": "uncalibrated",
                "page_no": 1,
                "floor_number": 1,
                "element_type": "room",
                "geometry": {
                    "points": [[0, 0], [10, 0], [10, 10], [0, 10]]
                },
            }
        ]
    }

    result, _ = mod.apply_geometry_metrics(
        payload,
        {"1": {"width": 100, "height": 100}},
    )
    floor = result["geometry_summary"]["floor_summaries"][0]

    assert floor["area_px2_total"] == 100.0
    assert floor["area_m2_total"] is None
    assert floor["metric_area_complete"] is False
    assert floor["uncalibrated_region_count"] == 1



def test_phase6_geometry_summary_overwrites_fake_client_totals():
    mod = _mod()
    payload = {
        "geometry_summary": {
            "summary_version": "fake",
            "region_count": 999,
            "floor_summaries": [{"area_m2_total": 999999}],
            "overlap_warning_count": 999,
        },
        "elements": [
            {
                "client_ref": "room-real",
                "page_no": 1,
                "floor_number": 1,
                "element_type": "room",
                "geometry": {
                    "points": [[0, 0], [100, 0], [100, 50], [0, 50]]
                },
            }
        ],
    }
    page_dimensions = {
        "1": {
            "width": 200,
            "height": 100,
            "calibration": {
                "method": "two_point",
                "point_a": [0, 0],
                "point_b": [100, 0],
                "reference_length_m": 2.0,
            },
        }
    }

    result, _ = mod.apply_geometry_metrics(payload, page_dimensions)
    summary = result["geometry_summary"]

    assert summary["summary_version"] == "drawing-geometry-summary-v1"
    assert summary["region_count"] == 1
    assert summary["overlap_warning_count"] == 0
    assert summary["floor_summaries"][0]["area_m2_total"] == 2.0
