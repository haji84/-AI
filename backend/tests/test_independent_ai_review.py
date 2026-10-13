"""Synthetic tests: no live GitHub write token, external API, or Ollama needed."""
import base64
import hashlib
import importlib.util
from pathlib import Path

import pytest

PATH = Path(__file__).resolve().parents[2] / "scripts/autonomy/independent_ai_review.py"
spec = importlib.util.spec_from_file_location("aios_independent_review", PATH)
review = importlib.util.module_from_spec(spec)
spec.loader.exec_module(review)
HEAD = "a" * 40
BASE = "b" * 40
PATCH = "@@ -0,0 +1 @@\n+safe = True"


def fake_get(path):
    if path.endswith("/pulls/133"):
        return {"number": 133, "state": "open", "merged_at": None,
                "changed_files": 1, "user": {"login": "author"},
                "head": {"sha": HEAD}, "base": {"sha": BASE, "ref": "main"}}
    if "/files?" in path:
        return [{"filename": "frontend/safe.py", "patch": PATCH,
                 "additions": 1, "deletions": 0}]
    if "/actions/runs?" in path:
        return {"total_count": 4, "workflow_runs": [
            {"name": n, "head_sha": HEAD, "event": "pull_request", "id": i + 100,
             "status": "completed", "conclusion": "success"}
            for i, n in enumerate(review.REQUIRED_CI)]}
    if "/contents/docs/SPECIFICATION.md?" in path:
        body = "\n".join(f"## {n}. Test chapter\nText" for n in (4, 38, 42, 43, 48, 53))
        return {"encoding": "base64", "content":
                base64.b64encode(("# Test specification\n" + body).encode()).decode("ascii")}
    if "/contents/AGENTS.md?" in path:
        return {"encoding": "base64", "content":
                base64.b64encode(b"# AGENTS.md\nRules").decode("ascii")}
    raise AssertionError(path)


def test_collect_pins_exact_head_and_all_ci():
    result = review.collect(133, HEAD, get=fake_get)
    data = review.validate_snapshot(result)
    assert data["ci"]["project-checks"] == 100
    assert data["head"] == HEAD and data["base"] == BASE
    assert data["files"][0]["path"] == "frontend/safe.py"
    assert "## 43." in data["specification_excerpt"]


def test_stale_head_rejected():
    with pytest.raises(review.ReviewStop, match="stale"):
        review.collect(133, "c" * 40, get=fake_get)


def test_missing_or_failed_ci_rejected():
    def broken(path):
        result = fake_get(path)
        if "/actions/runs?" in path:
            result["workflow_runs"][0]["conclusion"] = "failure"
        return result
    with pytest.raises(review.ReviewStop, match="not green"):
        review.collect(133, HEAD, get=broken)


def test_partial_patch_rejected():
    def broken(path):
        result = fake_get(path)
        if "/files?" in path:
            result[0]["additions"] = 4
        return result
    with pytest.raises(review.ReviewStop, match="truncated"):
        review.collect(133, HEAD, get=broken)


def test_tampered_snapshot_rejected():
    result = review.collect(133, HEAD, get=fake_get)
    result["snapshot"]["head"] = "d" * 40
    with pytest.raises(review.ReviewStop, match="tampered"):
        review.validate_snapshot(result)


def test_synthetic_ai_review_never_becomes_approval(monkeypatch):
    for key in review.PROTECTED_ENV:
        monkeypatch.delenv(key, raising=False)
    snap = review.collect(133, HEAD, get=fake_get)
    outcome = review.evaluate(snap, model=lambda _: {
        "verdict": "needs_changes", "summary": "Synthetic finding",
        "findings": [{"path": "frontend/safe.py", "severity": "medium",
                      "evidence": "Changed behavior lacks a regression test.",
                      "recommendation": "Add focused regression test."}]})
    assert outcome["verdict"] == "needs_changes"
    assert outcome["independent_github_approval"] is False
    assert outcome["merge_permitted"] is False
    assert outcome["github_comment_posted"] is False


def test_secrets_must_not_reach_model(monkeypatch):
    snap = review.collect(133, HEAD, get=fake_get)
    monkeypatch.setenv("GH_TOKEN", "synthetic-token-not-real")
    with pytest.raises(review.ReviewStop, match="credentials"):
        review.evaluate(snap, model=lambda _: {"verdict": "pass"})


def test_unapproved_path_and_contradictory_pass_rejected(monkeypatch):
    for key in review.PROTECTED_ENV:
        monkeypatch.delenv(key, raising=False)
    snap = review.collect(133, HEAD, get=fake_get)
    invalid_finding = {"path": "AGENTS.md", "severity": "high",
                       "evidence": "Unexpected repository path.",
                       "recommendation": "Do not invent target paths."}
    with pytest.raises(review.ReviewStop, match="path"):
        review.evaluate(snap, model=lambda _: {
            "verdict": "needs_changes", "summary": "Bad path",
            "findings": [invalid_finding]})
    invalid_finding["path"] = "frontend/safe.py"
    with pytest.raises(review.ReviewStop, match="contradictory"):
        review.evaluate(snap, model=lambda _: {
            "verdict": "pass", "summary": "Contradictory result",
            "findings": [invalid_finding]})


def test_model_process_rejects_on_disk_gh_cli_auth(tmp_path, monkeypatch):
    for key in review.PROTECTED_ENV:
        monkeypatch.delenv(key, raising=False)
    local = tmp_path / '.config' / 'gh'
    local.mkdir(parents=True)
    (local / 'hosts.yml').write_text('synthetic-auth-placeholder')
    assert review.evaluator_has_gh_credentials(environ={}, home=tmp_path) is True
    snap = review.collect(133, HEAD, get=fake_get)
    monkeypatch.setattr(review, 'evaluator_has_gh_credentials', lambda: True)
    with pytest.raises(review.ReviewStop, match='credentials'):
        review.evaluate(snap, model=lambda _: {'verdict': 'pass'})

def test_github_cli_missing_falls_back_to_public_read(monkeypatch):
    calls = []
    def no_gh(*args, **kwargs):
        raise FileNotFoundError("gh absent")
    monkeypatch.setattr(review.subprocess, "run", no_gh)
    monkeypatch.setattr(review, "public_api_get",
                        lambda path: calls.append(path) or {"public": True})
    assert review.api_get("repos/haji84/-AI/pulls/133") == {"public": True}
    assert calls == ["repos/haji84/-AI/pulls/133"]
    with pytest.raises(review.ReviewStop, match="requires GitHub CLI"):
        review.api_get("user")


def test_public_github_api_is_read_only_no_authorization(monkeypatch):
    observed = {}
    class FakeResponse:
        status = 200
        def __enter__(self):
            return self
        def __exit__(self, *args):
            return False
        def read(self, count):
            observed["read_limit"] = count
            return b'{"number":133}'
    def fake_open(req, timeout):
        observed["url"] = req.full_url
        observed["headers"] = dict(req.header_items())
        observed["method"] = req.get_method()
        observed["timeout"] = timeout
        return FakeResponse()
    monkeypatch.setattr(review, "urlopen", fake_open)
    assert review.public_api_get("repos/haji84/-AI/pulls/133") == {"number": 133}
    assert observed["method"] == "GET"
    assert observed["url"] == "https://api.github.com/repos/haji84/-AI/pulls/133"
    assert observed["read_limit"] == 1_000_001
    assert not any(key.lower() == "authorization" for key in observed["headers"])
    with pytest.raises(review.ReviewStop, match="untrusted"):
        review.public_api_get("repos/other-org/other-repo/pulls/1")
    with pytest.raises(review.ReviewStop, match="untrusted"):
        review.public_api_get("repos/haji84/-AI/../secrets")
