"""Offline model response verdict diagnostic with no raw text disclosure."""
import hashlib
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts/autonomy"))
import independent_ai_review as engine
import diagnose_review_format as fmt


def evidence():
    data = {
        "schema_version": 1, "repo": engine.REPO, "pr": 133,
        "head": "a" * 40, "base": "b" * 40, "ci": {
            x: i for i, x in enumerate(engine.REQUIRED_CI)},
        "specification_excerpt": "## 4. Example",
        "files": [{"path": "example.py", "patch": "@@ -0,0 +1 @@\n+x = 1"}],
    }
    envelope = {
        "snapshot": data,
        "sha256": hashlib.sha256(engine.canonical(data)).hexdigest(),
    }
    candidate = {
        "schema_version": 1, "kind": "untrusted_local_model_candidate",
        "repo": engine.REPO, "pr": 133, "head": data["head"],
        "snapshot_sha256": envelope["sha256"],
        "model": "qwen2.5-coder:3b", "context_tokens": 8192,
        "raw_response": {
            "verdict": "NEEDS_CHANGES", "summary": "Never print this secret-ish text",
            "findings": [{"path": "example.py", "anchor_id": "F01L0001"}],
        },
        "github_approved": False, "merge_permitted": False,
    }
    return envelope, candidate


def test_case_mismatch_diagnostic_without_raw_model_text():
    snapshot, candidate = evidence()
    result = fmt.inspect(snapshot, candidate)
    assert result["verdict_status"] == "wrong_case"
    assert result["verdict_type"] == "string"
    assert result["findings_count"] == 1
    assert result["accepted_review"] is False
    assert result["merge_permitted"] is False
    assert "NEEDS_CHANGES" not in str(result)
    assert "Never print" not in str(result)


def test_unknown_string_is_not_accepted_or_echoed():
    snapshot, candidate = evidence()
    candidate["raw_response"]["verdict"] = "APPROVE_AND_MERGE"
    assert fmt.inspect(snapshot, candidate)["verdict_status"] == "other_string"


def test_valid_enum_only_reports_format_success_not_security_approval():
    snapshot, candidate = evidence()
    candidate["raw_response"]["verdict"] = "needs_changes"
    result = fmt.inspect(snapshot, candidate)
    assert result["verdict_status"] == "accepted_enum"
    assert result["accepted_review"] is False


def test_missing_fields_and_non_object_response():
    snapshot, candidate = evidence()
    candidate["raw_response"] = {"summary": "No verdict", "findings": []}
    assert fmt.inspect(snapshot, candidate)["verdict_status"] == "missing"
    candidate["raw_response"] = []
    output = fmt.inspect(snapshot, candidate)
    assert output["response_shape"] == "array"
    assert output["findings_type"] == "null_or_absent"
    assert output["verdict_status"] == "missing"


def test_incorrect_identity_or_approval_is_rejected():
    snapshot, candidate = evidence()
    candidate["head"] = "f" * 40
    with pytest.raises(fmt.FormatStop, match="provenance"):
        fmt.inspect(snapshot, candidate)
    snapshot, candidate = evidence()
    candidate["github_approved"] = True
    with pytest.raises(fmt.FormatStop, match="provenance"):
        fmt.inspect(snapshot, candidate)
