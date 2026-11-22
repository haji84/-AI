"""The checked-in ledger is an index of candidates, not approved policy."""
from pathlib import Path

from app.emergency_rule_catalog import build_candidate_catalog, load_candidate_catalog


def test_generated_catalog_matches_433_existing_ledger_rows():
    catalog = load_candidate_catalog()
    assert catalog == build_candidate_catalog()
    assert catalog["candidate_count"] == 433
    rows = catalog["candidates"]
    assert len({row["candidate_id"] for row in rows}) == 433
    for prefix, total in (("ER", 202), ("CR", 64), ("EX", 167)):
        assert {row["candidate_id"] for row in rows if row["candidate_id"].startswith(prefix)} == {
            f"{prefix}-{index:03d}" for index in range(1, total + 1)}


def test_every_candidate_retains_its_exact_ledger_cells_and_cannot_execute():
    root = Path(__file__).resolve().parents[2]
    catalog = load_candidate_catalog()
    assert catalog["approval_status"] == "PROVISIONAL_NOT_APPROVED"
    assert catalog["first_pass_only"] is True
    assert catalog["executable"] is False
    for row in catalog["candidates"]:
        line = next(line for line in (root / row["ledger_path"]).read_text().splitlines()
                    if line.startswith("| " + row["candidate_id"] + " |"))
        cells = [value.strip() for value in line.strip("|").split("|")]
        reference, classification = (cells[2], cells[1]) if row["candidate_id"].startswith("CR") else (cells[1], cells[2])
        assert row["source_reference"] == reference
        assert row["source_class"] == classification
        assert row["summary"] == cells[3]
        assert row["executable"] is False and row["approval_status"] == "PROVISIONAL_NOT_APPROVED"
        assert "assertion" not in row


def test_source_holds_field_holds_and_examples_remain_flagged():
    rows = {row["candidate_id"]: row for row in load_candidate_catalog()["candidates"]}
    assert "HOLD_SOURCE" in rows["EX-009"]["flags"]
    assert "HOLD_FIELD" in rows["EX-155"]["flags"]
    assert "EXAMPLE_ONLY" in rows["CR-057"]["flags"]
    assert "DESIGN_GUARD" in rows["CR-063"]["flags"]
