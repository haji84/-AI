"""Synthetic-only source-index completeness checks for emergency report P01.

Checks uniqueness/coverage and mandatory provisional markers only. They DO NOT
claim any input rule has been independently proofread against the original
scanned manual or approved for the current real-world reporting system.
"""
from pathlib import Path
import re

import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]
DOC_ROOT = REPO_ROOT / "docs" / "emergency"
SOURCE_TABLES = (
    ("P01_ER202_FIELD_REVIEW_20261119.md", "ER", 202),
    ("P01_CR64_SOURCE_CLASSES_20261119.md", "CR", 64),
    ("P01_EX167_HOLD_REGISTER_20261119.md", "EX", 167),
)


@pytest.mark.parametrize("name,prefix,expected", SOURCE_TABLES)
def test_each_candidate_id_has_exactly_one_audit_row(name: str, prefix: str, expected: int) -> None:
    body = (DOC_ROOT / name).read_text(encoding="utf-8")
    match = re.compile(r"^\|\s*" + re.escape(prefix) + r"-(\d{3})\s*\|", re.MULTILINE)
    ids = [int(found.group(1)) for found in match.finditer(body)]
    assert len(ids) == expected
    assert ids == list(range(1, expected + 1))


@pytest.mark.parametrize("name,_,count", SOURCE_TABLES)
def test_all_audit_tables_keep_not_approved_gate(name: str, _: str, count: int) -> None:
    text = (DOC_ROOT / name).read_text(encoding="utf-8")
    assert "未合格" in text
    assert "本番" in text
    assert count > 0


def test_p02_candidate_prep_not_mistaken_for_formal_completion() -> None:
    text = (DOC_ROOT / "P02_DUPLICATE_CANDIDATE_PREP_20261119.md").read_text(encoding="utf-8")
    assert "P02正式着手・完了ではない" in text
    assert "433本の独立有効ルールではなく" in text


def test_all_managed_exceptions_keep_review_labels() -> None:
    er = (DOC_ROOT / "P01_ER202_FIELD_REVIEW_20261119.md").read_text(encoding="utf-8")
    cr = (DOC_ROOT / "P01_CR64_SOURCE_CLASSES_20261119.md").read_text(encoding="utf-8")
    ex = (DOC_ROOT / "P01_EX167_HOLD_REGISTER_20261119.md").read_text(encoding="utf-8")
    assert re.search(r"^\| ER-016 \| N05 \|.*\| HOLD_SOURCE \|", er, re.MULTILINE)
    assert re.search(r"^\| CR-001 \| USER \|.*\| USER_OPERATION_HOLD_FIELD \|", cr, re.MULTILINE)
    assert re.search(r"^\| EX-009 \| HOLD\(N05\) \| HOLD_NO_SOURCE_OR_FIELD \|", ex, re.MULTILINE)
    assert re.search(r"^\| EX-010 \| N24 \| SOURCE_REFERENCE_CORRECTED \|", ex, re.MULTILINE)
    assert re.search(r"^\| EX-056 \| N23 \| SOURCE_REFERENCE_CORRECTED \|", ex, re.MULTILINE)
