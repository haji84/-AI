#!/usr/bin/env python3
"""Read-only workstation readiness check for the bounded Fire AIOS AI worker.

Does not run a model, modify the repository, access GitHub credentials or
publish any output other than non-sensitive booleans and a local checkout SHA.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import subprocess
import sys
from urllib.request import urlopen

MODEL = "qwen2.5-coder:7b"
OLLAMA_TAGS = "http://127.0.0.1:11434/api/tags"
OPTIONS = (
    "--no-auto-commits",
    "--no-auto-test",
    "--no-auto-lint",
    "--no-suggest-shell-commands",
    "--no-check-update",
    "--no-gitignore",
    "--no-analytics",
    "--no-detect-urls",
    "--map-tokens",
    "--chat-history-file",
    "--input-history-file",
    "--llm-history-file",
    "--env-file",
    "--config",
)


def run_probe(args, cwd):
    result = subprocess.run(
        args, cwd=cwd, capture_output=True, text=True, timeout=15,
        check=False,
    )
    return result.returncode == 0, result.stdout[:200_000]


def local_models():
    with urlopen(OLLAMA_TAGS, timeout=4) as response:
        if response.status != 200:
            raise ValueError("local Ollama health check failed")
        data = response.read(1_000_001)
    if len(data) > 1_000_000:
        raise ValueError("oversized local Ollama response")
    models = json.loads(data).get("models", [])
    if not isinstance(models, list):
        raise ValueError("invalid local Ollama response")
    return {m.get("name") for m in models if isinstance(m, dict) and isinstance(m.get("name"), str)}


def inspect(repo, *, probe=run_probe, read_models=local_models):
    root = Path(repo).resolve(strict=True)
    if not (root / "AGENTS.md").is_file() or not (root / "docs/SPECIFICATION.md").is_file():
        raise ValueError("not the Fire AIOS checkout")
    git_ok, git_version = probe(["git", "--version"], root)
    commit_ok, sha = probe(["git", "rev-parse", "HEAD"], root)
    status_ok, status = probe(["git", "status", "--porcelain"], root)
    aider_ok, _ = probe(["aider", "--version"], root)
    options_ok, flags = probe(["aider", "--help"], root) if aider_ok else (False, "")
    available = False
    try:
        available = MODEL in read_models()
    except (OSError, ValueError, json.JSONDecodeError):
        pass
    result = {
        "schema_version": 1,
        "mode": "read_only_preflight",
        "python_311_or_newer": sys.version_info >= (3, 11),
        "git_available": bool(git_ok and "git version" in git_version),
        "valid_checkout_commit": bool(commit_ok and re.fullmatch(r"[0-9a-f]{40}", sha.strip())),
        "checkout_clean": bool(status_ok and status.strip() == ""),
        "aider_available": bool(aider_ok),
        "aider_flags_supported": bool(options_ok and all(flag in flags for flag in OPTIONS)),
        "local_ollama_model_available": bool(available),
        "inference_completed": False,
        "tests_on_zbook_completed": False,
        "pr_created": False,
        "merged": False,
    }
    required = ("python_311_or_newer", "git_available", "valid_checkout_commit",
                "checkout_clean", "aider_available", "aider_flags_supported",
                "local_ollama_model_available")
    result["ready_for_local_trial"] = all(result[k] for k in required)
    if result["valid_checkout_commit"]:
        result["commit"] = sha.strip()
    return result


def main(argv=None):
    p = argparse.ArgumentParser(description="Inspect local Fire AIOS Ollama readiness")
    p.add_argument("--repo", default=".")
    args = p.parse_args(argv)
    try:
        result = inspect(args.repo)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0 if result["ready_for_local_trial"] else 2
    except (OSError, ValueError, subprocess.SubprocessError):
        print("SAFE_STOP: AIOS preflight unavailable; no code or secrets accessed", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
