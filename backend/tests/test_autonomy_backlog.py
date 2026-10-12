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
    assert first == {"created": 2, "existing": 0}
    bodies = [a[-1] for a in observed if a[2] == "create"]
    observed.clear()
    def existing_runner(args, **kwargs):
        observed.append(args)
        if args[2] == "list":
            import json
            return SimpleNamespace(stdout=json.dumps([{"body": b} for b in bodies]))
        raise AssertionError("unexpected duplicate Issue creation")
    second = backlog.update_issues(repo, "haji84/-AI", runner=existing_runner)
    assert second == {"created": 0, "existing": 2}


def test_reject_unapproved_repository(repo):
    with pytest.raises(backlog.SafeStop):
        backlog.update_issues(repo, "external/repo")
