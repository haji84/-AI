from __future__ import annotations

from datetime import date, datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from ..audit import write_audit
from ..authz import require_permission
from ..db import get_db
from ..equipment_authoring_batch import equipment_requirement_batch_coverage
from ..equipment_regression import (
    equipment_regression_run_is_current,
    persist_equipment_regression_run,
    validate_equipment_test_case,
)
from ..models import (
    EquipmentRequirementTestCase,
    EquipmentRequirementTestRun,
    User,
)
from ..schemas import (
    EquipmentRegressionCaseCreate,
    EquipmentRegressionCaseOut,
    EquipmentRegressionCaseReview,
    EquipmentRegressionCaseUpdate,
    EquipmentRegressionRunCreate,
    EquipmentRegressionRunOut,
    EquipmentRegressionRunReview,
)


router = APIRouter(
    prefix="/equipment-regression",
    tags=["legal-review-queue"],
)


def _case_out(row: EquipmentRequirementTestCase) -> EquipmentRegressionCaseOut:
    return EquipmentRegressionCaseOut(
        equipment_requirement_test_case_id=row.equipment_requirement_test_case_id,
        worklist_sha256=row.worklist_sha256,
        name=row.name,
        input_snapshot=row.input_snapshot or {},
        expected_equipment_type_codes=row.expected_equipment_type_codes or [],
        notes=row.notes,
        status=row.status,
        version=row.version,
        created_at=row.created_at.isoformat(),
        reviewed_at=row.reviewed_at.isoformat() if row.reviewed_at else None,
    )


def _run_out(row: EquipmentRequirementTestRun) -> EquipmentRegressionRunOut:
    return EquipmentRegressionRunOut(
        equipment_requirement_test_run_id=row.equipment_requirement_test_run_id,
        worklist_sha256=row.worklist_sha256,
        result_sha256=row.result_sha256,
        case_count=row.case_count,
        passed_case_count=row.passed_case_count,
        failed_case_count=row.failed_case_count,
        over_requirement_case_count=row.over_requirement_case_count,
        under_requirement_case_count=row.under_requirement_case_count,
        result_payload=row.result_payload or {},
        review_status=row.review_status,
        human_decision=row.human_decision,
        review_notes=row.review_notes,
        version=row.version,
        created_at=row.created_at.isoformat(),
        reviewed_at=row.reviewed_at.isoformat() if row.reviewed_at else None,
    )


def _parse_date(value: str | None) -> date:
    if not value:
        return date.today()
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail="invalid evaluation_date") from exc


@router.get("/cases", response_model=list[EquipmentRegressionCaseOut])
def list_cases(
    worklist_sha256: str | None = None,
    status_filter: str | None = None,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("legal_rule.read")),
):
    stmt = select(EquipmentRequirementTestCase)
    if worklist_sha256:
        stmt = stmt.where(
            EquipmentRequirementTestCase.worklist_sha256 == worklist_sha256
        )
    if status_filter:
        stmt = stmt.where(EquipmentRequirementTestCase.status == status_filter)
    rows = db.scalars(
        stmt.order_by(
            EquipmentRequirementTestCase.worklist_sha256,
            EquipmentRequirementTestCase.name,
            EquipmentRequirementTestCase.created_at,
        )
    ).all()
    return [_case_out(x) for x in rows]


@router.post("/cases", response_model=EquipmentRegressionCaseOut, status_code=201)
def create_case(
    payload: EquipmentRegressionCaseCreate,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("legal_rule.manage")),
):
    coverage = equipment_requirement_batch_coverage(
        db,
        worklist_sha256=payload.worklist_sha256,
    )
    if not coverage.get("batch_found"):
        raise HTTPException(
            status_code=422,
            detail="equipment authoring batch not found for worklist_sha256",
        )

    row = EquipmentRequirementTestCase(
        worklist_sha256=payload.worklist_sha256,
        name=payload.name,
        input_snapshot=payload.input_snapshot,
        expected_equipment_type_codes=payload.expected_equipment_type_codes,
        notes=payload.notes,
        status="draft",
        created_by=user.user_id,
    )
    db.add(row)
    db.flush()
    write_audit(
        db,
        user_id=user.user_id,
        action="equipment_regression.case.create",
        entity_type="equipment_requirement_test_case",
        entity_id=row.equipment_requirement_test_case_id,
        after={
            "worklist_sha256": row.worklist_sha256,
            "name": row.name,
            "expected_equipment_type_codes": row.expected_equipment_type_codes,
            "status": row.status,
        },
    )
    db.commit()
    return _case_out(row)


@router.put("/cases/{case_id}", response_model=EquipmentRegressionCaseOut)
def update_case(
    case_id: str,
    payload: EquipmentRegressionCaseUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("legal_rule.manage")),
):
    current = db.get(EquipmentRequirementTestCase, case_id)
    if not current:
        raise HTTPException(status_code=404, detail="equipment regression case not found")
    if current.status != "draft":
        raise HTTPException(status_code=409, detail="only draft equipment regression cases can be edited")

    result = db.execute(
        update(EquipmentRequirementTestCase)
        .where(
            EquipmentRequirementTestCase.equipment_requirement_test_case_id == case_id,
            EquipmentRequirementTestCase.version == payload.expected_version,
        )
        .values(
            name=payload.name,
            input_snapshot=payload.input_snapshot,
            expected_equipment_type_codes=payload.expected_equipment_type_codes,
            notes=payload.notes,
            version=payload.expected_version + 1,
            updated_at=datetime.now(timezone.utc),
        )
    )
    if result.rowcount != 1:
        db.rollback()
        raise HTTPException(status_code=409, detail="equipment regression case was updated")

    row = db.get(EquipmentRequirementTestCase, case_id)
    write_audit(
        db,
        user_id=user.user_id,
        action="equipment_regression.case.update",
        entity_type="equipment_requirement_test_case",
        entity_id=case_id,
        after={"version": row.version},
    )
    db.commit()
    return _case_out(row)


@router.post("/cases/{case_id}/review", response_model=EquipmentRegressionCaseOut)
def review_case(
    case_id: str,
    payload: EquipmentRegressionCaseReview,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("legal_rule.approve")),
):
    row = db.get(EquipmentRequirementTestCase, case_id)
    if not row:
        raise HTTPException(status_code=404, detail="equipment regression case not found")
    if row.status != "draft":
        raise HTTPException(status_code=409, detail="only draft equipment regression cases can be reviewed")
    if row.version != payload.expected_version:
        raise HTTPException(status_code=409, detail="equipment regression case was updated")

    if payload.status == "reviewed":
        coverage = equipment_requirement_batch_coverage(
            db,
            worklist_sha256=row.worklist_sha256,
        )
        if not coverage.get("batch_found"):
            raise HTTPException(status_code=409, detail="equipment authoring batch is missing")
        try:
            normalized = validate_equipment_test_case(
                db,
                input_snapshot=row.input_snapshot or {},
                expected_equipment_type_codes=row.expected_equipment_type_codes or [],
            )
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc))
        row.expected_equipment_type_codes = normalized

    row.status = payload.status
    row.reviewed_by = user.user_id
    row.reviewed_at = datetime.now(timezone.utc)
    row.updated_at = datetime.now(timezone.utc)
    row.version += 1
    write_audit(
        db,
        user_id=user.user_id,
        action=f"equipment_regression.case.{payload.status}",
        entity_type="equipment_requirement_test_case",
        entity_id=case_id,
        after={"status": row.status, "version": row.version},
    )
    db.commit()
    return _case_out(row)


@router.get("/runs", response_model=list[EquipmentRegressionRunOut])
def list_runs(
    worklist_sha256: str | None = None,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("legal_rule.read")),
):
    stmt = select(EquipmentRequirementTestRun)
    if worklist_sha256:
        stmt = stmt.where(
            EquipmentRequirementTestRun.worklist_sha256 == worklist_sha256
        )
    rows = db.scalars(
        stmt.order_by(EquipmentRequirementTestRun.created_at.desc())
    ).all()
    return [_run_out(x) for x in rows]


@router.post("/runs", response_model=EquipmentRegressionRunOut, status_code=201)
def create_run(
    payload: EquipmentRegressionRunCreate,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("legal_rule.manage")),
):
    day = _parse_date(payload.evaluation_date)
    coverage = equipment_requirement_batch_coverage(
        db,
        worklist_sha256=payload.worklist_sha256,
        evaluation_date=day,
    )
    if not coverage.get("batch_found"):
        raise HTTPException(status_code=422, detail="equipment authoring batch not found")

    row = persist_equipment_regression_run(
        db,
        worklist_sha256=payload.worklist_sha256,
        evaluation_date=day,
        created_by=user.user_id,
    )
    write_audit(
        db,
        user_id=user.user_id,
        action="equipment_regression.run.create",
        entity_type="equipment_requirement_test_run",
        entity_id=row.equipment_requirement_test_run_id,
        after={
            "worklist_sha256": row.worklist_sha256,
            "result_sha256": row.result_sha256,
            "case_count": row.case_count,
            "passed_case_count": row.passed_case_count,
            "failed_case_count": row.failed_case_count,
            "over_requirement_case_count": row.over_requirement_case_count,
            "under_requirement_case_count": row.under_requirement_case_count,
            "overall_pass": bool((row.result_payload or {}).get("overall_pass")),
        },
    )
    db.commit()
    return _run_out(row)


@router.post("/runs/{run_id}/review", response_model=EquipmentRegressionRunOut)
def review_run(
    run_id: str,
    payload: EquipmentRegressionRunReview,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("legal_rule.approve")),
):
    row = db.get(EquipmentRequirementTestRun, run_id)
    if not row:
        raise HTTPException(status_code=404, detail="equipment regression run not found")
    if row.review_status != "pending":
        raise HTTPException(status_code=409, detail="equipment regression run already reviewed")
    if row.version != payload.expected_version:
        raise HTTPException(status_code=409, detail="equipment regression run was updated")

    if payload.human_decision == "accepted_regression":
        current, reason = equipment_regression_run_is_current(db, row)
        if not current:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"equipment regression run cannot be accepted: {reason}",
            )

    row.review_status = "reviewed"
    row.human_decision = payload.human_decision
    row.review_notes = payload.review_notes
    row.reviewed_by = user.user_id
    row.reviewed_at = datetime.now(timezone.utc)
    row.updated_at = datetime.now(timezone.utc)
    row.version += 1
    write_audit(
        db,
        user_id=user.user_id,
        action="equipment_regression.run.review",
        entity_type="equipment_requirement_test_run",
        entity_id=run_id,
        after={
            "human_decision": row.human_decision,
            "version": row.version,
            "rule_engine_fingerprint":
                (row.result_payload or {}).get("rule_engine_fingerprint"),
            "test_suite_fingerprint":
                (row.result_payload or {}).get("test_suite_fingerprint"),
        },
    )
    db.commit()
    return _run_out(row)
