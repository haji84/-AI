#!/usr/bin/env python3
"""Offline model response shape diagnosis; never disclose arbitrary model prose.

Validates immutable snapshot/candidate identity. It does not call Ollama or
GitHub and never creates an accepted or APPROVED review.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

import independent_ai_review as engine


class FormatStop(ValueError):
    pass


def category(value):
    if value is None:
        return "null_or_absent"
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, str):
        return "string"
    if isinstance(value, list):
        return "array"
    if isinstance(value, dict):
        return "object"
    if isinstance(value, (float, int)):
        return "number"
    return "unsupported_type"


def inspect(envelope, candidate):
    snapshot = engine.validate_snapshot(envelope)
    if (not isinstance(candidate, dict)
            or candidate.get("schema_version") != 1
            or candidate.get("kind") != "untrusted_local_model_candidate"
            or candidate.get("repo") != engine.REPO
            or candidate.get("pr") != snapshot["pr"]
            or candidate.get("head") != snapshot["head"]
            or candidate.get("snapshot_sha256") != envelope["sha256"]
            or candidate.get("model") not in engine.REVIEW_MODELS
            or candidate.get("context_tokens") not in engine.REVIEW_CONTEXTS
            or candidate.get("github_approved") is not False
            or candidate.get("merge_permitted") is not False):
        raise FormatStop("candidate provenance or authority mismatch")
    raw = candidate.get("raw_response")
    verdict = raw.get("verdict") if isinstance(raw, dict) else None
    verdict_kind = (
        "accepted_enum" if type(verdict) is str and verdict in ("pass", "needs_changes")
        else "missing" if not isinstance(raw, dict) or "verdict" not in raw
        else "wrong_case" if type(verdict) is str and verdict.lower() in
             ("pass", "needs_changes") and verdict not in ("pass", "needs_changes")
        else "other_string" if type(verdict) is str
        else "wrong_type"
    )
    findings = raw.get("findings") if isinstance(raw, dict) else None
    summary = raw.get("summary") if isinstance(raw, dict) else None
    return {
        "schema_version": 1,
        "kind": "untrusted_model_format_diagnostic",
        "repo": engine.REPO, "pr": snapshot["pr"], "head": snapshot["head"],
        "model": candidate["model"],
        "snapshot_matches": True,
        "response_shape": category(raw),
        "verdict_status": verdict_kind,
        "verdict_type": category(verdict),
        "summary_type": category(summary),
        "findings_type": category(findings),
        "findings_count": len(findings) if isinstance(findings, list) else None,
        "raw_verdict_included": False,
        "raw_model_text_included": False,
        "accepted_review": False,
        "independent_github_approval": False,
        "merge_permitted": False,
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description="Local offline AI response format probe")
    parser.add_argument("--snapshot", required=True, type=Path)
    parser.add_argument("--candidate", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        snap_path, can_path = args.snapshot.resolve(strict=True), args.candidate.resolve(strict=True)
        target = args.output.resolve()
        if (not snap_path.is_file() or snap_path.stat().st_size > engine.MAX_INPUT + 1000
                or not can_path.is_file() or can_path.stat().st_size > 80_000
                or target in (snap_path, can_path) or target.exists()):
            raise FormatStop("input or output safety gate")
        snapshot = json.loads(snap_path.read_text(encoding="utf-8"))
        candidate = json.loads(can_path.read_text(encoding="utf-8"))
        report = inspect(snapshot, candidate)
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open("x", encoding="utf-8") as stream:
            json.dump(report, stream, ensure_ascii=False, indent=2)
            stream.write("\n")
        print(json.dumps(report, ensure_ascii=False))
        return 0
    except (FormatStop, engine.ReviewStop, OSError, KeyError, ValueError, TypeError):
        print("SAFE_STOP: model response format diagnostic rejected", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
