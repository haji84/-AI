"""Synthetic regression for the scheduled read-only autonomy controller."""
import importlib.util
from pathlib import Path
import subprocess

import pytest

SOURCE = Path(__file__).resolve().parents[2] / "scripts/autonomy/inventory.py"
module_spec = importlib.util.spec_from_file_location("aios_autonomy_inventory", SOURCE)
module = importlib.util.module_from_spec(module_spec)
module_spec.loader.exec_module(module)


@pytest.fixture
def repo(tmp_path):
    root = tmp_path / "repo"
    (root / "docs/completion").mkdir(parents=True)
    subprocess.run(["git", "init", "-q", str(root)], check=True)
    subprocess.run(["git", "-C", str(root), "config", "user.name", "Tester"], check=True)
    subprocess.run(["git", "-C", str(root), "config", "user.email", "tester@example.invalid"], check=True)
    (root / "docs/SPECIFICATION.md").write_text(
        "\n".join(f"## {n}. Chapter\ncontent" for n in range(1, 58)), encoding="utf-8")
    (root / "docs/completion/CURRENT_COMPLETION_LEDGER.md").write_text(
        "Audited implementation base: " + chr(96) + "a" * 40 + chr(96) + "\n" +
        "\n".join(f"| {n} | chapter | {'Partial' if n == 12 else 'Completed'} | evidence |"
                  for n in range(1, 58)), encoding="utf-8")
    subprocess.run(["git", "-C", str(root), "add", "."], check=True)
    subprocess.run(["git", "-C", str(root), "commit", "-qm", "initial"], check=True)
    return root


def test_records_full_inventory(repo):
    result = module.inventory(repo)
    assert result["total"] == 57
    assert result["counts"]["Completed"] == 56
    assert result["next_candidates"] == [12]
    assert result["mode"] == "read_only"


def test_missing_chapter_rejected(repo):
    path = repo / "docs/completion/CURRENT_COMPLETION_LEDGER.md"
    path.write_text(path.read_text().replace("| 12 | chapter | Partial | evidence |", ""))
    with pytest.raises(module.InventoryError, match="ledger"):
        module.inventory(repo)


def test_duplicate_chapter_rejected(repo):
    path = repo / "docs/completion/CURRENT_COMPLETION_LEDGER.md"
    path.write_text(path.read_text() + "\n| 12 | chapter | Partial | evidence |\n")
    with pytest.raises(module.InventoryError, match="ledger"):
        module.inventory(repo)


def test_missing_spec_chapter_rejected(repo):
    path = repo / "docs/SPECIFICATION.md"
    path.write_text(path.read_text().replace("## 49. Chapter", "## missing"))
    with pytest.raises(module.InventoryError, match="specification"):
        module.inventory(repo)
