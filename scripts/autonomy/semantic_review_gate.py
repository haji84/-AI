#!/usr/bin/env python3
"""Stage 2: independent deterministic semantic triage of anchored model findings.

Stage 1 verifies locations. Stage 2 checks specific refutable claims against
source AST and labels everything else unverified. Neither is a GitHub APPROVED.
"""
import argparse
import ast
import hashlib
import json
from pathlib import Path
import re
import sys

import independent_ai_review as engine


class SemanticStop(ValueError):
    pass


def complete_new_python_source(patch):
    """Reconstruct ONLY full newly added Python files; reject partial diffs."""
    first = next((line for line in patch.splitlines() if line.startswith("@@ ")), "")
    if not re.match(r"@@ -0,0 \+1(?:,\d+)? @@", first):
        return None
    lines = []
    for line in patch.splitlines():
        if line.startswith("+") and not line.startswith("+++"):
            lines.append(line[1:])
        elif line.startswith("@@ ") or line.startswith("\\ No newline"):
            continue
        else:
            return None
    return "\n".join(lines) + "\n"


def ast_contradictions(finding, patch):
    """Negative factual checks only; never positively certify vulnerability."""
    text = (finding["evidence"] + " " + finding["recommendation"]).lower()
    source = complete_new_python_source(patch)
    if source is None:
        return []
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return []
    remarks = []
    re_imported = any(
        isinstance(n, ast.Import) and any(a.name == "re" for a in n.names)
        or isinstance(n, ast.ImportFrom) and n.module == "re"
        for n in ast.walk(tree)
    )
    re_calls = any(
        isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
        and isinstance(n.func.value, ast.Name) and n.func.value.id == "re"
        for n in ast.walk(tree)
    )
    if "use the re module" in text and re_imported and re_calls:
        remarks.append("Already imports and calls Python re; recommendation is contradicted.")
    run_calls = [
        n for n in ast.walk(tree)
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
        and isinstance(n.func.value, ast.Name) and n.func.value.id == "subprocess"
        and n.func.attr == "run"
    ]
    has_bounded_run = any(
        {"check", "timeout"}.issubset({k.arg for k in call.keywords})
        and any(k.arg == "check" and isinstance(k.value, ast.Constant)
                and k.value.value is True for k in call.keywords)
        for call in run_calls
    )
    if "check=true" in text and "timeout" in text and has_bounded_run:
        remarks.append("Source already invokes subprocess.run with check=True and timeout.")
    main_defs = [n for n in tree.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
                 and n.name == "main"]
    direct_main_run = any(
        isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
        and isinstance(n.func.value, ast.Name) and n.func.value.id == "subprocess"
        and n.func.attr == "run"
        for fn in main_defs for n in ast.walk(fn)
    )
    if "main" in text and "subprocess.run" in text and main_defs and not direct_main_run:
        remarks.append("main does not directly invoke subprocess.run.")
    return remarks


def triage(envelope, report):
    data = engine.validate_snapshot(envelope)
    if not isinstance(report, dict) or any((
        report.get("kind") != "local_ai_review_candidate",
        report.get("pr") != data["pr"], report.get("repo") != engine.REPO,
        report.get("head") != data["head"], report.get("base") != data["base"],
        report.get("snapshot_sha256") != envelope["sha256"],
        report.get("ci") != data["ci"],
        report.get("independent_github_approval") is not False,
        report.get("merge_permitted") is not False,
    )):
        raise SemanticStop("review does not match pinned evidence or safety contract")
    findings = report.get("findings")
    if not isinstance(findings, list) or len(findings) > 20:
        raise SemanticStop("invalid model findings")
    patches = {f["path"]: f["patch"] for f in data["files"]}
    assessments = []
    for n, finding in enumerate(findings):
        if not isinstance(finding, dict):
            raise SemanticStop("invalid finding")
        path, line = finding.get("path"), finding.get("source_line")
        if (path not in patches or not isinstance(line, str)
                or line not in engine.changed_source_lines(patches[path])):
            raise SemanticStop("ungrounded source line; semantic triage rejected")
        if any(not isinstance(finding.get(k), str) for k in ("evidence", "recommendation")):
            raise SemanticStop("finding text is missing")
        contradictions = ast_contradictions(finding, patches[path]) if path.endswith(".py") else []
        assessments.append({
            "finding_index": n, "path": path, "source_line": line,
            "source_quote_verified": True,
            "interpretation_status": "contradicted" if contradictions else "unverified",
            "reasons": contradictions if contradictions else [
                "Exact quote alone cannot establish the security claim; needs independent assessment."],
        })
    return {
        "schema_version": 1, "kind": "independent_semantic_triage_candidate",
        "repo": engine.REPO, "pr": data["pr"], "head": data["head"],
        "snapshot_sha256": envelope["sha256"],
        "review_sha256": hashlib.sha256(engine.canonical(report)).hexdigest(),
        "assessments": assessments,
        "semantic_approval_granted": False,
        "independent_github_approval": False,
        "merge_permitted": False,
        "context_completeness_proven": False,
        "independent_operator_verified": False,
    }


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--snapshot", type=Path, required=True)
    parser.add_argument("--review", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        if args.output.exists():
            raise SemanticStop("refusing to overwrite semantic evidence")
        snap = json.loads(args.snapshot.read_text(encoding="utf-8"))
        report = json.loads(args.review.read_text(encoding="utf-8"))
        result = triage(snap, report)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n",
                               encoding="utf-8")
        print(json.dumps({"mode": "semantic_triage", "output": str(args.output),
                          "findings": len(result["assessments"]),
                          "github_approved": False}))
        return 0
    except (SemanticStop, engine.ReviewStop, OSError, ValueError, TypeError, KeyError):
        print("SAFE_STOP: semantic triage not accepted", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
