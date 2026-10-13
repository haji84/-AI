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
    assert all("Do not use production data" in x["body"] for x in result)


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
    assert first == {"created": 2, "existing": 0}
    bodies = [a[-1] for a in observed if a[2] == "create"]
    observed.clear()
    def existing_runner(args, **kwargs):
        observed.append(args)
        if args[2] == "list":
            import json
            return SimpleNamespace(stdout=json.dumps([{"body": b, "author": {"login": "github-actions[bot]"}} for b in bodies]))
        raise AssertionError("unexpected duplicate Issue creation")
    second = backlog.update_issues(repo, "haji84/-AI", runner=existing_runner)
    assert second == {"created": 0, "existing": 2}


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
    assert result == {"created": 2, "existing": 0}


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


def test_closed_evidence_issue_allows_next_priority_chapter(repo):
    existing = backlog.proposals(repo)[:2]
    path = repo / "docs/completion/CURRENT_COMPLETION_LEDGER.md"
    path.write_text(path.read_text().replace(
        "| 13 | Chapter | Completed |", "| 13 | Chapter | Partial |"))
    rows = [
        {"body": existing[0]["body"], "author": {"login": "haji84"}, "state": "CLOSED"},
        {"body": existing[1]["body"], "author": {"login": "github-actions[bot]"}, "state": "OPEN"},
    ]
    calls = []
    def runner(args, **kwargs):
        calls.append(args)
        if args[2] == "list":
            import json
            return SimpleNamespace(stdout=json.dumps(rows))
        return SimpleNamespace(stdout="created")
    result = backlog.update_issues(repo, "haji84/-AI", runner=runner)
    assert result == {"created": 1, "existing": 2}
    assert len([a for a in calls if a[2] == "create"]) == 1
    assert "chapter 13" in [a for a in calls if a[2] == "create"][0][-1]


def test_two_active_investigations_hold_the_capacity(repo):
    existing = backlog.proposals(repo)[:2]
    rows = [
        {"body": item["body"], "author": {"login": "github-actions[bot]"}, "state": "OPEN"}
        for item in existing
    ]
    def runner(args, **kwargs):
        if args[2] == "list":
            import json
            return SimpleNamespace(stdout=json.dumps(rows))
        raise AssertionError("capacity must block issue creation")
    assert backlog.update_issues(repo, "haji84/-AI", runner=runner) == {
        "created": 0, "existing": 2}


def test_changed_gap_can_be_investigated_after_old_issue_closes(repo):
    before = backlog.proposals(repo)
    path = repo / "docs/completion/CURRENT_COMPLETION_LEDGER.md"
    contents = path.read_text().replace(
        "| 12 | Chapter | Partial | evidence |",
        "| 12 | Chapter | Partial | evidence | Newly confirmed gap.")
    path.write_text(contents)
    after = backlog.proposals(repo)
    assert after[0]["gap_marker"] != before[0]["gap_marker"]
    previous = [
        {"body": before[0]["body"], "author": {"login": "haji84"}, "state": "CLOSED"},
        {"body": before[1]["body"], "author": {"login": "github-actions[bot]"}, "state": "OPEN"},
    ]
    created = []
    def runner(args, **kwargs):
        if args[2] == "list":
            import json
            return SimpleNamespace(stdout=json.dumps(previous))
        created.append(args)
        return SimpleNamespace(stdout="created")
    assert backlog.update_issues(repo, "haji84/-AI", runner=runner)["created"] == 1
    assert len(created) == 1
    assert after[0]["gap_marker"] in created[0][-1]


def test_expanded_recovery_chapter_is_not_skipped(repo):
    path = repo / "docs/completion/CURRENT_COMPLETION_LEDGER.md"
    path.write_text(path.read_text().replace(
        "| 42 | Chapter | Completed |", "| 42 | Chapter | Partial |"))
    proposals = backlog.proposals(repo)
    assert set(x["chapter"] for x in proposals) == {12, 21, 42}
    assert proposals[0]["chapter"] == 42


def test_unlisted_future_partial_chapter_uses_fallback(repo):
    path = repo / "docs/completion/CURRENT_COMPLETION_LEDGER.md"
    path.write_text(path.read_text().replace(
        "| 47 | Chapter | Completed |", "| 47 | Chapter | Partial |"))
    assert 47 in {item["chapter"] for item in backlog.proposals(repo)}
