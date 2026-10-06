from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from .drawing_benchmark_export import build_drawing_hypothesis
from .models import (
    Document,
    DrawingAnalysis,
    DrawingAnnotationSet,
)


READINESS_FORMAT = "fire-ai-drawing-baseline-readiness-v1"


def _page_calibration_status(
    annotation: DrawingAnnotationSet,
) -> tuple[list[int], list[int]]:
    payload = annotation.payload or {}
    elements = [
        x for x in (payload.get("elements") or [])
        if isinstance(x, dict)
        and x.get("geometry")
    ]
    pages = sorted(
        {
            int(x.get("page_no", 1) or 1)
            for x in elements
        }
    )
    calibrated = []
    dimensions = annotation.page_dimensions or {}
    for page_no in pages:
        page = (
            dimensions.get(str(page_no))
            or dimensions.get(page_no)
            or {}
        )
        calibration = (
            page.get("calibration")
            if isinstance(page, dict)
            else None
        )
        meters_per_pixel = (
            calibration.get("meters_per_pixel")
            if isinstance(calibration, dict)
            else None
        )
        try:
            ready = (
                meters_per_pixel is not None
                and float(meters_per_pixel) > 0
            )
        except (TypeError, ValueError):
            ready = False
        if ready:
            calibrated.append(page_no)
    return pages, calibrated


def drawing_baseline_readiness(
    db: Session,
    *,
    analysis: DrawingAnalysis,
) -> dict:
    document = db.get(Document, analysis.document_id)
    annotations = db.scalars(
        select(DrawingAnnotationSet)
        .where(
            DrawingAnnotationSet.drawing_analysis_id
            == analysis.drawing_analysis_id
        )
        .order_by(
            DrawingAnnotationSet.reviewed_at.desc(),
            DrawingAnnotationSet.created_at.desc(),
        )
    ).all()
    reviewed = [
        row for row in annotations if row.status == "reviewed"
    ]
    drafts = [
        row for row in annotations if row.status == "draft"
    ]
    reference = reviewed[0] if reviewed else None

    blockers: list[dict] = []
    warnings: list[dict] = []

    if document is None:
        blockers.append(
            {
                "code": "source_document_missing",
                "message": "Source drawing Document is missing.",
            }
        )

    if reference is None:
        blockers.append(
            {
                "code": "human_reference_missing",
                "message": (
                    "No Human-reviewed drawing Annotation is available."
                ),
            }
        )
    elif len(reviewed) > 1:
        warnings.append(
            {
                "code": "multiple_reviewed_references",
                "message": (
                    "Multiple reviewed Annotations exist. "
                    "The most recently reviewed one is selected."
                ),
                "count": len(reviewed),
            }
        )

    reference_element_count = 0
    reference_fact_count = 0
    reference_equipment_count = 0
    used_pages: list[int] = []
    calibrated_pages: list[int] = []
    if reference is not None:
        body = reference.payload or {}
        reference_element_count = len(
            body.get("elements") or []
        )
        reference_fact_count = len(
            body.get("fact_candidates") or []
        )
        reference_equipment_count = len(
            body.get("equipment_candidates") or []
        )
        used_pages, calibrated_pages = (
            _page_calibration_status(reference)
        )
        if reference_element_count < 1:
            blockers.append(
                {
                    "code": "human_reference_geometry_empty",
                    "message": (
                        "Reviewed Human Reference has no geometry elements."
                    ),
                }
            )

    hypothesis = None
    hypothesis_error = None
    try:
        hypothesis = build_drawing_hypothesis(
            db,
            analysis,
        )
    except ValueError as exc:
        hypothesis_error = str(exc)
        blockers.append(
            {
                "code": "ai_hypothesis_not_ready",
                "message": hypothesis_error,
            }
        )

    source_sha = document.sha256 if document else None
    hypothesis_sha = (
        (hypothesis.get("source") or {}).get("sha256")
        if hypothesis
        else None
    )
    source_match = bool(
        source_sha
        and hypothesis_sha
        and source_sha == hypothesis_sha
    )
    if hypothesis is not None and not source_match:
        blockers.append(
            {
                "code": "source_sha_mismatch",
                "message": (
                    "AI Hypothesis source SHA-256 does not match "
                    "the source drawing Document."
                ),
                "document_sha256": source_sha,
                "hypothesis_sha256": hypothesis_sha,
            }
        )

    geometry_ready = not any(
        row["code"] in {
            "source_document_missing",
            "human_reference_missing",
            "human_reference_geometry_empty",
            "ai_hypothesis_not_ready",
            "source_sha_mismatch",
        }
        for row in blockers
    )

    uncalibrated_pages = sorted(
        set(used_pages) - set(calibrated_pages)
    )
    area_measurement_ready = bool(
        geometry_ready
        and used_pages
        and not uncalibrated_pages
    )

    if geometry_ready and uncalibrated_pages:
        warnings.append(
            {
                "code": "metric_area_uncalibrated",
                "message": (
                    "Geometry Benchmark is ready, but metric area "
                    "measurement is not calibrated on every used page."
                ),
                "uncalibrated_pages": uncalibrated_pages,
            }
        )

    return {
        "readiness_format": READINESS_FORMAT,
        "drawing_analysis_id":
            analysis.drawing_analysis_id,
        "analysis_method": analysis.analysis_method,
        "analysis_status": analysis.status,
        "model_version": analysis.model_version,
        "source": {
            "document_id":
                document.document_id if document else None,
            "filename":
                document.original_filename if document else None,
            "sha256": source_sha,
        },
        "human_reference": {
            "ready": reference is not None,
            "annotation_id": (
                reference.drawing_annotation_set_id
                if reference else None
            ),
            "annotation_version": (
                reference.version if reference else None
            ),
            "reviewed_at": (
                reference.reviewed_at.isoformat()
                if reference and reference.reviewed_at
                else None
            ),
            "element_count": reference_element_count,
            "fact_candidate_count": reference_fact_count,
            "equipment_candidate_count":
                reference_equipment_count,
            "draft_annotation_count": len(drafts),
            "reviewed_annotation_count": len(reviewed),
            "endpoint": (
                "/drawing-annotations/"
                f"{reference.drawing_annotation_set_id}"
                "/benchmark-reference"
                if reference else None
            ),
        },
        "ai_hypothesis": {
            "ready": hypothesis is not None,
            "error": hypothesis_error,
            "element_count": (
                len(hypothesis.get("elements") or [])
                if hypothesis else 0
            ),
            "fact_candidate_count": (
                len(
                    hypothesis.get("fact_candidates")
                    or []
                )
                if hypothesis else 0
            ),
            "equipment_candidate_count": (
                len(
                    hypothesis.get("equipment_candidates")
                    or []
                )
                if hypothesis else 0
            ),
            "source_sha256": hypothesis_sha,
            "source_match": source_match,
            "endpoint": (
                "/drawing-analyses/"
                f"{analysis.drawing_analysis_id}"
                "/benchmark-hypothesis"
                if hypothesis else None
            ),
        },
        "area_measurement": {
            "ready": area_measurement_ready,
            "used_pages": used_pages,
            "calibrated_pages": calibrated_pages,
            "uncalibrated_pages": uncalibrated_pages,
        },
        "geometry_baseline_ready": geometry_ready,
        "area_measurement_ready":
            area_measurement_ready,
        "blockers": blockers,
        "warnings": warnings,
        "policy": (
            "Geometry Baseline is ready only when a Human-reviewed "
            "Reference and an exportable AI Hypothesis exist for the "
            "same source drawing. Metric-area readiness additionally "
            "requires page calibration."
        ),
    }
