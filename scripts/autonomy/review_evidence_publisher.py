#!/usr/bin/env python3
"""Separate COMMENT-only publisher. Requires a distinct reviewer identity."""
import argparse
import hashlib
import hmac
import json
import os
import re
from pathlib import Path
import subprocess
import sys

import independent_ai_review as reviewer
import semantic_review_gate as semantic_gate


class PublishStop(ValueError):
    pass


def build_comment(envelope, report, semantic_report):
    data = reviewer.validate_snapshot(envelope)
    if (not isinstance(report, dict) or report.get("kind") != "local_ai_review_candidate"
            or report.get("repo") != reviewer.REPO or report.get("pr") != data["pr"]
            or report.get("head") != data["head"] or report.get("base") != data["base"]
            or report.get("model") not in reviewer.REVIEW_MODELS
            or report.get("snapshot_sha256") != envelope["sha256"]
            or report.get("ci") != data["ci"] or report.get("verdict") not in ("pass", "needs_changes")
            or report.get("independent_github_approval") is not False
            or report.get("merge_permitted") is not False
            or report.get("github_comment_posted") is not False):
        raise PublishStop("review result does not bind to snapshot")
    summary, findings = report.get("summary"), report.get("findings")
    if not isinstance(summary, str) or not 1 <= len(summary) <= 1600:
        raise PublishStop("invalid summary")
    if not isinstance(findings, list) or len(findings) > 20:
        raise PublishStop("invalid findings")
    expected_semantic = semantic_gate.triage(envelope, report)
    if semantic_report != expected_semantic:
        raise PublishStop("semantic gate missing, mismatched or altered")
    assessments = expected_semantic["assessments"]
    if any(x["interpretation_status"] == "contradicted" for x in assessments):
        raise PublishStop("contradicted model claims cannot be published as review")
    if any(x["interpretation_status"] == "insufficient_specificity" for x in assessments):
        raise PublishStop("generic code-only findings cannot be published as actionable review")
    files = {x["path"]: reviewer.changed_source_lines(x["patch"])
             for x in data["files"]}
    if report["verdict"] == "pass" and findings:
        raise PublishStop("PASS contradicts findings")
    lines = ["## AI reviewer candidate (COMMENT only, NOT APPROVED)", "",
             "PR #" + str(data["pr"]) + " head " + data["head"],
             "Base " + data["base"], "Snapshot sha256 " + envelope["sha256"],
             "Model: " + report["model"],
             "Verdict: " + report["verdict"], "Summary: " + summary]
    for finding in findings:
        if (not isinstance(finding, dict) or finding.get("path") not in files
                or finding.get("severity") not in ("critical", "high", "medium", "low")
                or finding.get("source_line") not in files[finding["path"]]
                or any(not isinstance(finding.get(k), str)
                       or not 3 <= len(finding[k]) <= 1200
                       for k in ("evidence", "recommendation"))):
            raise PublishStop("finding invalid")
        lines.extend(["", "Finding: " + finding["path"] + " [" + finding["severity"] + "]",
                      "Grounded changed line: " + finding["source_line"],
                      "Semantic interpretation: UNVERIFIED (independent review required)",
                      "Evidence: " + finding["evidence"],
                      "Recommendation: " + finding["recommendation"]])
    lines.extend(["", "Four CI run IDs: " + json.dumps(data["ci"], sort_keys=True),
                  "This is not GitHub APPROVED, independent operator verification, or a merge grant."])
    return "\n".join(lines)


def check_identity_and_head(envelope, get=reviewer.api_get):
    data = reviewer.validate_snapshot(envelope)
    identity = get("user")
    if (not isinstance(identity, dict) or not isinstance(identity.get("login"), str)
            or not identity["login"] or identity["login"] == data.get("author")):
        raise PublishStop("publisher must not be PR author")
    live = reviewer.collect(data["pr"], data["head"], get=get)
    if live["sha256"] != envelope["sha256"]:
        raise PublishStop("PR snapshot or CI changed")
    return identity["login"]


def publish_comment(pr, head, text, runner=subprocess.run):
    if not reviewer.SHA.fullmatch(str(head)):
        raise PublishStop("invalid reviewed commit identity")
    response = runner(["gh", "api", "--method", "POST",
                       f"repos/{reviewer.REPO}/pulls/{pr}/reviews",
                       "-f", "event=COMMENT", "-f", "commit_id=" + head,
                       "-f", "body=" + text],
                      check=True, capture_output=True, text=True, timeout=45)
    result = json.loads(response.stdout)
    if (not isinstance(result, dict) or result.get("state") != "COMMENTED"
            or type(result.get("id")) is not int or result["id"] < 1):
        raise PublishStop("unverified GitHub review response")
    return result["id"]


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--snapshot", type=Path, required=True)
    parser.add_argument("--result", type=Path, required=True)
    parser.add_argument("--semantic-report", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--publish-comment", action="store_true")
    parser.add_argument("--approved-preview", type=Path,
                        help="Already-inspected, immutable COMMENT preview (publish only)")
    parser.add_argument("--expected-preview-sha256",
                        help="SHA256 printed by prior preview-only invocation (publish only)")
    args = parser.parse_args(argv)
    post_attempted = False
    review_id = None
    receipt_saved = False
    try:
        if args.publish_comment:
            if (args.approved_preview is None
                    or not isinstance(args.expected_preview_sha256, str)
                    or not re.fullmatch(r"[0-9a-f]{64}", args.expected_preview_sha256)):
                raise PublishStop("publishing requires approved preview and expected SHA256")
        elif args.approved_preview is not None or args.expected_preview_sha256 is not None:
            raise PublishStop("preview-only mode cannot use publishing approvals")
        s = args.snapshot.resolve(strict=True)
        r = args.result.resolve(strict=True)
        if not s.is_file() or s.stat().st_size > reviewer.MAX_INPUT + 1000:
            raise PublishStop("missing snapshot")
        if not r.is_file() or r.stat().st_size > 60_000:
            raise PublishStop("missing review")
        envelope = json.loads(s.read_text(encoding="utf-8"))
        report = json.loads(r.read_text(encoding="utf-8"))
        sem_path = args.semantic_report.resolve(strict=True)
        if not sem_path.is_file() or sem_path.stat().st_size > 80_000:
            raise PublishStop("missing bounded semantic evidence")
        semantic_report = json.loads(sem_path.read_text(encoding="utf-8"))
        comment = build_comment(envelope, report, semantic_report)
        preview_bytes = (comment + "\n").encode("utf-8")
        if len(preview_bytes) > 60_000:
            raise PublishStop("oversized comment preview")
        digest = hashlib.sha256(preview_bytes).hexdigest()
        out = args.output.resolve()
        protected = {s, r, sem_path}
        if out.exists() or out in protected:
            raise PublishStop("refuse overwrite or protected output")
        if not args.publish_comment:
            out.parent.mkdir(parents=True, exist_ok=True)
            with out.open("xb") as stream:
                stream.write(preview_bytes)
            print(json.dumps({"preview": str(out), "preview_sha256": digest,
                              "comment_review_id": None, "github_approved": False}))
            return 0

        approved = args.approved_preview.resolve(strict=True)
        if (approved in protected or out == approved or not approved.is_file()
                or approved.stat().st_size > 60_000):
            raise PublishStop("unsafe or oversized approved preview")
        if not hmac.compare_digest(args.expected_preview_sha256, digest):
            raise PublishStop("expected SHA256 differs from rendered comment")
        if approved.read_bytes() != preview_bytes:
            raise PublishStop("approved preview does not match rendered comment")
        # Pre-prompt identity and exact-head check never authorizes publication by itself.
        identity = check_identity_and_head(envelope)
        print(json.dumps({"candidate_comment_sha256": digest,
                          "preview": str(approved), "pr": envelope["snapshot"]["pr"],
                          "head": envelope["snapshot"]["head"],
                          "publisher": identity, "github_approved": False}))
        if input("Inspected exact SHA256 preview above? Type YES to post COMMENT only: ") != "YES":
            raise PublishStop("publisher did not authorize")
        # The user may spend arbitrarily long inspecting/confirming.
        # Recheck both current PR and four exact-head CI streams immediately before POST.
        if check_identity_and_head(envelope) != identity:
            raise PublishStop("reviewer identity changed")
        if approved.read_bytes() != preview_bytes:
            raise PublishStop("approved preview changed after confirmation")
        if not hmac.compare_digest(
                hashlib.sha256(preview_bytes).hexdigest(), args.expected_preview_sha256):
            raise PublishStop("comment digest changed after confirmation")
        receipt = {
            "kind": "comment_only_publication_receipt", "pr": envelope["snapshot"]["pr"],
            "head": envelope["snapshot"]["head"], "comment_review_id": None,
            "preview_sha256": digest, "github_approved": False, "merge_permitted": False,
            "publication_status": "pending_or_unknown",
        }
        # Claim and persist the receipt before any remote side effect. An existing
        # claim blocks another invocation even if the response or final write fails.
        out.parent.mkdir(parents=True, exist_ok=True)
        with out.open("x+", encoding="utf-8") as stream:
            json.dump(receipt, stream, ensure_ascii=False)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
            post_attempted = True
            review_id = publish_comment(envelope["snapshot"]["pr"],
                                        envelope["snapshot"]["head"], comment)
            receipt["comment_review_id"] = review_id
            receipt["publication_status"] = "published"
            stream.seek(0)
            json.dump(receipt, stream, ensure_ascii=False)
            stream.write("\n")
            stream.truncate()
            stream.flush()
            os.fsync(stream.fileno())
            receipt_saved = True
        print(json.dumps({"receipt": str(out), "comment_review_id": review_id,
                          "github_approved": False}))
        return 0
    except (PublishStop, semantic_gate.SemanticStop, reviewer.ReviewStop, OSError, ValueError, TypeError,
            KeyError, subprocess.SubprocessError):
        if post_attempted:
            # A timed-out POST may already have been accepted. Never report it as
            # an unattempted publication, remove its claim, or automatically retry.
            print(json.dumps({
                "publication_status": ("published" if receipt_saved else
                                       "published_receipt_unavailable" if review_id is not None
                                       else "unknown"),
                "pr": envelope["snapshot"]["pr"], "head": envelope["snapshot"]["head"],
                "comment_review_id": review_id, "receipt": str(out),
                "preview_sha256": digest, "automatic_retry_permitted": False,
                "github_approved": False, "merge_permitted": False,
            }), file=sys.stderr)
            return 3
        print("SAFE_STOP: no GitHub publication attempted by this invocation", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
