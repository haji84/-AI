from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from ..audit import write_audit
from ..authz import require_permission
from ..db import get_db
from ..models import (
    FireEvidenceComparisonCandidate,
    FireInvestigationAIManifest,
    FireInvestigationCase,
    FireInvestigationMedia,
    FireStatementDraft,
    FireTimelineEvent,
    FireTranscriptSegment,
    User,
)
from ..schemas import (
    FireAIManifestIngestOut,
    FireEvidenceComparisonAIManifest,
    FireEvidenceComparisonOut,
    FireEvidenceComparisonReview,
    FireInvestigationMediaOut,
    FireTranscriptSearchItemOut,
    FireTranscriptSegmentOut,
)

router = APIRouter(prefix="/fire-audio", tags=["fire-audio"])


def _require_case(db: Session, case_id: str) -> FireInvestigationCase:
    row = db.get(FireInvestigationCase, case_id)
    if not row:
        raise HTTPException(status_code=404, detail="fire investigation case not found")
    return row


def _media_out(row: FireInvestigationMedia) -> FireInvestigationMediaOut:
    return FireInvestigationMediaOut(
        fire_investigation_media_id=row.fire_investigation_media_id,
        fire_investigation_case_id=row.fire_investigation_case_id,
        document_id=row.document_id,
        media_type=row.media_type,
        sequence_no=row.sequence_no,
        captured_at=row.captured_at.isoformat() if row.captured_at else None,
        location_label=row.location_label,
        floor_number=row.floor_number,
        notes=row.notes,
        review_status=row.review_status,
        ai_metadata=row.ai_metadata or {},
    )


def _segment_out(row: FireTranscriptSegment) -> FireTranscriptSegmentOut:
    return FireTranscriptSegmentOut(
        fire_transcript_segment_id=row.fire_transcript_segment_id,
        fire_investigation_media_id=row.fire_investigation_media_id,
        start_ms=row.start_ms,
        end_ms=row.end_ms,
        speaker_label=row.speaker_label,
        text=row.text,
        uncertainty_markers=row.uncertainty_markers or [],
        text_sha256=row.text_sha256,
        confidence=row.confidence,
        source_kind=row.source_kind,
        model_version=row.model_version,
        review_status=row.review_status,
        version=row.version,
    )


def _comparison_out(row: FireEvidenceComparisonCandidate) -> FireEvidenceComparisonOut:
    return FireEvidenceComparisonOut(
        fire_evidence_comparison_candidate_id=row.fire_evidence_comparison_candidate_id,
        fire_investigation_case_id=row.fire_investigation_case_id,
        issue_type=row.issue_type,
        summary=row.summary,
        left_ref=row.left_ref or {},
        right_ref=row.right_ref or {},
        evidence_refs=row.evidence_refs or [],
        confidence=row.confidence,
        extraction_method=row.extraction_method,
        model_version=row.model_version,
        status=row.status,
        version=row.version,
    )


def _canonical_hash(payload) -> str:
    body = json.dumps(
        payload.model_dump(mode="json"),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(body.encode("utf-8")).hexdigest()


def _validate_reviewed_ref(db: Session, case_id: str, ref) -> dict:
    ref_type = ref.type
    ref_id = ref.id
    if ref_type == "transcript_segment":
        row = db.get(FireTranscriptSegment, ref_id)
        if not row:
            raise HTTPException(status_code=422, detail=f"transcript segment not found: {ref_id}")
        media = db.get(FireInvestigationMedia, row.fire_investigation_media_id)
        if not media or media.fire_investigation_case_id != case_id:
            raise HTTPException(status_code=422, detail="transcript segment belongs to another case")
        if row.review_status != "accepted":
            raise HTTPException(status_code=409, detail="comparison can use only Human-accepted transcript segments")
        return {
            "type": ref_type,
            "id": ref_id,
            "speaker_label": row.speaker_label,
            "start_ms": row.start_ms,
            "end_ms": row.end_ms,
            "text": row.text,
            "uncertainty_markers": row.uncertainty_markers or [],
        }

    if ref_type == "statement":
        row = db.get(FireStatementDraft, ref_id)
        if not row or row.fire_investigation_case_id != case_id:
            raise HTTPException(status_code=422, detail="statement does not belong to case")
        if row.status != "reviewed":
            raise HTTPException(status_code=409, detail="comparison can use only Human-reviewed statements")
        return {
            "type": ref_type,
            "id": ref_id,
            "person_label": row.person_label,
            "text": row.draft_text,
            "source_uncertainty_markers": row.source_uncertainty_markers or [],
        }

    if ref_type == "timeline_event":
        row = db.get(FireTimelineEvent, ref_id)
        if not row or row.fire_investigation_case_id != case_id:
            raise HTTPException(status_code=422, detail="timeline event does not belong to case")
        if row.status != "confirmed":
            raise HTTPException(status_code=409, detail="comparison can use only Human-confirmed timeline events")
        return {
            "type": ref_type,
            "id": ref_id,
            "event_time": row.event_time.isoformat() if row.event_time else None,
            "event_time_text": row.event_time_text,
            "title": row.title,
            "description": row.description,
        }

    raise HTTPException(status_code=422, detail=f"unsupported evidence ref type: {ref_type}")


@router.get("/cases/{case_id}/search", response_model=list[FireTranscriptSearchItemOut])
def search_transcripts(
    case_id: str,
    q: str,
    accepted_only: bool = True,
    speaker: str | None = None,
    limit: int = 100,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("fire_investigation.read")),
):
    _require_case(db, case_id)
    query = (q or "").strip().lower()
    if not query:
        return []
    terms = [x for x in re.split(r"[\s,、]+", query) if x]

    stmt = (
        select(FireTranscriptSegment, FireInvestigationMedia)
        .join(
            FireInvestigationMedia,
            FireInvestigationMedia.fire_investigation_media_id
            == FireTranscriptSegment.fire_investigation_media_id,
        )
        .where(
            FireInvestigationMedia.fire_investigation_case_id == case_id,
            FireInvestigationMedia.media_type == "audio",
        )
        .order_by(FireTranscriptSegment.start_ms, FireTranscriptSegment.created_at)
    )
    if accepted_only:
        stmt = stmt.where(FireTranscriptSegment.review_status == "accepted")
    if speaker:
        stmt = stmt.where(FireTranscriptSegment.speaker_label == speaker)

    out: list[FireTranscriptSearchItemOut] = []
    for segment, media in db.execute(stmt).all():
        haystack = (segment.search_text or "\n".join([segment.speaker_label or "", segment.text or ""])).lower()
        score = sum(1 for term in terms if term in haystack)
        if score == 0:
            continue
        out.append(
            FireTranscriptSearchItemOut(
                segment=_segment_out(segment),
                media=_media_out(media),
                search_score=score,
            )
        )
    out.sort(key=lambda x: (-x.search_score, x.segment.start_ms if x.segment.start_ms is not None else 10**15))
    return out[: max(1, min(limit, 500))]


@router.post("/cases/{case_id}/comparison-ai-manifest", response_model=FireAIManifestIngestOut)
def ingest_comparison_ai_manifest(
    case_id: str,
    payload: FireEvidenceComparisonAIManifest,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("fire_investigation.update")),
):
    _require_case(db, case_id)
    digest = _canonical_hash(payload)
    scope_key = f"case:{case_id}"
    existing = db.scalar(
        select(FireInvestigationAIManifest).where(
            FireInvestigationAIManifest.scope_key == scope_key,
            FireInvestigationAIManifest.manifest_type == "evidence_comparison",
            FireInvestigationAIManifest.manifest_sha256 == digest,
        )
    )
    if existing:
        ids = list(
            db.scalars(
                select(FireEvidenceComparisonCandidate.fire_evidence_comparison_candidate_id)
                .where(FireEvidenceComparisonCandidate.source_manifest_id == existing.fire_investigation_ai_manifest_id)
                .order_by(FireEvidenceComparisonCandidate.created_at)
            ).all()
        )
        return FireAIManifestIngestOut(
            fire_investigation_ai_manifest_id=existing.fire_investigation_ai_manifest_id,
            manifest_type=existing.manifest_type,
            manifest_sha256=existing.manifest_sha256,
            model_version=existing.model_version,
            created=False,
            derived_ids=ids,
        )

    validated = []
    for item in payload.comparisons:
        if item.left_ref.type == item.right_ref.type and item.left_ref.id == item.right_ref.id:
            raise HTTPException(status_code=422, detail="comparison left_ref and right_ref must differ")
        left = _validate_reviewed_ref(db, case_id, item.left_ref)
        right = _validate_reviewed_ref(db, case_id, item.right_ref)
        evidence = [_validate_reviewed_ref(db, case_id, ref) for ref in item.evidence_refs]
        validated.append((item, left, right, evidence))

    manifest = FireInvestigationAIManifest(
        fire_investigation_case_id=case_id,
        scope_key=scope_key,
        manifest_type="evidence_comparison",
        manifest_sha256=digest,
        model_version=payload.model_version,
        payload_metadata=payload.payload_metadata,
        created_by=user.user_id,
    )
    db.add(manifest)
    db.flush()

    ids: list[str] = []
    for item, left, right, evidence in validated:
        row = FireEvidenceComparisonCandidate(
            fire_investigation_case_id=case_id,
            source_manifest_id=manifest.fire_investigation_ai_manifest_id,
            issue_type=item.issue_type,
            summary=item.summary,
            left_ref=left,
            right_ref=right,
            evidence_refs=evidence,
            confidence=item.confidence,
            extraction_method="ai",
            model_version=payload.model_version,
            status="pending",
            created_by=user.user_id,
        )
        db.add(row)
        db.flush()
        ids.append(row.fire_evidence_comparison_candidate_id)

    write_audit(
        db,
        user_id=user.user_id,
        action="fire_audio.evidence_comparison_manifest.ingest",
        entity_type="fire_investigation_ai_manifest",
        entity_id=manifest.fire_investigation_ai_manifest_id,
        after={
            "case_id": case_id,
            "comparison_count": len(ids),
            "manifest_sha256": digest,
        },
        ai_used=True,
        ai_model_version=payload.model_version,
    )
    db.commit()
    return FireAIManifestIngestOut(
        fire_investigation_ai_manifest_id=manifest.fire_investigation_ai_manifest_id,
        manifest_type=manifest.manifest_type,
        manifest_sha256=manifest.manifest_sha256,
        model_version=manifest.model_version,
        created=True,
        derived_ids=ids,
    )


@router.get("/cases/{case_id}/comparisons", response_model=list[FireEvidenceComparisonOut])
def list_comparisons(
    case_id: str,
    comparison_status: str | None = None,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("fire_investigation.read")),
):
    _require_case(db, case_id)
    stmt = select(FireEvidenceComparisonCandidate).where(
        FireEvidenceComparisonCandidate.fire_investigation_case_id == case_id
    )
    if comparison_status:
        stmt = stmt.where(FireEvidenceComparisonCandidate.status == comparison_status)
    rows = db.scalars(
        stmt.order_by(
            FireEvidenceComparisonCandidate.status,
            FireEvidenceComparisonCandidate.created_at,
        )
    ).all()
    return [_comparison_out(x) for x in rows]


@router.patch("/comparisons/{candidate_id}", response_model=FireEvidenceComparisonOut)
def review_comparison(
    candidate_id: str,
    payload: FireEvidenceComparisonReview,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("fire_investigation.review")),
):
    row = db.get(FireEvidenceComparisonCandidate, candidate_id)
    if not row:
        raise HTTPException(status_code=404, detail="comparison candidate not found")
    result = db.execute(
        update(FireEvidenceComparisonCandidate)
        .where(
            FireEvidenceComparisonCandidate.fire_evidence_comparison_candidate_id == candidate_id,
            FireEvidenceComparisonCandidate.version == payload.expected_version,
            FireEvidenceComparisonCandidate.status == "pending",
        )
        .values(
            status=payload.status,
            version=payload.expected_version + 1,
            reviewed_by=user.user_id,
            reviewed_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
    )
    if result.rowcount != 1:
        db.rollback()
        raise HTTPException(status_code=409, detail="comparison candidate was updated or already reviewed")
    row = db.get(FireEvidenceComparisonCandidate, candidate_id)
    write_audit(
        db,
        user_id=user.user_id,
        action=f"fire_audio.evidence_comparison.{payload.status}",
        entity_type="fire_evidence_comparison_candidate",
        entity_id=candidate_id,
        after=_comparison_out(row).model_dump(mode="json"),
    )
    db.commit()
    return _comparison_out(row)
