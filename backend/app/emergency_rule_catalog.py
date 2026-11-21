"""Read-only candidate index generated from the existing first-pass ledger.

No expression, formal code mapping, quotation, approval, or rule is inferred.
Source references and summaries remain the exact cells in the source ledger.
"""
import json
from pathlib import Path
import re


PROJECT_ROOT = Path(__file__).resolve().parents[2]
CATALOG_PATH = PROJECT_ROOT / "docs/emergency/RULE_CANDIDATES.json"
LEDGERS = (
    "P01_ER001_067_DIRECT_RECHECK_20261120.md",
    "P01_ER068_087_DIRECT_RECHECK_20261120.md",
    "P01_ER088_099_DIRECT_RECHECK_20261120.md",
    "P01_ER100_126_DIRECT_RECHECK_20261120.md",
    "P01_ER127_146_DIRECT_RECHECK_20261120.md",
    "P01_ER147_186_DIRECT_RECHECK_20261120.md",
    "P01_ER187_202_DIRECT_RECHECK_20261120.md",
    "P01_CR001_064_PROVENANCE_RECHECK_20261120.md",
    "P01_EX001_067_RECHECK_20261120.md",
    "P01_EX068_125_RECHECK_20261120.md",
    "P01_EX126_167_RECHECK_20261120.md",
)
_ID_ROW = re.compile(r"^\|\s*((?:ER|CR|EX)-[0-9]{3})\s*\|")


def _flags(classification):
    flags = [flag for flag in ("HOLD_SOURCE", "HOLD_FIELD", "EXAMPLE_ONLY", "DESIGN_GUARD", "USER_OPERATION")
             if flag in classification]
    shorthand = {"H": "HOLD_SOURCE", "F": "HOLD_FIELD", "E": "EXAMPLE_ONLY"}
    if classification in shorthand:
        flags.append(shorthand[classification])
    return flags


def build_candidate_catalog() -> dict:
    candidates = []
    for filename in LEDGERS:
        relative = "docs/emergency/" + filename
        for line in (PROJECT_ROOT / relative).read_text(encoding="utf-8").splitlines():
            match = _ID_ROW.match(line)
            if not match:
                continue
            cells = [cell.strip() for cell in line.strip("|").split("|")]
            if len(cells) != 4:
                raise ValueError("Unexpected candidate ledger table structure.")
            identity = match.group(1)
            reference, classification = (cells[2], cells[1]) if identity.startswith("CR-") else (cells[1], cells[2])
            candidates.append({
                "candidate_id": identity, "source_reference": reference,
                "source_class": classification, "summary": cells[3], "ledger_path": relative,
                "flags": _flags(classification), "approval_status": "PROVISIONAL_NOT_APPROVED", "executable": False,
            })
    expected = {f"{prefix}-{number:03d}" for prefix, total in (("ER", 202), ("CR", 64), ("EX", 167))
                for number in range(1, total + 1)}
    if len(candidates) != 433 or {row["candidate_id"] for row in candidates} != expected:
        raise ValueError("Candidate ledger coverage or identity mismatch.")
    return {
        "schema_version": "emergency-rule-candidate-index-v1", "candidate_count": len(candidates),
        "first_pass_only": True, "approval_status": "PROVISIONAL_NOT_APPROVED", "executable": False,
        "candidates": candidates,
    }


def load_candidate_catalog() -> dict:
    stored = json.loads(CATALOG_PATH.read_text(encoding="utf-8"))
    # Definitions are repository-controlled; consistency failure cannot promote
    # a modified artifact into an apparently reviewed or executable catalog.
    if stored != build_candidate_catalog():
        raise ValueError("Candidate index no longer matches its ledger.")
    return stored
