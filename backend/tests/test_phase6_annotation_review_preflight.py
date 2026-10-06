from app.drawing_annotation_preflight import (
    build_annotation_review_preflight,
    mark_reference_elements_reviewed,
)


def test_phase6_annotation_preflight_surfaces_overlap_area_and_approximate_warnings():
    payload = {
        "elements": [
            {
                "client_ref": "room-a",
                "element_type": "room",
                "label": "L",
                "floor_number": 1,
                "geometry": {"points": [[0,0],[100,0],[100,100],[0,100]]},
                "reference_meta": {
                    "geometry_quality": "open_plan_approx",
                    "human_review_status": "pending",
                },
            },
            {
                "client_ref": "room-b",
                "element_type": "room",
                "label": "D",
                "floor_number": 1,
                "geometry": {"points": [[50,0],[150,0],[150,100],[50,100]]},
            },
        ],
        "geometry_summary": {
            "overlap_warnings": [
                {
                    "page_no": 1,
                    "floor_number": 1,
                    "left_ref": "room-a",
                    "left_label": "L",
                    "right_ref": "room-b",
                    "right_label": "D",
                }
            ],
            "area_target_comparisons": [
                {
                    "floor_number": 1,
                    "status": "room_area_uncalibrated",
                    "target_area_m2": 78.66,
                    "measured_room_area_m2": None,
                    "difference_m2": None,
                    "difference_pct": None,
                }
            ],
        },
    }

    result = build_annotation_review_preflight(payload)
    assert result["ready_for_review"] is True
    assert result["acknowledgement_required"] is True
    assert result["blocker_count"] == 0
    codes = set(result["warning_codes"])
    assert "approximate_geometry:room-a" in codes
    assert "interior_overlap:room-a:room-b" in codes
    assert "area_target_uncalibrated:1" in codes


def test_phase6_annotation_preflight_blocks_missing_label_and_invalid_polygon():
    payload = {
        "elements": [
            {
                "client_ref": "room-a",
                "element_type": "room",
                "label": None,
                "floor_number": 1,
                "geometry": {"points": [[0,0],[10,0]]},
                "extracted_data": {},
            }
        ],
        "geometry_summary": {},
    }

    result = build_annotation_review_preflight(payload)
    assert result["ready_for_review"] is False
    codes = set(result["blocker_codes"])
    assert "missing_label_or_use:room-a" in codes
    assert "invalid_polygon:room-a" in codes


def test_phase6_annotation_preflight_area_comparison_is_information_not_auto_reject():
    payload = {
        "elements": [
            {
                "client_ref": "room-a",
                "element_type": "room",
                "label": "Room A",
                "floor_number": 1,
                "geometry": {"points": [[0,0],[10,0],[10,10],[0,10]]},
            }
        ],
        "geometry_summary": {
            "area_target_comparisons": [
                {
                    "floor_number": 1,
                    "status": "comparable",
                    "target_area_m2": 78.66,
                    "measured_room_area_m2": 77.5,
                    "difference_m2": -1.16,
                    "difference_pct": -1.4747,
                }
            ],
            "overlap_warnings": [],
        },
    }

    result = build_annotation_review_preflight(payload)
    assert result["ready_for_review"] is True
    assert result["warning_count"] == 0
    assert result["info_count"] == 1
    assert result["infos"][0]["code"] == "area_target_comparison:1"


def test_phase6_mark_reference_elements_reviewed_preserves_quality_and_marks_status():
    payload = {
        "elements": [
            {
                "client_ref": "room-a",
                "element_type": "room",
                "reference_meta": {
                    "geometry_quality": "open_plan_approx",
                    "human_review_status": "pending",
                },
            },
            {
                "client_ref": "zone-a",
                "element_type": "zone",
                "reference_meta": {
                    "geometry_quality": "service_area_approx",
                },
            },
        ]
    }

    out = mark_reference_elements_reviewed(
        payload,
        reviewed_at="2026-10-06T12:00:00+00:00",
    )
    assert out["elements"][0]["reference_meta"]["geometry_quality"] == "open_plan_approx"
    assert out["elements"][0]["reference_meta"]["human_review_status"] == "reviewed"
    assert out["elements"][1]["reference_meta"]["human_review_status"] == "reviewed"
    assert out["elements"][1]["reference_meta"]["human_reviewed_at"] == "2026-10-06T12:00:00+00:00"
