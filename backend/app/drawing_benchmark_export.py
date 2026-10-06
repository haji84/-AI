from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import (
    Document,
    DrawingAnalysis,
    DrawingAnnotationSet,
    DrawingElement,
    DrawingEquipmentCandidate,
    DrawingFactCandidate,
)


HYPOTHESIS_FORMAT = "fire-ai-drawing-hypothesis-v1"
REFERENCE_FORMAT = "fire-ai-drawing-human-reference-v1"



def build_drawing_reference(
    db: Session,
    annotation: DrawingAnnotationSet,
) -> dict:
    if annotation.status != "reviewed":
        raise ValueError(
            "benchmark Reference requires a reviewed Human Annotation"
        )
    analysis = db.get(
        DrawingAnalysis,
        annotation.drawing_analysis_id,
    )
    if not analysis:
        raise ValueError("drawing analysis missing")
    document = db.get(Document, analysis.document_id)
    if not document:
        raise ValueError("source drawing document missing")

    body = annotation.payload or {}
    return {
        "reference_format": REFERENCE_FORMAT,
        "drawing_annotation_set_id":
            annotation.drawing_annotation_set_id,
        "drawing_analysis_id":
            annotation.drawing_analysis_id,
        "source": {
            "document_id": document.document_id,
            "filename": document.original_filename,
            "sha256": document.sha256,
            "mime_type": document.mime_type,
        },
        "coordinate_space":
            annotation.coordinate_space,
        "page_dimensions":
            annotation.page_dimensions or {},
        "elements": body.get("elements", []),
        "equipment_candidates":
            body.get("equipment_candidates", []),
        "fact_candidates":
            body.get("fact_candidates", []),
        "human_review": {
            "status": annotation.status,
            "reviewed_at": (
                annotation.reviewed_at.isoformat()
                if annotation.reviewed_at
                else None
            ),
        },
    }

def build_drawing_hypothesis(
    db: Session,
    analysis: DrawingAnalysis,
) -> dict:
    if analysis.analysis_method != "ai":
        raise ValueError(
            "benchmark Hypothesis requires analysis_method=ai"
        )
    if analysis.status not in {"analyzed", "reviewed"}:
        raise ValueError(
            "benchmark Hypothesis requires an analyzed/reviewed DrawingAnalysis"
        )
    if not analysis.model_version:
        raise ValueError(
            "benchmark Hypothesis requires model_version"
        )

    document = db.get(Document, analysis.document_id)
    if not document:
        raise ValueError("source drawing document missing")

    elements = db.scalars(
        select(DrawingElement)
        .where(
            DrawingElement.drawing_analysis_id
            == analysis.drawing_analysis_id
        )
        .order_by(
            DrawingElement.page_no,
            DrawingElement.created_at,
            DrawingElement.drawing_element_id,
        )
    ).all()
    equipment = db.scalars(
        select(DrawingEquipmentCandidate)
        .where(
            DrawingEquipmentCandidate.drawing_analysis_id
            == analysis.drawing_analysis_id
        )
        .order_by(
            DrawingEquipmentCandidate.created_at,
            DrawingEquipmentCandidate.drawing_equipment_candidate_id,
        )
    ).all()
    facts = db.scalars(
        select(DrawingFactCandidate)
        .where(
            DrawingFactCandidate.drawing_analysis_id
            == analysis.drawing_analysis_id
        )
        .order_by(
            DrawingFactCandidate.created_at,
            DrawingFactCandidate.drawing_fact_candidate_id,
        )
    ).all()

    element_ref = {
        row.drawing_element_id: row.drawing_element_id
        for row in elements
    }

    return {
        "hypothesis_format": HYPOTHESIS_FORMAT,
        "drawing_analysis_id": analysis.drawing_analysis_id,
        "analysis_version": analysis.version,
        "analysis_status": analysis.status,
        "analysis_method": analysis.analysis_method,
        "model_version": analysis.model_version,
        "page_count": analysis.page_count,
        "confidence": analysis.confidence,
        "summary": analysis.summary or {},
        "evidence": analysis.evidence or {},
        "source": {
            "document_id": document.document_id,
            "filename": document.original_filename,
            "sha256": document.sha256,
            "mime_type": document.mime_type,
        },
        "elements": [
            {
                "client_ref": row.drawing_element_id,
                "page_no": row.page_no,
                "element_type": row.element_type,
                "label": row.label,
                "floor_number": row.floor_number,
                "geometry": row.geometry or {},
                "extracted_data": row.extracted_data or {},
                "confidence": row.confidence,
                "source_kind": row.source_kind,
                "review_status": row.review_status,
            }
            for row in elements
        ],
        "equipment_candidates": [
            {
                "drawing_element_ref":
                    element_ref.get(row.drawing_element_id),
                "suggested_equipment_type_code":
                    row.suggested_equipment_type_code,
                "suggested_label": row.suggested_label,
                "floor_number": row.floor_number,
                "location_text": row.location_text,
                "quantity": row.quantity,
                "confidence": row.confidence,
                "status": row.status,
            }
            for row in equipment
        ],
        "fact_candidates": [
            {
                "drawing_element_ref":
                    element_ref.get(row.drawing_element_id),
                "target_path": row.target_path,
                "proposed_value": row.proposed_value,
                "confidence": row.confidence,
                "evidence": row.evidence or {},
                "status": row.status,
            }
            for row in facts
        ],
        "policy": (
            "This payload is an AI Hypothesis, not Human truth. "
            "Benchmarking still requires a Human-accepted Reference "
            "for the same source drawing."
        ),
    }
