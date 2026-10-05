from __future__ import annotations

import importlib.util
import json
from pathlib import Path


def _load_module():
    script = Path(__file__).resolve().parents[2] / "scripts" / "benchmark_fire_evidence_comparison.py"
    spec = importlib.util.spec_from_file_location(
        "benchmark_fire_evidence_comparison",
        script,
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_phase9_evidence_comparison_benchmark_is_order_independent_and_counts_duplicates():
    mod = _load_module()
    reference = [
        {
            "issue_type": "time_conflict",
            "left_ref": {"type": "statement", "id": "s1"},
            "right_ref": {"type": "timeline_event", "id": "t1"},
        },
        {
            "issue_type": "location_conflict",
            "left_ref": {"type": "statement", "id": "s2"},
            "right_ref": {"type": "statement", "id": "s3"},
        },
    ]
    hypothesis = [
        {
            "issue_type": "time_conflict",
            "left_ref": {"type": "timeline_event", "id": "t1"},
            "right_ref": {"type": "statement", "id": "s1"},
        },
        {
            "issue_type": "time_conflict",
            "left_ref": {"type": "timeline_event", "id": "t1"},
            "right_ref": {"type": "statement", "id": "s1"},
        },
        {
            "issue_type": "cause_conflict",
            "left_ref": {"type": "statement", "id": "s4"},
            "right_ref": {"type": "statement", "id": "s5"},
        },
    ]

    result = mod.score_comparisons(reference, hypothesis)

    assert result["true_positive"] == 1
    assert result["false_positive"] == 2
    assert result["false_negative"] == 1
    assert result["precision"] == 1 / 3
    assert result["recall"] == 1 / 2
    assert round(result["f1"], 6) == 0.4
    assert result["by_issue_type"]["time_conflict"]["true_positive"] == 1
    assert result["by_issue_type"]["time_conflict"]["false_positive"] == 1
    assert result["by_issue_type"]["location_conflict"]["false_negative"] == 1
    assert result["by_issue_type"]["cause_conflict"]["false_positive"] == 1


def test_phase9_evidence_comparison_benchmark_manifest_micro_aggregate_and_hashes(tmp_path):
    mod = _load_module()

    r1 = {
        "comparisons": [
            {
                "issue_type": "time_conflict",
                "left_ref": {"type": "statement", "id": "a"},
                "right_ref": {"type": "timeline_event", "id": "b"},
            }
        ]
    }
    h1 = {
        "comparisons": [
            {
                "issue_type": "time_conflict",
                "left_ref": {"type": "timeline_event", "id": "b"},
                "right_ref": {"type": "statement", "id": "a"},
            },
            {
                "issue_type": "time_conflict",
                "left_ref": {"type": "statement", "id": "x"},
                "right_ref": {"type": "timeline_event", "id": "y"},
            },
        ]
    }
    r2 = {
        "comparisons": [
            {
                "issue_type": "location_conflict",
                "left_ref": {"type": "statement", "id": "c"},
                "right_ref": {"type": "statement", "id": "d"},
            }
        ]
    }
    h2 = {"comparisons": []}

    for name, payload in {
        "r1.json": r1,
        "h1.json": h1,
        "r2.json": r2,
        "h2.json": h2,
    }.items():
        (tmp_path / name).write_text(
            json.dumps(payload, ensure_ascii=False),
            encoding="utf-8",
        )

    manifest = {
        "cases": [
            {
                "id": "case-1",
                "reference": "r1.json",
                "hypothesis": "h1.json",
                "metadata": {"source": "human-reviewed"},
            },
            {
                "id": "case-2",
                "reference": "r2.json",
                "hypothesis": "h2.json",
            },
        ]
    }
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False),
        encoding="utf-8",
    )

    result = mod.score_manifest(manifest_path)
    aggregate = result["aggregate"]

    assert result["benchmark_format"] == "fire-ai-evidence-comparison-benchmark-v1"
    assert len(result["manifest_sha256"]) == 64
    assert len(result["cases"][0]["reference_sha256"]) == 64
    assert len(result["cases"][0]["hypothesis_sha256"]) == 64
    assert aggregate["case_count"] == 2
    assert aggregate["true_positive"] == 1
    assert aggregate["false_positive"] == 1
    assert aggregate["false_negative"] == 1
    assert aggregate["precision"] == 0.5
    assert aggregate["recall"] == 0.5
    assert aggregate["f1"] == 0.5
