from __future__ import annotations

from datetime import date
import hashlib
import json

from sqlalchemy import select
from sqlalchemy.orm import Session

from .equipment_placement_batch import equipment_placement_batch_coverage
from .equipment_placement_engine import (
    evaluate_placement_candidates,
    geometry_center,
    placement_rule_engine_fingerprint,
)
from .models import (
    EquipmentPlacementTestCase,
    EquipmentPlacementTestRun,
    EquipmentType,
)


PLACEMENT_TEST_INPUT_FIELDS = {
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

ALLOWED_EXPECTED_STATES = {
    "placement_candidate",
    "manual_placement_with_constraints",
    "approved_placement_rule_missing",
}


def _canonical_sha(value) -> str:
    raw = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def reviewed_placement_test_cases(
    db: Session,
    *,
    worklist_sha256: str,
) -> list[EquipmentPlacementTestCase]:
    return db.scalars(
        select(EquipmentPlacementTestCase)
        .where(
            EquipmentPlacementTestCase.worklist_sha256 == worklist_sha256,
            EquipmentPlacementTestCase.status == "reviewed",
        )
        .order_by(
            EquipmentPlacementTestCase.name,
            EquipmentPlacementTestCase.created_at,
        )
    ).all()


def placement_test_suite_fingerprint(
    db: Session,
    *,
    worklist_sha256: str,
) -> str | None:
    rows = reviewed_placement_test_cases(
        db,
        worklist_sha256=worklist_sha256,
    )
    if not rows:
        return None
    payload = [
        {
            "test_case_id": row.equipment_placement_test_case_id,
            "version": row.version,
            "name": row.name,
            "input_snapshot": row.input_snapshot or {},
            "rooms": row.rooms or [],
            "equipment_type_codes": row.equipment_type_codes or [],
            "expected_results": row.expected_results or [],
        }
        for row in rows
    ]
    return _canonical_sha(payload)


def _validate_room(room: dict, index: int) -> str:
    if not isinstance(room, dict):
        raise ValueError(f"rooms[{index}] must be an object")
    if str(room.get("element_type") or "") != "room":
        raise ValueError(f"rooms[{index}] element_type must be room")
    ref = str(room.get("client_ref") or "").strip()
    if not ref:
        raise ValueError(f"rooms[{index}] client_ref is required")
    if geometry_center(room.get("geometry") or {}) is None:
        raise ValueError(f"rooms[{index}] geometry is invalid")
    return ref


def validate_placement_test_case(
    db: Session,
    *,
    input_snapshot: dict,
    rooms: list[dict],
    equipment_type_codes: list[str],
    expected_results: list[dict],
) -> tuple[list[str], list[dict]]:
    if not isinstance(input_snapshot, dict) or not input_snapshot:
        raise ValueError("input_snapshot must be a non-empty object")
    unexpected = sorted(set(input_snapshot) - PLACEMENT_TEST_INPUT_FIELDS)
    if unexpected:
        raise ValueError(
            f"unsupported placement test input fields: {unexpected}"
        )
    classification_code = str(
        input_snapshot.get("classification_code") or ""
    ).strip()
    if not classification_code:
        raise ValueError("input_snapshot.classification_code is required")

    if not isinstance(rooms, list) or not rooms:
        raise ValueError("rooms must be a non-empty list")
    room_refs = []
    for index, room in enumerate(rooms):
        room_refs.append(_validate_room(room, index))
    if len(set(room_refs)) != len(room_refs):
        raise ValueError("room client_ref values must be unique")

    if not isinstance(equipment_type_codes, list) or not equipment_type_codes:
        raise ValueError("equipment_type_codes must be a non-empty list")
    codes = sorted(
        {
            str(code).strip()
            for code in equipment_type_codes
            if str(code).strip()
        }
    )
    if not codes:
        raise ValueError("equipment_type_codes must contain at least one code")
    for code in codes:
        equipment = db.scalar(
            select(EquipmentType).where(
                EquipmentType.code == code,
                EquipmentType.active.is_(True),
            )
        )
        if equipment is None:
            raise ValueError(
                f"unknown or inactive equipment_type_code: {code}"
            )

    if not isinstance(expected_results, list) or not expected_results:
        raise ValueError("expected_results must be a non-empty list")

    expected_by_code = {}
    normalized_results = []
    valid_room_refs = set(room_refs)
    for index, result in enumerate(expected_results):
        if not isinstance(result, dict):
            raise ValueError(f"expected_results[{index}] must be an object")
        code = str(result.get("equipment_type_code") or "").strip()
        if code not in codes:
            raise ValueError(
                f"expected_results[{index}] equipment code is not in equipment_type_codes: {code}"
            )
        if code in expected_by_code:
            raise ValueError(
                f"duplicate expected result for equipment_type_code: {code}"
            )

        state = str(result.get("expected_state") or "").strip()
        if state not in ALLOWED_EXPECTED_STATES:
            raise ValueError(
                f"unsupported expected_state for {code}: {state}"
            )

        refs = sorted(
            {
                str(x).strip()
                for x in (result.get("expected_room_refs") or [])
                if str(x).strip()
            }
        )
        unknown_refs = sorted(set(refs) - valid_room_refs)
        if unknown_refs:
            raise ValueError(
                f"unknown expected_room_refs for {code}: {unknown_refs}"
            )
        if state != "placement_candidate" and refs:
            raise ValueError(
                f"{code} cannot expect room markers when state is {state}"
            )

        constraints = result.get("expected_constraints")
        if constraints is None:
            constraints = []
        if not isinstance(constraints, list) or not all(
            isinstance(x, dict) for x in constraints
        ):
            raise ValueError(
                f"expected_constraints for {code} must be a list of objects"
            )

        normalized = {
            "equipment_type_code": code,
            "expected_state": state,
            "expected_room_refs": refs,
            "expected_constraints": constraints,
        }
        expected_by_code[code] = normalized
        normalized_results.append(normalized)

    if set(expected_by_code) != set(codes):
        missing = sorted(set(codes) - set(expected_by_code))
        raise ValueError(
            f"expected_results must cover every equipment_type_code; missing: {missing}"
        )

    normalized_results.sort(key=lambda x: x["equipment_type_code"])
    return codes, normalized_results


def _constraint_payloads(row: dict) -> list[dict]:
    return [
        x.get("constraints") or {}
        for x in (row.get("constraints") or [])
        if isinstance(x, dict)
    ]


def _actual_room_refs(row: dict) -> list[str]:
    return sorted(
        {
            str(x.get("room_ref"))
            for x in (row.get("markers") or [])
            if x.get("room_ref")
        }
    )


def _marker_geometry_checks(
    row: dict,
    rooms_by_ref: dict[str, dict],
) -> list[dict]:
    checks = []
    for marker in row.get("markers") or []:
        ref = str(marker.get("room_ref") or "")
        room = rooms_by_ref.get(ref)
        expected_center = (
            geometry_center(room.get("geometry") or {})
            if room else None
        )
        actual = marker.get("geometry")
        matches = bool(
            expected_center is not None
            and isinstance(actual, dict)
            and float(actual.get("x")) == float(expected_center["x"])
            and float(actual.get("y")) == float(expected_center["y"])
        )
        checks.append(
            {
                "room_ref": ref or None,
                "expected_center": expected_center,
                "actual_center": actual,
                "matches_room_center": matches,
            }
        )
    return checks


def build_placement_regression_result(
    db: Session,
    *,
    worklist_sha256: str,
    evaluation_date: date,
) -> dict:
    coverage = equipment_placement_batch_coverage(
        db,
        worklist_sha256=worklist_sha256,
        evaluation_date=evaluation_date,
    )
    authoring_complete = bool(
        coverage.get("authoring_coverage_complete")
    )
    cases = reviewed_placement_test_cases(
        db,
        worklist_sha256=worklist_sha256,
    )
    rule_fingerprint = placement_rule_engine_fingerprint(
        db,
        evaluation_date=evaluation_date,
    )
    suite_fingerprint = placement_test_suite_fingerprint(
        db,
        worklist_sha256=worklist_sha256,
    )

    case_results = []
    passed = 0
    failed = 0
    state_mismatch_cases = 0
    marker_mismatch_cases = 0
    constraint_mismatch_cases = 0

    for case in cases:
        input_snapshot = case.input_snapshot or {}
        classification_code = str(
            input_snapshot.get("classification_code") or ""
        )
        rooms = case.rooms or []
        equipment_codes = sorted(
            set(case.equipment_type_codes or [])
        )
        expected_by_code = {
            str(x.get("equipment_type_code")): x
            for x in (case.expected_results or [])
            if isinstance(x, dict)
        }
        actual_rows = evaluate_placement_candidates(
            db,
            input_snapshot=input_snapshot,
            classification_code=classification_code,
            rooms=rooms,
            equipment_type_codes=equipment_codes,
            evaluation_date=evaluation_date,
        )
        actual_by_code = {
            str(x.get("equipment_type_code")): x
            for x in actual_rows
        }
        rooms_by_ref = {
            str(room.get("client_ref")): room
            for room in rooms
            if isinstance(room, dict) and room.get("client_ref")
        }

        equipment_results = []
        case_state_mismatch = False
        case_marker_mismatch = False
        case_constraint_mismatch = False

        for code in equipment_codes:
            expected = expected_by_code.get(code) or {}
            actual = actual_by_code.get(code) or {
                "equipment_type_code": code,
                "state": None,
                "markers": [],
                "constraints": [],
            }

            expected_state = expected.get("expected_state")
            actual_state = actual.get("state")
            state_match = expected_state == actual_state
            if not state_match:
                case_state_mismatch = True

            expected_refs = sorted(
                set(expected.get("expected_room_refs") or [])
            )
            actual_refs = _actual_room_refs(actual)
            geometry_checks = _marker_geometry_checks(
                actual,
                rooms_by_ref,
            )
            geometry_ok = all(
                x["matches_room_center"] for x in geometry_checks
            )
            marker_match = (
                expected_refs == actual_refs and geometry_ok
            )
            if not marker_match:
                case_marker_mismatch = True

            expected_constraints = expected.get(
                "expected_constraints"
            ) or []
            actual_constraints = _constraint_payloads(actual)
            constraint_match = (
                sorted(
                    _canonical_sha(x)
                    for x in expected_constraints
                )
                == sorted(
                    _canonical_sha(x)
                    for x in actual_constraints
                )
            )
            if not constraint_match:
                case_constraint_mismatch = True

            equipment_results.append(
                {
                    "equipment_type_code": code,
                    "expected_state": expected_state,
                    "actual_state": actual_state,
                    "state_match": state_match,
                    "expected_room_refs": expected_refs,
                    "actual_room_refs": actual_refs,
                    "marker_match": marker_match,
                    "marker_geometry_checks": geometry_checks,
                    "expected_constraints": expected_constraints,
                    "actual_constraints": actual_constraints,
                    "constraint_match": constraint_match,
                    "actual_rule_evidence": actual.get(
                        "constraints"
                    ) or [],
                }
            )

        is_pass = not (
            case_state_mismatch
            or case_marker_mismatch
            or case_constraint_mismatch
        )
        if is_pass:
            passed += 1
        else:
            failed += 1
        if case_state_mismatch:
            state_mismatch_cases += 1
        if case_marker_mismatch:
            marker_mismatch_cases += 1
        if case_constraint_mismatch:
            constraint_mismatch_cases += 1

        case_results.append(
            {
                "test_case_id":
                    case.equipment_placement_test_case_id,
                "test_case_version": case.version,
                "name": case.name,
                "input_snapshot": input_snapshot,
                "equipment_type_codes": equipment_codes,
                "passed": is_pass,
                "state_mismatch": case_state_mismatch,
                "marker_mismatch": case_marker_mismatch,
                "constraint_mismatch":
                    case_constraint_mismatch,
                "equipment_results": equipment_results,
            }
        )

    suite_present = len(cases) > 0
    overall_pass = bool(
        authoring_complete
        and suite_present
        and failed == 0
        and rule_fingerprint
        and suite_fingerprint
    )

    blockers = []
    if not coverage.get("batch_found"):
        blockers.append(
            "equipment placement authoring batch is missing"
        )
    if not authoring_complete:
        blockers.append(
            "equipment placement authoring coverage is incomplete"
        )
    if not suite_present:
        blockers.append(
            "no reviewed equipment placement regression test cases"
        )
    if failed:
        blockers.append(
            f"failed placement regression cases: {failed}"
        )
    if state_mismatch_cases:
        blockers.append(
            f"placement state mismatch cases: {state_mismatch_cases}"
        )
    if marker_mismatch_cases:
        blockers.append(
            f"placement marker mismatch cases: {marker_mismatch_cases}"
        )
    if constraint_mismatch_cases:
        blockers.append(
            "placement constraint mismatch cases: "
            f"{constraint_mismatch_cases}"
        )

    return {
        "regression_format":
            "fire-ai-equipment-placement-regression-v1",
        "worklist_sha256": worklist_sha256,
        "evaluation_date": evaluation_date.isoformat(),
        "rule_engine_fingerprint": rule_fingerprint,
        "test_suite_fingerprint": suite_fingerprint,
        "authoring_coverage_complete": authoring_complete,
        "case_count": len(cases),
        "passed_case_count": passed,
        "failed_case_count": failed,
        "state_mismatch_case_count": state_mismatch_cases,
        "marker_mismatch_case_count": marker_mismatch_cases,
        "constraint_mismatch_case_count":
            constraint_mismatch_cases,
        "overall_pass": overall_pass,
        "blockers": blockers,
        "cases": case_results,
        "policy": (
            "Regression PASS is evidence only until Human "
            "acceptance. Any effective placement Rule or "
            "reviewed test-suite change invalidates the run."
        ),
    }


def persist_placement_regression_run(
    db: Session,
    *,
    worklist_sha256: str,
    evaluation_date: date,
    created_by: str | None,
) -> EquipmentPlacementTestRun:
    payload = build_placement_regression_result(
        db,
        worklist_sha256=worklist_sha256,
        evaluation_date=evaluation_date,
    )
    digest = _canonical_sha(payload)
    existing = db.scalar(
        select(EquipmentPlacementTestRun).where(
            EquipmentPlacementTestRun.result_sha256 == digest
        )
    )
    if existing:
        return existing

    row = EquipmentPlacementTestRun(
        worklist_sha256=worklist_sha256,
        result_sha256=digest,
        case_count=int(payload["case_count"]),
        passed_case_count=int(payload["passed_case_count"]),
        failed_case_count=int(payload["failed_case_count"]),
        state_mismatch_case_count=int(
            payload["state_mismatch_case_count"]
        ),
        marker_mismatch_case_count=int(
            payload["marker_mismatch_case_count"]
        ),
        constraint_mismatch_case_count=int(
            payload["constraint_mismatch_case_count"]
        ),
        result_payload=payload,
        created_by=created_by,
    )
    db.add(row)
    db.flush()
    return row


def placement_regression_run_is_current(
    db: Session,
    run: EquipmentPlacementTestRun,
) -> tuple[bool, str | None]:
    payload = run.result_payload or {}
    if not payload.get("overall_pass"):
        return False, "placement regression run did not pass"

    try:
        evaluation_date = date.fromisoformat(
            str(payload.get("evaluation_date") or "")
        )
    except ValueError:
        return False, (
            "placement regression run has invalid evaluation_date"
        )

    current_rule = placement_rule_engine_fingerprint(
        db,
        evaluation_date=evaluation_date,
    )
    if payload.get("rule_engine_fingerprint") != current_rule:
        return False, (
            "effective placement Rule set changed after this run"
        )

    current_suite = placement_test_suite_fingerprint(
        db,
        worklist_sha256=run.worklist_sha256,
    )
    if payload.get("test_suite_fingerprint") != current_suite:
        return False, (
            "reviewed placement regression suite changed after "
            "this run"
        )

    coverage = equipment_placement_batch_coverage(
        db,
        worklist_sha256=run.worklist_sha256,
        evaluation_date=evaluation_date,
    )
    if not coverage.get("authoring_coverage_complete"):
        return False, (
            "equipment placement authoring coverage is no longer "
            "complete"
        )

    return True, None
