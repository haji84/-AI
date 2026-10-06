from backend.app.drawing_annotation_qa import build_annotation_qa


def test_annotation_qa_blocks_missing_labels_and_overlap():
    result = build_annotation_qa(
        status="draft",
        payload={
            "elements": [
                {"element_type": "room", "page_no": 1, "geometry": {"points": [[0, 0], [2, 0], [2, 2], [0, 2]]}},
                {"element_type": "zone", "page_no": 1, "label": "通路", "geometry": {"points": [[1, 1], [3, 1], [3, 3], [1, 3]]}},
            ],
            "geometry_summary": {
                "overlap_warnings": [{"warning": "interior_overlap"}],
                "floor_summaries": [],
                "area_target_comparisons": [],
            },
        },
        page_dimensions={"1": {}},
    )

    assert result["reference_reviewable"] is False
    assert result["counts"]["missing_label_or_usage_count"] == 1
    assert result["counts"]["overlap_warning_count"] == 1
    assert result["uncalibrated_pages"] == [1]
    assert {x["code"] for x in result["blockers"]} == {
        "missing_label_or_usage",
        "overlap_warning",
    }


def test_annotation_qa_allows_review_with_calibration_and_tracks_open_plan():
    result = build_annotation_qa(
        status="reviewed",
        payload={
            "elements": [
                {
                    "element_type": "room",
                    "page_no": 1,
                    "label": "事務室",
                    "geometry": {"points": [[0, 0], [2, 0], [2, 2], [0, 2]]},
                    "extracted_data": {"open_plan_approximation": True},
                }
            ],
            "geometry_summary": {
                "overlap_warnings": [],
                "floor_summaries": [{"floor_number": 1, "region_count": 1}],
                "area_target_comparisons": [
                    {"floor_number": 1, "status": "comparable"}
                ],
            },
        },
        page_dimensions={"1": {"calibration": {"meters_per_pixel": 0.05}}},
    )

    assert result["reference_reviewable"] is True
    assert result["reviewed_reference_ready"] is True
    assert result["area_comparison_ready"] is True
    assert result["counts"]["open_plan_approximation_count"] == 1
    assert result["warnings"][0]["code"] == "open_plan_approximation"
