#!/usr/bin/env python3
"""Read-only GitHub-authenticated approval evidence. NEVER merges or grants privileges.

A chat instruction alone does not satisfy independent GitHub review. This module
only records an exact owner-issued approval for a specific PR head and expiry.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone, timedelta
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys

REPO = "haji84/-AI"
OWNER = "haji84"
COMMAND = re.compile(
    r"AIOS_APPROVE\nPR=(\d{1,7})\nHEAD=([a-f0-9]{40})"
    r"\nEXPIRES=(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z)"
    r"\nNONCE=([A-Za-z0-9_-]{12,64})"
)
MAX_EVENT_BYTES = 131072


class ApprovalError(ValueError):
    pass


def parse_time(value):
    if not isinstance(value, str) or not re.fullmatch(
        r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z", value
    ):
        raise ApprovalError("invalid UTC date format")
    try:
        return datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    except ValueError as exc:
        raise ApprovalError("invalid UTC date value") from exc


def inspect_event(event, pr, *, now=None):
    """Return a narrowly scoped receipt. Never count this as code review."""
    if now is None:
        now = datetime.now(timezone.utc)
    if not isinstance(event, dict) or not isinstance(pr, dict):
        raise ApprovalError("invalid GitHub response")
    repo = event.get("repository")
    issue = event.get("issue")
    comment = event.get("comment")
    sender = event.get("sender")
    if (not isinstance(repo, dict) or repo.get("full_name") != REPO
            or not isinstance(issue, dict) or not isinstance(issue.get("pull_request"), dict)
            or not isinstance(comment, dict) or not isinstance(sender, dict)):
        raise ApprovalError("unexpected GitHub event")
    number = issue.get("number")
    if type(number) is not int or number < 1 or number > 9999999:
        raise ApprovalError("invalid pull request number")
    author = comment.get("user")
    if (not isinstance(author, dict)
            or author.get("login") != OWNER
            or author.get("type") != "User"
            or sender.get("login") != OWNER
            or comment.get("author_association") != "OWNER"
            or event.get("action") != "created"):
        raise ApprovalError("not an owner-authored new comment")
    body = comment.get("body")
    if not isinstance(body, str) or len(body) > 512:
        raise ApprovalError("invalid approval command")
    match = COMMAND.fullmatch(body)
    if not match or int(match.group(1)) != number:
        raise ApprovalError("approval must identify exact PR")
    head = pr.get("head")
    base = pr.get("base")
    if (pr.get("number") != number or pr.get("state") != "open"
            or pr.get("merged_at") is not None
            or not isinstance(head, dict) or not isinstance(base, dict)
            or not isinstance(head.get("sha"), str)
            or base.get("ref") != "main"
            or match.group(2) != head["sha"]):
        raise ApprovalError("approval does not match current open PR head")
    created = parse_time(comment.get("created_at"))
    expires = parse_time(match.group(3))
    if (now < created or now - created > timedelta(hours=24)
            or expires <= now or expires - created > timedelta(hours=24)
            or expires <= created):
        raise ApprovalError("approval expired, future-dated, or excessive lifetime")
    nonce_hash = hashlib.sha256(match.group(4).encode("ascii")).hexdigest()
    comment_id = comment.get("id")
    if type(comment_id) is not int or comment_id < 1:
        raise ApprovalError("invalid comment identity")
    return {
        "schema_version": 1,
        "decision": "chat_authorized_for_bounded_next_step",
        "repo": REPO, "pr": number, "head": head["sha"],
        "comment_id": comment_id, "actor": OWNER,
        "created_at": comment["created_at"], "expires_at": match.group(3),
        "nonce_sha256": nonce_hash,
        "independent_review_satisfied": False,
        "auto_merge_permitted": False, "production_change_permitted": False,
    }


def gh_get(path):
    result = subprocess.run(
        ["gh", "api", path], capture_output=True, text=True, check=True, timeout=35
    )
    if len(result.stdout) > 1000000:
        raise ApprovalError("GitHub response oversized")
    return json.loads(result.stdout)


def main(argv=None):
    parser = argparse.ArgumentParser(description="Record owner-authenticated approval evidence")
    parser.add_argument("--event", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args(argv)
    try:
        src = Path(args.event).resolve(strict=True)
        if not src.is_file() or src.stat().st_size > MAX_EVENT_BYTES:
            raise ApprovalError("GitHub event not available")
        event = json.loads(src.read_text(encoding="utf-8"))
        number = event.get("issue", {}).get("number")
        if type(number) is not int or number < 1 or number > 9999999:
            raise ApprovalError("invalid PR number")
        if os.environ.get("GH_REPO") != REPO:
            raise ApprovalError("unexpected repository environment")
        pr = gh_get(f"repos/{REPO}/pulls/{number}")
        receipt = inspect_event(event, pr)
        output = Path(args.output).resolve()
        workspace = os.environ.get("GITHUB_WORKSPACE")
        if workspace and output.is_relative_to(Path(workspace).resolve()):
            raise ApprovalError("receipt output must stay outside checkout")
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(receipt, sort_keys=True, indent=2), encoding="utf-8")
        print(f"Approval receipt recorded for PR #{number}; not independent review; no merge")
        return 0
    except (ApprovalError, OSError, subprocess.SubprocessError,
            ValueError, TypeError, KeyError):
        print("SAFE_STOP: approval receipt rejected; no action taken", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
