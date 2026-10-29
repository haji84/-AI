"""Offline candidate-vs-diff diagnosis, no GitHub or Ollama calls."""
import hashlib
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts/autonomy"))
import independent_ai_review as review
import diagnose_local_candidate as diagnostic


def fixture():
    patch_a = "@@ -0,0 +1,2 @@\n+alpha = 1\n+beta = 2"
    patch_b = "@@ -0,0 +1 @@\n+gamma = 3"
    data = {"schema_version": 1, "repo": review.REPO, "pr": 133,
            "head": "a" * 40, "base": "b" * 40,
            "ci": {name: i + 1 for i, name in enumerate(review.REQUIRED_CI)},
            "specification_excerpt": "## 4. Synthetic",
            "files": [{"path": "one.py", "patch": patch_a},
                      {"path": "two.py", "patch": patch_b}]}
    snapshot = {"snapshot": data,
                "sha256": hashlib.sha256(review.canonical(data)).hexdigest()}
    candidate = {"schema_version": 1, "kind": "untrusted_local_model_candidate",
                 "repo": review.REPO, "pr": 133, "head": data["head"],
                 "snapshot_sha256": snapshot["sha256"],
                 "model": "qwen2.5-coder:3b", "context_tokens": 8192,
                 "raw_response": {"verdict": "needs_changes", "findings": []},
                 "github_approved": False, "merge_permitted": False}
    return snapshot, candidate


def test_offline_diagnostic_explains_each_unmatched_quote_without_exposing_it():
    snap, c = fixture()
    proposed = [
        ("one.py", "+alpha = 1"),
        ("one.py", "+gamma = 3"),
        ("one.py", " +alpha = 1 "),
        ("one.py", "-alpha = 1"),
        ("one.py", "+made_up = 1"),
        ("one.py", ""),
        ("unknown.py", "+alpha = 1"),
    ]
    c["raw_response"]["findings"] = [
        {"path": path, "source_line": line, "evidence": "model text not for output"}
        for path, line in proposed]
    output = diagnostic.diagnose(snap, c)
    statuses = [item["quote_status"] for item in output["findings"]]
    assert statuses == [
        "exact_match", "quoted_from_other_changed_file",
        "surrounding_whitespace_mismatch", "addition_deletion_sign_mismatch",
        "not_an_exact_changed_line", "missing_source_line", "unknown_path"]
    assert output["counts"]["exact_match"] == 1
    assert output["accepted_review"] is False
    assert output["independent_github_approval"] is False
    assert "model text not for output" not in str(output)
    assert "+made_up" not in str(output)


def test_never_treat_candidate_as_verified_interpretation():
    snap, c = fixture()
    c["raw_response"]["findings"] = [{"path": "one.py",
                                       "source_line": "+alpha = 1",
                                       "evidence": "unverified"}]
    result = diagnostic.diagnose(snap, c)
    assert result["counts"] == {"exact_match": 1}
    assert result["interpretation_verified"] is False
    assert result["merge_permitted"] is False


def test_mismatched_snapshot_head_or_review_authority_is_denied():
    snap, c = fixture()
    c["head"] = "f" * 40
    with pytest.raises(diagnostic.DiagnosticStop, match="contract"):
        diagnostic.diagnose(snap, c)
    snap, c = fixture()
    c["github_approved"] = True
    with pytest.raises(diagnostic.DiagnosticStop, match="contract"):
        diagnostic.diagnose(snap, c)


def test_non_list_findings_denied():
    snap, c = fixture()
    c["raw_response"]["findings"] = "not a list"
    with pytest.raises(diagnostic.DiagnosticStop, match="structured"):
        diagnostic.diagnose(snap, c)

def test_new_anchor_id_diagnosis_without_copied_model_code():
    snap, c = fixture()
    c["raw_response"]["findings"] = [
        {"path": "one.py", "anchor_id": "F01L0001", "evidence": "Do not publish me."},
        {"path": "one.py", "anchor_id": "F02L0001", "evidence": "Do not publish me."},
        {"path": "two.py", "anchor_id": "F02L9999", "evidence": "Do not publish me."},
    ]
    result = diagnostic.diagnose(snap, c)
    assert result["counts"] == {
        "valid_anchor_id": 1,
        "anchor_id_from_other_file": 1,
        "unrecognized_anchor_id": 1,
    }
    assert "Do not publish me" not in str(result)
    assert result["accepted_review"] is False
