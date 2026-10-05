from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from ..audit import write_audit
from ..authz import require_permission
from ..db import get_db
from ..models import DrawingBenchmarkRun, User
from ..schemas import (
    DrawingBenchmarkComparisonOut,
    DrawingBenchmarkRunCreate,
    DrawingBenchmarkRunOut,
    DrawingBenchmarkRunReview,
)

router = APIRouter(prefix="/drawing-benchmarks", tags=["drawings"])


def _canonical_sha(payload: dict) -> str:
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _validate_result(payload: dict) -> tuple[str, str | None, int]:
    if not isinstance(payload, dict):
        raise HTTPException(status_code=422, detail="result_payload must be an object")
    fmt = str(payload.get("benchmark_format") or "")
    if fmt != "fire-ai-drawing-benchmark-v1":
        raise HTTPException(status_code=422, detail="unsupported benchmark_format")
    manifest_sha = payload.get("manifest_sha256")
    if manifest_sha is not None and (not isinstance(manifest_sha, str) or len(manifest_sha) != 64):
        raise HTTPException(status_code=422, detail="invalid manifest_sha256")
    aggregate = payload.get("aggregate")
    if not isinstance(aggregate, dict):
        raise HTTPException(status_code=422, detail="aggregate must be an object")
    drawing_count = int(aggregate.get("drawing_count", 0))
    if drawing_count < 1:
        raise HTTPException(status_code=422, detail="drawing_count must be >= 1")
    geometry = aggregate.get("geometry_detection")
    if not isinstance(geometry, dict):
        raise HTTPException(status_code=422, detail="geometry_detection aggregate is required")
    for key in ("precision", "recall", "f1", "mean_iou", "element_type_accuracy"):
        raw = geometry.get(key)
        if raw is None:
            continue
        value = float(raw)
        if not 0 <= value <= 1:
            raise HTTPException(status_code=422, detail=f"{key} must be between 0 and 1")
    return fmt, manifest_sha, drawing_count


def _optional_float(value):
    return None if value is None else float(value)


def _metric_values(payload: dict) -> dict:
    aggregate = payload.get("aggregate") or {}
    geometry = aggregate.get("geometry_detection") or {}
    symbols = aggregate.get("symbol_classification") or {}
    equipment = aggregate.get("equipment_candidates") or {}
    facts = aggregate.get("fact_candidates") or {}
    drawing_count = max(1, int(aggregate.get("drawing_count", 1)))
    return {
        "geometry_f1": _optional_float(geometry.get("f1")),
        "mean_iou": _optional_float(geometry.get("mean_iou")),
        "element_type_accuracy": _optional_float(geometry.get("element_type_accuracy")),
        "symbol_accuracy": _optional_float(symbols.get("accuracy")),
        "equipment_f1": _optional_float(equipment.get("f1")),
        "fact_f1": _optional_float(facts.get("f1")),
        "geometry_false_positives_per_drawing": float(geometry.get("false_positive", 0)) / drawing_count,
    }


def _comparison_metric(left, right, *, higher_is_better: bool) -> dict:
    return {
        "left": left,
        "right": right,
        "delta_right_minus_left": None if left is None or right is None else right - left,
        "higher_is_better": higher_is_better,
        "applicable": left is not None and right is not None,
    }


def _out(row: DrawingBenchmarkRun) -> DrawingBenchmarkRunOut:
    return DrawingBenchmarkRunOut(
        drawing_benchmark_run_id=row.drawing_benchmark_run_id,
        benchmark_format=row.benchmark_format,
        dataset_label=row.dataset_label,
        manifest_sha256=row.manifest_sha256,
        result_sha256=row.result_sha256,
        drawing_count=row.drawing_count,
        result_payload=row.result_payload,
        review_status=row.review_status,
        human_decision=row.human_decision,
        review_notes=row.review_notes,
        version=row.version,
        created_at=row.created_at.isoformat(),
        reviewed_at=row.reviewed_at.isoformat() if row.reviewed_at else None,
    )


@router.get("/compare", response_model=DrawingBenchmarkComparisonOut)
def compare_drawing_benchmarks(
    left_id: str,
    right_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("drawing.read")),
):
    left = db.get(DrawingBenchmarkRun, left_id)
    right = db.get(DrawingBenchmarkRun, right_id)
    if not left or not right:
        raise HTTPException(status_code=404, detail="drawing benchmark run not found")
    lm = _metric_values(left.result_payload or {})
    rm = _metric_values(right.result_payload or {})
    metrics = {}
    for name in ("geometry_f1", "mean_iou", "element_type_accuracy", "symbol_accuracy", "equipment_f1", "fact_f1"):
        metrics[name] = _comparison_metric(lm[name], rm[name], higher_is_better=True)
    name = "geometry_false_positives_per_drawing"
    metrics[name] = {
        "left": lm[name],
        "right": rm[name],
        "delta_right_minus_left": rm[name] - lm[name],
        "lower_is_better": True,
        "applicable": True,
    }
    return DrawingBenchmarkComparisonOut(
        left_id=left.drawing_benchmark_run_id,
        right_id=right.drawing_benchmark_run_id,
        left_dataset_label=left.dataset_label,
        right_dataset_label=right.dataset_label,
        left_review_status=left.review_status,
        right_review_status=right.review_status,
        metrics=metrics,
        note="Compare only materially equivalent Human Reference policy, IoU threshold, drawing mix and image-quality coverage.",
    )


@router.get("", response_model=list[DrawingBenchmarkRunOut])
def list_drawing_benchmarks(
    limit: int = 100,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("drawing.read")),
):
    rows = db.scalars(
        select(DrawingBenchmarkRun)
        .order_by(DrawingBenchmarkRun.created_at.desc())
        .limit(max(1, min(limit, 500)))
    ).all()
    return [_out(x) for x in rows]


@router.post("", response_model=DrawingBenchmarkRunOut, status_code=201)
def create_drawing_benchmark(
    payload: DrawingBenchmarkRunCreate,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("drawing.analyze")),
):
    fmt, manifest_sha, drawing_count = _validate_result(payload.result_payload)
    digest = _canonical_sha(payload.result_payload)
    existing = db.scalar(select(DrawingBenchmarkRun).where(DrawingBenchmarkRun.result_sha256 == digest))
    if existing:
        return _out(existing)
    row = DrawingBenchmarkRun(
        benchmark_format=fmt,
        dataset_label=payload.dataset_label,
        manifest_sha256=manifest_sha,
        result_sha256=digest,
        drawing_count=drawing_count,
        result_payload=payload.result_payload,
        created_by=user.user_id,
    )
    db.add(row)
    db.flush()
    write_audit(
        db,
        user_id=user.user_id,
        action="drawing_benchmark.create",
        entity_type="drawing_benchmark_run",
        entity_id=row.drawing_benchmark_run_id,
        after={
            "benchmark_format": row.benchmark_format,
            "dataset_label": row.dataset_label,
            "drawing_count": row.drawing_count,
            "result_sha256": row.result_sha256,
        },
    )
    db.commit()
    return _out(row)


@router.post("/{benchmark_id}/review", response_model=DrawingBenchmarkRunOut)
def review_drawing_benchmark(
    benchmark_id: str,
    payload: DrawingBenchmarkRunReview,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("drawing.review")),
):
    current = db.get(DrawingBenchmarkRun, benchmark_id)
    if not current:
        raise HTTPException(status_code=404, detail="drawing benchmark run not found")
    if current.review_status != "pending":
        raise HTTPException(status_code=409, detail="drawing benchmark run already reviewed")
    result = db.execute(
        update(DrawingBenchmarkRun)
        .where(
            DrawingBenchmarkRun.drawing_benchmark_run_id == benchmark_id,
            DrawingBenchmarkRun.version == payload.expected_version,
        )
        .values(
            review_status="reviewed",
            human_decision=payload.human_decision,
            review_notes=payload.review_notes,
            reviewed_by=user.user_id,
            reviewed_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
            version=payload.expected_version + 1,
        )
    )
    if result.rowcount != 1:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="drawing benchmark run was updated by another user")
    row = db.get(DrawingBenchmarkRun, benchmark_id)
    write_audit(
        db,
        user_id=user.user_id,
        action="drawing_benchmark.review",
        entity_type="drawing_benchmark_run",
        entity_id=benchmark_id,
        after={"human_decision": row.human_decision, "version": row.version},
    )
    db.commit()
    return _out(row)
