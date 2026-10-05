from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from ..audit import write_audit
from ..authz import require_permission
from ..db import get_db
from ..drawing_annotation_geometry import apply_geometry_metrics
from ..models import (
    Document,
    DrawingAnalysis,
    DrawingAnnotationSet,
    DrawingElement,
    DrawingEquipmentCandidate,
    DrawingFactCandidate,
    User,
)
from ..schemas import (
    DrawingAnnotationReview,
    DrawingAnnotationSeedCreate,
    DrawingAnnotationSetCreate,
    DrawingAnnotationSetOut,
    DrawingAnnotationSetUpdate,
)


router = APIRouter(tags=["drawing-annotations"])


def _annotation_out(row: DrawingAnnotationSet) -> DrawingAnnotationSetOut:
    return DrawingAnnotationSetOut(
        drawing_annotation_set_id=row.drawing_annotation_set_id,
        drawing_analysis_id=row.drawing_analysis_id,
        annotation_kind=row.annotation_kind,
        coordinate_space=row.coordinate_space,
        page_dimensions=row.page_dimensions or {},
        payload=row.payload or {},
        source_method=row.source_method,
        status=row.status,
        version=row.version,
        created_at=row.created_at.isoformat(),
        reviewed_at=row.reviewed_at.isoformat() if row.reviewed_at else None,
    )


def _geometry_valid(geometry: dict) -> bool:
    if not isinstance(geometry, dict):
        return False
    if all(k in geometry for k in ("x", "y", "width", "height")):
        try:
            return float(geometry["width"]) > 0 and float(geometry["height"]) > 0
        except (TypeError, ValueError):
            return False
    if all(k in geometry for k in ("x1", "y1", "x2", "y2")):
        try:
            return float(geometry["x2"]) > float(geometry["x1"]) and float(geometry["y2"]) > float(geometry["y1"])
        except (TypeError, ValueError):
            return False
    bbox = geometry.get("bbox")
    if isinstance(bbox, list) and len(bbox) == 4:
        try:
            return float(bbox[2]) > 0 and float(bbox[3]) > 0
        except (TypeError, ValueError):
            return False
    points = geometry.get("points")
    if isinstance(points, list) and len(points) >= 3:
        valid = 0
        for point in points:
            if isinstance(point, dict) and "x" in point and "y" in point:
                valid += 1
            elif isinstance(point, (list, tuple)) and len(point) >= 2:
                valid += 1
        return valid >= 3
    return False


def _validate_reference_payload(payload: dict) -> None:
    if not isinstance(payload, dict):
        raise HTTPException(status_code=422, detail="annotation payload must be an object")
    for key in ("elements", "equipment_candidates", "fact_candidates"):
        value = payload.get(key, [])
        if not isinstance(value, list):
            raise HTTPException(status_code=422, detail=f"{key} must be a list")

    seen_refs: set[str] = set()
    for index, element in enumerate(payload.get("elements", [])):
        if not isinstance(element, dict):
            raise HTTPException(status_code=422, detail=f"elements[{index}] must be an object")
        geometry = element.get("geometry") or {}
        if not _geometry_valid(geometry):
            raise HTTPException(status_code=422, detail=f"elements[{index}] requires valid geometry")
        client_ref = str(element.get("client_ref") or "").strip()
        if client_ref:
            if client_ref in seen_refs:
                raise HTTPException(status_code=422, detail=f"duplicate client_ref: {client_ref}")
            seen_refs.add(client_ref)

        if str(element.get("element_type") or "").strip() == "room":
            extracted = element.get("extracted_data") or {}
            room_label = str(element.get("label") or "").strip()
            use_name = str(extracted.get("use_name") or "").strip() if isinstance(extracted, dict) else ""
            if not room_label and not use_name:
                raise HTTPException(
                    status_code=422,
                    detail=f"room element {client_ref or index} requires label or extracted_data.use_name",
                )


def _require_analysis(db: Session, analysis_id: str) -> DrawingAnalysis:
    row = db.get(DrawingAnalysis, analysis_id)
    if not row:
        raise HTTPException(status_code=404, detail="drawing analysis not found")
    return row


@router.get(
    "/drawing-analyses/{analysis_id}/annotations",
    response_model=list[DrawingAnnotationSetOut],
)
def list_annotations(
    analysis_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("drawing.read")),
):
    _require_analysis(db, analysis_id)
    rows = db.scalars(
        select(DrawingAnnotationSet)
        .where(DrawingAnnotationSet.drawing_analysis_id == analysis_id)
        .order_by(DrawingAnnotationSet.created_at.desc())
    ).all()
    return [_annotation_out(x) for x in rows]


@router.post(
    "/drawing-analyses/{analysis_id}/annotations",
    response_model=DrawingAnnotationSetOut,
    status_code=201,
)
def create_annotation(
    analysis_id: str,
    payload: DrawingAnnotationSetCreate,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("drawing.review")),
):
    _require_analysis(db, analysis_id)
    body = payload.payload
    if not isinstance(body, dict):
        raise HTTPException(status_code=422, detail="payload must be an object")
    try:
        body, page_dimensions = apply_geometry_metrics(
            body,
            payload.page_dimensions,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    row = DrawingAnnotationSet(
        drawing_analysis_id=analysis_id,
        annotation_kind="human_reference",
        coordinate_space=payload.coordinate_space,
        page_dimensions=page_dimensions,
        payload=body,
        source_method=payload.source_method,
        status="draft",
        created_by=user.user_id,
    )
    db.add(row)
    db.flush()
    write_audit(
        db,
        user_id=user.user_id,
        action="drawing_annotation.create",
        entity_type="drawing_annotation_set",
        entity_id=row.drawing_annotation_set_id,
        after=_annotation_out(row).model_dump(mode="json"),
    )
    db.commit()
    return _annotation_out(row)


@router.post(
    "/drawing-analyses/{analysis_id}/annotations/seed",
    response_model=DrawingAnnotationSetOut,
    status_code=201,
)
def seed_annotation_from_analysis(
    analysis_id: str,
    payload: DrawingAnnotationSeedCreate,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("drawing.review")),
):
    analysis = _require_analysis(db, analysis_id)
    if analysis.version != payload.expected_analysis_version:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"message": "drawing analysis was updated", "current_version": analysis.version},
        )

    elements = db.scalars(
        select(DrawingElement)
        .where(DrawingElement.drawing_analysis_id == analysis_id)
        .order_by(DrawingElement.page_no, DrawingElement.created_at)
    ).all()
    element_ref: dict[str, str] = {}
    element_payload = []
    for index, row in enumerate(elements):
        ref = f"element-{index + 1}"
        element_ref[row.drawing_element_id] = ref
        extracted = dict(row.extracted_data or {})
        element_payload.append(
            {
                "client_ref": ref,
                "page_no": row.page_no,
                "element_type": row.element_type,
                "label": row.label,
                "floor_number": row.floor_number,
                "geometry": row.geometry or {},
                "extracted_data": extracted,
                "confidence": row.confidence,
            }
        )

    equipment = db.scalars(
        select(DrawingEquipmentCandidate)
        .where(DrawingEquipmentCandidate.drawing_analysis_id == analysis_id)
        .order_by(DrawingEquipmentCandidate.created_at)
    ).all()
    equipment_payload = [
        {
            "drawing_element_ref": element_ref.get(row.drawing_element_id),
            "suggested_equipment_type_code": row.suggested_equipment_type_code,
            "suggested_label": row.suggested_label,
            "floor_number": row.floor_number,
            "location_text": row.location_text,
            "quantity": row.quantity,
            "confidence": row.confidence,
        }
        for row in equipment
    ]

    facts = db.scalars(
        select(DrawingFactCandidate)
        .where(DrawingFactCandidate.drawing_analysis_id == analysis_id)
        .order_by(DrawingFactCandidate.created_at)
    ).all()
    fact_payload = [
        {
            "drawing_element_ref": element_ref.get(row.drawing_element_id),
            "target_path": row.target_path,
            "proposed_value": row.proposed_value,
            "confidence": row.confidence,
            "evidence": row.evidence or {},
        }
        for row in facts
    ]

    try:
        seed_payload, page_dimensions = apply_geometry_metrics(
            {
                "elements": element_payload,
                "equipment_candidates": equipment_payload,
                "fact_candidates": fact_payload,
            },
            payload.page_dimensions,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))

    row = DrawingAnnotationSet(
        drawing_analysis_id=analysis_id,
        annotation_kind="human_reference",
        coordinate_space=payload.coordinate_space,
        page_dimensions=page_dimensions,
        payload=seed_payload,
        source_method="ai_seed",
        status="draft",
        created_by=user.user_id,
    )
    db.add(row)
    db.flush()
    write_audit(
        db,
        user_id=user.user_id,
        action="drawing_annotation.seed",
        entity_type="drawing_annotation_set",
        entity_id=row.drawing_annotation_set_id,
        after={
            "drawing_analysis_id": analysis_id,
            "element_count": len(element_payload),
            "equipment_candidate_count": len(equipment_payload),
            "fact_candidate_count": len(fact_payload),
        },
        ai_used=analysis.analysis_method == "ai",
        ai_model_version=analysis.model_version,
    )
    db.commit()
    return _annotation_out(row)


@router.put("/drawing-annotations/{annotation_id}", response_model=DrawingAnnotationSetOut)
def update_annotation(
    annotation_id: str,
    payload: DrawingAnnotationSetUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("drawing.review")),
):
    current = db.get(DrawingAnnotationSet, annotation_id)
    if not current:
        raise HTTPException(status_code=404, detail="drawing annotation set not found")
    if current.status != "draft":
        raise HTTPException(status_code=409, detail="only draft annotations can be edited")

    try:
        normalized_payload, page_dimensions = apply_geometry_metrics(
            payload.payload,
            payload.page_dimensions,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))

    values = {
        "coordinate_space": payload.coordinate_space,
        "page_dimensions": page_dimensions,
        "payload": normalized_payload,
        "version": payload.expected_version + 1,
        "updated_at": datetime.now(timezone.utc),
    }
    result = db.execute(
        update(DrawingAnnotationSet)
        .where(
            DrawingAnnotationSet.drawing_annotation_set_id == annotation_id,
            DrawingAnnotationSet.version == payload.expected_version,
        )
        .values(**values)
    )
    if result.rowcount != 1:
        db.rollback()
        raise HTTPException(status_code=409, detail="drawing annotation was updated by another user")
    row = db.get(DrawingAnnotationSet, annotation_id)
    write_audit(
        db,
        user_id=user.user_id,
        action="drawing_annotation.update",
        entity_type="drawing_annotation_set",
        entity_id=annotation_id,
        after={"version": row.version},
    )
    db.commit()
    return _annotation_out(row)


@router.post("/drawing-annotations/{annotation_id}/review", response_model=DrawingAnnotationSetOut)
def review_annotation(
    annotation_id: str,
    payload: DrawingAnnotationReview,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("drawing.review")),
):
    current = db.get(DrawingAnnotationSet, annotation_id)
    if not current:
        raise HTTPException(status_code=404, detail="drawing annotation set not found")
    if current.status != "draft":
        raise HTTPException(status_code=409, detail="only draft annotations can be reviewed")
    if payload.status == "reviewed":
        try:
            normalized_payload, page_dimensions = apply_geometry_metrics(
                current.payload or {},
                current.page_dimensions or {},
            )
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc))
        _validate_reference_payload(normalized_payload)
    else:
        normalized_payload = current.payload or {}
        page_dimensions = current.page_dimensions or {}

    result = db.execute(
        update(DrawingAnnotationSet)
        .where(
            DrawingAnnotationSet.drawing_annotation_set_id == annotation_id,
            DrawingAnnotationSet.version == payload.expected_version,
            DrawingAnnotationSet.status == "draft",
        )
        .values(
            status=payload.status,
            payload=normalized_payload,
            page_dimensions=page_dimensions,
            version=payload.expected_version + 1,
            reviewed_by=user.user_id,
            reviewed_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
    )
    if result.rowcount != 1:
        db.rollback()
        raise HTTPException(status_code=409, detail="drawing annotation was updated by another user")
    row = db.get(DrawingAnnotationSet, annotation_id)
    write_audit(
        db,
        user_id=user.user_id,
        action=f"drawing_annotation.{payload.status}",
        entity_type="drawing_annotation_set",
        entity_id=annotation_id,
        after={"status": row.status, "version": row.version},
    )
    db.commit()
    return _annotation_out(row)


@router.get("/drawing-annotations/{annotation_id}/benchmark-reference")
def export_benchmark_reference(
    annotation_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("drawing.read")),
):
    row = db.get(DrawingAnnotationSet, annotation_id)
    if not row:
        raise HTTPException(status_code=404, detail="drawing annotation set not found")
    if row.status != "reviewed":
        raise HTTPException(status_code=409, detail="only reviewed annotations can be exported")

    analysis = db.get(DrawingAnalysis, row.drawing_analysis_id)
    if not analysis:
        raise HTTPException(status_code=409, detail="drawing analysis missing")
    document = db.get(Document, analysis.document_id)
    if not document:
        raise HTTPException(status_code=409, detail="source drawing document missing")

    body = row.payload or {}
    return {
        "reference_format": "fire-ai-drawing-human-reference-v1",
        "drawing_annotation_set_id": row.drawing_annotation_set_id,
        "drawing_analysis_id": row.drawing_analysis_id,
        "source": {
            "document_id": document.document_id,
            "filename": document.original_filename,
            "sha256": document.sha256,
        },
        "coordinate_space": row.coordinate_space,
        "page_dimensions": row.page_dimensions or {},
        "elements": body.get("elements", []),
        "equipment_candidates": body.get("equipment_candidates", []),
        "fact_candidates": body.get("fact_candidates", []),
        "human_review": {
            "status": row.status,
            "reviewed_at": row.reviewed_at.isoformat() if row.reviewed_at else None,
        },
    }
