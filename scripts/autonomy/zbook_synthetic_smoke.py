#!/usr/bin/env python3
"""ZBook synthetic Aider/Ollama smoke: parse edits, never run model-written code.

Creates a temporary Git repo with one synthetic file; never opens Fire AIOS
production data, never pushes or accesses GitHub tokens.
"""
from __future__ import annotations

import argparse
import ast
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile

DEFAULT_MODEL = "qwen2.5-coder:7b"


class SmokeError(ValueError):
    pass


def validate_synthetic_edit(code):
    if not isinstance(code, str) or len(code) > 4096:
        raise SmokeError("synthetic output size invalid")
    try:
        tree = ast.parse(code)
    except SyntaxError as exc:
        raise SmokeError("synthetic output cannot be parsed") from exc
    if len(tree.body) != 1 or not isinstance(tree.body[0], ast.FunctionDef):
        raise SmokeError("extra statements in synthetic output")
    func = tree.body[0]
    if func.name != "status" or func.args.args or len(func.body) != 1:
        raise SmokeError("unexpected synthetic function")
    ret = func.body[0]
    if not isinstance(ret, ast.Return) or not isinstance(ret.value, ast.Constant) or ret.value.value != "ready":
        raise SmokeError("synthetic acceptance condition not met")
    return True


def safe_env():
    permitted = ("PATH", "SYSTEMROOT", "WINDIR", "TEMP", "TMP", "USERPROFILE", "HOME")
    result = {k: os.environ[k] for k in permitted if k in os.environ}
    result["OLLAMA_API_BASE"] = "http://127.0.0.1:11434"
    result["AIDER_ANALYTICS_DISABLE"] = "true"
    return result


def run_checked(args, *, cwd, env, timeout=30):
    result = subprocess.run(
        args, cwd=cwd, env=env, stdin=subprocess.DEVNULL, capture_output=True,
        timeout=timeout, check=False,
    )
    if result.returncode != 0:
        raise SmokeError("synthetic command failed")
    return result.stdout


def smoke(model=DEFAULT_MODEL):
    if not re.fullmatch(r"[A-Za-z0-9._:-]{3,80}", model):
        raise SmokeError("invalid model identifier")
    env = safe_env()
    with tempfile.TemporaryDirectory(prefix="aios-zbook-synthetic-") as root:
        directory = Path(root)
        workspace = directory / "synthetic-repo"
        workspace.mkdir()
        source = workspace / "app.py"
        source.write_text('def status():\n    return "not-ready"\n', encoding="utf-8")
        run_checked(["git", "init", "-q"], cwd=workspace, env=env)
        run_checked(["git", "-c", "user.name=AIOS Synthetic",
                     "-c", "user.email=aios-test@example.invalid",
                     "add", "app.py"], cwd=workspace, env=env)
        run_checked(["git", "-c", "user.name=AIOS Synthetic",
                     "-c", "user.email=aios-test@example.invalid",
                     "commit", "-qm", "synthetic fixture"], cwd=workspace, env=env)
        empty_config = directory / "empty.yml"
        empty_env = directory / "empty.env"
        empty_config.write_text("", encoding="utf-8")
        empty_env.write_text("", encoding="utf-8")
        prompt = (
            "Synthetic offline-only test. Edit app.py only. Change status() "
            "to return the exact string 'ready'. Do not add code, comments, "
            "imports, extra files, tests, or shell commands."
        )
        args = ["aider", "--model", f"ollama_chat/{model}",
                "--no-auto-commits", "--no-auto-test", "--no-auto-lint",
                "--no-suggest-shell-commands", "--no-check-update",
                "--no-gitignore", "--no-analytics", "--no-detect-urls",
                "--map-tokens", "0", "--yes",
                "--config", str(empty_config), "--env-file", str(empty_env),
                "--chat-history-file", str(directory / "chat.md"),
                "--input-history-file", str(directory / "input.history"),
                "--llm-history-file", str(directory / "llm.history"),
                "--message", prompt, str(source)]
        # Output and model text are private. No generated code is executed.
        run_checked(args, cwd=workspace, env=env, timeout=600)
        status = run_checked(
            ["git", "status", "--porcelain", "-z", "--ignored", "--untracked-files=all"],
            cwd=workspace, env=env,
        )
        if status != b" M app.py\x00":
            raise SmokeError("model modified an unapproved synthetic surface")
        validate_synthetic_edit(source.read_text(encoding="utf-8"))
        return {
            "schema_version": 1,
            "mode": "synthetic_local_inference",
            "model": model,
            "aider_ollama_smoke": "PASS",
            "synthetic_edit_parsed": True,
            "executed_model_generated_code": False,
            "business_workflow_tested": False,
            "pr_created": False,
            "merged": False,
        }


def main(argv=None):
    p = argparse.ArgumentParser(description="ZBook single-file synthetic local model smoke")
    p.add_argument("--model", default=DEFAULT_MODEL)
    args = p.parse_args(argv)
    try:
        print(json.dumps(smoke(args.model), ensure_ascii=False, indent=2))
        return 0
    except (SmokeError, OSError, subprocess.SubprocessError,
            SyntaxError, UnicodeError):
        print("SAFE_STOP: synthetic ZBook trial unsuccessful; no code published", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
