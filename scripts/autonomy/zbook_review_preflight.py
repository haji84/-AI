#!/usr/bin/env python3
"""Read-only local Ollama reviewer preflight. No inference, GitHub write or secrets."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys
from urllib.request import ProxyHandler, Request, build_opener

LOCAL_MODELS = "http://127.0.0.1:11434/api/tags"
MODEL = "qwen2.5-coder:7b"
SECRET_ENV = ("GH_TOKEN", "GITHUB_TOKEN", "GH_ENTERPRISE_TOKEN",
              "OPENAI_API_KEY", "ANTHROPIC_API_KEY", "AZURE_OPENAI_API_KEY",
              "HF_TOKEN", "HUGGING_FACE_HUB_TOKEN")


def model_available():
    req = Request(LOCAL_MODELS, method="GET")
    with build_opener(ProxyHandler({})).open(req, timeout=4) as response:
        if response.status != 200:
            return False
        raw = response.read(1_000_001)
    if len(raw) > 1_000_000:
        return False
    value = json.loads(raw)
    return isinstance(value, dict) and isinstance(value.get("models"), list) and any(
        isinstance(item, dict) and item.get("name") == MODEL
        for item in value["models"])


def cli_credentials_at(home, environ):
    """Detect common gh CLI on-disk auth stores without reading their contents."""
    root = Path(home)
    locations = [root / ".config" / "gh" / "hosts.yml",
                 root / "AppData" / "Roaming" / "GitHub CLI" / "hosts.yml"]
    if environ.get("GH_CONFIG_DIR"):
        locations.append(Path(environ["GH_CONFIG_DIR"]) / "hosts.yml")
    return any(path.is_file() for path in locations)


def inspect(*, environ=None, home=None, probe_model=model_available):
    env = dict(os.environ if environ is None else environ)
    root = Path.home() if home is None else Path(home)
    token_environment_present = any(bool(env.get(k)) for k in SECRET_ENV)
    disk_gh_credentials_found = cli_credentials_at(root, env)
    try:
        local_model = bool(probe_model())
    except (OSError, ValueError, KeyError, TimeoutError):
        local_model = False
    result = {
        "schema_version": 1,
        "mode": "read_only_local_review_preflight",
        "python_311_or_newer": sys.version_info >= (3, 11),
        "model": MODEL,
        "ollama_model_available": local_model,
        "secret_environment_present": token_environment_present,
        "github_cli_credential_store_found": disk_gh_credentials_found,
        "reviewer_independence_verified": False,
        "real_inference_completed": False,
        "github_review_posted": False,
        "github_approved": False,
    }
    result["ready_for_isolated_inference_trial"] = bool(
        result["python_311_or_newer"] and local_model
        and not token_environment_present and not disk_gh_credentials_found)
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description="Check isolated ZBook Ollama evaluator prerequisites")
    parser.parse_args(argv)
    result = inspect()
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["ready_for_isolated_inference_trial"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
