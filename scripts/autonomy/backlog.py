#!/usr/bin/env python3
"""Work-independent, deduplicated investigation Issue bootstrap."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys

ROW = re.compile(r"^\|\s*(\d{1,2})\s*\|[^|]*\|\s*(Completed|Partial|Missing|External Gate)\s*\|")
AUDIT = re.compile(r"Audited implementation base:\s*\x60([0-9a-f]{40})\x60")

# Canonical precedence from CONTINUATION_ORDER_20261008.md; not a completion estimate.
PRIORITY = (
    5, 6, 7, 9, 43, 42, 10, 12, 13, 14, 15, 16, 17, 18, 20,
    21, 25, 26, 27, 28, 33, 34, 35, 36, 19, 29, 30, 31,
    32, 37, 38, 39, 3, 4, 41, 44, 45, 46, 50, 51,
    48, 54, 1, 52, 53,
)
MAX_OPEN = 2
CHAPTER_MARKER = re.compile(r"<!-- aios-autonomy-chapter:(\d{1,2}) -->")



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
    by_chapter = {}
    for line in text.splitlines():
        match = ROW.match(line)
        if not match:
            continue
        chapter = int(match.group(1))
        parts = line.split("|")
        if len(parts) < 6:
            raise SafeStop("incomplete chapter evidence row")
        delta = parts[5].strip()
        fingerprint = hashlib.sha256(
            f"{chapter}\x00{match.group(2)}\x00{delta}".encode("utf-8")
        ).hexdigest()[:16]
        by_chapter[chapter] = (delta, fingerprint)
    out = []
    # The dated continuation order predates the expanded §42 recovery requirements.
    # Unknown future Partial chapters are added after known priorities, never lost.
    full_order = (*PRIORITY, *sorted(set(statuses) - set(PRIORITY)))
    for chapter in full_order:
        if statuses.get(chapter) not in ("Partial", "Missing"):
            continue
        delta, fingerprint = by_chapter[chapter]
        marker = f"<!-- aios-autonomy-chapter:{chapter} -->"
        gap_marker = f"<!-- aios-autonomy-gap:{chapter}:{fingerprint} -->"
        body = (
            f"{marker}\n{gap_marker}\nInvestigation candidate, not implementation credit.\n\n"
            f"Canonical chapter: docs/SPECIFICATION.md #{chapter}.\n"
            "Completion: docs/completion/CURRENT_COMPLETION_LEDGER.md.\n"
            f"Audited implementation base: {anchor.group(1)}.\n"
            f"Current documented remaining gap: {delta[:1000]}\n\n"
            "Investigate exact current main, existing code, tests, tenant/role boundary and "
            "the next smallest verifiable requirement. Do not infer missing implementation "
            "from Partial alone. Do not use production data, expose secrets, change privileges, "
            "alter formal legal/medical decisions, or auto-merge.\n"
            "Exit: a reviewed bounded implementation proposal with source evidence.\n"
        )
        out.append({"chapter": chapter, "marker": marker, "gap_marker": gap_marker,
                    "title": f"AIOS autonomy: chapter {chapter} gap {fingerprint} review",
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
    trusted_rows = [x for x in rows
                    if isinstance(x.get("author"), dict)
                    and x["author"].get("login") in trusted]
    active = set()
    for row in trusted_rows:
        if row.get("state") == "OPEN":
            match = CHAPTER_MARKER.search(row.get("body") or "")
            if match:
                active.add(int(match.group(1)))
    contents = [x.get("body") or "" for x in trusted_rows]
    created, existing = 0, 0
    for item in planned:
        chapter = item["chapter"]
        # Historical bootstrap issues without a gap fingerprint remain valid.
        if any(item["gap_marker"] in body or
               (item["marker"] in body and "<!-- aios-autonomy-gap:" not in body)
               for body in contents):
            existing += 1
            continue
        # A changed requirement may not start a second parallel investigation.
        if chapter in active or len(active) >= MAX_OPEN:
            continue
        execute(["gh", "issue", "create", "--repo", repo,
                 "--title", item["title"], "--body", item["body"]])
        contents.append(item["body"])
        active.add(chapter)
        created += 1
    return {"created": created, "existing": existing}


def main(argv=None):
    p = argparse.ArgumentParser(description="15-minute, 57-chapter guarded backlog")
    p.add_argument("--repo", default=".")
    p.add_argument("--publish", action="store_true")
    args = p.parse_args(argv)
    try:
        if args.publish:
            result = update_issues(args.repo, os.environ.get("GH_REPO", ""))
        else:
            result = {"mode": "read_only", "candidates": [x["chapter"] for x in proposals(args.repo)]}
        print(json.dumps(result, ensure_ascii=False))
        return 0
    except (SafeStop, OSError, ValueError, subprocess.SubprocessError) as e:
        print(f"SAFE_STOP: {type(e).__name__}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
