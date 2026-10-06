from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from .drawing_baseline_readiness import (
    drawing_baseline_readiness,
)
from .drawing_benchmark_core import (
    FORMAT_VERSION,
    aggregate_drawings,
    canonical_json_sha,
    score_payload_pair,
)
from .drawing_benchmark_export import (
    build_drawing_hypothesis,
    build_drawing_reference,
)
from .models import (
    DrawingAnalysis,
    DrawingAnnotationSet,
    DrawingBenchmarkRun,
)


def run_drawing_baseline(
    db: Session,
    *,
    analysis: DrawingAnalysis,
    iou_threshold: float,
    dataset_label: str | None,
    created_by: str | None,
) -> tuple[DrawingBenchmarkRun, bool]:
    if not 0 < iou_threshold <= 1:
        raise ValueError(
            "iou_threshold must be > 0 and <= 1"
        )

    readiness = drawing_baseline_readiness(
        db,
        analysis=analysis,
    )
    if not readiness.get("geometry_baseline_ready"):
        codes = [
            row.get("code")
            for row in readiness.get("blockers") or []
        ]
        raise ValueError(
            "drawing Baseline is not ready: "
            + ", ".join(
                str(x) for x in codes if x
            )
        )

    annotation_id = (
        readiness.get("human_reference") or {}
    ).get("annotation_id")
    annotation = (
        db.get(DrawingAnnotationSet, annotation_id)
        if annotation_id else None
    )
    if annotation is None:
        raise ValueError(
            "selected Human Reference Annotation is missing"
        )

    reference = build_drawing_reference(
        db,
        annotation,
    )
    hypothesis = build_drawing_hypothesis(
        db,
        analysis,
    )

    source = reference.get("source") or {}
    source_sha = source.get("sha256")
    manifest = {
        "execution_mode": "in_app",
        "drawing_analysis_id":
            analysis.drawing_analysis_id,
        "analysis_version": analysis.version,
        "drawing_annotation_set_id":
            annotation.drawing_annotation_set_id,
        "annotation_version": annotation.version,
        "source_document_id":
            source.get("document_id"),
        "source_sha256": source_sha,
        "model_version": analysis.model_version,
        "iou_threshold": iou_threshold,
    }
    manifest_sha = canonical_json_sha(manifest)

    pair = score_payload_pair(
        reference,
        hypothesis,
        drawing_id=analysis.drawing_analysis_id,
        metadata={
            "execution_mode": "in_app",
            "source_filename":
                source.get("filename"),
            "source_sha256": source_sha,
            "model_version":
                analysis.model_version,
            "annotation_id":
                annotation.drawing_annotation_set_id,
            "annotation_version":
                annotation.version,
            "analysis_version":
                analysis.version,
        },
        iou_threshold=iou_threshold,
    )
    pair["reference"] = {
        "drawing_annotation_set_id":
            annotation.drawing_annotation_set_id,
        "annotation_version":
            annotation.version,
        "endpoint": (
            "/drawing-annotations/"
            f"{annotation.drawing_annotation_set_id}"
            "/benchmark-reference"
        ),
    }
    pair["hypothesis"] = {
        "drawing_analysis_id":
            analysis.drawing_analysis_id,
        "analysis_version": analysis.version,
        "model_version": analysis.model_version,
        "endpoint": (
            "/drawing-analyses/"
            f"{analysis.drawing_analysis_id}"
            "/benchmark-hypothesis"
        ),
    }

    aggregate = aggregate_drawings(
        [pair],
        iou_threshold,
    )
    result_payload = {
        "benchmark_format": FORMAT_VERSION,
        "execution_mode": "in_app",
        "manifest_sha256": manifest_sha,
        "manifest": manifest,
        "iou_threshold": iou_threshold,
        "drawings": [pair],
        "aggregate": aggregate,
        "readiness_evidence": {
            "geometry_baseline_ready":
                readiness.get(
                    "geometry_baseline_ready"
                ),
            "area_measurement_ready":
                readiness.get(
                    "area_measurement_ready"
                ),
            "warnings":
                readiness.get("warnings") or [],
        },
        "policy": (
            "In-app drawing Baseline evidence only. "
            "The persisted Benchmark Run remains pending "
            "until separate Human Baseline review."
        ),
    }
    result_sha = canonical_json_sha(result_payload)

    existing = db.scalar(
        select(DrawingBenchmarkRun).where(
            DrawingBenchmarkRun.result_sha256
            == result_sha
        )
    )
    if existing is not None:
        return existing, False

    label = (
        (dataset_label or "").strip()
        or (
            "Drawing Baseline / "
            f"{source.get('filename') or analysis.drawing_analysis_id} "
            f"/ {analysis.model_version}"
        )
    )
    if len(label) > 300:
        label = label[:300]

    row = DrawingBenchmarkRun(
        benchmark_format=FORMAT_VERSION,
        dataset_label=label,
        manifest_sha256=manifest_sha,
        result_sha256=result_sha,
        drawing_count=1,
        result_payload=result_payload,
        created_by=created_by,
    )
    db.add(row)
    db.flush()
    return row, True
