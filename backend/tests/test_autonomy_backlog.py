"""Synthetic regression for scheduled autonomous Issue discovery."""
import importlib.util
from pathlib import Path
from types import SimpleNamespace

import pytest

SRC = Path(__file__).resolve().parents[2] / "scripts/autonomy/backlog.py"
spec = importlib.util.spec_from_file_location("aios_backlog", SRC)
backlog = importlib.util.module_from_spec(spec)
spec.loader.exec_module(backlog)


@pytest.fixture
def repo(tmp_path):
    root = tmp_path
    (root / "docs/completion").mkdir(parents=True)
    (root / "docs/SPECIFICATION.md").write_text(
        "\n".join(f"## {n}. Chapter\nRequirement" for n in range(1, 58)), encoding="utf-8")
    (root / "docs/completion/CURRENT_COMPLETION_LEDGER.md").write_text(
        "Audited implementation base: " + chr(96) + "a" * 40 + chr(96) + "\n" +
        "\n".join(f"| {n} | Chapter | {'Partial' if n in (12, 21) else 'Completed'} | evidence |"
                  for n in range(1, 58)), encoding="utf-8")
    return root


def test_two_bound_candidates_from_real_statuses(repo):
    result = backlog.proposals(repo)
    assert [x["chapter"] for x in result] == [12, 21]
    assert all("No production" in x["body"] for x in result)


def test_completed_chapter_is_not_requeued(repo):
    path = repo / "docs/completion/CURRENT_COMPLETION_LEDGER.md"
    path.write_text(path.read_text().replace("| 12 | Chapter | Partial |", "| 12 | Chapter | Completed |"))
    assert [x["chapter"] for x in backlog.proposals(repo)] == [21]


def test_reject_duplicate_ledger_row(repo):
    path = repo / "docs/completion/CURRENT_COMPLETION_LEDGER.md"
    path.write_text(path.read_text() + "\n| 12 | Chapter | Partial | evidence |\n")
    with pytest.raises(backlog.SafeStop):
        backlog.proposals(repo)


def test_issue_publish_is_deduplicated(repo):
    observed = []
    def runner(args, **kwargs):
        observed.append(args)
        if args[2] == "list":
            return SimpleNamespace(stdout="[]")
        return SimpleNamespace(stdout="created")
    first = backlog.update_issues(repo, "haji84/-AI", runner=runner)
    assert first == {"created": 2, "existing": 0, "paused": False}
    bodies = [a[-1] for a in observed if a[2] == "create"]
    observed.clear()
    def existing_runner(args, **kwargs):
        observed.append(args)
        if args[2] == "list":
            import json
            return SimpleNamespace(stdout=json.dumps([{"body": b, "author": {"login": "github-actions[bot]"}} for b in bodies]))
        raise AssertionError("unexpected duplicate Issue creation")
    second = backlog.update_issues(repo, "haji84/-AI", runner=existing_runner)
    assert second == {"created": 0, "existing": 2, "paused": False}


def test_reject_unapproved_repository(repo):
    with pytest.raises(backlog.SafeStop):
        backlog.update_issues(repo, "external/repo")


def test_untrusted_public_issue_cannot_fake_dedup(repo):
    observed = []
    def runner(args, **kwargs):
        observed.append(args)
        if args[2] == "list":
            import json
            return SimpleNamespace(stdout=json.dumps([
                {"body": "<!-- aios-autonomy-chapter:12 -->", "author": {"login": "someone-else"}}]))
        return SimpleNamespace(stdout="created")
    result = backlog.update_issues(repo, "haji84/-AI", runner=runner)
    assert result == {"created": 2, "existing": 0, "paused": False}


def test_owner_pause_marker_suppresses_issue_creation(repo):
    def runner(args, **kwargs):
        if args[2] == "list":
            import json
            return SimpleNamespace(stdout=json.dumps([{
                "body": "<!-- aios-autonomy-pause -->",
                "author": {"login": "haji84"}, "state": "OPEN"}]))
        raise AssertionError("must not create issues during owner pause")
    assert backlog.update_issues(repo, "haji84/-AI", runner=runner)["paused"] is True


def test_outsider_pause_marker_does_not_stop_controller(repo):
    created = []
    def runner(args, **kwargs):
        if args[2] == "list":
            import json
            return SimpleNamespace(stdout=json.dumps([{
                "body": "<!-- aios-autonomy-pause -->",
                "author": {"login": "untrusted-user"}, "state": "OPEN"}]))
        created.append(args)
        return SimpleNamespace(stdout="created")
    assert backlog.update_issues(repo, "haji84/-AI", runner=runner)["created"] == 2
    assert len(created) == 2


def test_cli_artifact_contains_bounded_summary_only_on_success(repo, tmp_path):
    import json
    output = tmp_path / "autonomy-backlog.json"
    assert backlog.main(["--repo", str(repo), "--output", str(output)]) == 0
    assert json.loads(output.read_text(encoding="utf-8")) == {
        "mode": "read_only", "candidates": [12, 21]}
    rejected = tmp_path / "failed.json"
    assert backlog.main(["--repo", str(tmp_path / "not-a-repo"),
                         "--output", str(rejected)]) == 2
    assert not rejected.exists()


def test_empty_backlog_still_reports_owner_pause(repo):
    import json
    ledger = repo / "docs/completion/CURRENT_COMPLETION_LEDGER.md"
    ledger.write_text(ledger.read_text().replace(
        "| 12 | Chapter | Partial |", "| 12 | Chapter | Completed |").replace(
        "| 21 | Chapter | Partial |", "| 21 | Chapter | Completed |"))
    calls = []
    def paused_runner(args, **kwargs):
        calls.append(args)
        assert args[2] == "list"
        return SimpleNamespace(stdout=json.dumps([{
            "body": "<!-- aios-autonomy-pause -->",
            "author": {"login": "haji84"}, "state": "OPEN"}]))
    assert backlog.update_issues(repo, "haji84/-AI", runner=paused_runner) == {
        "created": 0, "existing": 0, "paused": True}
    assert len(calls) == 1


def test_empty_backlog_reports_not_paused(repo):
    ledger = repo / "docs/completion/CURRENT_COMPLETION_LEDGER.md"
    ledger.write_text(ledger.read_text().replace(
        "| 12 | Chapter | Partial |", "| 12 | Chapter | Completed |").replace(
        "| 21 | Chapter | Partial |", "| 21 | Chapter | Completed |"))
    calls = []
    def runner(args, **kwargs):
        calls.append(args)
        assert args[2] == "list"
        return SimpleNamespace(stdout="[]")
    assert backlog.update_issues(repo, "haji84/-AI", runner=runner) == {
        "created": 0, "existing": 0, "paused": False}
    assert len(calls) == 1
