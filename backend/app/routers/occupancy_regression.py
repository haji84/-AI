from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from ..audit import write_audit
from ..authz import require_permission
from ..db import get_db
from ..models import (
    OccupancyClassificationTestCase,
    OccupancyClassificationTestRun,
    User,
)
from ..occupancy_regression import (
    persist_regression_run,
    regression_run_is_current,
    validate_test_case,
)
from ..schemas import (
    OccupancyRegressionCaseCreate,
    OccupancyRegressionCaseOut,
    OccupancyRegressionCaseReview,
    OccupancyRegressionCaseUpdate,
    OccupancyRegressionRunCreate,
    OccupancyRegressionRunOut,
    OccupancyRegressionRunReview,
)


router = APIRouter(
    prefix="/occupancy-regression",
    tags=["legal-rule-drafts"],
)


def _case_out(row: OccupancyClassificationTestCase) -> OccupancyRegressionCaseOut:
    return OccupancyRegressionCaseOut(
        occupancy_classification_test_case_id=row.occupancy_classification_test_case_id,
        source_xml_sha256=row.source_xml_sha256,
        name=row.name,
        input_snapshot=row.input_snapshot or {},
        expected_classification_codes=row.expected_classification_codes or [],
        notes=row.notes,
        status=row.status,
        version=row.version,
        created_at=row.created_at.isoformat(),
        reviewed_at=row.reviewed_at.isoformat() if row.reviewed_at else None,
    )


def _run_out(row: OccupancyClassificationTestRun) -> OccupancyRegressionRunOut:
    return OccupancyRegressionRunOut(
        occupancy_classification_test_run_id=row.occupancy_classification_test_run_id,
        source_xml_sha256=row.source_xml_sha256,
        result_sha256=row.result_sha256,
        case_count=row.case_count,
        passed_case_count=row.passed_case_count,
        failed_case_count=row.failed_case_count,
        ambiguous_case_count=row.ambiguous_case_count,
        result_payload=row.result_payload or {},
        review_status=row.review_status,
        human_decision=row.human_decision,
        review_notes=row.review_notes,
        version=row.version,
        created_at=row.created_at.isoformat(),
        reviewed_at=row.reviewed_at.isoformat() if row.reviewed_at else None,
    )


@router.get("/cases", response_model=list[OccupancyRegressionCaseOut])
def list_cases(
    source_xml_sha256: str | None = None,
    status_filter: str | None = None,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("legal_rule.read")),
):
    stmt = select(OccupancyClassificationTestCase)
    if source_xml_sha256:
        stmt = stmt.where(
            OccupancyClassificationTestCase.source_xml_sha256 == source_xml_sha256
        )
    if status_filter:
        stmt = stmt.where(OccupancyClassificationTestCase.status == status_filter)
    rows = db.scalars(
        stmt.order_by(
            OccupancyClassificationTestCase.source_xml_sha256,
            OccupancyClassificationTestCase.name,
            OccupancyClassificationTestCase.created_at,
        )
    ).all()
    return [_case_out(x) for x in rows]


@router.post("/cases", response_model=OccupancyRegressionCaseOut, status_code=201)
def create_case(
    payload: OccupancyRegressionCaseCreate,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("legal_rule.manage")),
):
    row = OccupancyClassificationTestCase(
        source_xml_sha256=payload.source_xml_sha256,
        name=payload.name,
        input_snapshot=payload.input_snapshot,
        expected_classification_codes=payload.expected_classification_codes,
        notes=payload.notes,
        status="draft",
        created_by=user.user_id,
    )
    db.add(row)
    db.flush()
    write_audit(
        db,
        user_id=user.user_id,
        action="occupancy_regression.case.create",
        entity_type="occupancy_classification_test_case",
        entity_id=row.occupancy_classification_test_case_id,
        after={
            "source_xml_sha256": row.source_xml_sha256,
            "name": row.name,
            "expected_classification_codes": row.expected_classification_codes,
            "status": row.status,
        },
    )
    db.commit()
    return _case_out(row)


@router.put("/cases/{case_id}", response_model=OccupancyRegressionCaseOut)
def update_case(
    case_id: str,
    payload: OccupancyRegressionCaseUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("legal_rule.manage")),
):
    current = db.get(OccupancyClassificationTestCase, case_id)
    if not current:
        raise HTTPException(status_code=404, detail="occupancy regression case not found")
    if current.status != "draft":
        raise HTTPException(status_code=409, detail="only draft regression cases can be edited")

    result = db.execute(
        update(OccupancyClassificationTestCase)
        .where(
            OccupancyClassificationTestCase.occupancy_classification_test_case_id == case_id,
            OccupancyClassificationTestCase.version == payload.expected_version,
        )
        .values(
            name=payload.name,
            input_snapshot=payload.input_snapshot,
            expected_classification_codes=payload.expected_classification_codes,
            notes=payload.notes,
            version=payload.expected_version + 1,
            updated_at=datetime.now(timezone.utc),
        )
    )
    if result.rowcount != 1:
        db.rollback()
        raise HTTPException(status_code=409, detail="occupancy regression case was updated")
    row = db.get(OccupancyClassificationTestCase, case_id)
    write_audit(
        db,
        user_id=user.user_id,
        action="occupancy_regression.case.update",
        entity_type="occupancy_classification_test_case",
        entity_id=case_id,
        after={"version": row.version},
    )
    db.commit()
    return _case_out(row)


@router.post("/cases/{case_id}/review", response_model=OccupancyRegressionCaseOut)
def review_case(
    case_id: str,
    payload: OccupancyRegressionCaseReview,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("legal_rule.approve")),
):
    row = db.get(OccupancyClassificationTestCase, case_id)
    if not row:
        raise HTTPException(status_code=404, detail="occupancy regression case not found")
    if row.status != "draft":
        raise HTTPException(status_code=409, detail="only draft regression cases can be reviewed")
    if row.version != payload.expected_version:
        raise HTTPException(status_code=409, detail="occupancy regression case was updated")

    if payload.status == "reviewed":
        try:
            validate_test_case(
                db,
                source_xml_sha256=row.source_xml_sha256,
                input_snapshot=row.input_snapshot or {},
                expected_classification_codes=row.expected_classification_codes or [],
            )
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc))

    row.status = payload.status
    row.reviewed_by = user.user_id
    row.reviewed_at = datetime.now(timezone.utc)
    row.updated_at = datetime.now(timezone.utc)
    row.version += 1
    write_audit(
        db,
        user_id=user.user_id,
        action=f"occupancy_regression.case.{payload.status}",
        entity_type="occupancy_classification_test_case",
        entity_id=case_id,
        after={"status": row.status, "version": row.version},
    )
    db.commit()
    return _case_out(row)


@router.get("/runs", response_model=list[OccupancyRegressionRunOut])
def list_runs(
    source_xml_sha256: str | None = None,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("legal_rule.read")),
):
    stmt = select(OccupancyClassificationTestRun)
    if source_xml_sha256:
        stmt = stmt.where(
            OccupancyClassificationTestRun.source_xml_sha256 == source_xml_sha256
        )
    rows = db.scalars(
        stmt.order_by(OccupancyClassificationTestRun.created_at.desc())
    ).all()
    return [_run_out(x) for x in rows]


@router.post("/runs", response_model=OccupancyRegressionRunOut, status_code=201)
def create_run(
    payload: OccupancyRegressionRunCreate,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("legal_rule.manage")),
):
    row = persist_regression_run(
        db,
        source_xml_sha256=payload.source_xml_sha256,
        created_by=user.user_id,
    )
    write_audit(
        db,
        user_id=user.user_id,
        action="occupancy_regression.run.create",
        entity_type="occupancy_classification_test_run",
        entity_id=row.occupancy_classification_test_run_id,
        after={
            "source_xml_sha256": row.source_xml_sha256,
            "result_sha256": row.result_sha256,
            "case_count": row.case_count,
            "passed_case_count": row.passed_case_count,
            "failed_case_count": row.failed_case_count,
            "ambiguous_case_count": row.ambiguous_case_count,
            "overall_pass": bool((row.result_payload or {}).get("overall_pass")),
        },
    )
    db.commit()
    return _run_out(row)


@router.post("/runs/{run_id}/review", response_model=OccupancyRegressionRunOut)
def review_run(
    run_id: str,
    payload: OccupancyRegressionRunReview,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("legal_rule.approve")),
):
    row = db.get(OccupancyClassificationTestRun, run_id)
    if not row:
        raise HTTPException(status_code=404, detail="occupancy regression run not found")
    if row.review_status != "pending":
        raise HTTPException(status_code=409, detail="occupancy regression run already reviewed")
    if row.version != payload.expected_version:
        raise HTTPException(status_code=409, detail="occupancy regression run was updated")

    if payload.human_decision == "accepted_regression":
        current, reason = regression_run_is_current(db, row)
        if not current:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"regression run cannot be accepted: {reason}",
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
        action="occupancy_regression.run.review",
        entity_type="occupancy_classification_test_run",
        entity_id=run_id,
        after={
            "human_decision": row.human_decision,
            "version": row.version,
            "authoring_fingerprint": (row.result_payload or {}).get("authoring_fingerprint"),
            "test_suite_fingerprint": (row.result_payload or {}).get("test_suite_fingerprint"),
        },
    )
    db.commit()
    return _run_out(row)
