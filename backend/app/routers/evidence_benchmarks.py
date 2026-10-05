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
from ..models import FireEvidenceComparisonBenchmarkRun, User
from ..schemas import (
    FireEvidenceComparisonBenchmarkComparisonOut,
    FireEvidenceComparisonBenchmarkRunCreate,
    FireEvidenceComparisonBenchmarkRunOut,
    FireEvidenceComparisonBenchmarkRunReview,
)


router = APIRouter(
    prefix="/fire-investigations/evidence-comparison-benchmarks",
    tags=["fire-investigations"],
)


def _canonical_sha(payload: dict) -> str:
    raw = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _validate_result(payload: dict) -> tuple[str, str | None, int]:
    if not isinstance(payload, dict):
        raise HTTPException(status_code=422, detail="result_payload must be an object")
    fmt = str(payload.get("benchmark_format") or "")
    if fmt != "fire-ai-evidence-comparison-benchmark-v1":
        raise HTTPException(status_code=422, detail="unsupported benchmark_format")

    manifest_sha = payload.get("manifest_sha256")
    if manifest_sha is not None and (
        not isinstance(manifest_sha, str) or len(manifest_sha) != 64
    ):
        raise HTTPException(status_code=422, detail="invalid manifest_sha256")

    aggregate = payload.get("aggregate")
    if not isinstance(aggregate, dict):
        raise HTTPException(status_code=422, detail="aggregate must be an object")

    case_count = int(aggregate.get("case_count", 0))
    if case_count < 1:
        raise HTTPException(status_code=422, detail="case_count must be >= 1")

    try:
        tp = int(aggregate.get("true_positive", 0))
        fp = int(aggregate.get("false_positive", 0))
        fn = int(aggregate.get("false_negative", 0))
        precision = float(aggregate.get("precision", 0))
        recall = float(aggregate.get("recall", 0))
        f1 = float(aggregate.get("f1", 0))
    except (TypeError, ValueError):
        raise HTTPException(status_code=422, detail="invalid aggregate metrics")

    if min(tp, fp, fn) < 0:
        raise HTTPException(status_code=422, detail="aggregate counts must be non-negative")
    if not all(0 <= x <= 1 for x in (precision, recall, f1)):
        raise HTTPException(status_code=422, detail="precision/recall/f1 must be between 0 and 1")

    reference_count = aggregate.get("reference_count")
    hypothesis_count = aggregate.get("hypothesis_count")
    if reference_count is not None and int(reference_count) != tp + fn:
        raise HTTPException(status_code=422, detail="reference_count does not match TP+FN")
    if hypothesis_count is not None and int(hypothesis_count) != tp + fp:
        raise HTTPException(status_code=422, detail="hypothesis_count does not match TP+FP")

    return fmt, manifest_sha, case_count


def _metrics(payload: dict) -> dict:
    aggregate = payload.get("aggregate") or {}
    case_count = max(1, int(aggregate.get("case_count", 1)))
    return {
        "precision": float(aggregate.get("precision", 0)),
        "recall": float(aggregate.get("recall", 0)),
        "f1": float(aggregate.get("f1", 0)),
        "false_positives_per_case": float(aggregate.get("false_positive", 0)) / case_count,
    }


def _out(row: FireEvidenceComparisonBenchmarkRun) -> FireEvidenceComparisonBenchmarkRunOut:
    return FireEvidenceComparisonBenchmarkRunOut(
        fire_evidence_comparison_benchmark_run_id=row.fire_evidence_comparison_benchmark_run_id,
        benchmark_format=row.benchmark_format,
        dataset_label=row.dataset_label,
        manifest_sha256=row.manifest_sha256,
        result_sha256=row.result_sha256,
        case_count=row.case_count,
        result_payload=row.result_payload,
        review_status=row.review_status,
        human_decision=row.human_decision,
        review_notes=row.review_notes,
        version=row.version,
        created_at=row.created_at.isoformat(),
        reviewed_at=row.reviewed_at.isoformat() if row.reviewed_at else None,
    )


@router.get("/compare", response_model=FireEvidenceComparisonBenchmarkComparisonOut)
def compare_evidence_comparison_benchmarks(
    left_id: str,
    right_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("fire_investigation.read")),
):
    left = db.get(FireEvidenceComparisonBenchmarkRun, left_id)
    right = db.get(FireEvidenceComparisonBenchmarkRun, right_id)
    if not left or not right:
        raise HTTPException(status_code=404, detail="evidence-comparison benchmark run not found")

    lm = _metrics(left.result_payload or {})
    rm = _metrics(right.result_payload or {})
    metrics = {}
    for name in ("precision", "recall", "f1"):
        metrics[name] = {
            "left": lm[name],
            "right": rm[name],
            "delta_right_minus_left": rm[name] - lm[name],
            "higher_is_better": True,
        }
    metrics["false_positives_per_case"] = {
        "left": lm["false_positives_per_case"],
        "right": rm["false_positives_per_case"],
        "delta_right_minus_left": (
            rm["false_positives_per_case"] - lm["false_positives_per_case"]
        ),
        "lower_is_better": True,
    }

    return FireEvidenceComparisonBenchmarkComparisonOut(
        left_id=left.fire_evidence_comparison_benchmark_run_id,
        right_id=right.fire_evidence_comparison_benchmark_run_id,
        left_dataset_label=left.dataset_label,
        right_dataset_label=right.dataset_label,
        left_review_status=left.review_status,
        right_review_status=right.review_status,
        metrics=metrics,
        note=(
            "Metric deltas are comparable only when Human Reference policy, case mix, "
            "issue-type coverage and dataset composition are materially equivalent."
        ),
    )


@router.get("", response_model=list[FireEvidenceComparisonBenchmarkRunOut])
def list_evidence_comparison_benchmarks(
    limit: int = 100,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("fire_investigation.read")),
):
    rows = db.scalars(
        select(FireEvidenceComparisonBenchmarkRun)
        .order_by(FireEvidenceComparisonBenchmarkRun.created_at.desc())
        .limit(max(1, min(limit, 500)))
    ).all()
    return [_out(x) for x in rows]


@router.post("", response_model=FireEvidenceComparisonBenchmarkRunOut, status_code=201)
def create_evidence_comparison_benchmark(
    payload: FireEvidenceComparisonBenchmarkRunCreate,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("fire_investigation.update")),
):
    fmt, manifest_sha, case_count = _validate_result(payload.result_payload)
    digest = _canonical_sha(payload.result_payload)
    existing = db.scalar(
        select(FireEvidenceComparisonBenchmarkRun).where(
            FireEvidenceComparisonBenchmarkRun.result_sha256 == digest
        )
    )
    if existing:
        return _out(existing)

    row = FireEvidenceComparisonBenchmarkRun(
        benchmark_format=fmt,
        dataset_label=payload.dataset_label,
        manifest_sha256=manifest_sha,
        result_sha256=digest,
        case_count=case_count,
        result_payload=payload.result_payload,
        created_by=user.user_id,
    )
    db.add(row)
    db.flush()
    write_audit(
        db,
        user_id=user.user_id,
        action="fire_evidence_comparison_benchmark.create",
        entity_type="fire_evidence_comparison_benchmark_run",
        entity_id=row.fire_evidence_comparison_benchmark_run_id,
        after={
            "benchmark_format": row.benchmark_format,
            "dataset_label": row.dataset_label,
            "case_count": row.case_count,
            "result_sha256": row.result_sha256,
        },
    )
    db.commit()
    return _out(row)


@router.post("/{benchmark_id}/review", response_model=FireEvidenceComparisonBenchmarkRunOut)
def review_evidence_comparison_benchmark(
    benchmark_id: str,
    payload: FireEvidenceComparisonBenchmarkRunReview,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("fire_investigation.review")),
):
    current = db.get(FireEvidenceComparisonBenchmarkRun, benchmark_id)
    if not current:
        raise HTTPException(status_code=404, detail="evidence-comparison benchmark run not found")
    if current.review_status != "pending":
        raise HTTPException(status_code=409, detail="evidence-comparison benchmark run already reviewed")

    values = {
        "review_status": "reviewed",
        "human_decision": payload.human_decision,
        "review_notes": payload.review_notes,
        "reviewed_by": user.user_id,
        "reviewed_at": datetime.now(timezone.utc),
        "updated_at": datetime.now(timezone.utc),
        "version": payload.expected_version + 1,
    }
    result = db.execute(
        update(FireEvidenceComparisonBenchmarkRun)
        .where(
            FireEvidenceComparisonBenchmarkRun.fire_evidence_comparison_benchmark_run_id
            == benchmark_id,
            FireEvidenceComparisonBenchmarkRun.version == payload.expected_version,
        )
        .values(**values)
    )
    if result.rowcount != 1:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="evidence-comparison benchmark run was updated by another user",
        )

    row = db.get(FireEvidenceComparisonBenchmarkRun, benchmark_id)
    write_audit(
        db,
        user_id=user.user_id,
        action="fire_evidence_comparison_benchmark.review",
        entity_type="fire_evidence_comparison_benchmark_run",
        entity_id=benchmark_id,
        after={
            "human_decision": row.human_decision,
            "version": row.version,
        },
    )
    db.commit()
    return _out(row)
