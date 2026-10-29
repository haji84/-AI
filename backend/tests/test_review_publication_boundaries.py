"""Offline integration regressions for the publisher's real CLI and GitHub boundary.

Only the external gh process, interactive input and faulted local writes are
replaced. No GitHub, Ollama, credential stores or user files are accessed.
"""
import base64
from contextlib import ExitStack, redirect_stderr, redirect_stdout
import hashlib
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts" / "autonomy"))
import independent_ai_review as engine
import review_evidence_publisher as publisher
import semantic_review_gate as semantic_gate

HEAD = "a" * 40
BASE = "b" * 40


class GithubDouble:
    """Complete bounded REST responses; every unexpected request is an error."""

    def __init__(self):
        self.head = HEAD
        self.login = "distinct-operator"
        self.calls = []
        self.posts = []
        self.timeout_after_accept = False
        self.post_response = {"id": 729, "state": "COMMENTED"}

    def get(self, path):
        if path == "user":
            return {"login": self.login}
        if path == f"repos/{engine.REPO}/pulls/133":
            return {"number": 133, "state": "open", "merged_at": None,
                    "changed_files": 1, "user": {"login": "author"},
                    "head": {"sha": self.head}, "base": {"ref": "main", "sha": BASE}}
        if path == f"repos/{engine.REPO}/pulls/133/files?per_page=100":
            return [{"filename": "frontend/safe.py", "patch": "@@ -0,0 +1 @@\n+safe = True",
                     "additions": 1, "deletions": 0}]
        if path == f"repos/{engine.REPO}/actions/runs?head_sha={HEAD}&per_page=100":
            return {"total_count": 4, "workflow_runs": [
                {"name": name, "head_sha": HEAD, "event": "pull_request", "id": i + 100,
                 "status": "completed", "conclusion": "success"}
                for i, name in enumerate(engine.REQUIRED_CI)]}
        if path == f"repos/{engine.REPO}/contents/AGENTS.md?ref={BASE}":
            return {"encoding": "base64", "content": base64.b64encode(b"# AGENTS.md\nRules").decode()}
        if path == f"repos/{engine.REPO}/contents/docs/SPECIFICATION.md?ref={BASE}":
            body = "# Synthetic specification\n" + "\n".join(
                f"## {n}. Test chapter\nText" for n in (4, 38, 42, 43, 48, 53))
            return {"encoding": "base64", "content": base64.b64encode(body.encode()).decode()}
        raise AssertionError(f"Unexpected read: {path}")

    def run(self, args, **kwargs):
        self.calls.append(args[:])
        if args[:4] == ["gh", "api", "--method", "GET"] and len(args) == 5:
            return SimpleNamespace(stdout=json.dumps(self.get(args[4])))
        if args[:5] == ["gh", "api", "--method", "POST", f"repos/{engine.REPO}/pulls/133/reviews"]:
            fields = dict(value.split("=", 1) for value in args[6::2])
            if fields.get("event") != "COMMENT" or fields.get("commit_id") != HEAD:
                raise AssertionError("The publisher attempted an unauthorized review operation")
            self.posts.append(fields)
            if self.timeout_after_accept:
                raise subprocess.TimeoutExpired("synthetic-gh", 45)
            return SimpleNamespace(stdout=json.dumps(self.post_response))
        raise AssertionError(f"Unexpected external operation: {args[:5]}")


class PublisherBoundaryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(
            prefix="publisher-check-", dir=os.environ.get("AIOS_REVIEW_TEST_TMP_ROOT"))
        self.addCleanup(self.temp.cleanup)
        self.area = Path(self.temp.name)
        self.github = GithubDouble()
        self.envelope = engine.collect(133, HEAD, get=self.github.get)
        data = self.envelope["snapshot"]
        report = {"kind": "local_ai_review_candidate", "schema_version": 1,
                  "repo": engine.REPO, "pr": 133, "head": HEAD, "base": BASE,
                  "ci": data["ci"], "snapshot_sha256": self.envelope["sha256"],
                  "model": engine.MODEL, "verdict": "pass", "summary": "Synthetic proposal only",
                  "findings": [], "github_comment_posted": False,
                  "independent_github_approval": False, "merge_permitted": False}
        semantic = semantic_gate.triage(self.envelope, report)
        self.flags = []
        for flag, name, content in (("--snapshot", "snapshot.json", self.envelope),
                                    ("--result", "review.json", report),
                                    ("--semantic-report", "semantic.json", semantic)):
            path = self.area / name
            path.write_text(json.dumps(content), encoding="utf-8")
            self.flags.extend([flag, str(path)])
        self.preview = self.area / "approved.md"
        code, _, _ = self.invoke(self.flags + ["--output", str(self.preview)])
        self.assertEqual(code, 0)
        self.digest = hashlib.sha256(self.preview.read_bytes()).hexdigest()
        self.receipt = self.area / "receipt.json"

    def invoke(self, args, consent=None):
        stdout, stderr = io.StringIO(), io.StringIO()
        def denied(*unused, **kwargs):
            raise AssertionError("Unexpected network or credential-store access")
        with ExitStack() as stack:
            stack.enter_context(patch.object(publisher.subprocess, "run", self.github.run))
            # publish_comment captures subprocess.run as a definition-time default;
            # replace that external boundary too, while running its actual body.
            stack.enter_context(patch.object(publisher.publish_comment, "__defaults__", (self.github.run,)))
            stack.enter_context(patch.object(engine, "urlopen", denied))
            stack.enter_context(patch.object(engine, "build_opener", denied))
            stack.enter_context(patch.object(Path, "home", denied))
            stack.enter_context(patch("builtins.input", consent or (lambda _: "YES")))
            stack.enter_context(redirect_stdout(stdout))
            stack.enter_context(redirect_stderr(stderr))
            code = publisher.main(args)
        return code, stdout.getvalue(), stderr.getvalue()

    def publication_args(self, output=None):
        return self.flags + ["--output", str(output or self.receipt), "--publish-comment",
                             "--approved-preview", str(self.preview),
                             "--expected-preview-sha256", self.digest]

    def assert_no_post(self, code):
        self.assertEqual(code, 2)
        self.assertEqual(self.github.posts, [])
        self.assertFalse(self.receipt.exists())

    def test_unusable_receipt_parent_stops_before_github_post(self):
        blocker = self.area / "parent-is-a-file"
        blocker.write_text("synthetic local file", encoding="utf-8")
        code, _, _ = self.invoke(self.publication_args(blocker / "receipt.json"))
        self.assertEqual(code, 2)
        self.assertEqual(self.github.posts, [], "receipt readiness must precede the external side effect")

    def test_same_receipt_claim_blocks_overlapping_publication(self):
        inner_result = []
        def consent(_prompt):
            inner_result.append(self.invoke(self.publication_args())[0])
            return "YES"
        code, _, _ = self.invoke(self.publication_args(), consent=consent)
        self.assertEqual(inner_result, [0])
        self.assertEqual(code, 2)
        self.assertEqual(len(self.github.posts), 1, "the same output must allow only one publication")
        self.assertEqual(json.loads(self.receipt.read_text())["comment_review_id"], 729)

    def test_confirmed_post_receipt_failure_reports_remote_success_and_blocks_retry(self):
        real_dump = json.dump
        def fail_confirmed_receipt(value, stream, *args, **kwargs):
            if isinstance(value, dict) and value.get("comment_review_id") == 729:
                raise OSError("synthetic disk failure after accepted POST")
            return real_dump(value, stream, *args, **kwargs)
        with patch.object(publisher.json, "dump", fail_confirmed_receipt):
            code, _, stderr = self.invoke(self.publication_args())
        self.assertEqual(code, 3, "post-side-effect failures need a distinct reconciliation result")
        status = json.loads(stderr.strip().splitlines()[-1])
        self.assertEqual(status["publication_status"], "published_receipt_unavailable")
        self.assertEqual(status["comment_review_id"], 729)
        self.assertFalse(status["automatic_retry_permitted"])
        self.assertEqual(self.invoke(self.publication_args())[0], 2)
        self.assertEqual(len(self.github.posts), 1)

    def test_ambiguous_post_timeout_retains_attempt_and_blocks_same_output_retry(self):
        self.github.timeout_after_accept = True
        code, _, stderr = self.invoke(self.publication_args())
        self.assertEqual(code, 3)
        status = json.loads(stderr.strip().splitlines()[-1])
        self.assertEqual(status["publication_status"], "unknown")
        self.assertIsNone(status["comment_review_id"])
        self.assertFalse(status["automatic_retry_permitted"])
        self.assertTrue(self.receipt.exists())
        self.assertEqual(self.invoke(self.publication_args())[0], 2)
        self.assertEqual(len(self.github.posts), 1)

    def test_preview_mutation_during_consent_causes_zero_posts(self):
        def consent(_prompt):
            self.preview.write_text("changed while waiting", encoding="utf-8")
            return "YES"
        code, _, _ = self.invoke(self.publication_args(), consent=consent)
        self.assert_no_post(code)

    def test_unusable_post_responses_remain_unknown_and_block_retry(self):
        responses = [[], None, "unexpected", {},
                     {"state": "COMMENTED", "id": None},
                     {"state": "COMMENTED", "id": True},
                     {"state": "COMMENTED", "id": 0},
                     {"state": "COMMENTED", "id": -1},
                     {"state": "COMMENTED", "id": "729"},
                     {"state": "APPROVED", "id": 729}]
        for index, response in enumerate(responses):
            with self.subTest(response=response):
                self.github.post_response = response
                output = self.area / f"invalid-response-{index}.json"
                code, _, stderr = self.invoke(self.publication_args(output))
                self.assertEqual(code, 3)
                status = json.loads(stderr.strip().splitlines()[-1])
                self.assertEqual(status["publication_status"], "unknown")
                self.assertIsNone(status["comment_review_id"])
                self.assertFalse(status["automatic_retry_permitted"])
                self.assertTrue(output.exists())
                self.assertEqual(self.invoke(self.publication_args(output))[0], 2)
                self.assertEqual(len(self.github.posts), index + 1)

    def test_real_fresh_collector_rejects_head_changed_after_yes(self):
        def consent(_prompt):
            self.github.head = "c" * 40
            return "YES"
        code, _, _ = self.invoke(self.publication_args(), consent=consent)
        self.assert_no_post(code)

    def test_reviewer_identity_change_after_yes_causes_zero_posts(self):
        def consent(_prompt):
            self.github.login = "another-operator"
            return "YES"
        code, _, _ = self.invoke(self.publication_args(), consent=consent)
        self.assert_no_post(code)

    def test_wrong_digest_fails_before_any_github_read_or_post(self):
        args = self.publication_args()
        args[-1] = "f" * 64
        code, _, _ = self.invoke(args)
        self.assert_no_post(code)
        self.assertEqual(self.github.calls, [])

    def test_changed_preview_fails_before_any_github_read_or_post(self):
        self.preview.write_text("changed before publishing", encoding="utf-8")
        code, _, _ = self.invoke(self.publication_args())
        self.assert_no_post(code)
        self.assertEqual(self.github.calls, [])

    def test_missing_preview_approval_fails_before_any_github_read_or_post(self):
        code, _, _ = self.invoke(self.flags + ["--output", str(self.receipt), "--publish-comment"])
        self.assert_no_post(code)
        self.assertEqual(self.github.calls, [])

    def test_tampered_semantic_report_fails_before_any_github_read_or_post(self):
        target = self.area / "semantic.json"
        content = json.loads(target.read_text())
        content["merge_permitted"] = True
        target.write_text(json.dumps(content), encoding="utf-8")
        code, _, _ = self.invoke(self.publication_args())
        self.assert_no_post(code)
        self.assertEqual(self.github.calls, [])

    def test_refused_consent_causes_zero_posts(self):
        code, _, _ = self.invoke(self.publication_args(), consent=lambda _: "NO")
        self.assert_no_post(code)

    def test_happy_path_publishes_exact_preview_once_and_receipts(self):
        code, _, _ = self.invoke(self.publication_args())
        self.assertEqual(code, 0)
        self.assertEqual(len(self.github.posts), 1)
        self.assertEqual(self.github.posts[0]["body"] + "\n", self.preview.read_text())
        receipt = json.loads(self.receipt.read_text())
        self.assertEqual(receipt["comment_review_id"], 729)
        self.assertEqual(receipt["head"], HEAD)
        self.assertFalse(receipt["github_approved"])
        self.assertFalse(receipt["merge_permitted"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
