"""Synthetic non-secret readiness tests; no real local model or network required."""
import importlib.util
from pathlib import Path
import json

import pytest

PATH = Path(__file__).resolve().parents[2] / "scripts/autonomy/zbook_preflight.py"
spec = importlib.util.spec_from_file_location("aios_zbook_preflight", PATH)
probe = importlib.util.module_from_spec(spec)
spec.loader.exec_module(probe)


@pytest.fixture
def repo(tmp_path):
    root = tmp_path
    (root / "docs").mkdir()
    (root / "AGENTS.md").write_text("Synthetic only", encoding="utf-8")
    (root / "docs/SPECIFICATION.md").write_text("Synthetic only", encoding="utf-8")
    return root


def fake_probe(args, cwd):
    if args == ["git", "--version"]:
        return True, "git version 2.50.0"
    if args == ["git", "rev-parse", "HEAD"]:
        return True, "a" * 40
    if args == ["git", "status", "--porcelain"]:
        return True, ""
    if args == ["aider", "--version"]:
        return True, "aider 0.86"
    if args == ["aider", "--help"]:
        return True, "\n".join(probe.OPTIONS)
    raise AssertionError(f"unexpected command {args}")


def test_ready_requires_aider_ollama_clean_checkout(repo):
    result = probe.inspect(repo, probe=fake_probe, read_models=lambda: {probe.MODEL})
    assert result["ready_for_local_trial"] is True
    assert result["valid_checkout_commit"] is True
    assert result["inference_completed"] is False
    assert result["pr_created"] is False
    assert result["merged"] is False
    assert result["commit"] == "a" * 40
    assert "aider 0.86" not in json.dumps(result)


def test_missing_model_never_claims_ready(repo):
    result = probe.inspect(repo, probe=fake_probe, read_models=lambda: set())
    assert result["local_ollama_model_available"] is False
    assert result["ready_for_local_trial"] is False


def test_missing_required_flag_never_claims_ready(repo):
    def old_aider(args, cwd):
        success, output = fake_probe(args, cwd)
        if args == ["aider", "--help"]:
            output = output.replace("--no-auto-commits", "")
        return success, output
    result = probe.inspect(repo, probe=old_aider, read_models=lambda: {probe.MODEL})
    assert result["ready_for_local_trial"] is False
    assert result["aider_flags_supported"] is False


def test_dirty_checkout_never_claims_ready(repo):
    def dirty(args, cwd):
        if args == ["git", "status", "--porcelain"]:
            return True, " M backend/app/synthetic.py"
        return fake_probe(args, cwd)
    result = probe.inspect(repo, probe=dirty, read_models=lambda: {probe.MODEL})
    assert result["checkout_clean"] is False
    assert result["ready_for_local_trial"] is False


def test_missing_fire_aios_checkout_fails_closed(tmp_path):
    with pytest.raises(ValueError, match="not the Fire AIOS checkout"):
        probe.inspect(tmp_path, probe=fake_probe, read_models=lambda: {probe.MODEL})


def test_ollama_connection_refused_without_secret_or_server_log(repo):
    def offline():
        raise OSError("synthetic network refusal")
    result = probe.inspect(repo, probe=fake_probe, read_models=offline)
    assert result["local_ollama_model_available"] is False
    assert result["ready_for_local_trial"] is False
