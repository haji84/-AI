#!/usr/bin/env python3
"""Separate COMMENT-only publisher. Requires a distinct reviewer identity."""
import argparse
import json
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
    if result.get("state") != "COMMENTED":
        raise PublishStop("unexpected GitHub review state")
    return result["id"]


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--snapshot", type=Path, required=True)
    parser.add_argument("--result", type=Path, required=True)
    parser.add_argument("--semantic-report", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--publish-comment", action="store_true")
    args = parser.parse_args(argv)
    try:
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
        out = args.output.resolve()
        if out.exists():
            raise PublishStop("refuse overwrite")
        if args.publish_comment:
            check_identity_and_head(envelope)
            if input("Submit COMMENT as independent operator? Enter YES: ") != "YES":
                raise PublishStop("publisher did not authorize")
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(comment + "\n", encoding="utf-8")
        review_id = publish_comment(envelope["snapshot"]["pr"],
                                    envelope["snapshot"]["head"], comment) if args.publish_comment else None
        print(json.dumps({"preview": str(out), "comment_review_id": review_id,
                          "github_approved": False}))
        return 0
    except (PublishStop, semantic_gate.SemanticStop, reviewer.ReviewStop, OSError, ValueError, TypeError,
            KeyError, subprocess.SubprocessError):
        print("SAFE_STOP: no review publication or approval accepted", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
