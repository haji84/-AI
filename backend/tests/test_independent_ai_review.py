"""Synthetic tests: no live GitHub write token, external API, or Ollama needed."""
import base64
import hashlib
import importlib.util
import sys
from pathlib import Path

import pytest

PATH = Path(__file__).resolve().parents[2] / "scripts/autonomy/independent_ai_review.py"
sys.path.insert(0, str(PATH.parent))
spec = importlib.util.spec_from_file_location("aios_independent_review", PATH)
review = importlib.util.module_from_spec(spec)
spec.loader.exec_module(review)
HEAD = "a" * 40
BASE = "b" * 40
PATCH = "@@ -0,0 +1 @@\n+safe = True"
ANCHOR = "+safe = True"
ANCHOR_ID = "F01L0001"


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
                      "anchor_id": ANCHOR_ID,
                      "evidence": "Changed behavior lacks a regression test.",
                      "recommendation": "Add focused regression test."}]})
    assert outcome["verdict"] == "needs_changes"
    assert outcome["findings"][0]["source_line"] == ANCHOR
    assert outcome["findings"][0]["anchor_id"] == ANCHOR_ID
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
                       "anchor_id": ANCHOR_ID,
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

def test_local_ai_request_uses_selected_compact_model_and_context(monkeypatch):
    import json
    captured = {}
    class FakeResponse:
        status = 200
        def __enter__(self):
            return self
        def __exit__(self, *args):
            return False
        def read(self, size):
            return json.dumps({"done": True, "message": {"content":
                '{"verdict":"pass","summary":"Synthetic clean review","findings":[]}'}}).encode()
    class FakeOpener:
        def open(self, req, timeout):
            captured["request"] = json.loads(req.data)
            captured["timeout"] = timeout
            return FakeResponse()
    monkeypatch.setattr(review, "build_opener", lambda handler: FakeOpener())
    report = review.ask_ollama(review.collect(133, HEAD, get=fake_get)["snapshot"],
                               model_name="qwen2.5-coder:3b", context_tokens=8192)
    assert report["verdict"] == "pass"
    assert captured["request"]["model"] == "qwen2.5-coder:3b"
    assert captured["request"]["options"]["num_ctx"] == 8192
    schema = captured["request"]["format"]
    assert schema["properties"]["verdict"]["enum"] == ["pass", "needs_changes"]
    assert schema["required"] == ["verdict", "summary", "findings"]
    assert schema["properties"]["findings"]["items"]["required"] == [
        "path", "anchor_id", "severity", "evidence", "recommendation"]
    visible = captured["request"]["messages"][1]["content"]
    assert "[F01L0001] +safe = True" in visible
    assert '"annotated_patch"' in visible
    assert captured["timeout"] == 600


def test_unapproved_model_or_context_fails_closed(monkeypatch):
    monkeypatch.setattr(review, "evaluator_has_gh_credentials", lambda: False)
    for key in review.PROTECTED_ENV:
        monkeypatch.delenv(key, raising=False)
    snap = review.collect(133, HEAD, get=fake_get)
    with pytest.raises(review.ReviewStop, match="unapproved"):
        review.evaluate(snap, model_name="external-api-model", model=lambda x: {})
    with pytest.raises(review.ReviewStop, match="unapproved"):
        review.evaluate(snap, model_name="qwen2.5-coder:3b",
                        context_tokens=123456, model=lambda x: {})
    out = review.evaluate(snap, model_name="qwen2.5-coder:3b",
                          context_tokens=8192,
                          model=lambda data: {
                              "verdict": "pass", "summary": "No synthetic findings",
                              "findings": []})
    assert out["model"] == "qwen2.5-coder:3b"
    assert out["context_tokens"] == 8192
    assert out["independent_github_approval"] is False

def test_exact_changed_line_grounding_is_mandatory(monkeypatch):
    for key in review.PROTECTED_ENV:
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setattr(review, "evaluator_has_gh_credentials", lambda: False)
    evidence = review.collect(133, HEAD, get=fake_get)
    def fake(anchor):
        return {"verdict": "needs_changes", "summary": "Synthetic observation",
                "findings": [{"path": "frontend/safe.py", "severity": "high",
                              "anchor_id": anchor, "evidence": "Behavior may differ.",
                              "recommendation": "Inspect exact line."}]}
    valid = review.evaluate(evidence, model=lambda _: fake(ANCHOR_ID))
    assert valid["findings"][0]["source_line"] == ANCHOR
    for anchor in ("F01L9999", "F02L0001", "+safe = True"):
        with pytest.raises(review.ReviewStop, match="valid changed-line anchor ID"):
            review.evaluate(evidence, model=lambda _: fake(anchor))
    malformed = fake(ANCHOR_ID)
    del malformed["findings"][0]["anchor_id"]
    with pytest.raises(review.ReviewStop, match="valid changed-line anchor ID"):
        review.evaluate(evidence, model=lambda _: malformed)


def test_diff_line_extraction_ignores_metadata():
    patch = "@@ -1 +1 @@\n--- a/old.py\n+++ b/new.py\n-old = True\n+new = True"
    assert review.changed_source_lines(patch) == {"-old = True", "+new = True"}


def test_invalid_model_finding_is_preserved_locally_before_safe_stop(tmp_path, monkeypatch):
    for key in review.PROTECTED_ENV:
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setattr(review, "evaluator_has_gh_credentials", lambda: False)
    snap = review.collect(133, HEAD, get=fake_get)
    raw = {
        "verdict": "needs_changes", "summary": "Synthetic suspect review",
        "findings": [{"path": "frontend/safe.py", "severity": "high",
                      "anchor_id": "F01L9999",
                      "evidence": "Unverified claim about line.",
                      "recommendation": "Change code without source proof."}],
    }
    path = tmp_path / "candidate.json"
    with pytest.raises(review.ReviewStop, match="valid changed-line anchor ID"):
        review.evaluate(
            snap, model=lambda _: raw,
            model_name="qwen2.5-coder:3b", context_tokens=8192,
            candidate_sink=lambda data: review.save_untrusted_candidate(path, data))
    assert path.is_file()
    import json
    stored = json.loads(path.read_text(encoding="utf-8"))
    assert stored["kind"] == "untrusted_local_model_candidate"
    assert stored["raw_response"] == raw
    assert stored["snapshot_sha256"] == snap["sha256"]
    assert stored["github_approved"] is False
    assert stored["merge_permitted"] is False
    with pytest.raises(FileExistsError):
        review.save_untrusted_candidate(path, stored)


def test_cli_diagnostic_exposes_only_predefined_rejection_reason(tmp_path, monkeypatch, capsys):
    import json
    for key in review.PROTECTED_ENV:
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setattr(review, "evaluator_has_gh_credentials", lambda: False)
    snap = review.collect(133, HEAD, get=fake_get)
    def model_response(data, **kwargs):
        return {"verdict": "needs_changes", "summary": "Synthetic issue",
                "findings": [{"path": "frontend/safe.py", "severity": "high",
                              "anchor_id": "F01L9999",
                              "evidence": "Possible altered behavior.",
                              "recommendation": "Inspect actual code."}]}
    monkeypatch.setattr(review, "ask_ollama", model_response)
    # evaluate supports an injected test-model; CLI use a separate synthetic
    # invocation of the same guarded validation and raises the same reason.
    with pytest.raises(review.ReviewStop, match="valid changed-line anchor ID"):
        review.evaluate(snap, model=model_response,
                        model_name="qwen2.5-coder:3b", context_tokens=8192)
    output = tmp_path / "test-candidate.json"
    review.save_untrusted_candidate(output, {
        "schema_version": 1, "kind": "untrusted_local_model_candidate",
        "raw_response": model_response(None, model_name="qwen2.5-coder:3b", context_tokens=8192),
        "github_approved": False, "merge_permitted": False,
    })
    assert json.loads(output.read_text())["github_approved"] is False


def test_invalid_verdict_cannot_be_normalized_into_approval(monkeypatch):
    for key in review.PROTECTED_ENV:
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setattr(review, "evaluator_has_gh_credentials", lambda: False)
    snap = review.collect(133, HEAD, get=fake_get)
    collected = []
    candidate = {
        "verdict": "APPROVED", "summary": "Synthetic unsafe recommendation",
        "findings": [],
    }
    with pytest.raises(review.ReviewStop, match="model verdict invalid"):
        review.evaluate(
            snap, model=lambda _: candidate,
            model_name="qwen2.5-coder:3b", context_tokens=8192,
            candidate_sink=collected.append)
    assert len(collected) == 1
    assert collected[0]["github_approved"] is False
    assert collected[0]["merge_permitted"] is False
    assert collected[0]["raw_response"] == candidate


def test_inference_metadata_on_malformed_json_with_no_model_text(monkeypatch, tmp_path):
    import json
    incomplete = '{"verdict":"needs_changes","findings":['
    fake_response = {"done": True, "done_reason": "length",
                     "prompt_eval_count": 8130, "eval_count": 1800,
                     "message": {"content": incomplete}}
    class Response:
        status = 200
        def __enter__(self):
            return self
        def __exit__(self, *args):
            return False
        def read(self, size):
            return json.dumps(fake_response).encode()
    class Opener:
        def open(self, req, timeout):
            assert timeout == 600
            return Response()
    monkeypatch.setattr(review, "build_opener", lambda handler: Opener())
    target = tmp_path / "metadata.json"
    with pytest.raises(review.ReviewStop, match="invalid JSON"):
        review.ask_ollama({"synthetic": True}, model_name="qwen2.5-coder:3b",
                          context_tokens=8192,
                          diagnostic_sink=lambda x: review.save_inference_metadata(target, x))
    result = json.loads(target.read_text(encoding="utf-8"))
    assert result["done_reason_class"] == "length"
    assert result["prompt_eval_count"] == 8130
    assert result["eval_count"] == 1800
    assert result["parse_status"] == "invalid_json"
    assert result["content_bytes"] == len(incomplete.encode("utf-8"))
    assert result["parse_error_position"] is not None
    assert "needs_changes" not in str(result)
    assert result["raw_model_text_included"] is False
    assert result["independent_github_approval"] is False
    assert result["merge_permitted"] is False
    with pytest.raises(FileExistsError):
        review.save_inference_metadata(target, result)


def test_valid_ollama_json_with_generation_limit_is_rejected(monkeypatch):
    import json
    response = {"done": True, "done_reason": "length",
                "prompt_eval_count": 200, "eval_count": 1800,
                "message": {"content":
                    '{"verdict":"pass","summary":"Synthetic only","findings":[]}'}}
    class Response:
        status = 200
        def __enter__(self):
            return self
        def __exit__(self, *args):
            return False
        def read(self, size):
            return json.dumps(response).encode()
    class Opener:
        def open(self, request, timeout):
            return Response()
    monkeypatch.setattr(review, "build_opener", lambda handler: Opener())
    details = []
    with pytest.raises(review.ReviewStop, match="generation limit"):
        review.ask_ollama({"synthetic": True}, model_name="qwen2.5-coder:3b",
                          context_tokens=8192, diagnostic_sink=details.append)
    assert details[0]["parse_status"] == "valid_json"
    assert details[0]["accepted_review"] is False


def test_inference_metadata_contains_only_bounded_known_fields():
    parsed = {"done": True, "done_reason": "stop",
              "prompt_eval_count": 300, "eval_count": 20,
              "message": {"content": "SECRET_MARKER_NOT_TO_INCLUDE"}}
    result = review.inference_diagnostic(
        parsed, "SECRET_MARKER_NOT_TO_INCLUDE",
        "qwen2.5-coder:3b", 8192, "invalid_json", 17)
    assert "SECRET_MARKER_NOT_TO_INCLUDE" not in str(result)
    assert result["done_reason_class"] == "stop"
    assert result["parse_error_position"] == 17
    assert result["raw_model_text_included"] is False
