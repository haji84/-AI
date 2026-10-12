#!/usr/bin/env python3
"""Bounded local Ollama/Aider code candidate generator. No push, tests or merges."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile

ALLOWED_SUFFIXES = (".py", ".js", ".css", ".html")
FORBIDDEN = ("auth", "security", "tenant", "password", "secret", "migrat", "audit", "permission")
MAX_FILE = 40000


class GuardError(ValueError):
    pass


def git(root, *args):
    result = subprocess.run(["git", "-C", str(root), *args], capture_output=True,
                            text=True, timeout=35, check=True)
    return result.stdout.strip()


def checked_source(root, name):
    if not isinstance(name, str) or len(name) > 240 or "\\" in name:
        raise GuardError("unsafe path")
    if (any(part in ("", ".", "..") for part in name.split("/"))
            or not name.startswith(("frontend/", "backend/app/"))
            or not name.endswith(ALLOWED_SUFFIXES)
            or any(part in name.lower() for part in FORBIDDEN)):
        raise GuardError("unowned or sensitive path")
    path = root / name
    if (not path.is_file() or path.is_symlink() or path.stat().st_size > MAX_FILE
            or not path.resolve().is_relative_to(root.resolve())):
        raise GuardError("invalid source file")
    if name not in git(root, "ls-files", "--", name).splitlines():
        raise GuardError("source not tracked")
    return path


def validate_task(root, task):
    if (not isinstance(task, dict) or task.get("schema_version") != 1
            or task.get("mode") != "candidate_only"
            or type(task.get("chapter")) is not int or task["chapter"] not in range(1, 58)
            or not re.fullmatch(r"[0-9a-f]{40}", str(task.get("base_commit", "")))
            or not re.fullmatch(r"[0-9a-f]{64}", str(task.get("source_sha256", "")))
            or not isinstance(task.get("acceptance"), str)
            or not 30 <= len(task["acceptance"]) <= 1600):
        raise GuardError("invalid task contract")
    ancestry = subprocess.run(["git", "-C", str(root), "merge-base", "--is-ancestor",
                               task["base_commit"], "HEAD"], capture_output=True, timeout=35)
    if ancestry.returncode != 0:
        raise GuardError("stale source commit")
    source = checked_source(root, task.get("source"))
    if hashlib.sha256(source.read_bytes()).hexdigest() != task["source_sha256"]:
        raise GuardError("stale source hash")
    if git(root, "status", "--porcelain"):
        raise GuardError("checkout not clean")
    return source


def verify_changes(worktree, allowed):
    result = subprocess.run(["git", "-C", str(worktree), "status", "--porcelain", "-z"],
                            capture_output=True, check=True, timeout=30)
    edited = []
    for entry in result.stdout.split(b"\x00"):
        if not entry:
            continue
        status = entry[:2].decode("ascii", errors="replace")
        name = entry[3:].decode("utf-8")
        if status != " M" or name != allowed:
            raise GuardError("agent changed forbidden or untracked path")
        edited.append(name)
    return len(edited) == 1


def generate(repo, task, worktrees, model="qwen2.5-coder:7b", runner=subprocess.run):
    repo = Path(repo).resolve(strict=True)
    source = validate_task(repo, task)
    if not re.fullmatch(r"[A-Za-z0-9._:-]{3,80}", model):
        raise GuardError("invalid local model tag")
    parent = Path(worktrees).resolve()
    if parent.is_relative_to(repo):
        raise GuardError("worktree parent is inside repo")
    parent.mkdir(parents=True, exist_ok=True)
    current = git(repo, "rev-parse", "HEAD")
    target = parent / f"aios-{task['chapter']}-{current[:12]}"
    if target.exists():
        raise GuardError("worktree already exists")
    git(repo, "worktree", "add", "--detach", str(target), current)
    generated = checked_source(target, task["source"])
    prompt = (
        "Implement only this specific accepted criterion within the supplied file. "
        "Do not change authorization, audit, official judgements, tenant boundaries, "
        "migrations or secrets. Never suggest shell commands. If impossible with "
        "one file, make no edits.\n"
        f"Chapter {task['chapter']}, base {task['base_commit']}\n"
        f"Acceptance: {task['acceptance']}"
    )
    env = {key: os.environ[key] for key in
           ("PATH", "HOME", "USERPROFILE", "SYSTEMROOT", "WINDIR", "TEMP", "TMP")
           if key in os.environ}
    env["OLLAMA_API_BASE"] = "http://127.0.0.1:11434"
    env["AIDER_ANALYTICS_DISABLE"] = "true"
    # Explicit empty config/env files block accidentally loading user keys from home.
    with tempfile.TemporaryDirectory(prefix="aios-agent-config-") as work:
        config = Path(work) / "empty.yml"
        dotenv = Path(work) / "empty.env"
        config.write_text("", encoding="utf-8")
        dotenv.write_text("", encoding="utf-8")
        argv = ["aider", "--model", f"ollama_chat/{model}",
                "--no-auto-commits", "--no-auto-test", "--no-auto-lint",
                "--no-suggest-shell-commands", "--no-check-update",
                "--no-gitignore", "--no-analytics", "--yes",
                "--config", str(config), "--env-file", str(dotenv),
                "--message", prompt, str(generated)]
        result = runner(argv, cwd=target, env=env, capture_output=True,
                        text=True, timeout=1800, check=False)
    if result.returncode:
        raise GuardError("coding agent failed; no publication attempted")
    changed = verify_changes(target, task["source"])
    output = {"mode": "candidate_only", "chapter": task["chapter"],
              "baseline": task["base_commit"], "checkout_commit": current,
              "source": task["source"],
              "worktree": str(target), "outcome": "no_change",
              "tests_passed": False, "pr_created": False, "merged": False}
    if changed:
        data = generated.read_bytes()
        if len(data) > 2 * MAX_FILE:
            raise GuardError("generated file oversized")
        output["source_sha256_after"] = hashlib.sha256(data).hexdigest()
        output["outcome"] = "candidate_unverified"
    return output


def main(argv=None):
    parser = argparse.ArgumentParser(description="Work-independent local coding candidate")
    parser.add_argument("--repo", required=True)
    parser.add_argument("--task", required=True)
    parser.add_argument("--worktrees", required=True)
    parser.add_argument("--model", default="qwen2.5-coder:7b")
    args = parser.parse_args(argv)
    try:
        root = Path(args.repo).resolve(strict=True)
        path = Path(args.task).resolve(strict=True)
        if (not path.is_relative_to(root) or path.is_symlink()
                or path.stat().st_size > 5000):
            raise GuardError("task must be a bounded trusted file")
        name = path.relative_to(root).as_posix()
        if (not name.startswith("docs/autonomy/tasks/")
                or name not in git(root, "ls-files", "--", name).splitlines()):
            raise GuardError("task must be in tracked docs/autonomy/tasks")
        task = json.loads(path.read_text(encoding="utf-8"))
        print(json.dumps(generate(root, task, args.worktrees, model=args.model),
                         ensure_ascii=False, indent=2))
        return 0
    except Exception as error:
        print(f"SAFE_STOP: {type(error).__name__}: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
