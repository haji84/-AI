#!/usr/bin/env python3
"""Read-only, fail-closed inventory of 57 canonical Fire AIOS chapters."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys

ROW = re.compile(r"^\|\s*(\d{1,2})\s*\|[^|]*\|\s*(Completed|Partial|Missing|External Gate)\s*\|")
CHAPTER = re.compile(r"^##\s+(\d{1,2})\.\s+")
STATUSES = ("Completed", "Partial", "Missing", "External Gate")


class InventoryError(ValueError):
    pass


def inventory(repo):
    root = Path(repo).resolve(strict=True)
    spec = root / "docs/SPECIFICATION.md"
    ledger = root / "docs/completion/CURRENT_COMPLETION_LEDGER.md"
    if any(not x.is_file() or x.is_symlink() for x in (spec, ledger)):
        raise InventoryError("canonical source unavailable")
    spec_text = spec.read_text(encoding="utf-8")
    ledger_text = ledger.read_text(encoding="utf-8")
    chapters = [int(m.group(1)) for line in spec_text.splitlines()
                if (m := CHAPTER.match(line))]
    if len(chapters) != 57 or set(chapters) != set(range(1, 58)):
        raise InventoryError("specification must have 57 unique chapters")
    rows = [(int(m.group(1)), m.group(2)) for line in ledger_text.splitlines()
            if (m := ROW.match(line))]
    if len(rows) != 57 or {n for n, _ in rows} != set(range(1, 58)):
        raise InventoryError("ledger must classify 57 chapters exactly once")
    # Audit base is a dated evidence anchor, distinct from current checkout SHA.
    match = re.search(r"Audited implementation base:\s*\x60([0-9a-f]{40})\x60", ledger_text)
    if not match:
        raise InventoryError("audited base unavailable")
    sha = subprocess.run(["git", "-C", str(root), "rev-parse", "HEAD"],
                         capture_output=True, text=True, check=True, timeout=20).stdout.strip()
    if not re.fullmatch(r"[a-f0-9]{40}", sha):
        raise InventoryError("invalid Git SHA")
    return {
        "schema_version": 1, "mode": "read_only", "commit": sha,
        "audited_implementation_base": match.group(1), "total": 57,
        "counts": {status: sum(s == status for _, s in rows) for status in STATUSES},
        "next_candidates": [n for n, status in rows if status in ("Partial", "Missing")][:8],
        "canonical_sha256": {"spec": hashlib.sha256(spec.read_bytes()).hexdigest(),
                             "ledger": hashlib.sha256(ledger.read_bytes()).hexdigest()},
        "ai_worker_connected": False, "code_changed": False,
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description="Read-only chapter inventory")
    parser.add_argument("--repo", default=".")
    parser.add_argument("--output", required=True)
    args = parser.parse_args(argv)
    try:
        report = inventory(args.repo)
        destination = Path(args.output).resolve()
        if destination.is_relative_to(Path(args.repo).resolve()):
            raise InventoryError("output must stay outside checkout")
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps(report, ensure_ascii=False))
        return 0
    except (InventoryError, OSError, subprocess.SubprocessError) as exc:
        print(f"SAFE_STOP: {type(exc).__name__}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
