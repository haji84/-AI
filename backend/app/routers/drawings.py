from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from ..audit import write_audit
from ..authz import require_permission
from ..db import get_db
from ..models import (
    Document,
    DrawingAnalysis,
    DrawingElement,
    DrawingEquipmentCandidate,
    DrawingFactCandidate,
    EquipmentType,
    Facility,
    FacilityDetail,
    FacilityEquipment,
    User,
)
from ..schemas import (
    DrawingAnalysisCreate,
    DrawingAnalysisDetailOut,
    DrawingAnalysisOut,
    DrawingAnalysisReview,
    DrawingElementCreate,
    DrawingElementOut,
    DrawingEquipmentCandidateCreate,
    DrawingEquipmentCandidateOut,
    DrawingEquipmentCandidatePromote,
    DrawingEquipmentCandidateReview,
    DrawingFactCandidateApply,
    DrawingFactCandidateCreate,
    DrawingFactCandidateOut,
    DrawingFactCandidateReview,
)

router = APIRouter(tags=["drawings"])

DRAWING_FACT_APPLY_FIELDS = {
    "detail.classification_code": ("classification_code", "str"),
    "detail.classification_detail_1": ("classification_detail_1", "str"),
    "detail.classification_detail_2": ("classification_detail_2", "str"),
    "detail.structure": ("structure", "str"),
    "detail.zoning": ("zoning", "str"),
    "detail.article8_partition": ("article8_partition", "str"),
    "detail.above_ground_floors": ("above_ground_floors", "int_nonnegative"),
    "detail.basement_floors": ("basement_floors", "int_nonnegative"),
    "detail.building_area": ("building_area", "number_nonnegative"),
    "detail.total_floor_area": ("total_floor_area", "number_nonnegative"),
    "detail.occupancy_total": ("occupancy_total", "int_nonnegative"),
    "detail.employee_total": ("employee_total", "int_nonnegative"),
}


def _validated_fact_value(target_path: str, proposed: dict):
    if target_path not in DRAWING_FACT_APPLY_FIELDS:
        raise HTTPException(status_code=422, detail="target_path is not allowed for drawing fact application")
    if not isinstance(proposed, dict) or "value" not in proposed:
        raise HTTPException(status_code=422, detail="proposed_value must contain value")
    value = proposed.get("value")
    _field, kind = DRAWING_FACT_APPLY_FIELDS[target_path]
    if kind == "str":
        if value is not None and not isinstance(value, str):
            raise HTTPException(status_code=422, detail="proposed value must be a string or null")
        return value
    if kind == "int_nonnegative":
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise HTTPException(status_code=422, detail="proposed value must be a non-negative integer")
        return value
    if kind == "number_nonnegative":
        if isinstance(value, bool) or not isinstance(value, (int, float)) or value < 0:
            raise HTTPException(status_code=422, detail="proposed value must be a non-negative number")
        return float(value)
    raise HTTPException(status_code=422, detail="unsupported drawing fact target type")




def _analysis_out(row: DrawingAnalysis) -> DrawingAnalysisOut:
    return DrawingAnalysisOut(
        drawing_analysis_id=row.drawing_analysis_id,
        building_id=row.building_id,
        document_id=row.document_id,
        status=row.status,
        analysis_method=row.analysis_method,
        model_version=row.model_version,
        page_count=row.page_count,
        confidence=row.confidence,
        summary=row.summary or {},
        evidence=row.evidence or {},
        version=row.version,
        created_at=row.created_at.isoformat(),
    )


def _element_out(row: DrawingElement) -> DrawingElementOut:
    return DrawingElementOut(
        drawing_element_id=row.drawing_element_id,
        drawing_analysis_id=row.drawing_analysis_id,
        page_no=row.page_no,
        element_type=row.element_type,
        label=row.label,
        floor_number=row.floor_number,
        geometry=row.geometry or {},
        extracted_data=row.extracted_data or {},
        confidence=row.confidence,
        source_kind=row.source_kind,
        review_status=row.review_status,
    )


def _equipment_candidate_out(row: DrawingEquipmentCandidate) -> DrawingEquipmentCandidateOut:
    return DrawingEquipmentCandidateOut(
        drawing_equipment_candidate_id=row.drawing_equipment_candidate_id,
        drawing_analysis_id=row.drawing_analysis_id,
        drawing_element_id=row.drawing_element_id,
        equipment_type_id=row.equipment_type_id,
        suggested_equipment_type_code=row.suggested_equipment_type_code,
        suggested_label=row.suggested_label,
        floor_number=row.floor_number,
        location_text=row.location_text,
        quantity=row.quantity,
        confidence=row.confidence,
        status=row.status,
        facility_equipment_id=row.facility_equipment_id,
        version=row.version,
    )


def _fact_candidate_out(row: DrawingFactCandidate) -> DrawingFactCandidateOut:
    return DrawingFactCandidateOut(
        drawing_fact_candidate_id=row.drawing_fact_candidate_id,
        drawing_analysis_id=row.drawing_analysis_id,
        drawing_element_id=row.drawing_element_id,
        target_path=row.target_path,
        proposed_value=row.proposed_value,
        confidence=row.confidence,
        evidence=row.evidence or {},
        status=row.status,
        version=row.version,
        applied_by=row.applied_by,
        applied_at=row.applied_at.isoformat() if row.applied_at else None,
        applied_facility_version=row.applied_facility_version,
    )


def _detail(db: Session, analysis: DrawingAnalysis) -> DrawingAnalysisDetailOut:
    elements = db.scalars(
        select(DrawingElement)
        .where(DrawingElement.drawing_analysis_id == analysis.drawing_analysis_id)
        .order_by(DrawingElement.page_no, DrawingElement.created_at)
    ).all()
    equipment = db.scalars(
        select(DrawingEquipmentCandidate)
        .where(DrawingEquipmentCandidate.drawing_analysis_id == analysis.drawing_analysis_id)
        .order_by(DrawingEquipmentCandidate.created_at)
    ).all()
    facts = db.scalars(
        select(DrawingFactCandidate)
        .where(DrawingFactCandidate.drawing_analysis_id == analysis.drawing_analysis_id)
        .order_by(DrawingFactCandidate.created_at)
    ).all()
    return DrawingAnalysisDetailOut(
        analysis=_analysis_out(analysis),
        elements=[_element_out(x) for x in elements],
        equipment_candidates=[_equipment_candidate_out(x) for x in equipment],
        fact_candidates=[_fact_candidate_out(x) for x in facts],
    )


def _mark_analysis_analyzed(analysis: DrawingAnalysis) -> None:
    if analysis.status == "pending":
        analysis.status = "analyzed"
        analysis.updated_at = datetime.now(timezone.utc)


def _require_element(db: Session, analysis_id: str, element_id: str | None) -> DrawingElement | None:
    if not element_id:
        return None
    row = db.get(DrawingElement, element_id)
    if not row or row.drawing_analysis_id != analysis_id:
        raise HTTPException(status_code=422, detail="drawing_element_id does not belong to this analysis")
    return row


@router.get("/facilities/{building_id}/drawing-analyses", response_model=list[DrawingAnalysisOut])
def list_drawing_analyses(
    building_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("drawing.read")),
):
    if not db.get(Facility, building_id):
        raise HTTPException(status_code=404, detail="facility not found")
    rows = db.scalars(
        select(DrawingAnalysis)
        .where(DrawingAnalysis.building_id == building_id)
        .order_by(DrawingAnalysis.created_at.desc())
    ).all()
    return [_analysis_out(x) for x in rows]


@router.post("/facilities/{building_id}/drawing-analyses", response_model=DrawingAnalysisOut, status_code=201)
def create_drawing_analysis(
    building_id: str,
    payload: DrawingAnalysisCreate,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("drawing.analyze")),
):
    if not db.get(Facility, building_id):
        raise HTTPException(status_code=404, detail="facility not found")
    doc = db.get(Document, payload.document_id)
    if not doc:
        raise HTTPException(status_code=404, detail="document not found")
    if doc.building_id and doc.building_id != building_id:
        raise HTTPException(status_code=409, detail="document belongs to another facility")
    if not doc.building_id:
        doc.building_id = building_id

    row = DrawingAnalysis(
        building_id=building_id,
        document_id=payload.document_id,
        status="pending",
        analysis_method=payload.analysis_method,
        model_version=payload.model_version,
        page_count=payload.page_count,
        confidence=payload.confidence,
        summary=payload.summary,
        evidence=payload.evidence,
        created_by=user.user_id,
    )
    db.add(row)
    db.flush()
    write_audit(
        db,
        user_id=user.user_id,
        action="drawing_analysis.create",
        entity_type="drawing_analysis",
        entity_id=row.drawing_analysis_id,
        after=_analysis_out(row).model_dump(mode="json"),
        ai_used=payload.analysis_method == "ai",
        ai_model_version=payload.model_version,
    )
    db.commit()
    return _analysis_out(row)


@router.get("/drawing-analyses/{analysis_id}", response_model=DrawingAnalysisDetailOut)
def get_drawing_analysis(
    analysis_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("drawing.read")),
):
    row = db.get(DrawingAnalysis, analysis_id)
    if not row:
        raise HTTPException(status_code=404, detail="drawing analysis not found")
    return _detail(db, row)


@router.post("/drawing-analyses/{analysis_id}/elements", response_model=DrawingElementOut, status_code=201)
def create_drawing_element(
    analysis_id: str,
    payload: DrawingElementCreate,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("drawing.analyze")),
):
    analysis = db.get(DrawingAnalysis, analysis_id)
    if not analysis:
        raise HTTPException(status_code=404, detail="drawing analysis not found")
    if analysis.status == "reviewed":
        raise HTTPException(status_code=409, detail="reviewed drawing analysis is locked")
    _mark_analysis_analyzed(analysis)
    row = DrawingElement(
        drawing_analysis_id=analysis_id,
        page_no=payload.page_no,
        element_type=payload.element_type,
        label=payload.label,
        floor_number=payload.floor_number,
        geometry=payload.geometry,
        extracted_data=payload.extracted_data,
        confidence=payload.confidence,
        source_kind=payload.source_kind,
        review_status="pending",
    )
    db.add(row)
    db.flush()
    write_audit(
        db,
        user_id=user.user_id,
        action="drawing_element.create",
        entity_type="drawing_element",
        entity_id=row.drawing_element_id,
        after=_element_out(row).model_dump(mode="json"),
        ai_used=payload.source_kind == "ai",
        ai_model_version=analysis.model_version,
    )
    db.commit()
    return _element_out(row)


@router.post(
    "/drawing-analyses/{analysis_id}/equipment-candidates",
    response_model=DrawingEquipmentCandidateOut,
    status_code=201,
)
def create_drawing_equipment_candidate(
    analysis_id: str,
    payload: DrawingEquipmentCandidateCreate,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("drawing.analyze")),
):
    analysis = db.get(DrawingAnalysis, analysis_id)
    if not analysis:
        raise HTTPException(status_code=404, detail="drawing analysis not found")
    if analysis.status == "reviewed":
        raise HTTPException(status_code=409, detail="reviewed drawing analysis is locked")
    _mark_analysis_analyzed(analysis)
    _require_element(db, analysis_id, payload.drawing_element_id)

    equipment_type_id = None
    if payload.suggested_equipment_type_code:
        et = db.scalar(
            select(EquipmentType).where(
                EquipmentType.code == payload.suggested_equipment_type_code,
                EquipmentType.active.is_(True),
            )
        )
        if et:
            equipment_type_id = et.equipment_type_id

    row = DrawingEquipmentCandidate(
        drawing_analysis_id=analysis_id,
        drawing_element_id=payload.drawing_element_id,
        equipment_type_id=equipment_type_id,
        suggested_equipment_type_code=payload.suggested_equipment_type_code,
        suggested_label=payload.suggested_label,
        floor_number=payload.floor_number,
        location_text=payload.location_text,
        quantity=payload.quantity,
        confidence=payload.confidence,
        status="pending",
    )
    db.add(row)
    db.flush()
    write_audit(
        db,
        user_id=user.user_id,
        action="drawing_equipment_candidate.create",
        entity_type="drawing_equipment_candidate",
        entity_id=row.drawing_equipment_candidate_id,
        after=_equipment_candidate_out(row).model_dump(mode="json"),
        ai_used=analysis.analysis_method == "ai",
        ai_model_version=analysis.model_version,
    )
    db.commit()
    return _equipment_candidate_out(row)


@router.patch(
    "/drawing-equipment-candidates/{candidate_id}",
    response_model=DrawingEquipmentCandidateOut,
)
def review_drawing_equipment_candidate(
    candidate_id: str,
    payload: DrawingEquipmentCandidateReview,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("drawing.review")),
):
    row = db.get(DrawingEquipmentCandidate, candidate_id)
    if not row:
        raise HTTPException(status_code=404, detail="drawing equipment candidate not found")
    if row.version != payload.expected_version:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="drawing equipment candidate was updated")
    if row.status != "pending":
        raise HTTPException(status_code=409, detail="only pending candidates can be reviewed")
    row.status = payload.status
    row.reviewed_by = user.user_id
    row.reviewed_at = datetime.now(timezone.utc)
    row.version += 1
    row.updated_at = datetime.now(timezone.utc)
    write_audit(
        db,
        user_id=user.user_id,
        action=f"drawing_equipment_candidate.{payload.status}",
        entity_type="drawing_equipment_candidate",
        entity_id=row.drawing_equipment_candidate_id,
        after=_equipment_candidate_out(row).model_dump(mode="json"),
    )
    db.commit()
    return _equipment_candidate_out(row)


@router.post(
    "/drawing-equipment-candidates/{candidate_id}/promote",
    response_model=DrawingEquipmentCandidateOut,
)
def promote_drawing_equipment_candidate(
    candidate_id: str,
    payload: DrawingEquipmentCandidatePromote,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("drawing.review")),
):
    row = db.get(DrawingEquipmentCandidate, candidate_id)
    if not row:
        raise HTTPException(status_code=404, detail="drawing equipment candidate not found")
    if row.version != payload.expected_version:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="drawing equipment candidate was updated")
    if row.status != "accepted":
        raise HTTPException(status_code=409, detail="candidate must be accepted before promotion")
    if row.facility_equipment_id:
        raise HTTPException(status_code=409, detail="candidate is already promoted")

    analysis = db.get(DrawingAnalysis, row.drawing_analysis_id)
    if not analysis:
        raise HTTPException(status_code=409, detail="drawing analysis missing")
    code = payload.equipment_type_code or row.suggested_equipment_type_code
    if not code:
        raise HTTPException(status_code=422, detail="equipment_type_code is required for promotion")
    et = db.scalar(
        select(EquipmentType).where(
            EquipmentType.code == code,
            EquipmentType.active.is_(True),
        )
    )
    if not et:
        raise HTTPException(status_code=422, detail="equipment type not found")

    equipment = FacilityEquipment(
        building_id=analysis.building_id,
        equipment_type_id=et.equipment_type_id,
        floor_number=row.floor_number,
        location_text=row.location_text,
        quantity=row.quantity,
        operational_status="installed",
        verification_status="ai_candidate",
        source_kind="drawing_ai",
        source_document_id=analysis.document_id,
        notes=payload.notes or (
            f"Promoted from drawing candidate {row.drawing_equipment_candidate_id}; "
            "requires independent verification before verified status."
        ),
        created_by=user.user_id,
        updated_by=user.user_id,
    )
    db.add(equipment)
    db.flush()

    row.status = "promoted"
    row.facility_equipment_id = equipment.facility_equipment_id
    row.equipment_type_id = et.equipment_type_id
    row.version += 1
    row.reviewed_by = user.user_id
    row.reviewed_at = datetime.now(timezone.utc)
    row.updated_at = datetime.now(timezone.utc)

    write_audit(
        db,
        user_id=user.user_id,
        action="drawing_equipment_candidate.promote",
        entity_type="drawing_equipment_candidate",
        entity_id=row.drawing_equipment_candidate_id,
        after={
            "facility_equipment_id": equipment.facility_equipment_id,
            "verification_status": "ai_candidate",
            "source_kind": "drawing_ai",
        },
        ai_used=analysis.analysis_method == "ai",
        ai_model_version=analysis.model_version,
    )
    db.commit()
    return _equipment_candidate_out(row)


@router.post(
    "/drawing-analyses/{analysis_id}/fact-candidates",
    response_model=DrawingFactCandidateOut,
    status_code=201,
)
def create_drawing_fact_candidate(
    analysis_id: str,
    payload: DrawingFactCandidateCreate,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("drawing.analyze")),
):
    analysis = db.get(DrawingAnalysis, analysis_id)
    if not analysis:
        raise HTTPException(status_code=404, detail="drawing analysis not found")
    if analysis.status == "reviewed":
        raise HTTPException(status_code=409, detail="reviewed drawing analysis is locked")
    _mark_analysis_analyzed(analysis)
    _require_element(db, analysis_id, payload.drawing_element_id)
    row = DrawingFactCandidate(
        drawing_analysis_id=analysis_id,
        drawing_element_id=payload.drawing_element_id,
        target_path=payload.target_path,
        proposed_value=payload.proposed_value,
        confidence=payload.confidence,
        evidence=payload.evidence,
        status="pending",
    )
    db.add(row)
    db.flush()
    write_audit(
        db,
        user_id=user.user_id,
        action="drawing_fact_candidate.create",
        entity_type="drawing_fact_candidate",
        entity_id=row.drawing_fact_candidate_id,
        after=_fact_candidate_out(row).model_dump(mode="json"),
        ai_used=analysis.analysis_method == "ai",
        ai_model_version=analysis.model_version,
    )
    db.commit()
    return _fact_candidate_out(row)


@router.patch(
    "/drawing-fact-candidates/{candidate_id}",
    response_model=DrawingFactCandidateOut,
)
def review_drawing_fact_candidate(
    candidate_id: str,
    payload: DrawingFactCandidateReview,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("drawing.review")),
):
    row = db.get(DrawingFactCandidate, candidate_id)
    if not row:
        raise HTTPException(status_code=404, detail="drawing fact candidate not found")
    if row.version != payload.expected_version:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="drawing fact candidate was updated")
    if row.status != "pending":
        raise HTTPException(status_code=409, detail="only pending candidates can be reviewed")
    row.status = payload.status
    row.reviewed_by = user.user_id
    row.reviewed_at = datetime.now(timezone.utc)
    row.version += 1
    row.updated_at = datetime.now(timezone.utc)
    write_audit(
        db,
        user_id=user.user_id,
        action=f"drawing_fact_candidate.{payload.status}",
        entity_type="drawing_fact_candidate",
        entity_id=row.drawing_fact_candidate_id,
        after=_fact_candidate_out(row).model_dump(mode="json"),
    )
    db.commit()
    return _fact_candidate_out(row)


@router.post(
    "/drawing-fact-candidates/{candidate_id}/apply",
    response_model=DrawingFactCandidateOut,
)
def apply_drawing_fact_candidate(
    candidate_id: str,
    payload: DrawingFactCandidateApply,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("drawing.review")),
):
    row = db.get(DrawingFactCandidate, candidate_id)
    if not row:
        raise HTTPException(status_code=404, detail="drawing fact candidate not found")
    if row.version != payload.expected_version:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="drawing fact candidate was updated")
    if row.status != "accepted":
        raise HTTPException(status_code=409, detail="drawing fact candidate must be accepted before apply")
    if row.applied_at is not None:
        raise HTTPException(status_code=409, detail="drawing fact candidate already applied")

    analysis = db.get(DrawingAnalysis, row.drawing_analysis_id)
    if not analysis:
        raise HTTPException(status_code=409, detail="drawing analysis missing")
    facility = db.get(Facility, analysis.building_id)
    if not facility:
        raise HTTPException(status_code=404, detail="facility not found")
    if facility.version != payload.expected_facility_version:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "message": "facility was updated by another user",
                "current_version": facility.version,
            },
        )

    value = _validated_fact_value(row.target_path, row.proposed_value)
    detail_field, _kind = DRAWING_FACT_APPLY_FIELDS[row.target_path]
    detail = db.get(FacilityDetail, facility.building_id)
    if detail is None:
        detail = FacilityDetail(building_id=facility.building_id)
        db.add(detail)
        db.flush()

    before_value = getattr(detail, detail_field)
    setattr(detail, detail_field, value)
    detail.updated_at = datetime.now(timezone.utc)

    result = db.execute(
        update(Facility)
        .where(
            Facility.building_id == facility.building_id,
            Facility.version == payload.expected_facility_version,
        )
        .values(
            version=payload.expected_facility_version + 1,
            updated_at=datetime.now(timezone.utc),
        )
    )
    if result.rowcount != 1:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="facility version changed during apply")

    row.applied_by = user.user_id
    row.applied_at = datetime.now(timezone.utc)
    row.applied_facility_version = payload.expected_facility_version + 1
    row.version += 1
    row.updated_at = datetime.now(timezone.utc)

    write_audit(
        db,
        user_id=user.user_id,
        action="drawing_fact_candidate.apply",
        entity_type="facility",
        entity_id=facility.building_id,
        before={
            "target_path": row.target_path,
            "value": before_value,
            "facility_version": payload.expected_facility_version,
        },
        after={
            "target_path": row.target_path,
            "value": value,
            "facility_version": payload.expected_facility_version + 1,
            "drawing_fact_candidate_id": row.drawing_fact_candidate_id,
        },
        ai_used=analysis.analysis_method == "ai",
        ai_model_version=analysis.model_version,
    )
    db.commit()
    return _fact_candidate_out(row)


@router.post("/drawing-analyses/{analysis_id}/review", response_model=DrawingAnalysisOut)
def review_drawing_analysis(
    analysis_id: str,
    payload: DrawingAnalysisReview,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("drawing.review")),
):
    row = db.get(DrawingAnalysis, analysis_id)
    if not row:
        raise HTTPException(status_code=404, detail="drawing analysis not found")
    if row.version != payload.expected_version:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="drawing analysis was updated")
    if row.status == "reviewed":
        raise HTTPException(status_code=409, detail="drawing analysis already reviewed")

    pending_equipment = db.scalar(
        select(DrawingEquipmentCandidate)
        .where(
            DrawingEquipmentCandidate.drawing_analysis_id == analysis_id,
            DrawingEquipmentCandidate.status == "pending",
        )
        .limit(1)
    )
    pending_facts = db.scalar(
        select(DrawingFactCandidate)
        .where(
            DrawingFactCandidate.drawing_analysis_id == analysis_id,
            DrawingFactCandidate.status == "pending",
        )
        .limit(1)
    )
    if pending_equipment or pending_facts:
        raise HTTPException(status_code=409, detail="all drawing candidates must be reviewed first")

    row.status = "reviewed"
    row.reviewed_by = user.user_id
    row.reviewed_at = datetime.now(timezone.utc)
    row.version += 1
    row.updated_at = datetime.now(timezone.utc)
    write_audit(
        db,
        user_id=user.user_id,
        action="drawing_analysis.review",
        entity_type="drawing_analysis",
        entity_id=row.drawing_analysis_id,
        after=_analysis_out(row).model_dump(mode="json"),
    )
    db.commit()
    return _analysis_out(row)
