from __future__ import annotations

from datetime import date, datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from ..audit import write_audit
from ..authz import require_permission
from ..db import get_db
from ..models import Facility, Inspection, InspectionFinding, User
from ..schemas import (
    InspectionCreate,
    InspectionFindingCreate,
    InspectionFindingOut,
    InspectionFindingPatch,
    InspectionOut,
    InspectionPatch,
)

router = APIRouter(tags=["inspections"])


def _date(value: str | None) -> date | None:
    if value in (None, ""):
        return None
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=f"invalid date: {value}") from exc


def _finding_out(row: InspectionFinding) -> InspectionFindingOut:
    return InspectionFindingOut(
        finding_id=row.finding_id,
        inspection_id=row.inspection_id,
        category=row.category,
        finding_text=row.finding_text,
        severity=row.severity,
        corrective_status=row.corrective_status,
        due_date=row.due_date.isoformat() if row.due_date else None,
        completed_at=row.completed_at.isoformat() if row.completed_at else None,
        notes=row.notes,
        version=row.version,
    )


def _inspection_out(db: Session, row: Inspection) -> InspectionOut:
    findings = db.scalars(
        select(InspectionFinding)
        .where(InspectionFinding.inspection_id == row.inspection_id)
        .order_by(InspectionFinding.created_at, InspectionFinding.finding_id)
    ).all()
    return InspectionOut(
        inspection_id=row.inspection_id,
        building_id=row.building_id,
        inspected_at=row.inspected_at.isoformat(),
        inspection_type=row.inspection_type,
        status=row.status,
        notes=row.notes,
        version=row.version,
        findings=[_finding_out(x) for x in findings],
    )


@router.get("/facilities/{building_id}/inspections", response_model=list[InspectionOut])
def list_facility_inspections(
    building_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("inspection.read")),
):
    if not db.get(Facility, building_id):
        raise HTTPException(status_code=404, detail="facility not found")
    rows = db.scalars(
        select(Inspection)
        .where(Inspection.building_id == building_id)
        .order_by(Inspection.inspected_at.desc(), Inspection.created_at.desc())
    ).all()
    return [_inspection_out(db, x) for x in rows]


@router.get("/inspections", response_model=list[InspectionOut])
def list_inspections(
    building_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("inspection.read")),
):
    if not db.get(Facility, building_id):
        raise HTTPException(status_code=404, detail="facility not found")
    rows = db.scalars(
        select(Inspection).where(Inspection.building_id == building_id).order_by(Inspection.inspected_at.desc(), Inspection.created_at.desc())
    ).all()
    return [_inspection_out(db, x) for x in rows]


@router.get("/inspections/{inspection_id}", response_model=InspectionOut)
def get_inspection(
    inspection_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("inspection.read")),
):
    row = db.get(Inspection, inspection_id)
    if not row:
        raise HTTPException(status_code=404, detail="inspection not found")
    return _inspection_out(db, row)


@router.post("/inspections", response_model=InspectionOut, status_code=201)
def create_inspection(
    payload: InspectionCreate,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("inspection.create")),
):
    if not db.get(Facility, payload.building_id):
        raise HTTPException(status_code=404, detail="facility not found")
    row = Inspection(
        building_id=payload.building_id,
        inspected_at=_date(payload.inspected_at),
        inspection_type=payload.inspection_type,
        status=payload.status,
        notes=payload.notes,
        created_by=user.user_id,
    )
    db.add(row)
    db.flush()
    for finding in payload.findings:
        db.add(
            InspectionFinding(
                inspection_id=row.inspection_id,
                category=finding.category,
                finding_text=finding.finding_text,
                severity=finding.severity,
                corrective_status=finding.corrective_status,
                due_date=_date(finding.due_date),
                notes=finding.notes,
            )
        )
    db.flush()
    out = _inspection_out(db, row)
    write_audit(db, user_id=user.user_id, action="inspection.create", entity_type="inspection", entity_id=row.inspection_id, after=out.model_dump(mode="json"))
    db.commit()
    return out


@router.patch("/inspections/{inspection_id}", response_model=InspectionOut)
def patch_inspection(
    inspection_id: str,
    payload: InspectionPatch,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("inspection.update")),
):
    current = db.get(Inspection, inspection_id)
    if not current:
        raise HTTPException(status_code=404, detail="inspection not found")
    before = _inspection_out(db, current).model_dump(mode="json")
    values = payload.model_dump(exclude_unset=True, exclude={"expected_version"})
    if "inspected_at" in values:
        values["inspected_at"] = _date(values["inspected_at"])
    values["version"] = payload.expected_version + 1
    values["updated_at"] = datetime.now(timezone.utc)
    result = db.execute(
        update(Inspection)
        .where(Inspection.inspection_id == inspection_id, Inspection.version == payload.expected_version)
        .values(**values)
    )
    if result.rowcount != 1:
        db.rollback()
        latest = db.get(Inspection, inspection_id)
        detail = {"message": "record was updated by another user"}
        if latest:
            detail["current"] = _inspection_out(db, latest).model_dump(mode="json")
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=detail)
    db.flush()
    latest = db.get(Inspection, inspection_id)
    out = _inspection_out(db, latest)
    write_audit(db, user_id=user.user_id, action="inspection.update", entity_type="inspection", entity_id=inspection_id, before=before, after=out.model_dump(mode="json"))
    db.commit()
    return out


@router.post("/inspections/{inspection_id}/findings", response_model=InspectionFindingOut, status_code=201)
def add_finding(
    inspection_id: str,
    payload: InspectionFindingCreate,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("inspection.update")),
):
    if not db.get(Inspection, inspection_id):
        raise HTTPException(status_code=404, detail="inspection not found")
    row = InspectionFinding(
        inspection_id=inspection_id,
        category=payload.category,
        finding_text=payload.finding_text,
        severity=payload.severity,
        corrective_status=payload.corrective_status,
        due_date=_date(payload.due_date),
        notes=payload.notes,
    )
    db.add(row)
    db.flush()
    out = _finding_out(row)
    write_audit(db, user_id=user.user_id, action="inspection.finding.create", entity_type="inspection_finding", entity_id=row.finding_id, after=out.model_dump(mode="json"))
    db.commit()
    return out


@router.patch("/inspection-findings/{finding_id}", response_model=InspectionFindingOut)
@router.patch("/inspections/findings/{finding_id}", response_model=InspectionFindingOut)
def patch_finding(
    finding_id: str,
    payload: InspectionFindingPatch,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("inspection.update")),
):
    current = db.get(InspectionFinding, finding_id)
    if not current:
        raise HTTPException(status_code=404, detail="finding not found")
    before = _finding_out(current).model_dump(mode="json")
    values = payload.model_dump(exclude_unset=True, exclude={"expected_version"})
    for key in ("due_date", "completed_at"):
        if key in values:
            values[key] = _date(values[key])
    values["version"] = payload.expected_version + 1
    values["updated_at"] = datetime.now(timezone.utc)
    result = db.execute(
        update(InspectionFinding)
        .where(InspectionFinding.finding_id == finding_id, InspectionFinding.version == payload.expected_version)
        .values(**values)
    )
    if result.rowcount != 1:
        db.rollback()
        latest = db.get(InspectionFinding, finding_id)
        detail = {"message": "record was updated by another user"}
        if latest:
            detail["current"] = _finding_out(latest).model_dump(mode="json")
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=detail)
    latest = db.get(InspectionFinding, finding_id)
    out = _finding_out(latest)
    write_audit(db, user_id=user.user_id, action="inspection.finding.update", entity_type="inspection_finding", entity_id=finding_id, before=before, after=out.model_dump(mode="json"))
    db.commit()
    return out