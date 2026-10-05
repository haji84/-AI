from __future__ import annotations

from datetime import date, datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from ..audit import write_audit
from ..authz import require_permission
from ..db import get_db
from ..legal_requirement_engine import evaluate_approved_requirement_rules
from ..models import (
    Document,
    EquipmentType,
    Facility,
    FacilityEquipment,
    RequirementEvaluation,
    Submission,
    User,
)
from ..schemas import (
    EquipmentRequirementComparisonItemOut,
    EquipmentTypeCreate,
    EquipmentTypeOut,
    FacilityEquipmentCreate,
    FacilityEquipmentOut,
    FacilityEquipmentPatch,
    FacilityEquipmentRequirementComplianceOut,
)

router = APIRouter(tags=["equipment"])


def _date(value: str | None) -> date | None:
    if value in (None, ""):
        return None
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=f"invalid date: {value}") from exc


def _type_out(row: EquipmentType) -> EquipmentTypeOut:
    return EquipmentTypeOut(
        equipment_type_id=row.equipment_type_id,
        code=row.code,
        name=row.name,
        category=row.category,
        active=row.active,
        metadata=row.equipment_metadata or {},
    )


def _equipment_out(db: Session, row: FacilityEquipment) -> FacilityEquipmentOut:
    et = db.get(EquipmentType, row.equipment_type_id)
    return FacilityEquipmentOut(
        facility_equipment_id=row.facility_equipment_id,
        building_id=row.building_id,
        equipment_type_id=row.equipment_type_id,
        equipment_type_code=et.code if et else "unknown",
        equipment_type_name=et.name if et else "unknown",
        floor_number=row.floor_number,
        location_text=row.location_text,
        quantity=row.quantity,
        operational_status=row.operational_status,
        verification_status=row.verification_status,
        source_kind=row.source_kind,
        source_document_id=row.source_document_id,
        submission_id=row.submission_id,
        installed_at=row.installed_at.isoformat() if row.installed_at else None,
        last_verified_at=row.last_verified_at.isoformat() if row.last_verified_at else None,
        notes=row.notes,
        version=row.version,
    )


def _validate_refs(
    db: Session,
    *,
    building_id: str,
    source_document_id: str | None,
    submission_id: str | None,
) -> None:
    if source_document_id:
        doc = db.get(Document, source_document_id)
        if not doc:
            raise HTTPException(status_code=422, detail="source_document_id not found")
        if doc.building_id and doc.building_id != building_id:
            raise HTTPException(status_code=409, detail="source document belongs to another facility")
    if submission_id:
        submission = db.get(Submission, submission_id)
        if not submission:
            raise HTTPException(status_code=422, detail="submission_id not found")
        if submission.building_id != building_id:
            raise HTTPException(status_code=409, detail="submission belongs to another facility")


@router.get("/equipment-types", response_model=list[EquipmentTypeOut])
def list_equipment_types(
    active_only: bool = True,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("equipment.read")),
):
    stmt = select(EquipmentType)
    if active_only:
        stmt = stmt.where(EquipmentType.active.is_(True))
    rows = db.scalars(stmt.order_by(EquipmentType.category, EquipmentType.name)).all()
    return [_type_out(x) for x in rows]


@router.post("/equipment-types", response_model=EquipmentTypeOut, status_code=201)
def create_equipment_type(
    payload: EquipmentTypeCreate,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("equipment.manage")),
):
    if db.scalar(select(EquipmentType).where(EquipmentType.code == payload.code)):
        raise HTTPException(status_code=409, detail="equipment type code already exists")
    row = EquipmentType(
        code=payload.code,
        name=payload.name,
        category=payload.category,
        equipment_metadata=payload.metadata,
    )
    db.add(row)
    db.flush()
    write_audit(
        db,
        user_id=user.user_id,
        action="equipment_type.create",
        entity_type="equipment_type",
        entity_id=row.equipment_type_id,
        after=_type_out(row).model_dump(mode="json"),
    )
    db.commit()
    return _type_out(row)


@router.get("/facilities/{building_id}/equipment", response_model=list[FacilityEquipmentOut])
def list_facility_equipment(
    building_id: str,
    include_removed: bool = False,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("equipment.read")),
):
    if not db.get(Facility, building_id):
        raise HTTPException(status_code=404, detail="facility not found")
    stmt = (
        select(FacilityEquipment)
        .where(FacilityEquipment.building_id == building_id)
        .order_by(FacilityEquipment.floor_number, FacilityEquipment.created_at)
    )
    if not include_removed:
        stmt = stmt.where(FacilityEquipment.operational_status != "removed")
    return [_equipment_out(db, x) for x in db.scalars(stmt).all()]


@router.post("/facilities/{building_id}/equipment", response_model=FacilityEquipmentOut, status_code=201)
def create_facility_equipment(
    building_id: str,
    payload: FacilityEquipmentCreate,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("equipment.manage")),
):
    if not db.get(Facility, building_id):
        raise HTTPException(status_code=404, detail="facility not found")
    et = db.scalar(
        select(EquipmentType).where(
            EquipmentType.code == payload.equipment_type_code,
            EquipmentType.active.is_(True),
        )
    )
    if not et:
        raise HTTPException(status_code=404, detail="equipment type not found")
    _validate_refs(
        db,
        building_id=building_id,
        source_document_id=payload.source_document_id,
        submission_id=payload.submission_id,
    )
    row = FacilityEquipment(
        building_id=building_id,
        equipment_type_id=et.equipment_type_id,
        floor_number=payload.floor_number,
        location_text=payload.location_text,
        quantity=payload.quantity,
        operational_status=payload.operational_status,
        verification_status=payload.verification_status,
        source_kind=payload.source_kind,
        source_document_id=payload.source_document_id,
        submission_id=payload.submission_id,
        installed_at=_date(payload.installed_at),
        last_verified_at=_date(payload.last_verified_at),
        notes=payload.notes,
        created_by=user.user_id,
        updated_by=user.user_id,
    )
    db.add(row)
    db.flush()
    out = _equipment_out(db, row)
    write_audit(
        db,
        user_id=user.user_id,
        action="facility_equipment.create",
        entity_type="facility_equipment",
        entity_id=row.facility_equipment_id,
        after=out.model_dump(mode="json"),
    )
    db.commit()
    return out


@router.patch("/facility-equipment/{facility_equipment_id}", response_model=FacilityEquipmentOut)
def patch_facility_equipment(
    facility_equipment_id: str,
    payload: FacilityEquipmentPatch,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("equipment.manage")),
):
    current = db.get(FacilityEquipment, facility_equipment_id)
    if not current:
        raise HTTPException(status_code=404, detail="facility equipment not found")
    before = _equipment_out(db, current).model_dump(mode="json")
    values = payload.model_dump(exclude_unset=True, exclude={"expected_version"})
    if "installed_at" in values:
        values["installed_at"] = _date(values["installed_at"])
    if "last_verified_at" in values:
        values["last_verified_at"] = _date(values["last_verified_at"])
    _validate_refs(
        db,
        building_id=current.building_id,
        source_document_id=values.get("source_document_id", current.source_document_id),
        submission_id=values.get("submission_id", current.submission_id),
    )
    values["version"] = payload.expected_version + 1
    values["updated_at"] = datetime.now(timezone.utc)
    values["updated_by"] = user.user_id
    result = db.execute(
        update(FacilityEquipment)
        .where(
            FacilityEquipment.facility_equipment_id == facility_equipment_id,
            FacilityEquipment.version == payload.expected_version,
        )
        .values(**values)
    )
    if result.rowcount != 1:
        db.rollback()
        latest = db.get(FacilityEquipment, facility_equipment_id)
        detail = {"message": "equipment record was updated by another user"}
        if latest:
            detail["current"] = _equipment_out(db, latest).model_dump(mode="json")
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=detail)
    latest = db.get(FacilityEquipment, facility_equipment_id)
    out = _equipment_out(db, latest)
    write_audit(
        db,
        user_id=user.user_id,
        action="facility_equipment.update",
        entity_type="facility_equipment",
        entity_id=facility_equipment_id,
        before=before,
        after=out.model_dump(mode="json"),
    )
    db.commit()
    return out


@router.post(
    "/facilities/{building_id}/equipment-compliance/evaluate",
    response_model=FacilityEquipmentRequirementComplianceOut,
)
def evaluate_equipment_compliance(
    building_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("equipment.read")),
):
    facility = db.get(Facility, building_id)
    if not facility:
        raise HTTPException(status_code=404, detail="facility not found")

    evaluation_date = date.today()
    snapshot, results = evaluate_approved_requirement_rules(
        db,
        facility=facility,
        domain="equipment_requirement",
        evaluation_date=evaluation_date,
    )
    evaluation = RequirementEvaluation(
        building_id=building_id,
        domain="equipment_requirement",
        evaluation_date=evaluation_date,
        facility_version=facility.version,
        input_snapshot=snapshot,
        results=results,
        status="candidate",
        created_by=user.user_id,
    )
    db.add(evaluation)
    db.flush()

    groups: dict[str, dict] = {}
    unmapped_rules: list[dict] = []
    manual_review_count = 0
    actionable_rule_count = 0

    for result in results:
        outcome = result.get("outcome") or {}
        decision = outcome.get("decision")
        equipment_type_code = outcome.get("equipment_type_code")
        comparison_mode = outcome.get("comparison_mode")

        if decision != "required":
            manual_review_count += 1
            unmapped_rules.append({
                "rule_code": result.get("rule_code"),
                "reason": "decision_not_explicit_required",
                "decision": decision,
                "outcome": outcome,
            })
            continue
        if not equipment_type_code:
            manual_review_count += 1
            unmapped_rules.append({
                "rule_code": result.get("rule_code"),
                "reason": "equipment_type_code_missing",
                "outcome": outcome,
            })
            continue

        et = db.scalar(
            select(EquipmentType).where(
                EquipmentType.code == equipment_type_code,
                EquipmentType.active.is_(True),
            )
        )
        if not et:
            manual_review_count += 1
            unmapped_rules.append({
                "rule_code": result.get("rule_code"),
                "reason": "equipment_type_not_registered",
                "equipment_type_code": equipment_type_code,
                "outcome": outcome,
            })
            continue

        group = groups.setdefault(
            equipment_type_code,
            {"equipment_type": et, "rules": [], "comparison_modes": set()},
        )
        group["rules"].append(result)
        group["comparison_modes"].add(comparison_mode)
        if comparison_mode == "presence":
            actionable_rule_count += 1

    items: list[EquipmentRequirementComparisonItemOut] = []
    gap_candidate_count = 0

    for code, group in sorted(groups.items()):
        et: EquipmentType = group["equipment_type"]
        rules = group["rules"]
        modes = group["comparison_modes"]

        if modes != {"presence"}:
            manual_review_count += 1
            items.append(
                EquipmentRequirementComparisonItemOut(
                    equipment_type_code=code,
                    equipment_type_name=et.name,
                    state="manual_review_required",
                    rule_evidence=rules,
                    detail={
                        "comparison_modes": sorted(
                            str(x) if x is not None else "(unset)" for x in modes
                        ),
                        "reason": "only explicit presence comparison is automated",
                    },
                )
            )
            continue

        records = db.scalars(
            select(FacilityEquipment).where(
                FacilityEquipment.building_id == building_id,
                FacilityEquipment.equipment_type_id == et.equipment_type_id,
                FacilityEquipment.operational_status == "installed",
            )
        ).all()
        verified = [x for x in records if x.verification_status == "verified"]
        evidence_only = [x for x in records if x.verification_status != "verified"]

        if verified:
            items.append(
                EquipmentRequirementComparisonItemOut(
                    equipment_type_code=code,
                    equipment_type_name=et.name,
                    state="verified_installed",
                    verified_equipment_ids=[x.facility_equipment_id for x in verified],
                    evidence_equipment_ids=[x.facility_equipment_id for x in evidence_only],
                    rule_evidence=rules,
                    detail={"comparison_mode": "presence"},
                )
            )
            continue

        if evidence_only:
            manual_review_count += 1
            items.append(
                EquipmentRequirementComparisonItemOut(
                    equipment_type_code=code,
                    equipment_type_name=et.name,
                    state="unverified_evidence_only",
                    evidence_equipment_ids=[x.facility_equipment_id for x in evidence_only],
                    rule_evidence=rules,
                    detail={
                        "comparison_mode": "presence",
                        "verification_statuses": sorted({x.verification_status for x in evidence_only}),
                        "source_kinds": sorted({x.source_kind for x in evidence_only}),
                        "reason": "legacy/unverified/AI evidence is not treated as verified installed equipment",
                    },
                )
            )
            continue

        gap_candidate_count += 1
        items.append(
            EquipmentRequirementComparisonItemOut(
                equipment_type_code=code,
                equipment_type_name=et.name,
                state="missing_equipment_candidate",
                rule_evidence=rules,
                detail={
                    "comparison_mode": "presence",
                    "reason": "approved Rule explicitly requires the equipment type and no installed equipment record was found",
                },
            )
        )

    write_audit(
        db,
        user_id=user.user_id,
        action="equipment_compliance.evaluate",
        entity_type="facility",
        entity_id=building_id,
        after={
            "requirement_evaluation_id": evaluation.evaluation_id,
            "matched_rule_count": len(results),
            "actionable_rule_count": actionable_rule_count,
            "gap_candidate_count": gap_candidate_count,
            "manual_review_count": manual_review_count,
        },
    )
    db.commit()

    return FacilityEquipmentRequirementComplianceOut(
        building_id=building_id,
        evaluation_id=evaluation.evaluation_id,
        evaluation_date=evaluation_date.isoformat(),
        facility_version=facility.version,
        matched_rule_count=len(results),
        actionable_rule_count=actionable_rule_count,
        gap_candidate_count=gap_candidate_count,
        manual_review_count=manual_review_count,
        items=items,
        unmapped_rules=unmapped_rules,
        note=(
            "A missing_equipment_candidate is not a formal violation finding. "
            "Only Approved Rules with decision=required, an explicit equipment_type_code, "
            "and comparison_mode=presence are automatically compared. "
            "legacy_only, unverified, and drawing_ai evidence remain review-only."
        ),
    )
