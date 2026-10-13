"""Synthetic proof: AI report cannot self-approve or self-publish."""
import hashlib
from pathlib import Path
import sys
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts/autonomy"))
import independent_ai_review as engine  # noqa: E402
import review_evidence_publisher as publisher  # noqa: E402


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
    comment = publisher.build_comment(snap, result(snap))
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
        publisher.build_comment(snap, unsafe)
    unsafe = result(snap)
    unsafe["verdict"] = "needs_changes"
    unsafe["findings"] = [{"path": "outside.py", "severity": "high",
                           "evidence": "Dangerous code was introduced.",
                           "recommendation": "Reject this change."}]
    with pytest.raises(publisher.PublishStop, match="finding"):
        publisher.build_comment(snap, unsafe)


def test_writer_posts_only_comment():
    called = []
    def fake(args, **kwargs):
        called.extend(args)
        return SimpleNamespace(stdout='{"id":999,"state":"COMMENTED"}')
    assert publisher.publish_comment(133, "a" * 40, "Synthetic review", runner=fake) == 999
    assert "event=COMMENT" in called
    assert "commit_id=" + "a" * 40 in called
    assert "event=APPROVE" not in called
