from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json

from sqlalchemy import select
from sqlalchemy.orm import Session

from .legal_requirement_engine import match_conditions
from .models import (
    OccupancyClassificationTestCase,
    OccupancyClassificationTestRun,
)
from .occupancy_authoring_workbench import (
    EXPECTED_OCCUPANCY_CLASSIFICATION_COUNT,
    OCCUPANCY_CONDITION_FIELDS,
    build_occupancy_authoring_worklist,
    occupancy_authoring_fingerprint,
)


def _canonical_sha(value) -> str:
    raw = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def reviewed_test_cases(
    db: Session,
    *,
    source_xml_sha256: str,
) -> list[OccupancyClassificationTestCase]:
    return db.scalars(
        select(OccupancyClassificationTestCase)
        .where(
            OccupancyClassificationTestCase.source_xml_sha256 == source_xml_sha256,
            OccupancyClassificationTestCase.status == "reviewed",
        )
        .order_by(
            OccupancyClassificationTestCase.name,
            OccupancyClassificationTestCase.created_at,
        )
    ).all()


def test_suite_fingerprint(
    db: Session,
    *,
    source_xml_sha256: str,
) -> str | None:
    rows = reviewed_test_cases(db, source_xml_sha256=source_xml_sha256)
    if not rows:
        return None
    payload = [
        {
            "test_case_id": row.occupancy_classification_test_case_id,
            "version": row.version,
            "name": row.name,
            "input_snapshot": row.input_snapshot or {},
            "expected_classification_codes": row.expected_classification_codes or [],
        }
        for row in rows
    ]
    return _canonical_sha(payload)


def validate_test_case(
    db: Session,
    *,
    source_xml_sha256: str,
    input_snapshot: dict,
    expected_classification_codes: list[str],
) -> None:
    if not isinstance(input_snapshot, dict) or not input_snapshot:
        raise ValueError("input_snapshot must be a non-empty object")

    unexpected = sorted(set(input_snapshot) - OCCUPANCY_CONDITION_FIELDS)
    if unexpected:
        raise ValueError(f"unsupported test input fields: {unexpected}")

    if not isinstance(expected_classification_codes, list):
        raise ValueError("expected_classification_codes must be a list")
    normalized = [str(x).strip() for x in expected_classification_codes if str(x).strip()]
    if len(normalized) != 1 or len(set(normalized)) != 1:
        raise ValueError(
            "exactly one expected classification code is required for a reviewed test case"
        )

    worklist = build_occupancy_authoring_worklist(
        db,
        source_xml_sha256=source_xml_sha256,
    )
    known_codes = {
        str(x["classification_code"])
        for x in worklist["items"]
        if x.get("classification_code")
    }
    if normalized[0] not in known_codes:
        raise ValueError(
            f"expected classification code is not in the selected official authoring batch: {normalized[0]}"
        )


def duplicate_condition_groups(worklist: dict) -> list[dict]:
    groups: dict[str, list[str]] = {}
    payload_by_hash: dict[str, dict] = {}
    for item in worklist.get("items", []):
        if item.get("condition_status") != "valid":
            continue
        conditions = item.get("proposed_conditions") or {}
        digest = _canonical_sha(conditions)
        groups.setdefault(digest, []).append(str(item.get("classification_code") or ""))
        payload_by_hash[digest] = conditions

    out = []
    for digest, codes in groups.items():
        clean = sorted({x for x in codes if x})
        if len(clean) <= 1:
            continue
        out.append(
            {
                "condition_sha256": digest,
                "classification_codes": clean,
                "conditions": payload_by_hash[digest],
            }
        )
    return sorted(out, key=lambda x: x["classification_codes"])


def build_regression_result(
    db: Session,
    *,
    source_xml_sha256: str,
) -> dict:
    worklist = build_occupancy_authoring_worklist(
        db,
        source_xml_sha256=source_xml_sha256,
    )
    items = worklist["items"]
    authoring_fingerprint = occupancy_authoring_fingerprint(
        db,
        source_xml_sha256=source_xml_sha256,
    )
    cases = reviewed_test_cases(
        db,
        source_xml_sha256=source_xml_sha256,
    )
    suite_fingerprint = test_suite_fingerprint(
        db,
        source_xml_sha256=source_xml_sha256,
    )

    valid_items = [
        item for item in items if item.get("condition_status") == "valid"
    ]
    invalid_items = [
        {
            "draft_id": item.get("draft_id"),
            "classification_code": item.get("classification_code"),
            "condition_status": item.get("condition_status"),
            "condition_error": item.get("condition_error"),
        }
        for item in items
        if item.get("condition_status") != "valid"
    ]
    duplicate_groups = duplicate_condition_groups(worklist)

    case_results = []
    passed = 0
    failed = 0
    ambiguous = 0

    for case in cases:
        snapshot = case.input_snapshot or {}
        expected = [str(x) for x in (case.expected_classification_codes or [])]
        matched = []

        for item in valid_items:
            matched_ok, evidence = match_conditions(
                item.get("proposed_conditions") or {},
                snapshot,
            )
            if matched_ok:
                matched.append(
                    {
                        "classification_code": item.get("classification_code"),
                        "draft_id": item.get("draft_id"),
                        "evidence": evidence,
                    }
                )

        matched_codes = sorted(
            {str(x["classification_code"]) for x in matched if x.get("classification_code")}
        )
        expected_codes = sorted(set(expected))
        missing_expected = sorted(set(expected_codes) - set(matched_codes))
        unexpected_matches = sorted(set(matched_codes) - set(expected_codes))
        is_ambiguous = len(matched_codes) > 1
        is_pass = (
            len(expected_codes) == 1
            and matched_codes == expected_codes
            and not is_ambiguous
        )

        if is_pass:
            passed += 1
        else:
            failed += 1
        if is_ambiguous:
            ambiguous += 1

        case_results.append(
            {
                "test_case_id": case.occupancy_classification_test_case_id,
                "test_case_version": case.version,
                "name": case.name,
                "input_snapshot": snapshot,
                "expected_classification_codes": expected_codes,
                "matched_classification_codes": matched_codes,
                "missing_expected": missing_expected,
                "unexpected_matches": unexpected_matches,
                "ambiguous": is_ambiguous,
                "passed": is_pass,
                "matches": matched,
            }
        )

    authoring_complete = (
        len(items) == EXPECTED_OCCUPANCY_CLASSIFICATION_COUNT
        and len(valid_items) == EXPECTED_OCCUPANCY_CLASSIFICATION_COUNT
        and not worklist["summary"].get("duplicate_classification_codes")
    )
    suite_present = len(cases) > 0
    overall_pass = (
        authoring_complete
        and suite_present
        and failed == 0
        and ambiguous == 0
        and not duplicate_groups
        and authoring_fingerprint is not None
        and suite_fingerprint is not None
    )

    blockers = []
    if len(items) != EXPECTED_OCCUPANCY_CLASSIFICATION_COUNT:
        blockers.append(
            f"authoring skeleton count {len(items)}/{EXPECTED_OCCUPANCY_CLASSIFICATION_COUNT}"
        )
    if invalid_items:
        blockers.append(
            f"invalid or blank authoring conditions {len(invalid_items)}"
        )
    if worklist["summary"].get("duplicate_classification_codes"):
        blockers.append(
            "duplicate classification codes exist in the authoring batch"
        )
    if duplicate_groups:
        blockers.append(
            f"exact duplicate condition groups map to different classifications: {len(duplicate_groups)}"
        )
    if not suite_present:
        blockers.append("no reviewed regression test cases")
    if failed:
        blockers.append(f"failed regression cases: {failed}")
    if ambiguous:
        blockers.append(f"ambiguous regression cases: {ambiguous}")

    return {
        "regression_format": "fire-ai-occupancy-regression-v1",
        "source_xml_sha256": source_xml_sha256,
        "authoring_fingerprint": authoring_fingerprint,
        "test_suite_fingerprint": suite_fingerprint,
        "expected_classification_count": EXPECTED_OCCUPANCY_CLASSIFICATION_COUNT,
        "authoring_skeleton_count": len(items),
        "valid_authoring_condition_count": len(valid_items),
        "invalid_authoring_items": invalid_items,
        "duplicate_condition_groups": duplicate_groups,
        "case_count": len(cases),
        "passed_case_count": passed,
        "failed_case_count": failed,
        "ambiguous_case_count": ambiguous,
        "overall_pass": overall_pass,
        "blockers": blockers,
        "cases": case_results,
        "policy": (
            "Regression PASS is evidence only until a Human accepts the run. "
            "Any authoring-condition or reviewed-test-case change invalidates the accepted run."
        ),
    }


def persist_regression_run(
    db: Session,
    *,
    source_xml_sha256: str,
    created_by: str | None,
) -> OccupancyClassificationTestRun:
    payload = build_regression_result(
        db,
        source_xml_sha256=source_xml_sha256,
    )
    digest = _canonical_sha(payload)
    existing = db.scalar(
        select(OccupancyClassificationTestRun).where(
            OccupancyClassificationTestRun.result_sha256 == digest
        )
    )
    if existing:
        return existing

    row = OccupancyClassificationTestRun(
        source_xml_sha256=source_xml_sha256,
        result_sha256=digest,
        case_count=int(payload["case_count"]),
        passed_case_count=int(payload["passed_case_count"]),
        failed_case_count=int(payload["failed_case_count"]),
        ambiguous_case_count=int(payload["ambiguous_case_count"]),
        result_payload=payload,
        created_by=created_by,
    )
    db.add(row)
    db.flush()
    return row


def regression_run_is_current(
    db: Session,
    run: OccupancyClassificationTestRun,
) -> tuple[bool, str | None]:
    payload = run.result_payload or {}
    if not payload.get("overall_pass"):
        return False, "regression run did not pass"

    current_authoring = occupancy_authoring_fingerprint(
        db,
        source_xml_sha256=run.source_xml_sha256,
    )
    if payload.get("authoring_fingerprint") != current_authoring:
        return False, "authoring conditions changed after this regression run"

    current_suite = test_suite_fingerprint(
        db,
        source_xml_sha256=run.source_xml_sha256,
    )
    if payload.get("test_suite_fingerprint") != current_suite:
        return False, "reviewed regression test suite changed after this regression run"

    return True, None
