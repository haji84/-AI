from __future__ import annotations

import csv
from datetime import datetime, timezone
from decimal import Decimal
from functools import lru_cache
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import delete, func, or_, select, update
from sqlalchemy.orm import Session

from ..audit import write_audit
from ..authz import require_permission
from ..db import get_db
from ..models import (
    AuditLog,
    Facility,
    FacilityContact,
    FacilityDetail,
    FacilityFloor,
    LegacyFacilitySourceRow,
    User,
)
from ..schemas import (
    FacilityContactInput,
    FacilityCreate,
    FacilityDetailInput,
    FacilityDetailOut,
    FacilityFloorOut,
    FacilityHistoryItem,
    FacilityListOut,
    FacilityOut,
    FacilityPatch,
    FacilityStateChange,
    LegacyReviewField,
)

router = APIRouter(prefix="/facilities", tags=["facilities"])


def _num(value: Decimal | None) -> float | None:
    return float(value) if value is not None else None


def as_out(f: Facility) -> FacilityOut:
    return FacilityOut(
        building_id=f.building_id,
        legacy_internal_key=f.legacy_internal_key,
        legacy_serial_no=f.legacy_serial_no,
        name=f.name,
        phone=f.phone,
        address=f.address,
        status=f.status,
        version=f.version,
    )


def _detail_input(row: FacilityDetail | None) -> FacilityDetailInput:
    if row is None:
        return FacilityDetailInput()
    return FacilityDetailInput(
        legacy_book_type=row.legacy_book_type,
        content_as_of=row.content_as_of,
        classification_code=row.classification_code,
        classification_detail_1=row.classification_detail_1,
        classification_detail_2=row.classification_detail_2,
        zoning=row.zoning,
        article8_partition=row.article8_partition,
        structure=row.structure,
        above_ground_floors=row.above_ground_floors,
        basement_floors=row.basement_floors,
        building_area=_num(row.building_area),
        total_floor_area=_num(row.total_floor_area),
        occupancy_total=row.occupancy_total,
        employee_total=row.employee_total,
    )


def _contact_input(row: FacilityContact | None) -> FacilityContactInput:
    if row is None:
        return FacilityContactInput()
    return FacilityContactInput(
        representative_name=row.representative_name,
        representative_title=row.representative_title,
        representative_address=row.representative_address,
        representative_phone=row.representative_phone,
    )


def _floor_out(row: FacilityFloor) -> FacilityFloorOut:
    return FacilityFloorOut(
        facility_floor_id=row.facility_floor_id,
        floor_number=row.floor_number,
        floor_label=row.floor_label,
        floor_area=_num(row.floor_area),
        use_name=row.use_name,
        occupancy_count=row.occupancy_count,
        employee_count=row.employee_count,
        windowless_status=row.windowless_status,
        curtain_status=row.curtain_status,
        carpet_status=row.carpet_status,
        plywood_status=row.plywood_status,
    )


def aggregate_out(db: Session, f: Facility) -> FacilityDetailOut:
    detail = db.get(FacilityDetail, f.building_id)
    contact = db.get(FacilityContact, f.building_id)
    floors = db.scalars(
        select(FacilityFloor)
        .where(FacilityFloor.building_id == f.building_id)
        .order_by(FacilityFloor.floor_number)
    ).all()
    return FacilityDetailOut(
        facility=as_out(f),
        detail=_detail_input(detail),
        contact=_contact_input(contact),
        floors=[_floor_out(x) for x in floors],
    )


def _audit_payload(value: FacilityDetailOut) -> dict:
    return value.model_dump(mode="json")


def _ensure_unique_floor_numbers(floors) -> None:
    nums = [x.floor_number for x in floors]
    if len(nums) != len(set(nums)):
        raise HTTPException(status_code=422, detail="floor_number must be unique within a facility")


def _upsert_detail(db: Session, building_id: str, payload: FacilityDetailInput | None) -> None:
    if payload is None:
        return
    row = db.get(FacilityDetail, building_id)
    if row is None:
        row = FacilityDetail(building_id=building_id)
        db.add(row)
    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(row, key, value)
    row.updated_at = datetime.now(timezone.utc)


def _upsert_contact(db: Session, building_id: str, payload: FacilityContactInput | None) -> None:
    if payload is None:
        return
    row = db.get(FacilityContact, building_id)
    if row is None:
        row = FacilityContact(building_id=building_id)
        db.add(row)
    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(row, key, value)
    row.updated_at = datetime.now(timezone.utc)


def _replace_floors(db: Session, building_id: str, floors) -> None:
    if floors is None:
        return
    _ensure_unique_floor_numbers(floors)
    db.execute(delete(FacilityFloor).where(FacilityFloor.building_id == building_id))
    for item in floors:
        db.add(FacilityFloor(building_id=building_id, **item.model_dump()))
    detail = db.get(FacilityDetail, building_id)
    if detail is None:
        detail = FacilityDetail(building_id=building_id)
        db.add(detail)
    occupancy_values = [x.occupancy_count for x in floors if x.occupancy_count is not None]
    employee_values = [x.employee_count for x in floors if x.employee_count is not None]
    detail.occupancy_total = sum(occupancy_values) if occupancy_values else None
    detail.employee_total = sum(employee_values) if employee_values else None
    detail.updated_at = datetime.now(timezone.utc)


@router.get("", response_model=FacilityListOut)
def list_facilities(
    q: str | None = None,
    status_filter: str | None = None,
    offset: int = 0,
    limit: int = 50,
    sort_by: str = "name",
    sort_dir: str = "asc",
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("facility.read")),
):
    limit = max(1, min(limit, 200))
    offset = max(offset, 0)
    stmt = select(Facility)
    count_stmt = select(func.count()).select_from(Facility)
    conditions = []
    if q:
        needle = f"%{q}%"
        conditions.append(
            or_(
                Facility.name.ilike(needle),
                Facility.address.ilike(needle),
                Facility.legacy_internal_key.ilike(needle),
                Facility.legacy_serial_no.ilike(needle),
            )
        )
    if status_filter:
        conditions.append(Facility.status == status_filter)
    if conditions:
        stmt = stmt.where(*conditions)
        count_stmt = count_stmt.where(*conditions)
    total = db.scalar(count_stmt) or 0
    sort_columns = {
        "name": Facility.name,
        "address": Facility.address,
        "legacy_serial_no": Facility.legacy_serial_no,
        "updated_at": Facility.updated_at,
    }
    order = sort_columns.get(sort_by, Facility.name)
    if sort_dir.lower() == "desc":
        order = order.desc()
    else:
        order = order.asc()
    rows = db.scalars(stmt.order_by(order, Facility.building_id).offset(offset).limit(limit)).all()
    return FacilityListOut(items=[as_out(r) for r in rows], total=total)


@router.get("/{building_id}", response_model=FacilityOut)
def get_facility(
    building_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("facility.read")),
):
    f = db.get(Facility, building_id)
    if not f:
        raise HTTPException(status_code=404, detail="facility not found")
    return as_out(f)


@router.get("/{building_id}/detail", response_model=FacilityDetailOut)
def get_facility_detail(
    building_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("facility.read")),
):
    f = db.get(Facility, building_id)
    if not f:
        raise HTTPException(status_code=404, detail="facility not found")
    return aggregate_out(db, f)


@router.post("", response_model=FacilityOut, status_code=201)
def create_facility(
    payload: FacilityCreate,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("facility.create")),
):
    _ensure_unique_floor_numbers(payload.floors)
    if payload.legacy_internal_key:
        duplicate = db.scalar(select(Facility).where(Facility.legacy_internal_key == payload.legacy_internal_key))
        if duplicate:
            raise HTTPException(status_code=409, detail="legacy_internal_key already exists")
    f = Facility(
        name=payload.name,
        phone=payload.phone,
        address=payload.address,
        legacy_internal_key=payload.legacy_internal_key,
        legacy_serial_no=payload.legacy_serial_no,
    )
    db.add(f)
    db.flush()
    _upsert_detail(db, f.building_id, payload.detail)
    _upsert_contact(db, f.building_id, payload.contact)
    db.flush()
    _replace_floors(db, f.building_id, payload.floors)
    db.flush()
    result = aggregate_out(db, f)
    write_audit(
        db,
        user_id=user.user_id,
        action="facility.create",
        entity_type="facility",
        entity_id=f.building_id,
        after=_audit_payload(result),
    )
    db.commit()
    return as_out(f)


@router.patch("/{building_id}", response_model=FacilityOut)
def patch_facility(
    building_id: str,
    payload: FacilityPatch,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("facility.update")),
):
    current = db.get(Facility, building_id)
    if not current:
        raise HTTPException(status_code=404, detail="facility not found")
    before = aggregate_out(db, current)
    base_fields = {"name", "phone", "address", "legacy_serial_no"}
    values = {
        k: v
        for k, v in payload.model_dump(exclude_unset=True, exclude={"expected_version", "detail", "contact", "floors"}).items()
        if k in base_fields
    }
    values["version"] = payload.expected_version + 1
    values["updated_at"] = datetime.now(timezone.utc)
    result = db.execute(
        update(Facility)
        .where(Facility.building_id == building_id, Facility.version == payload.expected_version)
        .values(**values)
    )
    if result.rowcount != 1:
        db.rollback()
        latest = db.get(Facility, building_id)
        detail = {"message": "record was updated by another user"}
        if latest:
            detail["current"] = _audit_payload(aggregate_out(db, latest))
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=detail)

    _upsert_detail(db, building_id, payload.detail if "detail" in payload.model_fields_set else None)
    _upsert_contact(db, building_id, payload.contact if "contact" in payload.model_fields_set else None)
    db.flush()
    _replace_floors(db, building_id, payload.floors if "floors" in payload.model_fields_set else None)
    db.flush()
    refreshed = db.get(Facility, building_id)
    after = aggregate_out(db, refreshed)
    write_audit(
        db,
        user_id=user.user_id,
        action="facility.update",
        entity_type="facility",
        entity_id=building_id,
        before=_audit_payload(before),
        after=_audit_payload(after),
    )
    db.commit()
    return as_out(refreshed)


def _change_state(
    *,
    db: Session,
    user: User,
    building_id: str,
    expected_version: int,
    new_status: str,
    action: str,
) -> FacilityOut:
    current = db.get(Facility, building_id)
    if not current:
        raise HTTPException(status_code=404, detail="facility not found")
    before = aggregate_out(db, current)
    result = db.execute(
        update(Facility)
        .where(Facility.building_id == building_id, Facility.version == expected_version)
        .values(status=new_status, version=expected_version + 1, updated_at=datetime.now(timezone.utc))
    )
    if result.rowcount != 1:
        db.rollback()
        latest = db.get(Facility, building_id)
        detail = {"message": "record was updated by another user"}
        if latest:
            detail["current"] = _audit_payload(aggregate_out(db, latest))
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=detail)
    refreshed = db.get(Facility, building_id)
    after = aggregate_out(db, refreshed)
    write_audit(
        db,
        user_id=user.user_id,
        action=action,
        entity_type="facility",
        entity_id=building_id,
        before=_audit_payload(before),
        after=_audit_payload(after),
    )
    db.commit()
    return as_out(refreshed)


@router.post("/{building_id}/abolish", response_model=FacilityOut)
def abolish_facility(
    building_id: str,
    payload: FacilityStateChange,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("facility.update")),
):
    return _change_state(
        db=db,
        user=user,
        building_id=building_id,
        expected_version=payload.expected_version,
        new_status="abolished",
        action="facility.abolish",
    )


@router.post("/{building_id}/restore", response_model=FacilityOut)
def restore_facility(
    building_id: str,
    payload: FacilityStateChange,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("facility.restore")),
):
    return _change_state(
        db=db,
        user=user,
        building_id=building_id,
        expected_version=payload.expected_version,
        new_status="active",
        action="facility.restore",
    )


@router.get("/{building_id}/history", response_model=list[FacilityHistoryItem])
def facility_history(
    building_id: str,
    limit: int = 100,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("facility.read")),
):
    if not db.get(Facility, building_id):
        raise HTTPException(status_code=404, detail="facility not found")
    rows = db.scalars(
        select(AuditLog)
        .where(AuditLog.entity_type == "facility", AuditLog.entity_id == building_id)
        .order_by(AuditLog.audit_id.desc())
        .limit(max(1, min(limit, 500)))
    ).all()
    return [
        FacilityHistoryItem(
            audit_id=x.audit_id,
            occurred_at=x.occurred_at.isoformat(),
            action=x.action,
            user_id=x.user_id,
            before_data=x.before_data,
            after_data=x.after_data,
        )
        for x in rows
    ]


@lru_cache(maxsize=1)
def _review_mapping() -> list[dict]:
    root = Path(__file__).resolve().parents[3]
    path = root / "docs" / "phase0" / "legacy_to_target_mapping.csv"
    with path.open(encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    return [x for x in rows if x.get("mapping_status") == "review"]


@router.get("/{building_id}/legacy-review", response_model=list[LegacyReviewField])
def legacy_review_fields(
    building_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("facility.read")),
):
    if not db.get(Facility, building_id):
        raise HTTPException(status_code=404, detail="facility not found")
    source = db.scalar(
        select(LegacyFacilitySourceRow)
        .where(LegacyFacilitySourceRow.building_id == building_id)
        .order_by(LegacyFacilitySourceRow.created_at.desc())
    )
    if not source:
        return []
    raw = source.raw_payload or {}
    return [
        LegacyReviewField(
            excel_col=row["excel_col"],
            legacy_header=row.get("legacy_header") or "(見出しなし)",
            value=raw.get(row["excel_col"]),
            mapping_note=row.get("mapping_note") or None,
        )
        for row in _review_mapping()
        if raw.get(row["excel_col"]) not in (None, "")
    ]