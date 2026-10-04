from __future__ import annotations

from datetime import date, datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from ..audit import write_audit
from ..authz import require_permission
from ..db import get_db
from ..models import (
    Document,
    EquipmentInspectionReport,
    Facility,
    FireManagementAssignment,
    FirePlan,
    Inspection,
    InspectionFinding,
    Submission,
    SubmissionFile,
    SubmissionType,
    User,
)
from ..schemas import (
    FacilityComplianceStatusOut,
    FacilityDashboardOut,
    SubmissionCreate,
    SubmissionOut,
    SubmissionPatch,
    SubmissionTypeCreate,
    SubmissionTypeOut,
)

router = APIRouter(tags=["submissions"])


def _date(value: str | None) -> date | None:
    if value in (None, ""):
        return None
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=f"invalid date: {value}") from exc


def _type_out(row: SubmissionType) -> SubmissionTypeOut:
    return SubmissionTypeOut(
        submission_type_id=row.submission_type_id,
        code=row.code,
        name=row.name,
        category=row.category,
        active=row.active,
        requires_document=row.requires_document,
        rules=row.rules or {},
    )


def _submission_out(db: Session, row: Submission) -> SubmissionOut:
    st = db.get(SubmissionType, row.submission_type_id)
    docs = db.scalars(select(SubmissionFile.document_id).where(SubmissionFile.submission_id == row.submission_id)).all()
    return SubmissionOut(
        submission_id=row.submission_id,
        building_id=row.building_id,
        submission_type_id=row.submission_type_id,
        submission_type_code=st.code if st else "unknown",
        submission_type_name=st.name if st else "unknown",
        official_number=row.official_number,
        received_at=row.received_at.isoformat(),
        submitted_at=row.submitted_at.isoformat() if row.submitted_at else None,
        status=row.status,
        submitted_by=row.submitted_by,
        notes=row.notes,
        payload_data=row.payload_data or {},
        version=row.version,
        document_ids=list(docs),
    )


def _validate_official_number(value: str | None) -> None:
    if value not in (None, "") and not value.isdigit():
        raise HTTPException(status_code=422, detail="official_number must contain digits only")


def _link_documents(db: Session, row: Submission, document_ids: list[str], requires_document: bool) -> None:
    if requires_document and not document_ids:
        raise HTTPException(status_code=422, detail="this submission type requires an original document")
    seen: set[str] = set()
    for order, document_id in enumerate(document_ids, start=1):
        if document_id in seen:
            continue
        seen.add(document_id)
        doc = db.get(Document, document_id)
        if not doc:
            raise HTTPException(status_code=404, detail=f"document not found: {document_id}")
        if doc.building_id and doc.building_id != row.building_id:
            raise HTTPException(status_code=409, detail="document belongs to another facility")
        if not doc.building_id:
            doc.building_id = row.building_id
        db.add(SubmissionFile(submission_id=row.submission_id, document_id=document_id, file_role="original", page_order=order))


def _sync_specialized(db: Session, row: Submission, type_code: str) -> None:
    p = row.payload_data or {}
    if type_code == "equipment_inspection_report":
        item = db.scalar(select(EquipmentInspectionReport).where(EquipmentInspectionReport.submission_id == row.submission_id))
        if item is None:
            item = EquipmentInspectionReport(building_id=row.building_id, submission_id=row.submission_id)
            db.add(item)
        item.submitted_at = row.submitted_at
        item.inspection_date = _date(p.get("inspection_date"))
        item.result_summary = p.get("result_summary")
        item.next_due_at = _date(p.get("next_due_at"))
    elif type_code == "fire_manager_appointment":
        item = db.scalar(select(FireManagementAssignment).where(FireManagementAssignment.submission_id == row.submission_id))
        if item is None:
            item = FireManagementAssignment(building_id=row.building_id, submission_id=row.submission_id)
            db.add(item)
        item.manager_name = p.get("manager_name")
        item.manager_title = p.get("manager_title")
        item.appointed_at = _date(p.get("appointed_at"))
        item.status = p.get("assignment_status") or "active"
    elif type_code == "fire_plan":
        item = db.scalar(select(FirePlan).where(FirePlan.submission_id == row.submission_id))
        if item is None:
            item = FirePlan(building_id=row.building_id, submission_id=row.submission_id)
            db.add(item)
        item.submitted_at = row.submitted_at
        item.plan_version_label = p.get("plan_version_label")
        item.status = p.get("plan_status") or "submitted"


@router.get("/submission-types", response_model=list[SubmissionTypeOut])
@router.get("/submissions/types", response_model=list[SubmissionTypeOut])
def list_submission_types(
    active_only: bool = True,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("submission.read")),
):
    stmt = select(SubmissionType)
    if active_only:
        stmt = stmt.where(SubmissionType.active.is_(True))
    rows = db.scalars(stmt.order_by(SubmissionType.category, SubmissionType.name)).all()
    return [_type_out(x) for x in rows]


@router.post("/submission-types", response_model=SubmissionTypeOut, status_code=201)
def create_submission_type(
    payload: SubmissionTypeCreate,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("submission.manage")),
):
    if db.scalar(select(SubmissionType).where(SubmissionType.code == payload.code)):
        raise HTTPException(status_code=409, detail="submission type code already exists")
    row = SubmissionType(**payload.model_dump())
    db.add(row)
    db.flush()
    out = _type_out(row)
    write_audit(db, user_id=user.user_id, action="submission_type.create", entity_type="submission_type", entity_id=row.submission_type_id, after=out.model_dump(mode="json"))
    db.commit()
    return out


@router.get("/submissions", response_model=list[SubmissionOut])
def list_submissions(
    building_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("submission.read")),
):
    if not db.get(Facility, building_id):
        raise HTTPException(status_code=404, detail="facility not found")
    rows = db.scalars(select(Submission).where(Submission.building_id == building_id).order_by(Submission.received_at.desc(), Submission.created_at.desc())).all()
    return [_submission_out(db, x) for x in rows]


@router.get("/facilities/{building_id}/submissions", response_model=list[SubmissionOut])
def list_facility_submissions(
    building_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("submission.read")),
):
    if not db.get(Facility, building_id):
        raise HTTPException(status_code=404, detail="facility not found")
    rows = db.scalars(
        select(Submission)
        .where(Submission.building_id == building_id)
        .order_by(Submission.received_at.desc(), Submission.created_at.desc())
    ).all()
    return [_submission_out(db, x) for x in rows]


@router.get("/submissions/{submission_id}", response_model=SubmissionOut)
def get_submission(
    submission_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("submission.read")),
):
    row = db.get(Submission, submission_id)
    if not row:
        raise HTTPException(status_code=404, detail="submission not found")
    return _submission_out(db, row)


@router.post("/submissions", response_model=SubmissionOut, status_code=201)
def create_submission(
    payload: SubmissionCreate,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("submission.create")),
):
    facility = db.get(Facility, payload.building_id)
    if not facility:
        raise HTTPException(status_code=404, detail="facility not found")
    st = db.scalar(select(SubmissionType).where(SubmissionType.code == payload.submission_type_code, SubmissionType.active.is_(True)))
    if not st:
        raise HTTPException(status_code=404, detail="submission type not found")
    _validate_official_number(payload.official_number)
    row = Submission(
        building_id=payload.building_id,
        submission_type_id=st.submission_type_id,
        official_number=payload.official_number,
        submitted_at=_date(payload.submitted_at),
        submitted_by=payload.submitted_by,
        notes=payload.notes,
        payload_data=payload.payload_data,
        status="received",
        created_by=user.user_id,
    )
    db.add(row)
    db.flush()
    _link_documents(db, row, payload.document_ids, st.requires_document)
    _sync_specialized(db, row, st.code)
    db.flush()
    out = _submission_out(db, row)
    write_audit(db, user_id=user.user_id, action="submission.create", entity_type="submission", entity_id=row.submission_id, after=out.model_dump(mode="json"))
    db.commit()
    return out


@router.patch("/submissions/{submission_id}", response_model=SubmissionOut)
def patch_submission(
    submission_id: str,
    payload: SubmissionPatch,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("submission.update")),
):
    current = db.get(Submission, submission_id)
    if not current:
        raise HTTPException(status_code=404, detail="submission not found")
    before = _submission_out(db, current).model_dump(mode="json")
    values = payload.model_dump(exclude_unset=True, exclude={"expected_version"})
    if "official_number" in values:
        _validate_official_number(values["official_number"])
    if "submitted_at" in values:
        values["submitted_at"] = _date(values["submitted_at"])
    values["version"] = payload.expected_version + 1
    values["updated_at"] = datetime.now(timezone.utc)
    result = db.execute(
        update(Submission)
        .where(Submission.submission_id == submission_id, Submission.version == payload.expected_version)
        .values(**values)
    )
    if result.rowcount != 1:
        db.rollback()
        latest = db.get(Submission, submission_id)
        detail = {"message": "record was updated by another user"}
        if latest:
            detail["current"] = _submission_out(db, latest).model_dump(mode="json")
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=detail)
    latest = db.get(Submission, submission_id)
    st = db.get(SubmissionType, latest.submission_type_id)
    _sync_specialized(db, latest, st.code if st else "")
    db.flush()
    out = _submission_out(db, latest)
    write_audit(db, user_id=user.user_id, action="submission.update", entity_type="submission", entity_id=submission_id, before=before, after=out.model_dump(mode="json"))
    db.commit()
    return out


@router.get("/facilities/{building_id}/dashboard", response_model=FacilityDashboardOut)
def facility_dashboard(
    building_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("facility.read")),
):
    if not db.get(Facility, building_id):
        raise HTTPException(status_code=404, detail="facility not found")
    inspections_total = db.scalar(select(func.count()).select_from(Inspection).where(Inspection.building_id == building_id)) or 0
    open_findings = db.scalar(
        select(func.count()).select_from(InspectionFinding)
        .join(Inspection, Inspection.inspection_id == InspectionFinding.inspection_id)
        .where(Inspection.building_id == building_id, InspectionFinding.corrective_status != "completed")
    ) or 0
    latest_inspection = db.scalar(
        select(Inspection).where(Inspection.building_id == building_id).order_by(Inspection.inspected_at.desc()).limit(1)
    )
    types = db.scalars(select(SubmissionType).where(SubmissionType.active.is_(True)).order_by(SubmissionType.name)).all()
    statuses: list[FacilityComplianceStatusOut] = []
    for st in types:
        if not (st.rules or {}).get("dashboard"):
            continue
        latest = db.scalar(
            select(Submission)
            .where(Submission.building_id == building_id, Submission.submission_type_id == st.submission_type_id)
            .order_by(Submission.received_at.desc(), Submission.created_at.desc())
            .limit(1)
        )
        if latest:
            state = latest.status
            latest_id = latest.submission_id
            latest_date = latest.submitted_at.isoformat() if latest.submitted_at else None
            detail = {"requirement_status": "not_evaluated", "submission_status": latest.status}
        else:
            state = "not_submitted"
            latest_id = None
            latest_date = None
            detail = {"requirement_status": "not_evaluated"}
        statuses.append(FacilityComplianceStatusOut(code=st.code, name=st.name, state=state, latest_submission_id=latest_id, latest_submitted_at=latest_date, detail=detail))
    return FacilityDashboardOut(
        building_id=building_id,
        inspections_total=inspections_total,
        open_findings=open_findings,
        latest_inspection_at=latest_inspection.inspected_at.isoformat() if latest_inspection else None,
        submission_statuses=statuses,
    )