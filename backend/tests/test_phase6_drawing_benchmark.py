from __future__ import annotations

import importlib.util
import json
from pathlib import Path


def _mod():
    script = Path(__file__).resolve().parents[2] / "scripts" / "benchmark_drawing_analysis.py"
    spec = importlib.util.spec_from_file_location("benchmark_drawing_analysis", script)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_phase6_drawing_benchmark_geometry_symbol_equipment_and_fact_metrics():
    mod = _mod()
    reference = {
        "elements": [
            {
                "client_ref": "r1",
                "page_no": 1,
                "element_type": "equipment_symbol",
                "geometry": {"x": 0, "y": 0, "width": 100, "height": 100},
                "extracted_data": {"symbol": "FA"},
            },
            {
                "client_ref": "r2",
                "page_no": 1,
                "element_type": "room",
                "geometry": {"x1": 200, "y1": 0, "x2": 300, "y2": 100},
            },
        ],
        "equipment_candidates": [
            {"drawing_element_ref": "r1", "suggested_equipment_type_code": "automatic_fire_alarm"}
        ],
        "fact_candidates": [
            {"target_path": "detail.total_floor_area", "proposed_value": {"value": 999.5}}
        ],
    }
    hypothesis = {
        "elements": [
            {
                "client_ref": "h1",
                "page_no": 1,
                "element_type": "equipment_symbol",
                "geometry": {"bbox": [5, 5, 100, 100]},
                "extracted_data": {"symbol": "FA"},
            },
            {
                "client_ref": "h2",
                "page_no": 1,
                "element_type": "text",
                "geometry": {"x": 200, "y": 0, "width": 100, "height": 100},
            },
            {
                "client_ref": "extra",
                "page_no": 1,
                "element_type": "equipment_symbol",
                "geometry": {"x": 400, "y": 0, "width": 50, "height": 50},
                "extracted_data": {"symbol": "X"},
            },
        ],
        "equipment_candidates": [
            {"drawing_element_ref": "h1", "suggested_equipment_type_code": "automatic_fire_alarm"},
            {"drawing_element_ref": "extra", "suggested_equipment_type_code": "sprinkler"},
        ],
        "fact_candidates": [
            {"target_path": "detail.total_floor_area", "proposed_value": {"value": 999.5}},
            {"target_path": "detail.above_ground_floors", "proposed_value": {"value": 3}},
        ],
    }

    result = mod.score_drawing(reference, hypothesis, 0.5)
    geo = result["geometry_detection"]
    assert geo["true_positive"] == 2
    assert geo["false_positive"] == 1
    assert geo["false_negative"] == 0
    assert geo["element_type_correct"] == 1
    assert geo["element_type_accuracy"] == 0.5
    assert result["symbol_classification"]["accuracy"] == 1.0
    assert result["equipment_candidates"]["true_positive"] == 1
    assert result["equipment_candidates"]["false_positive"] == 1
    assert result["fact_candidates"]["true_positive"] == 1
    assert result["fact_candidates"]["false_positive"] == 1


def test_phase6_drawing_benchmark_one_to_one_geometry_matching_prevents_double_match():
    mod = _mod()
    reference = {
        "elements": [
            {"page_no": 1, "element_type": "symbol", "geometry": {"x": 0, "y": 0, "width": 100, "height": 100}},
            {"page_no": 1, "element_type": "symbol", "geometry": {"x": 10, "y": 10, "width": 80, "height": 80}},
        ]
    }
    hypothesis = {
        "elements": [
            {"page_no": 1, "element_type": "symbol", "geometry": {"x": 0, "y": 0, "width": 100, "height": 100}}
        ]
    }
    result = mod.score_drawing(reference, hypothesis, 0.5)
    assert result["geometry_detection"]["true_positive"] == 1
    assert result["geometry_detection"]["false_negative"] == 1
    assert result["geometry_detection"]["false_positive"] == 0


def test_phase6_drawing_benchmark_manifest_micro_aggregate_and_hashes(tmp_path):
    mod = _mod()
    r1 = {"elements": [{"page_no": 1, "element_type": "room", "geometry": {"points": [[0,0],[10,0],[10,10],[0,10]]}}]}
    h1 = {"elements": [{"page_no": 1, "element_type": "room", "geometry": {"x": 0, "y": 0, "width": 10, "height": 10}}]}
    r2 = {"elements": [{"page_no": 1, "element_type": "room", "geometry": {"x": 0, "y": 0, "width": 10, "height": 10}}]}
    h2 = {"elements": []}

    for name, payload in {"r1.json": r1, "h1.json": h1, "r2.json": r2, "h2.json": h2}.items():
        (tmp_path / name).write_text(json.dumps(payload), encoding="utf-8")

    manifest = {
        "iou_threshold": 0.5,
        "drawings": [
            {"id": "one", "reference": "r1.json", "hypothesis": "h1.json"},
            {"id": "two", "reference": "r2.json", "hypothesis": "h2.json"},
        ],
    }
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps(manifest), encoding="utf-8")

    result = mod.score_manifest(path)
    assert result["benchmark_format"] == "fire-ai-drawing-benchmark-v1"
    assert len(result["manifest_sha256"]) == 64
    assert len(result["drawings"][0]["reference_sha256"]) == 64
    assert result["aggregate"]["drawing_count"] == 2
    assert result["aggregate"]["geometry_detection"]["true_positive"] == 1
    assert result["aggregate"]["geometry_detection"]["false_negative"] == 1
    assert result["aggregate"]["geometry_detection"]["recall"] == 0.5
    assert result["aggregate"]["geometry_detection"]["mean_iou"] == 1.0



def test_phase6_drawing_benchmark_empty_optional_targets_are_not_fake_perfect_scores():
    mod = _mod()
    reference = {
        "elements": [
            {
                "client_ref": "room-1",
                "page_no": 1,
                "element_type": "room",
                "geometry": {"x": 0, "y": 0, "width": 100, "height": 100},
            }
        ],
        "equipment_candidates": [],
        "fact_candidates": [],
    }
    hypothesis = {
        "elements": [
            {
                "client_ref": "room-a",
                "page_no": 1,
                "element_type": "room",
                "geometry": {"x": 0, "y": 0, "width": 100, "height": 100},
            }
        ],
        "equipment_candidates": [],
        "fact_candidates": [],
    }
    result = mod.score_drawing(reference, hypothesis, 0.5)

    assert result["geometry_detection"]["f1"] == 1.0
    assert result["symbol_classification"]["accuracy"] is None
    assert result["symbol_classification"]["applicable"] is False
    assert result["equipment_candidates"]["f1"] is None
    assert result["equipment_candidates"]["applicable"] is False
    assert result["fact_candidates"]["f1"] is None
    assert result["fact_candidates"]["applicable"] is False


def test_phase6_drawing_benchmark_false_positive_only_category_is_not_na():
    mod = _mod()
    result = mod.score_drawing(
        {"elements": [], "equipment_candidates": []},
        {
            "elements": [],
            "equipment_candidates": [
                {"suggested_equipment_type_code": "sprinkler", "floor_number": 1}
            ],
        },
        0.5,
    )
    equipment = result["equipment_candidates"]
    assert equipment["applicable"] is True
    assert equipment["false_positive"] == 1
    assert equipment["precision"] == 0.0
    assert equipment["recall"] is None
    assert equipment["f1"] == 0.0



def test_phase6_drawing_benchmark_blocks_pending_human_reference(tmp_path):
    mod = _mod()
    reference = {
        "reference_format": "fire-ai-drawing-human-reference-draft-v1",
        "reference_status": "pending_human_acceptance",
        "elements": [],
        "equipment_candidates": [],
        "fact_candidates": [],
    }
    hypothesis = {
        "elements": [],
        "equipment_candidates": [],
        "fact_candidates": [],
    }
    ref_path = tmp_path / "reference.json"
    hyp_path = tmp_path / "hypothesis.json"
    ref_path.write_text(json.dumps(reference), encoding="utf-8")
    hyp_path.write_text(json.dumps(hypothesis), encoding="utf-8")

    try:
        mod.score_pair(ref_path, hyp_path)
        assert False, "expected ValueError"
    except ValueError as exc:
        assert "Human-accepted drawing reference is required" in str(exc)


def test_phase6_drawing_benchmark_accepts_human_accepted_reference(tmp_path):
    mod = _mod()
    reference = {
        "reference_format": "fire-ai-drawing-human-reference-v1",
        "reference_status": "human_accepted",
        "elements": [
            {
                "page_no": 1,
                "element_type": "room",
                "geometry": {"x": 0, "y": 0, "width": 10, "height": 10},
            }
        ],
        "equipment_candidates": [],
        "fact_candidates": [],
    }
    hypothesis = {
        "elements": [
            {
                "page_no": 1,
                "element_type": "room",
                "geometry": {"x": 0, "y": 0, "width": 10, "height": 10},
            }
        ],
        "equipment_candidates": [],
        "fact_candidates": [],
    }
    ref_path = tmp_path / "reference.json"
    hyp_path = tmp_path / "hypothesis.json"
    ref_path.write_text(json.dumps(reference), encoding="utf-8")
    hyp_path.write_text(json.dumps(hypothesis), encoding="utf-8")

    result = mod.score_pair(ref_path, hyp_path)
    assert result["metrics"]["geometry_detection"]["f1"] == 1.0


def test_phase6_drawing_benchmark_accepts_reviewed_export_reference(tmp_path):
    mod = _mod()
    reference = {
        "reference_format": "fire-ai-drawing-human-reference-v1",
        "human_review": {"status": "reviewed"},
        "elements": [],
        "equipment_candidates": [],
        "fact_candidates": [],
    }
    hypothesis = {
        "elements": [],
        "equipment_candidates": [],
        "fact_candidates": [],
    }
    ref_path = tmp_path / "reference.json"
    hyp_path = tmp_path / "hypothesis.json"
    ref_path.write_text(json.dumps(reference), encoding="utf-8")
    hyp_path.write_text(json.dumps(hypothesis), encoding="utf-8")

    result = mod.score_pair(ref_path, hyp_path)
    assert result["metrics"]["geometry_detection"]["applicable"] is False


def test_phase6_house_plan_001_geometry_draft_is_complete_but_not_accepted():
    path = (
        Path(__file__).resolve().parents[2]
        / "benchmarks"
        / "phase6"
        / "reference"
        / "house-plan-001.reference.json"
    )
    data = json.loads(path.read_text(encoding="utf-8"))

    assert data["reference_status"] == "pending_human_acceptance"
    assert data["scope"]["geometry_annotation_complete"] is True
    assert data["scope"]["geometry_human_review_required"] is True
    assert data["human_gate"]["accepted"] is False
    assert len(data["elements"]) == 12

    labels = {x["label"] for x in data["elements"]}
    assert labels == {
        "UB",
        "トイレ",
        "洗面脱衣室",
        "玄関",
        "ホール",
        "WIC",
        "主寝室",
        "タタミコーナー",
        "L",
        "D",
        "K",
        "P",
    }

    width = data["source"]["pixel_width"]
    height = data["source"]["pixel_height"]
    refs = set()
    for element in data["elements"]:
        assert element["client_ref"] not in refs
        refs.add(element["client_ref"])
        assert element["element_type"] == "room"
        assert element["page_no"] == 1
        points = element["geometry"]["points"]
        assert len(points) >= 3
        assert all(0 <= x <= width and 0 <= y <= height for x, y in points)
        assert element["reference_meta"]["human_review_status"] == "pending"



def test_phase6_drawing_benchmark_rejects_status_only_acceptance_when_human_gate_is_false(tmp_path):
    mod = _mod()
    reference = {
        "reference_format": "fire-ai-drawing-human-reference-draft-v1",
        "reference_status": "human_accepted",
        "human_gate": {
            "required": True,
            "accepted": False,
        },
        "elements": [],
        "equipment_candidates": [],
        "fact_candidates": [],
    }
    hypothesis = {
        "elements": [],
        "equipment_candidates": [],
        "fact_candidates": [],
    }
    ref_path = tmp_path / "reference.json"
    hyp_path = tmp_path / "hypothesis.json"
    ref_path.write_text(json.dumps(reference), encoding="utf-8")
    hyp_path.write_text(json.dumps(hypothesis), encoding="utf-8")

    try:
        mod.score_pair(ref_path, hyp_path)
        assert False, "expected ValueError"
    except ValueError as exc:
        assert "Human-accepted drawing reference is required" in str(exc)



def test_phase6_drawing_benchmark_rejects_reference_hypothesis_source_mismatch(tmp_path):
    mod = _mod()
    reference = {
        "reference_format": "fire-ai-drawing-human-reference-v1",
        "reference_status": "human_accepted",
        "source": {"sha256": "a" * 64},
        "elements": [],
        "equipment_candidates": [],
        "fact_candidates": [],
    }
    hypothesis = {
        "hypothesis_format": "fire-ai-drawing-hypothesis-v1",
        "source": {"sha256": "b" * 64},
        "elements": [],
        "equipment_candidates": [],
        "fact_candidates": [],
    }
    ref_path = tmp_path / "reference.json"
    hyp_path = tmp_path / "hypothesis.json"
    ref_path.write_text(json.dumps(reference), encoding="utf-8")
    hyp_path.write_text(json.dumps(hypothesis), encoding="utf-8")

    try:
        mod.score_pair(ref_path, hyp_path)
        assert False, "expected ValueError"
    except ValueError as exc:
        assert "source drawing SHA-256 mismatch" in str(exc)


def test_phase6_drawing_benchmark_accepts_same_source_reference_hypothesis(tmp_path):
    mod = _mod()
    source_sha = "c" * 64
    reference = {
        "reference_format": "fire-ai-drawing-human-reference-v1",
        "reference_status": "human_accepted",
        "source": {"sha256": source_sha},
        "elements": [],
        "equipment_candidates": [],
        "fact_candidates": [],
    }
    hypothesis = {
        "hypothesis_format": "fire-ai-drawing-hypothesis-v1",
        "source": {"sha256": source_sha},
        "elements": [],
        "equipment_candidates": [],
        "fact_candidates": [],
    }
    ref_path = tmp_path / "reference.json"
    hyp_path = tmp_path / "hypothesis.json"
    ref_path.write_text(json.dumps(reference), encoding="utf-8")
    hyp_path.write_text(json.dumps(hypothesis), encoding="utf-8")

    result = mod.score_pair(ref_path, hyp_path)
    assert result["metrics"]["geometry_detection"]["applicable"] is False
