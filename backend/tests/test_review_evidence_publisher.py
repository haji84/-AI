"""Synthetic proof: AI report cannot self-approve or self-publish."""
import hashlib
import json
from pathlib import Path
import sys
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts/autonomy"))
import independent_ai_review as engine  # noqa: E402
import review_evidence_publisher as publisher  # noqa: E402
import semantic_review_gate as semantic_gate  # noqa: E402


def fixture_bundle():
    data = {"schema_version": 1, "repo": engine.REPO, "pr": 133,
            "author": "author", "head": "a" * 40, "base": "b" * 40,
            "rules": "# AGENTS.md\n", "specification_excerpt": "## 4. Test",
            "ci": {name: i + 1 for i, name in enumerate(engine.REQUIRED_CI)},
            "files": [{"path": "frontend/app.js", "patch": "+const ok = true;"}]}
    return {"snapshot": data,
            "sha256": hashlib.sha256(engine.canonical(data)).hexdigest()}


def result(snap):
    data = snap["snapshot"]
    return {"kind": "local_ai_review_candidate", "schema_version": 1,
            "repo": engine.REPO, "pr": data["pr"], "head": data["head"],
            "base": data["base"], "ci": data["ci"],
            "snapshot_sha256": snap["sha256"],
            "model": engine.MODEL,
            "verdict": "pass", "summary": "Synthetic proposal only",
            "findings": [], "github_comment_posted": False,
            "independent_github_approval": False, "merge_permitted": False}


def test_comment_candidate_is_not_approved():
    snap = fixture_bundle()
    candidate = result(snap)
    comment = publisher.build_comment(snap, candidate, semantic_gate.triage(snap, candidate))
    assert "NOT APPROVED" in comment
    assert "Four CI run IDs" in comment


def test_self_review_rejected():
    snap = fixture_bundle()
    with pytest.raises(publisher.PublishStop, match="author"):
        publisher.check_identity_and_head(snap, get=lambda path: {"login": "author"})


def test_stale_snapshot_rejected(monkeypatch):
    snap = fixture_bundle()
    monkeypatch.setattr(publisher.reviewer, "collect",
                        lambda *args, **kwargs: {"sha256": "0" * 64})
    with pytest.raises(publisher.PublishStop, match="changed"):
        publisher.check_identity_and_head(snap, get=lambda path: {"login": "other"})


def test_forged_permissions_and_invalid_paths_rejected():
    snap = fixture_bundle()
    unsafe = result(snap)
    unsafe["merge_permitted"] = True
    with pytest.raises(publisher.PublishStop, match="bind"):
        publisher.build_comment(snap, unsafe, None)
    unsafe = result(snap)
    unsafe["verdict"] = "needs_changes"
    unsafe["findings"] = [{"path": "outside.py", "severity": "high",
                           "evidence": "Dangerous code was introduced.",
                           "recommendation": "Reject this change."}]
    with pytest.raises(semantic_gate.SemanticStop, match="ungrounded"):
        semantic_gate.triage(snap, unsafe)


def test_writer_posts_only_comment():
    called = []
    def fake(args, **kwargs):
        called.extend(args)
        return SimpleNamespace(stdout='{"id":999,"state":"COMMENTED"}')
    assert publisher.publish_comment(133, "a" * 40, "Synthetic review", runner=fake) == 999
    assert "event=COMMENT" in called
    assert "commit_id=" + "a" * 40 in called
    assert "event=APPROVE" not in called

def test_publisher_never_trusts_model_semantics_alone():
    snap = fixture_bundle()
    candidate = result(snap)
    semantic = semantic_gate.triage(snap, candidate)
    assert "NOT APPROVED" in publisher.build_comment(snap, candidate, semantic)
    with pytest.raises(publisher.PublishStop, match="semantic"):
        publisher.build_comment(snap, candidate, None)
    forged = dict(semantic, merge_permitted=True)
    with pytest.raises(publisher.PublishStop, match="semantic"):
        publisher.build_comment(snap, candidate, forged)


def test_publisher_rejects_fabricated_source_line():
    snap = fixture_bundle()
    candidate = result(snap)
    candidate["verdict"] = "needs_changes"
    candidate["findings"] = [{
        "path": "frontend/app.js", "severity": "high", "source_line": "+invented = True",
        "evidence": "Potential issue in updated behavior.",
        "recommendation": "Audit the code line."
    }]
    with pytest.raises(semantic_gate.SemanticStop, match="ungrounded"):
        semantic_gate.triage(snap, candidate)

def test_code_only_generic_advice_cannot_be_published_as_actionable():
    snap = fixture_bundle()
    snap["snapshot"]["files"][0]["patch"] = "@@ -0,0 +1 @@\n+const ok = true;"
    snap["sha256"] = hashlib.sha256(engine.canonical(snap["snapshot"])).hexdigest()
    candidate = result(snap)
    candidate["verdict"] = "needs_changes"
    candidate["findings"] = [{
        "path": "frontend/app.js",
        "anchor_id": "F01L0001",
        "source_line": "+const ok = true;",
        "severity": "high",
        "evidence": "const ok = true;",
        "recommendation": "Ensure that this code is expected and properly validated.",
    }]
    semantic = semantic_gate.triage(snap, candidate)
    assert semantic["assessments"][0]["interpretation_status"] == "insufficient_specificity"
    with pytest.raises(publisher.PublishStop, match="generic code-only"):
        publisher.build_comment(snap, candidate, semantic)


def publisher_cli_files(tmp_path):
    """Complete local test evidence, no network and no model inference."""
    snap = fixture_bundle()
    report = result(snap)
    semantic = semantic_gate.triage(snap, report)
    locations = tuple(tmp_path / name for name in
                      ("snapshot.json", "review.json", "semantic.json"))
    for path, record in zip(locations, (snap, report, semantic)):
        path.write_text(json.dumps(record), encoding="utf-8")
    flags = ["--snapshot", str(locations[0]), "--result", str(locations[1]),
             "--semantic-report", str(locations[2])]
    return snap, report, flags


def test_cli_preview_is_created_before_any_consent_or_github_write(tmp_path, monkeypatch, capsys):
    snap, report, flags = publisher_cli_files(tmp_path)
    preview = tmp_path / "approved-preview.md"
    monkeypatch.setattr("builtins.input", lambda *args: (_ for _ in ()).throw(
        AssertionError("preview must not request consent")))
    monkeypatch.setattr(publisher, "publish_comment", lambda *args: (_ for _ in ()).throw(
        AssertionError("preview must not publish")))
    assert publisher.main(flags + ["--output", str(preview)]) == 0
    expected = (publisher.build_comment(snap, report, semantic_gate.triage(snap, report)) + "\n").encode()
    assert preview.read_bytes() == expected
    result_json = json.loads(capsys.readouterr().out)
    assert result_json["preview_sha256"] == hashlib.sha256(expected).hexdigest()
    assert result_json["github_approved"] is False
    assert publisher.main(flags + ["--output", str(preview)]) == 2
    assert preview.read_bytes() == expected


def test_publish_requires_approved_preview_digest(tmp_path, monkeypatch):
    _, _, flags = publisher_cli_files(tmp_path)
    monkeypatch.setattr(publisher, "publish_comment", lambda *args: (_ for _ in ()).throw(
        AssertionError("publication requires preview")))
    monkeypatch.setattr("builtins.input", lambda *args: (_ for _ in ()).throw(
        AssertionError("missing preview must not ask for consent")))
    assert publisher.main(flags + ["--output", str(tmp_path / "receipt.json"),
                                   "--publish-comment"]) == 2
    assert not (tmp_path / "receipt.json").exists()


def test_publish_matching_prior_preview_checks_head_twice_and_receipts(tmp_path, monkeypatch):
    _, _, flags = publisher_cli_files(tmp_path)
    preview = tmp_path / "approved.md"
    assert publisher.main(flags + ["--output", str(preview)]) == 0
    digest = hashlib.sha256(preview.read_bytes()).hexdigest()
    checks, posts = [], []
    def identity(envelope):
        checks.append(envelope["snapshot"]["head"])
        return "distinct-operator"
    def post(pr, head, comment):
        posts.append((pr, head, hashlib.sha256((comment + "\n").encode()).hexdigest()))
        return 729
    monkeypatch.setattr(publisher, "check_identity_and_head", identity)
    monkeypatch.setattr(publisher, "publish_comment", post)
    monkeypatch.setattr("builtins.input", lambda *args: "YES")
    receipt = tmp_path / "receipt.json"
    assert publisher.main(flags + ["--output", str(receipt),
                                   "--publish-comment",
                                   "--approved-preview", str(preview),
                                   "--expected-preview-sha256", digest]) == 0
    assert checks == ["a" * 40, "a" * 40]
    assert posts == [(133, "a" * 40, digest)]
    result_json = json.loads(receipt.read_text())
    assert result_json["comment_review_id"] == 729
    assert result_json["preview_sha256"] == digest
    assert result_json["github_approved"] is False
    assert result_json["merge_permitted"] is False


def test_publish_denies_changed_head_after_consent_no_network_post(tmp_path, monkeypatch):
    _, _, flags = publisher_cli_files(tmp_path)
    preview = tmp_path / "approved.md"
    assert publisher.main(flags + ["--output", str(preview)]) == 0
    digest = hashlib.sha256(preview.read_bytes()).hexdigest()
    checks, published = [], []
    def identity(_envelope):
        checks.append(1)
        if len(checks) == 2:
            raise publisher.PublishStop("mocked PR head advanced after consent")
        return "distinct-operator"
    monkeypatch.setattr(publisher, "check_identity_and_head", identity)
    monkeypatch.setattr(publisher, "publish_comment", lambda *args: published.append(args))
    monkeypatch.setattr("builtins.input", lambda *args: "YES")
    receipt = tmp_path / "receipt.json"
    assert publisher.main(flags + ["--output", str(receipt),
                                   "--publish-comment",
                                   "--approved-preview", str(preview),
                                   "--expected-preview-sha256", digest]) == 2
    assert len(checks) == 2
    assert published == []
    assert not receipt.exists()


def test_publish_denies_preview_mutation_during_prompt(tmp_path, monkeypatch):
    _, _, flags = publisher_cli_files(tmp_path)
    preview = tmp_path / "approved.md"
    assert publisher.main(flags + ["--output", str(preview)]) == 0
    digest = hashlib.sha256(preview.read_bytes()).hexdigest()
    monkeypatch.setattr(publisher, "check_identity_and_head", lambda _: "distinct-operator")
    posts = []
    monkeypatch.setattr(publisher, "publish_comment", lambda *args: posts.append(args))
    def consent(*args):
        preview.write_text("tampered while waiting for consent", encoding="utf-8")
        return "YES"
    monkeypatch.setattr("builtins.input", consent)
    receipt = tmp_path / "receipt.json"
    assert publisher.main(flags + ["--output", str(receipt),
                                   "--publish-comment", "--approved-preview", str(preview),
                                   "--expected-preview-sha256", digest]) == 2
    assert not posts and not receipt.exists()


def test_publish_denies_wrong_preview_sha_before_identity_or_prompt(tmp_path, monkeypatch):
    _, _, flags = publisher_cli_files(tmp_path)
    preview = tmp_path / "approved.md"
    assert publisher.main(flags + ["--output", str(preview)]) == 0
    monkeypatch.setattr(publisher, "check_identity_and_head", lambda _: (_ for _ in ()).throw(
        AssertionError("mismatched SHA must fail before GitHub calls")))
    monkeypatch.setattr("builtins.input", lambda *args: (_ for _ in ()).throw(
        AssertionError("mismatched SHA must fail before consent")))
    assert publisher.main(flags + ["--output", str(tmp_path / "receipt.json"),
                                   "--publish-comment", "--approved-preview", str(preview),
                                   "--expected-preview-sha256", "f" * 64]) == 2
