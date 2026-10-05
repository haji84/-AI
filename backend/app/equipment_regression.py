from __future__ import annotations

from datetime import date
import hashlib
import json

from sqlalchemy import select
from sqlalchemy.orm import Session

from .equipment_authoring_batch import (
    equipment_requirement_batch_coverage,
    equipment_rule_engine_fingerprint,
    equipment_test_suite_fingerprint,
)
from .legal_requirement_engine import evaluate_approved_rules_for_snapshot
from .models import (
    EquipmentRequirementTestCase,
    EquipmentRequirementTestRun,
    EquipmentType,
)


EQUIPMENT_TEST_INPUT_FIELDS = {
    "classification_code",
    "structure",
    "above_ground_floors",
    "basement_floors",
    "building_area",
    "total_floor_area",
    "occupancy_total",
    "employee_total",
    "floor_count",
    "primary_use",
    "use_tags",
    "has_sleeping_use",
    "has_food_service",
    "public_access",
    "mixed_use",
    "windowless_floor_count",
}


def _canonical_sha(value) -> str:
    raw = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def reviewed_equipment_test_cases(
    db: Session,
    *,
    worklist_sha256: str,
) -> list[EquipmentRequirementTestCase]:
    return db.scalars(
        select(EquipmentRequirementTestCase)
        .where(
            EquipmentRequirementTestCase.worklist_sha256 == worklist_sha256,
            EquipmentRequirementTestCase.status == "reviewed",
        )
        .order_by(
            EquipmentRequirementTestCase.name,
            EquipmentRequirementTestCase.created_at,
        )
    ).all()


def validate_equipment_test_case(
    db: Session,
    *,
    input_snapshot: dict,
    expected_equipment_type_codes: list[str],
) -> list[str]:
    if not isinstance(input_snapshot, dict) or not input_snapshot:
        raise ValueError("input_snapshot must be a non-empty object")
    unexpected = sorted(set(input_snapshot) - EQUIPMENT_TEST_INPUT_FIELDS)
    if unexpected:
        raise ValueError(f"unsupported equipment test input fields: {unexpected}")

    if not isinstance(expected_equipment_type_codes, list):
        raise ValueError("expected_equipment_type_codes must be a list")
    normalized = sorted(
        {
            str(code).strip()
            for code in expected_equipment_type_codes
            if str(code).strip()
        }
    )
    for code in normalized:
        equipment = db.scalar(
            select(EquipmentType).where(
                EquipmentType.code == code,
                EquipmentType.active.is_(True),
            )
        )
        if equipment is None:
            raise ValueError(f"unknown or inactive equipment_type_code: {code}")
    return normalized


def build_equipment_regression_result(
    db: Session,
    *,
    worklist_sha256: str,
    evaluation_date: date,
) -> dict:
    coverage = equipment_requirement_batch_coverage(
        db,
        worklist_sha256=worklist_sha256,
        evaluation_date=evaluation_date,
    )
    authoring_complete = bool(
        coverage.get("authoring_coverage_complete")
    )
    cases = reviewed_equipment_test_cases(
        db,
        worklist_sha256=worklist_sha256,
    )
    rule_fingerprint = equipment_rule_engine_fingerprint(
        db,
        evaluation_date=evaluation_date,
    )
    suite_fingerprint = equipment_test_suite_fingerprint(
        db,
        worklist_sha256=worklist_sha256,
    )

    results = []
    passed = 0
    failed = 0
    over_count = 0
    under_count = 0

    for case in cases:
        expected = sorted(
            set(case.expected_equipment_type_codes or [])
        )
        matches = evaluate_approved_rules_for_snapshot(
            db,
            snapshot=case.input_snapshot or {},
            domain="equipment_requirement",
            evaluation_date=evaluation_date,
        )

        matched_rule_evidence = []
        actual_codes = set()
        invalid_required_outcomes = []
        for match in matches:
            outcome = match.get("outcome") or {}
            if outcome.get("decision") != "required":
                continue
            code = str(outcome.get("equipment_type_code") or "").strip()
            if not code:
                invalid_required_outcomes.append(
                    {
                        "rule_code": match.get("rule_code"),
                        "legal_rule_version_id": match.get("legal_rule_version_id"),
                    }
                )
                continue
            actual_codes.add(code)
            matched_rule_evidence.append(
                {
                    "equipment_type_code": code,
                    "rule_code": match.get("rule_code"),
                    "rule_name": match.get("rule_name"),
                    "legal_rule_version_id": match.get("legal_rule_version_id"),
                    "citations": match.get("citations") or [],
                    "evidence": match.get("evidence") or {},
                }
            )

        actual = sorted(actual_codes)
        missing = sorted(set(expected) - set(actual))
        unexpected = sorted(set(actual) - set(expected))
        under = bool(missing)
        over = bool(unexpected)
        is_pass = (
            not under
            and not over
            and not invalid_required_outcomes
        )
        if is_pass:
            passed += 1
        else:
            failed += 1
        if under:
            under_count += 1
        if over:
            over_count += 1

        results.append(
            {
                "test_case_id": case.equipment_requirement_test_case_id,
                "test_case_version": case.version,
                "name": case.name,
                "input_snapshot": case.input_snapshot or {},
                "expected_equipment_type_codes": expected,
                "actual_equipment_type_codes": actual,
                "missing_expected_equipment": missing,
                "unexpected_equipment": unexpected,
                "under_requirement": under,
                "over_requirement": over,
                "invalid_required_outcomes": invalid_required_outcomes,
                "passed": is_pass,
                "matched_rule_evidence": matched_rule_evidence,
            }
        )

    suite_present = len(cases) > 0
    overall_pass = (
        authoring_complete
        and suite_present
        and failed == 0
        and under_count == 0
        and over_count == 0
        and rule_fingerprint is not None
        and suite_fingerprint is not None
    )

    blockers = []
    if not coverage.get("batch_found"):
        blockers.append("equipment requirement authoring batch is missing")
    if not authoring_complete:
        blockers.append("equipment requirement authoring coverage is incomplete")
    if not suite_present:
        blockers.append("no reviewed equipment regression test cases")
    if failed:
        blockers.append(f"failed equipment regression cases: {failed}")
    if under_count:
        blockers.append(f"under-requirement cases: {under_count}")
    if over_count:
        blockers.append(f"over-requirement cases: {over_count}")

    return {
        "regression_format": "fire-ai-equipment-requirement-regression-v1",
        "worklist_sha256": worklist_sha256,
        "evaluation_date": evaluation_date.isoformat(),
        "rule_engine_fingerprint": rule_fingerprint,
        "test_suite_fingerprint": suite_fingerprint,
        "authoring_coverage_complete": authoring_complete,
        "case_count": len(cases),
        "passed_case_count": passed,
        "failed_case_count": failed,
        "over_requirement_case_count": over_count,
        "under_requirement_case_count": under_count,
        "overall_pass": overall_pass,
        "blockers": blockers,
        "cases": results,
        "policy": (
            "Regression PASS is evidence only until Human acceptance. "
            "Any effective equipment Rule or reviewed test-suite change invalidates the accepted run."
        ),
    }


def persist_equipment_regression_run(
    db: Session,
    *,
    worklist_sha256: str,
    evaluation_date: date,
    created_by: str | None,
) -> EquipmentRequirementTestRun:
    payload = build_equipment_regression_result(
        db,
        worklist_sha256=worklist_sha256,
        evaluation_date=evaluation_date,
    )
    digest = _canonical_sha(payload)
    existing = db.scalar(
        select(EquipmentRequirementTestRun).where(
            EquipmentRequirementTestRun.result_sha256 == digest
        )
    )
    if existing:
        return existing

    row = EquipmentRequirementTestRun(
        worklist_sha256=worklist_sha256,
        result_sha256=digest,
        case_count=int(payload["case_count"]),
        passed_case_count=int(payload["passed_case_count"]),
        failed_case_count=int(payload["failed_case_count"]),
        over_requirement_case_count=int(
            payload["over_requirement_case_count"]
        ),
        under_requirement_case_count=int(
            payload["under_requirement_case_count"]
        ),
        result_payload=payload,
        created_by=created_by,
    )
    db.add(row)
    db.flush()
    return row


def equipment_regression_run_is_current(
    db: Session,
    run: EquipmentRequirementTestRun,
) -> tuple[bool, str | None]:
    payload = run.result_payload or {}
    if not payload.get("overall_pass"):
        return False, "equipment regression run did not pass"

    try:
        evaluation_date = date.fromisoformat(
            str(payload.get("evaluation_date") or "")
        )
    except ValueError:
        return False, "equipment regression run has invalid evaluation_date"

    current_rule = equipment_rule_engine_fingerprint(
        db,
        evaluation_date=evaluation_date,
    )
    if payload.get("rule_engine_fingerprint") != current_rule:
        return False, "effective equipment Rule set changed after this run"

    current_suite = equipment_test_suite_fingerprint(
        db,
        worklist_sha256=run.worklist_sha256,
    )
    if payload.get("test_suite_fingerprint") != current_suite:
        return False, "reviewed equipment regression suite changed after this run"

    coverage = equipment_requirement_batch_coverage(
        db,
        worklist_sha256=run.worklist_sha256,
        evaluation_date=evaluation_date,
    )
    if not coverage.get("authoring_coverage_complete"):
        return False, "equipment authoring coverage is no longer complete"

    return True, None
