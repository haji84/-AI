"""Synthetic Git regression for the bounded Work-independent Ollama worker."""
import hashlib
import importlib.util
from pathlib import Path
import subprocess
import tempfile
from types import SimpleNamespace

import pytest

SCRIPT = Path(__file__).resolve().parents[2] / "scripts/autonomy/bounded_worker.py"
spec = importlib.util.spec_from_file_location("bounded_autonomy_worker", SCRIPT)
worker = importlib.util.module_from_spec(spec)
spec.loader.exec_module(worker)


def git(root, *args):
    return subprocess.run(["git", "-C", str(root), *args], text=True,
                          capture_output=True, check=True).stdout.strip()


@pytest.fixture
def env(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    git(repo, "init", "-q")
    git(repo, "config", "user.name", "Test")
    git(repo, "config", "user.email", "test@example.invalid")
    (repo / "frontend").mkdir()
    (repo / "frontend/inspection.js").write_text("export const ready = false;\n")
    git(repo, "add", ".")
    git(repo, "commit", "-qm", "initial")
    sha = git(repo, "rev-parse", "HEAD")
    digest = hashlib.sha256((repo / "frontend/inspection.js").read_bytes()).hexdigest()
    task = dict(schema_version=1, mode="candidate_only", chapter=12,
                base_commit=sha, source="frontend/inspection.js",
                source_sha256=digest,
                acceptance="Make the status indicator accurate for synthetic tests.")
    return repo, task, tmp_path / "trees"


def test_refuses_stale_or_sensitive_source(env):
    repo, task, _ = env
    with pytest.raises(worker.GuardError, match="stale"):
        worker.validate_task(repo, dict(task, base_commit="f" * 40))
    for path in ("../secret.py", ".github/workflows/job.yml", "backend/app/auth.py",
                 "frontend/../../b.js"):
        with pytest.raises(worker.GuardError):
            worker.checked_source(repo, path)


def test_candidate_keeps_main_unchanged(env):
    repo, task, parent = env

    def fake(argv, cwd, env, capture_output, text, timeout, check):
        assert "ollama_chat/qwen2.5-coder:7b" in argv
        assert "GITHUB_TOKEN" not in env
        assert "--no-auto-commits" in argv
        assert "--no-suggest-shell-commands" in argv
        (cwd / "frontend/inspection.js").write_text("export const ready = true;\n")
        return SimpleNamespace(returncode=0)

    result = worker.generate(repo, task, parent, runner=fake)
    assert result["outcome"] == "candidate_unverified"
    assert result["pr_created"] is False
    assert result["tests_passed"] is False
    assert (repo / "frontend/inspection.js").read_text() == "export const ready = false;\n"


def test_blocks_other_files_even_if_agent_exit_zero(env):
    repo, task, parent = env

    def fake(argv, cwd, env, capture_output, text, timeout, check):
        (cwd / "frontend/inspection.js").write_text("export const ready = true;\n")
        (cwd / "frontend/new_secret.js").write_text("untracked")
        return SimpleNamespace(returncode=0)

    with pytest.raises(worker.GuardError, match="forbidden"):
        worker.generate(repo, task, parent, runner=fake)


def test_no_change_is_not_completion(env):
    repo, task, parent = env
    fake = lambda *args, **kwargs: SimpleNamespace(returncode=0)
    result = worker.generate(repo, task, parent, runner=fake)
    assert result["outcome"] == "no_change"
    assert not result["merged"]


def test_invalid_contract_approval_is_rejected(env):
    repo, task, _ = env
    with pytest.raises(worker.GuardError, match="contract"):
        worker.validate_task(repo, dict(task, mode="auto_merge"))
