#!/usr/bin/env python3
"""Work-independent, deduplicated investigation Issue bootstrap."""
import argparse
import json
import os
from pathlib import Path
import re
import subprocess
import sys

ROW = re.compile(r"^\|\s*(\d{1,2})\s*\|[^|]*\|\s*(Completed|Partial|Missing|External Gate)\s*\|")
AUDIT = re.compile(r"Audited implementation base:\s*\x60([0-9a-f]{40})\x60")


class SafeStop(ValueError):
    pass


def proposals(root):
    root = Path(root).resolve(strict=True)
    ledger_file = root / "docs/completion/CURRENT_COMPLETION_LEDGER.md"
    spec_file = root / "docs/SPECIFICATION.md"
    if not ledger_file.is_file() or not spec_file.is_file():
        raise SafeStop("canonical documents missing")
    text = ledger_file.read_text(encoding="utf-8")
    spec = spec_file.read_text(encoding="utf-8")
    rows = [(int(m.group(1)), m.group(2)) for line in text.splitlines()
            if (m := ROW.match(line))]
    chapters = [int(m.group(1)) for line in spec.splitlines()
                if (m := re.match(r"^##\s+(\d{1,2})\.\s+", line))]
    if (len(rows) != 57 or len(chapters) != 57
            or {n for n, _ in rows} != set(range(1, 58))
            or set(chapters) != set(range(1, 58))):
        raise SafeStop("canonical chapter count or identity unverified")
    anchor = AUDIT.search(text)
    if not anchor:
        raise SafeStop("audited implementation base missing")
    statuses = dict(rows)
    out = []
    for chapter in (12, 21):
        if statuses[chapter] not in ("Partial", "Missing"):
            continue
        marker = f"<!-- aios-autonomy-chapter:{chapter} -->"
        body = (
            f"{marker}\nInvestigate evidence before implementation; not completion credit.\n\n"
            f"Canonical chapter: docs/SPECIFICATION.md #{chapter}.\n"
            "Completion: docs/completion/CURRENT_COMPLETION_LEDGER.md.\n"
            f"Audited base: {anchor.group(1)}.\n\n"
            "Review current main, live module/tests/permissions and exact missing "
            "requirement. Never infer that Partial means a missing module. "
            "No production data, secrets, legal determination or automatic merge.\n"
            "Exit: one documented and reviewed bounded implementation proposal.\n"
        )
        out.append({"chapter": chapter, "marker": marker,
                    "title": f"AIOS autonomy: chapter {chapter} evidence-backed gap review",
                    "body": body})
    return out


def update_issues(root, repo, runner=subprocess.run):
    if repo != "haji84/-AI":
        raise SafeStop("unexpected GitHub repository")
    planned = proposals(root)
    if not planned:
        return {"created": 0, "existing": 0}
    def execute(args):
        return runner(args, text=True, capture_output=True, check=True, timeout=70)
    listed = execute(["gh", "issue", "list", "--repo", repo, "--state", "all",
                      "--limit", "1000", "--json", "body,author,state"])
    rows = json.loads(listed.stdout)
    if not isinstance(rows, list) or len(rows) >= 1000 or any(not isinstance(x, dict) for x in rows):
        raise SafeStop("issue pagination incomplete")
    trusted = {"github-actions[bot]", "haji84"}
    if any(x.get("state") == "OPEN"
           and isinstance(x.get("author"), dict)
           and x["author"].get("login") == "haji84"
           and "<!-- aios-autonomy-pause -->" in (x.get("body") or "")
           for x in rows):
        return {"created": 0, "existing": 0, "paused": True}
    contents = [x.get("body") or "" for x in rows
                if isinstance(x.get("author"), dict)
                and x["author"].get("login") in trusted]
    created, existing = 0, 0
    for item in planned:
        if any(item["marker"] in body for body in contents):
            existing += 1
            continue
        execute(["gh", "issue", "create", "--repo", repo,
                 "--title", item["title"], "--body", item["body"]])
        contents.append(item["body"])
        created += 1
    return {"created": created, "existing": existing}


def main(argv=None):
    p = argparse.ArgumentParser(description="15-minute, 57-chapter guarded backlog")
    p.add_argument("--repo", default=".")
    p.add_argument("--publish", action="store_true")
    p.add_argument("--output", type=Path, help="Write successful summary JSON evidence")
    args = p.parse_args(argv)
    try:
        if args.publish:
            result = update_issues(args.repo, os.environ.get("GH_REPO", ""))
        else:
            result = {"mode": "read_only", "candidates": [x["chapter"] for x in proposals(args.repo)]}
        encoded = json.dumps(result, ensure_ascii=False)
        if args.output is not None:
            args.output.write_text(encoded + "\n", encoding="utf-8")
        print(encoded)
        return 0
    except (SafeStop, OSError, ValueError, subprocess.SubprocessError) as e:
        print(f"SAFE_STOP: {type(e).__name__}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
