"""Only generated synthetic credentials are used; never store token literals."""
import importlib.util
import os
from pathlib import Path
import secrets
import selectors
import signal
import subprocess
import sys

import pytest

SCRIPT = Path(__file__).resolve().parents[2] / "scripts/security_scan.py"


@pytest.fixture
def binary():
    value = os.environ.get("FIRE_AI_GITLEAKS_BIN")
    if not value:
        pytest.fail("FIRE_AI_GITLEAKS_BIN must identify the pinned official binary")
    return Path(value)


@pytest.fixture
def repo(tmp_path):
    path = tmp_path / "repository"
    path.mkdir()
    git(path, "init", "-q")
    git(path, "config", "user.email", "synthetic@example.invalid")
    git(path, "config", "user.name", "Synthetic Test")
    (path / "readme").write_text("synthetic clean content\n")
    commit(path)
    return path


def git(repo, *args):
    subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True)


def commit(repo):
    git(repo, "add", "-A")
    git(repo, "commit", "-qm", "synthetic fixture")


def fake_token():
    return "gh" + "p_" + "".join(secrets.choice("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789") for _ in range(36))


def run(repo, binary, env=None):
    return subprocess.run([sys.executable, str(SCRIPT), "--repository", str(repo), "--gitleaks", str(binary)], capture_output=True, text=True, env=env)


def assert_private(result, token, path):
    output = result.stdout + result.stderr
    assert token not in output
    assert str(path) not in output
    assert "private-fixture" not in output


def test_clean_repository(repo, binary):
    result = run(repo, binary)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "findings=0" in result.stdout


@pytest.mark.parametrize("ignored", [False, True])
def test_dirty_and_ignored_working_tree(repo, binary, ignored):
    token = fake_token()
    path = repo / "private-fixture.txt"
    if ignored:
        (repo / ".gitignore").write_text("private-fixture.txt\n")
    path.write_text("credential = " + token + "\n")
    result = run(repo, binary)
    assert result.returncode == 1
    assert "findings=" in result.stdout
    assert_private(result, token, path)


def test_deleted_secret_in_other_fetched_ref(repo, binary):
    token = fake_token()
    path = repo / "private-fixture.txt"
    path.write_text("credential = " + token + "\n")
    commit(repo)
    path.unlink()
    commit(repo)
    git(repo, "update-ref", "refs/remotes/origin/synthetic", "HEAD")
    git(repo, "reset", "--hard", "HEAD~2")
    result = run(repo, binary)
    assert result.returncode == 1
    assert_private(result, token, path)


def test_history_binary_attribute_and_replace_ref_cannot_hide_secret(repo, binary):
    token = fake_token()
    path = repo / "private-fixture.txt"
    clean = subprocess.check_output(["git", "-C", str(repo), "rev-parse", "HEAD"], text=True).strip()
    (repo / ".gitattributes").write_text("private-fixture.txt -diff\n")
    path.write_text("credential = " + token + "\n")
    commit(repo)
    secret_commit = subprocess.check_output(["git", "-C", str(repo), "rev-parse", "HEAD"], text=True).strip()
    path.unlink()
    commit(repo)
    git(repo, "replace", secret_commit, clean)
    result = run(repo, binary)
    assert result.returncode == 1
    assert_private(result, token, path)


def test_repository_and_environment_cannot_allow_secret(repo, binary):
    token = fake_token()
    path = repo / "private-fixture.txt"
    path.write_text("credential = " + token + " # gitleaks:allow\n")
    (repo / ".gitleaks.toml").write_text('[allowlist]\npaths = [".*"]\n')
    (repo / ".gitleaksignore").write_text("*\n")
    env = dict(os.environ, GITLEAKS_CONFIG=str(repo / ".gitleaks.toml"), GITLEAKS_CONFIG_TOML='[allowlist]\npaths=[".*"]')
    result = run(repo, binary, env)
    assert result.returncode == 1
    assert_private(result, token, path)


def test_missing_and_wrong_binary_fail_closed(repo, tmp_path):
    for candidate in (tmp_path / "missing", tmp_path / "wrong"):
        if candidate.name == "wrong":
            candidate.write_text("#!/bin/sh\necho private-fixture\nexit 0\n")
            candidate.chmod(0o700)
        result = run(repo, candidate)
        assert result.returncode == 2
        assert "private-fixture" not in result.stdout + result.stderr


def module():
    spec = importlib.util.spec_from_file_location("security_scan", SCRIPT)
    loaded = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(loaded)
    return loaded


def test_execution_timeout_and_output_bound(tmp_path):
    scanner = module()
    with pytest.raises(scanner.ScanFailure):
        scanner.run_private([sys.executable, "-c", "import time; time.sleep(5)"], tmp_path, os.environ.copy(), timeout=0.1, max_bytes=1024)
    with pytest.raises(scanner.ScanFailure):
        scanner.run_private([sys.executable, "-c", "import sys; sys.stdout.write('x'*100000)"], tmp_path, os.environ.copy(), timeout=5, max_bytes=1024)
    with pytest.raises(scanner.ScanFailure):
        scanner.run_private([sys.executable, "-c", "open('report.json','wb').write(b'x'*100000)"], tmp_path, os.environ.copy(), timeout=5, max_bytes=1024)


def test_timeout_terminates_children_after_parent_exits(tmp_path):
    scanner = module()
    command = "import subprocess,sys; p=subprocess.Popen([sys.executable,'-c','import time; time.sleep(30)']); open('child.pid','w').write(str(p.pid))"
    child_pid = None
    try:
        with pytest.raises(scanner.ScanFailure):
            scanner.run_private([sys.executable, "-c", command], tmp_path,
                                os.environ.copy(), timeout=0.3, max_bytes=1024)
        child_pid = int((tmp_path / "child.pid").read_text())
        try:
            pidfd = os.pidfd_open(child_pid)
        except ProcessLookupError:
            return
        try:
            with selectors.DefaultSelector() as selector:
                selector.register(pidfd, selectors.EVENT_READ)
                assert selector.select(timeout=1), "scanner descendant survived timeout"
        finally:
            os.close(pidfd)
    finally:
        if child_pid is None and (tmp_path / "child.pid").exists():
            child_pid = int((tmp_path / "child.pid").read_text())
        if child_pid is not None:
            try:
                os.kill(child_pid, signal.SIGKILL)
            except ProcessLookupError:
                pass


def test_exception_and_wrong_version_are_generic(repo, binary, monkeypatch, capsys):
    scanner = module()
    monkeypatch.setattr(scanner, "run_private", lambda *args, **kwargs: (_ for _ in ()).throw(OSError("private-fixture")))
    assert scanner.main(["--repository", str(repo), "--gitleaks", str(binary)]) == 2
    assert "private-fixture" not in capsys.readouterr().out
    monkeypatch.setattr(scanner, "run_private", lambda *args, **kwargs: (0, b"0.0.0\n"))
    assert scanner.main(["--repository", str(repo), "--gitleaks", str(binary)]) == 2
    assert "private-fixture" not in capsys.readouterr().out


@pytest.mark.parametrize("failure", ["exit", "malformed", "missing", "config", "ignore", "inconsistent"])
def test_scan_failures_do_not_expose_reports(repo, binary, monkeypatch, capsys, failure):
    scanner = module()

    def fake(command, private, env, **kwargs):
        if command[1] == "version":
            return 0, scanner.VERSION.encode()
        if failure == "config":
            (private / "trusted.toml").write_text("private-fixture")
        if failure == "ignore":
            (private / "empty.ignore").write_text("private-fixture")
        if failure != "missing":
            (private / "report.json").write_text("private-fixture" if failure == "malformed" else '[]')
        return (2 if failure == "exit" else 1), b"private-fixture"

    monkeypatch.setattr(scanner, "run_private", fake)
    assert scanner.main(["--repository", str(repo), "--gitleaks", str(binary)]) == 2
    captured = capsys.readouterr()
    assert "private-fixture" not in captured.out + captured.err


def test_argument_errors_do_not_echo_values(capsys):
    scanner = module()
    assert scanner.main(["--private-fixture"]) == 2
    captured = capsys.readouterr()
    assert "private-fixture" not in captured.out + captured.err


def test_report_rotation_is_tolerated_only_during_polling(tmp_path, monkeypatch):
    scanner = module()
    report = tmp_path / "report.json"
    report.write_text("[]")
    original = Path.stat

    def rotating(path, *args, **kwargs):
        if path == report:
            raise FileNotFoundError()
        return original(path, *args, **kwargs)

    monkeypatch.setattr(Path, "stat", rotating)
    assert scanner.report_bytes(tmp_path) == 0


def test_environment_has_no_untrusted_tool_routing(monkeypatch):
    scanner = module()
    for name in ("GITLEAKS_CONFIG", "GITLEAKS_CONFIG_TOML", "GIT_DIR", "LD_PRELOAD", "PATH"):
        monkeypatch.setenv(name, "private-fixture")
    environment = scanner.safe_environment()
    assert "private-fixture" not in environment.values()
    assert environment["GIT_NO_REPLACE_OBJECTS"] == "1"
