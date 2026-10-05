from __future__ import annotations

from datetime import date, datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from ..audit import write_audit
from ..authz import require_permission
from ..db import get_db
from ..consultation_response import build_consultation_response_package
from ..equipment_authoring_batch import equipment_requirement_batch_coverage
from ..equipment_placement_batch import equipment_placement_batch_coverage
from ..equipment_placement_engine import evaluate_placement_candidates
from ..occupancy_authoring_workbench import occupancy_rule_coverage
from ..legal_requirement_engine import (
    approved_rule_count,
    evaluate_approved_rules_for_snapshot,
    required_input_fields_for_domain,
)
from ..models import (
    DrawingAnalysis,
    DrawingAnnotationSet,
    DrawingConsultation,
    EquipmentType,
    User,
)
from ..schemas import (
    DrawingConsultationClassificationConfirm,
    DrawingConsultationClassify,
    DrawingConsultationCreate,
    DrawingConsultationEquipmentEvaluate,
    DrawingConsultationOut,
    DrawingConsultationUpdateAnswers,
    DrawingConsultationResponseReview,
    DrawingConsultationResponseOut,
)


router = APIRouter(tags=["drawing-consultations"])


CONSULTATION_ANSWER_FIELDS = {
    "primary_use",
    "use_tags",
    "has_sleeping_use",
    "has_food_service",
    "public_access",
    "mixed_use",
    "windowless_floor_count",
    "structure",
    "above_ground_floors",
    "basement_floors",
    "building_area",
    "total_floor_area",
    "occupancy_total",
    "employee_total",
}


def _date(value: str | None) -> date:
    if value in (None, ""):
        return date.today()
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=f"invalid evaluation_date: {value}") from exc


def _out(row: DrawingConsultation) -> DrawingConsultationOut:
    return DrawingConsultationOut(
        drawing_consultation_id=row.drawing_consultation_id,
        drawing_analysis_id=row.drawing_analysis_id,
        drawing_annotation_set_id=row.drawing_annotation_set_id,
        status=row.status,
        input_snapshot=row.input_snapshot or {},
        classification_results=row.classification_results or [],
        missing_information=row.missing_information or [],
        confirmed_classification_code=row.confirmed_classification_code,
        confirmed_classification_label=row.confirmed_classification_label,
        confirmed_classification_rule_version_id=row.confirmed_classification_rule_version_id,
        equipment_results=row.equipment_results or [],
        placement_results=row.placement_results or [],
        consultation_notes=row.consultation_notes,
        version=row.version,
        created_at=row.created_at.isoformat(),
        classification_confirmed_at=(
            row.classification_confirmed_at.isoformat()
            if row.classification_confirmed_at
            else None
        ),
    )


def _require_analysis(db: Session, analysis_id: str) -> DrawingAnalysis:
    row = db.get(DrawingAnalysis, analysis_id)
    if not row:
        raise HTTPException(status_code=404, detail="drawing analysis not found")
    return row


def _require_consultation(db: Session, consultation_id: str) -> DrawingConsultation:
    row = db.get(DrawingConsultation, consultation_id)
    if not row:
        raise HTTPException(status_code=404, detail="drawing consultation not found")
    return row


def _require_reviewed_annotation(
    db: Session,
    *,
    analysis_id: str,
    annotation_id: str,
) -> DrawingAnnotationSet:
    row = db.get(DrawingAnnotationSet, annotation_id)
    if not row or row.drawing_analysis_id != analysis_id:
        raise HTTPException(status_code=422, detail="annotation does not belong to drawing analysis")
    if row.status != "reviewed":
        raise HTTPException(
            status_code=409,
            detail="drawing consultation requires a Human-reviewed annotation set",
        )
    return row


def _fact_value(row: dict):
    proposed = row.get("proposed_value")
    if isinstance(proposed, dict) and "value" in proposed:
        return proposed["value"]
    return None


def _build_snapshot(annotation: DrawingAnnotationSet, answers: dict) -> dict:
    payload = annotation.payload or {}
    use_tags: list[str] = []
    room_labels: list[str] = []
    floor_numbers: set[int] = set()

    for element in payload.get("elements", []):
        if not isinstance(element, dict):
            continue
        floor = element.get("floor_number")
        if isinstance(floor, int):
            floor_numbers.add(floor)
        if str(element.get("element_type") or "") != "room":
            continue
        label = str(element.get("label") or "").strip()
        if label:
            room_labels.append(label)
        extracted = element.get("extracted_data") or {}
        if isinstance(extracted, dict):
            use_name = str(extracted.get("use_name") or "").strip()
            if use_name:
                use_tags.append(use_name)

    snapshot: dict = {
        "classification_code": None,
        "primary_use": None,
        "use_tags": sorted(set(use_tags)),
        "room_labels": sorted(set(room_labels)),
        "floor_numbers": sorted(floor_numbers),
        "has_sleeping_use": None,
        "has_food_service": None,
        "public_access": None,
        "mixed_use": None,
        "windowless_floor_count": None,
        "structure": None,
        "above_ground_floors": None,
        "basement_floors": None,
        "building_area": None,
        "total_floor_area": None,
        "occupancy_total": None,
        "employee_total": None,
        "source_annotation_set_id": annotation.drawing_annotation_set_id,
        "source_annotation_version": annotation.version,
    }

    fact_map = {
        "detail.structure": "structure",
        "detail.above_ground_floors": "above_ground_floors",
        "detail.basement_floors": "basement_floors",
        "detail.building_area": "building_area",
        "detail.total_floor_area": "total_floor_area",
        "detail.occupancy_total": "occupancy_total",
        "detail.employee_total": "employee_total",
    }
    for fact in payload.get("fact_candidates", []):
        if not isinstance(fact, dict):
            continue
        field = fact_map.get(str(fact.get("target_path") or ""))
        if field:
            snapshot[field] = _fact_value(fact)

    if not isinstance(answers, dict):
        raise HTTPException(status_code=422, detail="answers must be an object")
    unexpected = set(answers) - CONSULTATION_ANSWER_FIELDS
    if unexpected:
        raise HTTPException(
            status_code=422,
            detail=f"unsupported consultation answer fields: {sorted(unexpected)}",
        )
    for key, value in answers.items():
        snapshot[key] = value

    return snapshot


def _missing_fields(
    db: Session,
    *,
    snapshot: dict,
    domain: str,
    evaluation_date: date,
) -> list[dict]:
    rule_count = approved_rule_count(
        db,
        domain=domain,
        evaluation_date=evaluation_date,
    )
    if rule_count == 0:
        return [
            {
                "field": "approved_rule_set",
                "reason": f"no approved {domain} Rules are effective for the evaluation date",
            }
        ]

    required = required_input_fields_for_domain(
        db,
        domain=domain,
        evaluation_date=evaluation_date,
    )
    rows = []
    for field in sorted(required):
        value = snapshot.get(field)
        if value in (None, "", [], {}):
            rows.append(
                {
                    "field": field,
                    "reason": "required by at least one effective Approved Rule but not supplied",
                }
            )
    return rows


@router.get(
    "/drawing-analyses/{analysis_id}/consultations",
    response_model=list[DrawingConsultationOut],
)
def list_consultations(
    analysis_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("drawing.read")),
):
    _require_analysis(db, analysis_id)
    rows = db.scalars(
        select(DrawingConsultation)
        .where(DrawingConsultation.drawing_analysis_id == analysis_id)
        .order_by(DrawingConsultation.created_at.desc())
    ).all()
    return [_out(x) for x in rows]


@router.post(
    "/drawing-analyses/{analysis_id}/consultations",
    response_model=DrawingConsultationOut,
    status_code=201,
)
def create_consultation(
    analysis_id: str,
    payload: DrawingConsultationCreate,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("drawing.review")),
):
    _require_analysis(db, analysis_id)
    annotation = _require_reviewed_annotation(
        db,
        analysis_id=analysis_id,
        annotation_id=payload.drawing_annotation_set_id,
    )
    snapshot = _build_snapshot(annotation, payload.answers)
    row = DrawingConsultation(
        drawing_analysis_id=analysis_id,
        drawing_annotation_set_id=annotation.drawing_annotation_set_id,
        status="draft",
        input_snapshot=snapshot,
        consultation_notes=payload.notes,
        created_by=user.user_id,
    )
    db.add(row)
    db.flush()
    write_audit(
        db,
        user_id=user.user_id,
        action="drawing_consultation.create",
        entity_type="drawing_consultation",
        entity_id=row.drawing_consultation_id,
        after={
            "drawing_analysis_id": analysis_id,
            "annotation_id": annotation.drawing_annotation_set_id,
            "snapshot": snapshot,
        },
    )
    db.commit()
    return _out(row)


@router.put(
    "/drawing-consultations/{consultation_id}/answers",
    response_model=DrawingConsultationOut,
)
def update_consultation_answers(
    consultation_id: str,
    payload: DrawingConsultationUpdateAnswers,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("drawing.review")),
):
    row = _require_consultation(db, consultation_id)
    if row.status not in {"draft", "classification_pending", "classification_candidate"}:
        raise HTTPException(status_code=409, detail="answers are locked after classification confirmation")
    annotation = _require_reviewed_annotation(
        db,
        analysis_id=row.drawing_analysis_id,
        annotation_id=row.drawing_annotation_set_id,
    )
    snapshot = _build_snapshot(annotation, payload.answers)
    result = db.execute(
        update(DrawingConsultation)
        .where(
            DrawingConsultation.drawing_consultation_id == consultation_id,
            DrawingConsultation.version == payload.expected_version,
        )
        .values(
            input_snapshot=snapshot,
            classification_results=[],
            missing_information=[],
            status="draft",
            version=payload.expected_version + 1,
            updated_at=datetime.now(timezone.utc),
        )
    )
    if result.rowcount != 1:
        db.rollback()
        raise HTTPException(status_code=409, detail="drawing consultation was updated by another user")
    row = db.get(DrawingConsultation, consultation_id)
    db.commit()
    return _out(row)


@router.post(
    "/drawing-consultations/{consultation_id}/classify",
    response_model=DrawingConsultationOut,
)
def classify_consultation(
    consultation_id: str,
    payload: DrawingConsultationClassify,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("drawing.review")),
):
    row = _require_consultation(db, consultation_id)
    if row.version != payload.expected_version:
        raise HTTPException(status_code=409, detail="drawing consultation was updated")
    if row.confirmed_classification_code:
        raise HTTPException(status_code=409, detail="classification is already confirmed")

    evaluation_date = _date(payload.evaluation_date)
    snapshot = row.input_snapshot or {}
    results = evaluate_approved_rules_for_snapshot(
        db,
        snapshot=snapshot,
        domain="occupancy_classification",
        evaluation_date=evaluation_date,
    )
    missing = _missing_fields(
        db,
        snapshot=snapshot,
        domain="occupancy_classification",
        evaluation_date=evaluation_date,
    )
    coverage = occupancy_rule_coverage(
        db,
        evaluation_date=evaluation_date,
    )
    if not coverage["coverage_complete"]:
        missing.append(
            {
                "field": "occupancy_classification_rule_coverage",
                "reason": "occupancy classification Rule coverage is not complete",
                "coverage": {
                    "source_xml_sha256": coverage["source_xml_sha256"],
                    "expected_classification_count": coverage["expected_classification_count"],
                    "approved_effective_count": coverage["approved_effective_count"],
                    "blockers": coverage["blockers"],
                },
            }
        )

    row.classification_results = results
    row.missing_information = missing
    row.status = "classification_candidate" if results else "classification_pending"
    row.version += 1
    row.updated_at = datetime.now(timezone.utc)
    write_audit(
        db,
        user_id=user.user_id,
        action="drawing_consultation.classify",
        entity_type="drawing_consultation",
        entity_id=consultation_id,
        after={
            "candidate_count": len(results),
            "missing_information": missing,
            "evaluation_date": evaluation_date.isoformat(),
            "coverage_complete": coverage["coverage_complete"],
            "coverage_approved_effective_count": coverage["approved_effective_count"],
        },
    )
    db.commit()
    return _out(row)


@router.post(
    "/drawing-consultations/{consultation_id}/classification/confirm",
    response_model=DrawingConsultationOut,
)
def confirm_classification(
    consultation_id: str,
    payload: DrawingConsultationClassificationConfirm,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("drawing.review")),
):
    row = _require_consultation(db, consultation_id)
    if row.version != payload.expected_version:
        raise HTTPException(status_code=409, detail="drawing consultation was updated")
    if row.confirmed_classification_code:
        raise HTTPException(status_code=409, detail="classification is already confirmed")

    selected = None
    if payload.candidate_rule_version_id:
        for result in row.classification_results or []:
            if result.get("legal_rule_version_id") == payload.candidate_rule_version_id:
                selected = result
                break
        if not selected:
            raise HTTPException(status_code=422, detail="candidate Rule Version is not in consultation results")
        outcome = selected.get("outcome") or {}
        if str(outcome.get("classification_code") or "") != payload.classification_code:
            raise HTTPException(status_code=422, detail="classification_code does not match selected candidate")
        if str(outcome.get("classification_label") or "") != payload.classification_label:
            raise HTTPException(status_code=422, detail="classification_label does not match selected candidate")
    elif not (payload.review_note or "").strip():
        raise HTTPException(
            status_code=422,
            detail="manual classification confirmation requires review_note",
        )

    snapshot = dict(row.input_snapshot or {})
    snapshot["classification_code"] = payload.classification_code
    row.input_snapshot = snapshot
    row.confirmed_classification_code = payload.classification_code
    row.confirmed_classification_label = payload.classification_label
    row.confirmed_classification_rule_version_id = payload.candidate_rule_version_id
    row.classification_confirmed_by = user.user_id
    row.classification_confirmed_at = datetime.now(timezone.utc)
    row.consultation_notes = payload.review_note or row.consultation_notes
    row.status = "classified"
    row.version += 1
    row.updated_at = datetime.now(timezone.utc)

    write_audit(
        db,
        user_id=user.user_id,
        action="drawing_consultation.classification_confirm",
        entity_type="drawing_consultation",
        entity_id=consultation_id,
        after={
            "classification_code": payload.classification_code,
            "classification_label": payload.classification_label,
            "candidate_rule_version_id": payload.candidate_rule_version_id,
            "manual_confirmation": payload.candidate_rule_version_id is None,
        },
    )
    db.commit()
    return _out(row)


@router.post(
    "/drawing-consultations/{consultation_id}/equipment/evaluate",
    response_model=DrawingConsultationOut,
)
def evaluate_required_equipment(
    consultation_id: str,
    payload: DrawingConsultationEquipmentEvaluate,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("drawing.review")),
):
    row = _require_consultation(db, consultation_id)
    if row.version != payload.expected_version:
        raise HTTPException(status_code=409, detail="drawing consultation was updated")
    if not row.confirmed_classification_code:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="occupancy classification must be Human-confirmed before equipment evaluation",
        )

    evaluation_date = _date(payload.evaluation_date)
    snapshot = {
        **(row.input_snapshot or {}),
        "classification_code": row.confirmed_classification_code,
    }
    raw_results = evaluate_approved_rules_for_snapshot(
        db,
        snapshot=snapshot,
        domain="equipment_requirement",
        evaluation_date=evaluation_date,
    )
    missing = _missing_fields(
        db,
        snapshot=snapshot,
        domain="equipment_requirement",
        evaluation_date=evaluation_date,
    )
    equipment_coverage = equipment_requirement_batch_coverage(
        db,
        evaluation_date=evaluation_date,
    )
    if not equipment_coverage.get("coverage_complete"):
        missing.append(
            {
                "field": "equipment_requirement_rule_coverage",
                "reason": "equipment requirement Rule coverage is not complete",
                "coverage": {
                    "batch_found": equipment_coverage.get("batch_found"),
                    "worklist_sha256": equipment_coverage.get("worklist_sha256"),
                    "expected_candidate_count": equipment_coverage.get("expected_candidate_count"),
                    "processed_candidate_count": equipment_coverage.get("processed_candidate_count"),
                    "blockers": equipment_coverage.get("blockers") or [],
                },
            }
        )

    required: list[dict] = []
    manual_review: list[dict] = []
    for result in raw_results:
        outcome = result.get("outcome") or {}
        if outcome.get("decision") != "required" or not outcome.get("equipment_type_code"):
            manual_review.append(result)
            continue
        code = str(outcome["equipment_type_code"])
        et = db.scalar(
            select(EquipmentType).where(
                EquipmentType.code == code,
                EquipmentType.active.is_(True),
            )
        )
        required.append(
            {
                "equipment_type_code": code,
                "equipment_type_name": et.name if et else None,
                "comparison_mode": outcome.get("comparison_mode"),
                "rule_code": result.get("rule_code"),
                "rule_name": result.get("rule_name"),
                "legal_rule_version_id": result.get("legal_rule_version_id"),
                "citations": result.get("citations") or [],
                "source_reference": result.get("source_reference"),
                "outcome": outcome,
                "state": "required_candidate",
            }
        )

    placement_coverage = equipment_placement_batch_coverage(
        db,
        evaluation_date=evaluation_date,
    )
    if not placement_coverage.get("coverage_complete"):
        missing.append(
            {
                "field": "equipment_placement_rule_coverage",
                "reason": "equipment placement Rule coverage is not complete",
                "coverage": {
                    "batch_found": placement_coverage.get("batch_found"),
                    "worklist_sha256": placement_coverage.get("worklist_sha256"),
                    "expected_candidate_count": placement_coverage.get("expected_candidate_count"),
                    "processed_candidate_count": placement_coverage.get("processed_candidate_count"),
                    "authoring_coverage_complete": placement_coverage.get("authoring_coverage_complete"),
                    "regression_gate_passed": placement_coverage.get("regression_gate_passed"),
                    "blockers": placement_coverage.get("blockers") or [],
                },
            }
        )

    annotation = _require_reviewed_annotation(
        db,
        analysis_id=row.drawing_analysis_id,
        annotation_id=row.drawing_annotation_set_id,
    )
    placement = evaluate_placement_candidates(
        db,
        input_snapshot=row.input_snapshot or {},
        classification_code=row.confirmed_classification_code,
        rooms=(annotation.payload or {}).get("elements", []),
        equipment_type_codes=[
            str(x["equipment_type_code"])
            for x in required
            if x.get("equipment_type_code")
        ],
        evaluation_date=evaluation_date,
    )

    if row.status == "reviewed":
        row.response_payload = {}
        row.response_sha256 = None
        row.response_review_notes = None
        row.reviewed_by = None
        row.reviewed_at = None

    row.equipment_results = [
        {
            "required": required,
            "manual_review": manual_review,
            "matched_rule_count": len(raw_results),
            "approved_rule_count": approved_rule_count(
                db,
                domain="equipment_requirement",
                evaluation_date=evaluation_date,
            ),
            "missing_information": missing,
            "equipment_rule_coverage_complete": bool(
                equipment_coverage.get("coverage_complete")
            ),
            "equipment_placement_rule_coverage_complete": bool(
                placement_coverage.get("coverage_complete")
            ),
            "note": (
                "Zero matched Rules does not mean zero required equipment unless the Approved Rule set "
                "has been independently declared complete for this use case."
            ),
        }
    ]
    row.placement_results = placement
    row.missing_information = missing
    row.status = "equipment_evaluated"
    row.version += 1
    row.updated_at = datetime.now(timezone.utc)

    write_audit(
        db,
        user_id=user.user_id,
        action="drawing_consultation.equipment_evaluate",
        entity_type="drawing_consultation",
        entity_id=consultation_id,
        after={
            "classification_code": row.confirmed_classification_code,
            "required_equipment_count": len(required),
            "manual_review_count": len(manual_review),
            "placement_group_count": len(placement),
            "evaluation_date": evaluation_date.isoformat(),
            "equipment_rule_coverage_complete": bool(
                equipment_coverage.get("coverage_complete")
            ),
            "equipment_placement_rule_coverage_complete": bool(
                placement_coverage.get("coverage_complete")
            ),
        },
    )
    db.commit()
    return _out(row)


@router.get(
    "/drawing-consultations/{consultation_id}/response",
    response_model=DrawingConsultationResponseOut,
)
def get_consultation_response(
    consultation_id: str,
    evaluation_date: str | None = None,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("drawing.read")),
):
    row = _require_consultation(db, consultation_id)
    day = _date(evaluation_date)
    return DrawingConsultationResponseOut(
        **build_consultation_response_package(
            db,
            consultation=row,
            evaluation_date=day,
        )
    )


@router.post(
    "/drawing-consultations/{consultation_id}/response/review",
    response_model=DrawingConsultationResponseOut,
)
def review_consultation_response(
    consultation_id: str,
    payload: DrawingConsultationResponseReview,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("drawing.review")),
):
    row = _require_consultation(db, consultation_id)
    if row.version != payload.expected_version:
        raise HTTPException(
            status_code=409,
            detail="drawing consultation was updated",
        )

    day = _date(payload.evaluation_date)
    package = build_consultation_response_package(
        db,
        consultation=row,
        evaluation_date=day,
    )
    if not package.get("reviewable"):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "message": "consultation response is not review-ready",
                "answer_state": package.get("answer_state"),
                "blockers": package.get("blockers") or [],
                "coverage": package.get("coverage") or {},
                "unresolved_questions":
                    package.get("unresolved_questions") or [],
            },
        )

    row.response_payload = package
    row.response_sha256 = package["response_sha256"]
    row.response_review_notes = payload.review_notes
    row.status = "reviewed"
    row.reviewed_by = user.user_id
    row.reviewed_at = datetime.now(timezone.utc)
    row.updated_at = datetime.now(timezone.utc)
    row.version += 1

    write_audit(
        db,
        user_id=user.user_id,
        action="drawing_consultation.response_review",
        entity_type="drawing_consultation",
        entity_id=consultation_id,
        after={
            "response_sha256": row.response_sha256,
            "evaluation_date": day.isoformat(),
            "version": row.version,
            "coverage_complete":
                package.get("coverage_complete"),
        },
    )
    db.commit()

    return DrawingConsultationResponseOut(
        **build_consultation_response_package(
            db,
            consultation=row,
            evaluation_date=day,
        )
    )
