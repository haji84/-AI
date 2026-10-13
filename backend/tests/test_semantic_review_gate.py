"""Two separate gates: source-quote existence and interpretation checking."""
import hashlib
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts/autonomy"))
import independent_ai_review as engine
import semantic_review_gate as gate


def fixture():
    source = [
        "import re", "import subprocess",
        'ROW = re.compile(r"^item")',
        "def main():", "    return 0",
        "def worker():",
        '    subprocess.run(["gh", "api"], check=True, timeout=70)',
    ]
    patch = "@@ -0,0 +1,7 @@\n" + "\n".join("+" + line for line in source)
    data = {
        "schema_version": 1, "repo": engine.REPO, "pr": 133, "author": "author",
        "head": "a" * 40, "base": "b" * 40,
        "rules": "# AGENTS.md", "specification_excerpt": "## 4. Test",
        "ci": {name: i for i, name in enumerate(engine.REQUIRED_CI)},
        "files": [{"path": "scripts/example.py", "patch": patch}],
    }
    snap = {"snapshot": data, "sha256": hashlib.sha256(engine.canonical(data)).hexdigest()}
    report = {
        "kind": "local_ai_review_candidate", "repo": engine.REPO, "pr": 133,
        "head": data["head"], "base": data["base"], "ci": data["ci"],
        "snapshot_sha256": snap["sha256"],
        "independent_github_approval": False, "merge_permitted": False,
        "findings": [{
            "path": "scripts/example.py", "anchor_id": "F01L0003",
            "source_line": '+ROW = re.compile(r"^item")',
            "severity": "high", "evidence": "Parser is using unsafe regular expressions.",
            "recommendation": "Use the re module to parse the ledger instead."
        }]
    }
    return snap, report


def test_quote_is_present_but_semantic_claim_is_contradicted():
    snap, report = fixture()
    result = gate.triage(snap, report)
    assessment = result["assessments"][0]
    assert assessment["source_quote_verified"] is True
    assert assessment["interpretation_status"] == "contradicted"
    assert "Already imports and calls Python re" in assessment["reasons"][0]
    assert result["semantic_approval_granted"] is False
    assert result["independent_github_approval"] is False


def test_subprocess_claim_already_bounded():
    snap, report = fixture()
    f = report["findings"][0]
    f["source_line"] = '+    subprocess.run(["gh", "api"], check=True, timeout=70)'
    f["anchor_id"] = "F01L0007"
    f["recommendation"] = "Use subprocess.run with check=True and timeout."
    f["evidence"] = "The worker is missing subprocess safety options."
    result = gate.triage(snap, report)
    assert result["assessments"][0]["interpretation_status"] == "contradicted"


def test_main_direct_call_claim_is_contradicted():
    snap, report = fixture()
    f = report["findings"][0]
    f["source_line"] = "+def main():"
    f["anchor_id"] = "F01L0004"
    f["evidence"] = "main function uses subprocess.run and it is unsafe."
    f["recommendation"] = "Change subprocess.run inside main."
    output = gate.triage(snap, report)
    assert output["assessments"][0]["interpretation_status"] == "contradicted"


def test_grounded_but_unproved_claim_is_not_automatically_verified():
    snap, report = fixture()
    report["findings"][0]["evidence"] = "Potential issue under unusual runtime state."
    report["findings"][0]["recommendation"] = "Investigate the effect with a regression test."
    outcome = gate.triage(snap, report)
    assert outcome["assessments"][0]["interpretation_status"] == "unverified"
    assert outcome["context_completeness_proven"] is False
    assert outcome["merge_permitted"] is False


def test_fabricated_or_wrong_path_anchor_rejected():
    snap, report = fixture()
    report["findings"][0]["source_line"] = "+completely fabricated"
    with pytest.raises(gate.SemanticStop, match="ungrounded"):
        gate.triage(snap, report)
    snap, report = fixture()
    report["findings"][0]["path"] = "unrelated.py"
    with pytest.raises(gate.SemanticStop, match="ungrounded"):
        gate.triage(snap, report)


def test_snapshot_and_review_mismatch_rejected():
    snap, report = fixture()
    report["head"] = "c" * 40
    with pytest.raises(gate.SemanticStop, match="does not match"):
        gate.triage(snap, report)


def test_partial_patch_cannot_supply_semantic_proof():
    patch = "@@ -7,1 +7,1 @@\n-old = 1\n+new = 2"
    assert gate.complete_new_python_source(patch) is None

def test_anchored_line_and_id_must_agree():
    snap, report = fixture()
    report["findings"][0]["anchor_id"] = "F01L0004"
    with pytest.raises(gate.SemanticStop, match="does not match"):
        gate.triage(snap, report)
    snap, report = fixture()
    del report["findings"][0]["anchor_id"]
    with pytest.raises(gate.SemanticStop, match="anchor ID"):
        gate.triage(snap, report)

def test_code_only_evidence_with_generic_advice_is_not_actionable():
    snap, report = fixture()
    finding = report["findings"][0]
    finding["evidence"] = 'ROW = re.compile(r"^item")'
    finding["recommendation"] = (
        "Ensure that the output is expected and properly formatted.")
    assessment = gate.triage(snap, report)["assessments"][0]
    assert assessment["source_quote_verified"] is True
    assert assessment["interpretation_status"] == "insufficient_specificity"
    assert "Only a code line was quoted" in assessment["reasons"][0]


def test_specific_claim_is_not_automatically_dismissed():
    snap, report = fixture()
    finding = report["findings"][0]
    finding["evidence"] = "Unexpected input exposes a distinct privilege boundary."
    finding["recommendation"] = "Ensure that the authorization policy is properly checked."
    assessment = gate.triage(snap, report)["assessments"][0]
    assert assessment["interpretation_status"] == "unverified"


def test_exact_hardcoded_credential_claim_is_not_silently_dismissed():
    snap, report = fixture()
    finding = report["findings"][0]
    finding["evidence"] = 'ROW = re.compile(r"^item")'
    finding["recommendation"] = "Remove hardcoded credentials and rotate exposed values."
    assessment = gate.triage(snap, report)["assessments"][0]
    assert assessment["interpretation_status"] == "unverified"


def test_generic_finding_is_a_quality_flag_not_a_github_approval():
    snap, report = fixture()
    finding = report["findings"][0]
    finding["evidence"] = 'ROW = re.compile(r"^item")'
    finding["recommendation"] = (
        "Validate the output of the ROW function to ensure it is expected and properly formatted.")
    result = gate.triage(snap, report)
    assert result["assessments"][0]["interpretation_status"] == "insufficient_specificity"
    assert result["semantic_approval_granted"] is False
    assert result["independent_github_approval"] is False
    assert result["merge_permitted"] is False
