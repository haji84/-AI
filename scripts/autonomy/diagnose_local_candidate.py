#!/usr/bin/env python3
"""Offline grounding diagnostics for a rejected untrusted local AI review.

Only reports bounded status codes, never raw source lines or model prose.
Does NOT re-run Ollama, write GitHub, approve PRs or accept a review.
"""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import sys

import independent_ai_review as engine


class DiagnosticStop(ValueError):
    pass


def diagnose(envelope, candidate):
    data = engine.validate_snapshot(envelope)
    if (not isinstance(candidate, dict)
            or candidate.get("schema_version") != 1
            or candidate.get("kind") != "untrusted_local_model_candidate"
            or candidate.get("repo") != engine.REPO
            or candidate.get("pr") != data["pr"]
            or candidate.get("head") != data["head"]
            or candidate.get("snapshot_sha256") != envelope["sha256"]
            or candidate.get("model") not in engine.REVIEW_MODELS
            or candidate.get("context_tokens") not in engine.REVIEW_CONTEXTS
            or candidate.get("github_approved") is not False
            or candidate.get("merge_permitted") is not False):
        raise DiagnosticStop("candidate identity or safety contract mismatch")
    raw = candidate.get("raw_response")
    if not isinstance(raw, dict) or not isinstance(raw.get("findings"), list):
        raise DiagnosticStop("no structured model findings")
    findings = raw["findings"]
    if len(findings) > 20:
        raise DiagnosticStop("unbounded candidate findings")
    known = {f["path"]: engine.changed_source_lines(f["patch"]) for f in data["files"]}
    records = []
    for index, finding in enumerate(findings, 1):
        status = "invalid_record"
        path = None
        if isinstance(finding, dict):
            name = finding.get("path")
            quote = finding.get("source_line")
            if isinstance(name, str) and name in known:
                path = name
                if not isinstance(quote, str) or not quote:
                    status = "missing_source_line"
                elif quote in known[name]:
                    status = "exact_match"
                elif any(quote in other for label, other in known.items() if label != name):
                    status = "quoted_from_other_changed_file"
                elif any(quote.strip() == line.strip() for line in known[name]):
                    status = "surrounding_whitespace_mismatch"
                elif (quote[:1] in ("+", "-")
                      and any(line[:1] in ("+", "-")
                              and line[:1] != quote[:1] and line[1:] == quote[1:]
                              for line in known[name])):
                    status = "addition_deletion_sign_mismatch"
                else:
                    status = "not_an_exact_changed_line"
            elif isinstance(name, str):
                status = "unknown_path"
        records.append({"finding_index": index, "known_path": path, "quote_status": status})
    counts = dict(sorted(Counter(item["quote_status"] for item in records).items()))
    return {
        "schema_version": 1, "kind": "untrusted_candidate_grounding_diagnostic",
        "repo": engine.REPO, "pr": data["pr"], "head": data["head"],
        "model": candidate["model"], "context_tokens": candidate["context_tokens"],
        "snapshot_sha256": envelope["sha256"],
        "candidate_sha256": hashlib.sha256(engine.canonical(candidate)).hexdigest(),
        "total_findings": len(findings), "counts": counts, "findings": records,
        "model_output_replayed": False, "raw_model_text_included": False,
        "accepted_review": False, "interpretation_verified": False,
        "independent_github_approval": False, "merge_permitted": False,
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description="Offline, no-inference model grounding diagnosis")
    parser.add_argument("--snapshot", type=Path, required=True)
    parser.add_argument("--candidate", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        snapshot_path = args.snapshot.resolve(strict=True)
        candidate_path = args.candidate.resolve(strict=True)
        output = args.output.resolve()
        if (not snapshot_path.is_file()
                or not candidate_path.is_file()
                or snapshot_path.stat().st_size > engine.MAX_INPUT + 1000
                or candidate_path.stat().st_size > 80_000
                or output.exists()
                or output in (snapshot_path, candidate_path)):
            raise DiagnosticStop("input unavailable, oversized or output exists")
        envelope = json.loads(snapshot_path.read_text(encoding="utf-8"))
        candidate = json.loads(candidate_path.read_text(encoding="utf-8"))
        report = diagnose(envelope, candidate)
        output.parent.mkdir(parents=True, exist_ok=True)
        with output.open("x", encoding="utf-8") as file:
            json.dump(report, file, ensure_ascii=False, indent=2)
            file.write("\n")
        # No raw diff or untrusted model prose is emitted to stdout.
        print(json.dumps({"pr": report["pr"], "total_findings": report["total_findings"],
                          "counts": report["counts"], "diagnostic_output": str(output),
                          "github_approved": False}, ensure_ascii=False))
        return 0
    except (DiagnosticStop, engine.ReviewStop, OSError, ValueError, TypeError, KeyError):
        print("SAFE_STOP: local candidate diagnosis not accepted", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
