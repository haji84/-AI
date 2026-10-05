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
from ..models import FireAudioBenchmarkRun, User
from ..schemas import (
    FireAudioBenchmarkComparisonOut,
    FireAudioBenchmarkRunCreate,
    FireAudioBenchmarkRunOut,
    FireAudioBenchmarkRunReview,
)

router = APIRouter(
    prefix="/fire-investigations/audio-benchmarks",
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
    if fmt != "fire-ai-japanese-stt-benchmark-v2":
        raise HTTPException(status_code=422, detail="unsupported benchmark_format")
    manifest_sha = payload.get("manifest_sha256")
    if manifest_sha is not None and (not isinstance(manifest_sha, str) or len(manifest_sha) != 64):
        raise HTTPException(status_code=422, detail="invalid manifest_sha256")
    aggregate = payload.get("aggregate")
    if aggregate is not None:
        if not isinstance(aggregate, dict):
            raise HTTPException(status_code=422, detail="aggregate must be an object")
        recording_count = int(aggregate.get("recording_count", 0))
    else:
        recording_count = 1
    if recording_count < 1:
        raise HTTPException(status_code=422, detail="recording_count must be >= 1")
    return fmt, manifest_sha, recording_count


def _metric_triplet(payload: dict) -> dict:
    aggregate = payload.get("aggregate")
    if isinstance(aggregate, dict):
        return {
            "cer": float((aggregate.get("text_micro") or {}).get("cer", 0)),
            "speaker_error_rate": float((aggregate.get("diarization_micro") or {}).get("speaker_error_rate", 0)),
            "uncertainty_f1": float((aggregate.get("uncertainty_markers_micro") or {}).get("f1", 0)),
        }
    return {
        "cer": float((payload.get("text") or {}).get("cer", 0)),
        "speaker_error_rate": float((payload.get("diarization") or {}).get("speaker_error_rate", 0)),
        "uncertainty_f1": float((payload.get("uncertainty_markers") or {}).get("f1", 0)),
    }


def _out(row: FireAudioBenchmarkRun) -> FireAudioBenchmarkRunOut:
    return FireAudioBenchmarkRunOut(
        fire_audio_benchmark_run_id=row.fire_audio_benchmark_run_id,
        benchmark_format=row.benchmark_format,
        dataset_label=row.dataset_label,
        manifest_sha256=row.manifest_sha256,
        result_sha256=row.result_sha256,
        recording_count=row.recording_count,
        result_payload=row.result_payload,
        review_status=row.review_status,
        human_decision=row.human_decision,
        review_notes=row.review_notes,
        version=row.version,
        created_at=row.created_at.isoformat(),
        reviewed_at=row.reviewed_at.isoformat() if row.reviewed_at else None,
    )


@router.get("/compare", response_model=FireAudioBenchmarkComparisonOut)
def compare_audio_benchmarks(
    left_id: str,
    right_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("fire_investigation.read")),
):
    left = db.get(FireAudioBenchmarkRun, left_id)
    right = db.get(FireAudioBenchmarkRun, right_id)
    if not left or not right:
        raise HTTPException(status_code=404, detail="audio benchmark run not found")
    lm = _metric_triplet(left.result_payload or {})
    rm = _metric_triplet(right.result_payload or {})
    return FireAudioBenchmarkComparisonOut(
        left_id=left.fire_audio_benchmark_run_id,
        right_id=right.fire_audio_benchmark_run_id,
        left_dataset_label=left.dataset_label,
        right_dataset_label=right.dataset_label,
        left_review_status=left.review_status,
        right_review_status=right.review_status,
        metrics={
            "cer": {
                "left": lm["cer"],
                "right": rm["cer"],
                "delta_right_minus_left": rm["cer"] - lm["cer"],
                "lower_is_better": True,
            },
            "speaker_error_rate": {
                "left": lm["speaker_error_rate"],
                "right": rm["speaker_error_rate"],
                "delta_right_minus_left": rm["speaker_error_rate"] - lm["speaker_error_rate"],
                "lower_is_better": True,
            },
            "uncertainty_f1": {
                "left": lm["uncertainty_f1"],
                "right": rm["uncertainty_f1"],
                "delta_right_minus_left": rm["uncertainty_f1"] - lm["uncertainty_f1"],
                "higher_is_better": True,
            },
        },
        note=(
            "Metric deltas show benchmark movement only. Dataset composition and recording metadata "
            "must be comparable before treating a delta as a model-quality change."
        ),
    )


@router.get("", response_model=list[FireAudioBenchmarkRunOut])
def list_audio_benchmarks(
    limit: int = 100,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("fire_investigation.read")),
):
    rows = db.scalars(
        select(FireAudioBenchmarkRun)
        .order_by(FireAudioBenchmarkRun.created_at.desc())
        .limit(max(1, min(limit, 500)))
    ).all()
    return [_out(x) for x in rows]


@router.post("", response_model=FireAudioBenchmarkRunOut, status_code=201)
def create_audio_benchmark(
    payload: FireAudioBenchmarkRunCreate,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("fire_investigation.update")),
):
    fmt, manifest_sha, recording_count = _validate_result(payload.result_payload)
    digest = _canonical_sha(payload.result_payload)
    existing = db.scalar(
        select(FireAudioBenchmarkRun).where(
            FireAudioBenchmarkRun.result_sha256 == digest
        )
    )
    if existing:
        return _out(existing)

    row = FireAudioBenchmarkRun(
        benchmark_format=fmt,
        dataset_label=payload.dataset_label,
        manifest_sha256=manifest_sha,
        result_sha256=digest,
        recording_count=recording_count,
        result_payload=payload.result_payload,
        created_by=user.user_id,
    )
    db.add(row)
    db.flush()
    write_audit(
        db,
        user_id=user.user_id,
        action="fire_audio_benchmark.create",
        entity_type="fire_audio_benchmark_run",
        entity_id=row.fire_audio_benchmark_run_id,
        after={
            "benchmark_format": row.benchmark_format,
            "dataset_label": row.dataset_label,
            "recording_count": row.recording_count,
            "result_sha256": row.result_sha256,
        },
    )
    db.commit()
    return _out(row)


@router.post("/{benchmark_id}/review", response_model=FireAudioBenchmarkRunOut)
def review_audio_benchmark(
    benchmark_id: str,
    payload: FireAudioBenchmarkRunReview,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("fire_investigation.review")),
):
    current = db.get(FireAudioBenchmarkRun, benchmark_id)
    if not current:
        raise HTTPException(status_code=404, detail="audio benchmark run not found")
    if current.review_status != "pending":
        raise HTTPException(status_code=409, detail="audio benchmark run already reviewed")

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
        update(FireAudioBenchmarkRun)
        .where(
            FireAudioBenchmarkRun.fire_audio_benchmark_run_id == benchmark_id,
            FireAudioBenchmarkRun.version == payload.expected_version,
        )
        .values(**values)
    )
    if result.rowcount != 1:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="audio benchmark run was updated by another user",
        )
    row = db.get(FireAudioBenchmarkRun, benchmark_id)
    write_audit(
        db,
        user_id=user.user_id,
        action="fire_audio_benchmark.review",
        entity_type="fire_audio_benchmark_run",
        entity_id=benchmark_id,
        after={
            "human_decision": row.human_decision,
            "version": row.version,
        },
    )
    db.commit()
    return _out(row)
