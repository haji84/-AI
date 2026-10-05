from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import or_, select, update
from sqlalchemy.orm import Session

from ..audit import write_audit
from ..authz import require_permission
from ..db import get_db
from ..models import (
    Document,
    Facility,
    FireCauseCandidate,
    FireEvidenceSnapshot,
    FireInvestigationAIManifest,
    FireInvestigationCase,
    FireInvestigationMedia,
    FirePhotoAnnotation,
    FireReportDraft,
    FireStatementDraft,
    FireTimelineEvent,
    FireTranscriptSegment,
    FormTemplate,
    User,
)
from ..schemas import (
    FireAIManifestIngestOut,
    FireCauseCandidateCreate,
    FireCauseCandidateOut,
    FireEvidenceSnapshotCreate,
    FireEvidenceSnapshotOut,
    FireCauseCandidateReview,
    FireInvestigationCaseCreate,
    FireInvestigationCaseDetailOut,
    FireInvestigationCaseOut,
    FireInvestigationCasePatch,
    FireInvestigationMediaCreate,
    FireInvestigationMediaOut,
    FireOfficialCauseApprove,
    FirePhotoAIManifest,
    FirePhotoAnnotationCreate,
    FirePhotoAnnotationOut,
    FirePhotoAnnotationReview,
    FireReportAIManifest,
    FireReportDraftApprove,
    FireReportDraftCreate,
    FireReportDraftOut,
    FireReportDraftReview,
    FireStatementAIManifest,
    FireStatementDraftCreate,
    FireStatementDraftOut,
    FireStatementDraftReview,
    FireTimelineEventCreate,
    FireTimelineEventOut,
    FireTimelineEventReview,
    FireTranscriptAIManifest,
    FireTranscriptSegmentCreate,
    FireTranscriptSegmentOut,
    FireTranscriptSegmentReview,
)

router = APIRouter(prefix="/fire-investigations", tags=["fire-investigations"])


def _dt(value: str | None) -> datetime | None:
    if value in (None, ""):
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=f"invalid datetime: {value}") from exc
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def _manifest_hash(payload) -> str:
    raw = json.dumps(
        payload.model_dump(mode="json"),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _manifest_out(
    row: FireInvestigationAIManifest,
    *,
    created: bool,
    derived_ids: list[str],
) -> FireAIManifestIngestOut:
    return FireAIManifestIngestOut(
        fire_investigation_ai_manifest_id=row.fire_investigation_ai_manifest_id,
        manifest_type=row.manifest_type,
        manifest_sha256=row.manifest_sha256,
        model_version=row.model_version,
        created=created,
        derived_ids=derived_ids,
    )


def _existing_manifest(
    db: Session,
    *,
    scope_key: str,
    manifest_type: str,
    manifest_sha256: str,
) -> FireInvestigationAIManifest | None:
    return db.scalar(
        select(FireInvestigationAIManifest).where(
            FireInvestigationAIManifest.scope_key == scope_key,
            FireInvestigationAIManifest.manifest_type == manifest_type,
            FireInvestigationAIManifest.manifest_sha256 == manifest_sha256,
        )
    )


def _case_out(row: FireInvestigationCase) -> FireInvestigationCaseOut:
    return FireInvestigationCaseOut(
        fire_investigation_case_id=row.fire_investigation_case_id,
        case_number=row.case_number,
        building_id=row.building_id,
        title=row.title,
        occurred_at=row.occurred_at.isoformat() if row.occurred_at else None,
        location_text=row.location_text,
        status=row.status,
        official_cause_text=row.official_cause_text,
        official_cause_candidate_id=row.official_cause_candidate_id,
        final_report_document_id=row.final_report_document_id,
        version=row.version,
        cause_approved_by=row.cause_approved_by,
        cause_approved_at=row.cause_approved_at.isoformat() if row.cause_approved_at else None,
        created_at=row.created_at.isoformat(),
    )


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


def _photo_out(row: FirePhotoAnnotation) -> FirePhotoAnnotationOut:
    return FirePhotoAnnotationOut(
        fire_photo_annotation_id=row.fire_photo_annotation_id,
        fire_investigation_media_id=row.fire_investigation_media_id,
        description=row.description,
        tags=row.tags or [],
        map_position=row.map_position or {},
        confidence=row.confidence,
        source_kind=row.source_kind,
        model_version=row.model_version,
        status=row.status,
        version=row.version,
    )


def _segment_out(row: FireTranscriptSegment) -> FireTranscriptSegmentOut:
    return FireTranscriptSegmentOut(
        fire_transcript_segment_id=row.fire_transcript_segment_id,
        fire_investigation_media_id=row.fire_investigation_media_id,
        start_ms=row.start_ms,
        end_ms=row.end_ms,
        speaker_label=row.speaker_label,
        text=row.text,
        confidence=row.confidence,
        source_kind=row.source_kind,
        model_version=row.model_version,
        review_status=row.review_status,
        version=row.version,
    )


def _statement_out(row: FireStatementDraft) -> FireStatementDraftOut:
    return FireStatementDraftOut(
        fire_statement_draft_id=row.fire_statement_draft_id,
        fire_investigation_case_id=row.fire_investigation_case_id,
        fire_investigation_media_id=row.fire_investigation_media_id,
        person_label=row.person_label,
        draft_text=row.draft_text,
        evidence_segment_ids=row.evidence_segment_ids or [],
        ai_generated=row.ai_generated,
        model_version=row.model_version,
        status=row.status,
        version=row.version,
    )


def _timeline_out(row: FireTimelineEvent) -> FireTimelineEventOut:
    return FireTimelineEventOut(
        fire_timeline_event_id=row.fire_timeline_event_id,
        fire_investigation_case_id=row.fire_investigation_case_id,
        event_time=row.event_time.isoformat() if row.event_time else None,
        event_time_text=row.event_time_text,
        event_type=row.event_type,
        title=row.title,
        description=row.description,
        source_refs=row.source_refs or [],
        confidence=row.confidence,
        status=row.status,
        version=row.version,
    )


def _cause_out(row: FireCauseCandidate) -> FireCauseCandidateOut:
    return FireCauseCandidateOut(
        fire_cause_candidate_id=row.fire_cause_candidate_id,
        fire_investigation_case_id=row.fire_investigation_case_id,
        cause_category=row.cause_category,
        cause_text=row.cause_text,
        hypothesis=row.hypothesis or {},
        evidence_refs=row.evidence_refs or [],
        confidence=row.confidence,
        extraction_method=row.extraction_method,
        model_version=row.model_version,
        status=row.status,
        version=row.version,
    )


def _report_out(row: FireReportDraft) -> FireReportDraftOut:
    return FireReportDraftOut(
        fire_report_draft_id=row.fire_report_draft_id,
        fire_investigation_case_id=row.fire_investigation_case_id,
        report_type=row.report_type,
        form_template_id=row.form_template_id,
        narrative_text=row.narrative_text,
        structured_content=row.structured_content or {},
        evidence_refs=row.evidence_refs or [],
        fire_evidence_snapshot_id=row.fire_evidence_snapshot_id,
        source_manifest_id=row.source_manifest_id,
        ai_generated=row.ai_generated,
        model_version=row.model_version,
        status=row.status,
        version=row.version,
    )


def _evidence_snapshot_out(row: FireEvidenceSnapshot) -> FireEvidenceSnapshotOut:
    return FireEvidenceSnapshotOut(
        fire_evidence_snapshot_id=row.fire_evidence_snapshot_id,
        fire_investigation_case_id=row.fire_investigation_case_id,
        case_version=row.case_version,
        snapshot_sha256=row.snapshot_sha256,
        photo_annotation_ids=row.photo_annotation_ids or [],
        transcript_segment_ids=row.transcript_segment_ids or [],
        statement_draft_ids=row.statement_draft_ids or [],
        timeline_event_ids=row.timeline_event_ids or [],
        official_cause_candidate_id=row.official_cause_candidate_id,
        media_document_hashes=row.media_document_hashes or {},
        metadata=row.snapshot_metadata or {},
        created_at=row.created_at.isoformat(),
    )


def _snapshot_ref_set(row: FireEvidenceSnapshot) -> dict[str, set[str]]:
    return {
        "photo_annotation": set(row.photo_annotation_ids or []),
        "transcript_segment": set(row.transcript_segment_ids or []),
        "statement": set(row.statement_draft_ids or []),
        "timeline_event": set(row.timeline_event_ids or []),
        "official_cause": ({row.official_cause_candidate_id} if row.official_cause_candidate_id else set()),
    }


def _snapshot_default_refs(row: FireEvidenceSnapshot) -> list[dict]:
    out: list[dict] = []
    for ref_type, ids in _snapshot_ref_set(row).items():
        for ref_id in sorted(ids):
            out.append({"type": ref_type, "id": ref_id})
    return out


def _validate_report_evidence_refs(row: FireEvidenceSnapshot, refs: list[dict]) -> None:
    allowed = _snapshot_ref_set(row)
    for ref in refs:
        ref_type = ref.get("type")
        ref_id = ref.get("id")
        if ref_type not in allowed or not ref_id or ref_id not in allowed[ref_type]:
            raise HTTPException(
                status_code=422,
                detail=f"report evidence reference is not present in snapshot: {ref_type}:{ref_id}",
            )


def _validate_report_template(
    db: Session,
    *,
    case: FireInvestigationCase,
    form_template_id: str | None,
) -> FormTemplate | None:
    if not form_template_id:
        return None
    template = db.get(FormTemplate, form_template_id)
    if not template:
        raise HTTPException(status_code=422, detail="form_template_id not found")
    if template.status != "active":
        raise HTTPException(status_code=409, detail="form template is not active")
    target_date = (
        case.occurred_at.date()
        if case.occurred_at
        else datetime.now(timezone.utc).date()
    )
    if template.effective_from and template.effective_from > target_date:
        raise HTTPException(status_code=409, detail="form template is not yet effective for this case date")
    if template.effective_to and template.effective_to < target_date:
        raise HTTPException(status_code=409, detail="form template was expired for this case date")
    return template


def _case_detail(db: Session, row: FireInvestigationCase) -> FireInvestigationCaseDetailOut:
    media = db.scalars(
        select(FireInvestigationMedia)
        .where(FireInvestigationMedia.fire_investigation_case_id == row.fire_investigation_case_id)
        .order_by(FireInvestigationMedia.sequence_no, FireInvestigationMedia.created_at)
    ).all()
    statements = db.scalars(
        select(FireStatementDraft)
        .where(FireStatementDraft.fire_investigation_case_id == row.fire_investigation_case_id)
        .order_by(FireStatementDraft.created_at)
    ).all()
    timeline = db.scalars(
        select(FireTimelineEvent)
        .where(FireTimelineEvent.fire_investigation_case_id == row.fire_investigation_case_id)
        .order_by(FireTimelineEvent.event_time, FireTimelineEvent.created_at)
    ).all()
    causes = db.scalars(
        select(FireCauseCandidate)
        .where(FireCauseCandidate.fire_investigation_case_id == row.fire_investigation_case_id)
        .order_by(FireCauseCandidate.created_at)
    ).all()
    reports = db.scalars(
        select(FireReportDraft)
        .where(FireReportDraft.fire_investigation_case_id == row.fire_investigation_case_id)
        .order_by(FireReportDraft.created_at)
    ).all()
    snapshots = db.scalars(
        select(FireEvidenceSnapshot)
        .where(FireEvidenceSnapshot.fire_investigation_case_id == row.fire_investigation_case_id)
        .order_by(FireEvidenceSnapshot.created_at.desc())
    ).all()
    return FireInvestigationCaseDetailOut(
        case=_case_out(row),
        media=[_media_out(x) for x in media],
        statements=[_statement_out(x) for x in statements],
        timeline=[_timeline_out(x) for x in timeline],
        cause_candidates=[_cause_out(x) for x in causes],
        report_drafts=[_report_out(x) for x in reports],
        evidence_snapshots=[_evidence_snapshot_out(x).model_dump(mode="json") for x in snapshots],
    )


def _require_case(db: Session, case_id: str) -> FireInvestigationCase:
    row = db.get(FireInvestigationCase, case_id)
    if not row:
        raise HTTPException(status_code=404, detail="fire investigation case not found")
    return row


def _require_media(db: Session, media_id: str, media_type: str | None = None) -> FireInvestigationMedia:
    row = db.get(FireInvestigationMedia, media_id)
    if not row:
        raise HTTPException(status_code=404, detail="fire investigation media not found")
    if media_type and row.media_type != media_type:
        raise HTTPException(status_code=422, detail=f"media must be {media_type}")
    return row


@router.get("", response_model=list[FireInvestigationCaseOut])
def list_cases(
    q: str | None = None,
    case_status: str | None = None,
    building_id: str | None = None,
    limit: int = 100,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("fire_investigation.read")),
):
    stmt = select(FireInvestigationCase)
    if q:
        needle = f"%{q}%"
        stmt = stmt.where(
            or_(
                FireInvestigationCase.title.ilike(needle),
                FireInvestigationCase.case_number.ilike(needle),
                FireInvestigationCase.location_text.ilike(needle),
            )
        )
    if case_status:
        stmt = stmt.where(FireInvestigationCase.status == case_status)
    if building_id:
        stmt = stmt.where(FireInvestigationCase.building_id == building_id)
    rows = db.scalars(
        stmt.order_by(FireInvestigationCase.occurred_at.desc(), FireInvestigationCase.created_at.desc())
        .limit(max(1, min(limit, 500)))
    ).all()
    return [_case_out(x) for x in rows]


@router.post("", response_model=FireInvestigationCaseOut, status_code=201)
def create_case(
    payload: FireInvestigationCaseCreate,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("fire_investigation.create")),
):
    if payload.building_id and not db.get(Facility, payload.building_id):
        raise HTTPException(status_code=422, detail="building_id not found")
    if payload.case_number and db.scalar(
        select(FireInvestigationCase).where(FireInvestigationCase.case_number == payload.case_number)
    ):
        raise HTTPException(status_code=409, detail="case_number already exists")
    row = FireInvestigationCase(
        case_number=payload.case_number,
        building_id=payload.building_id,
        title=payload.title,
        occurred_at=_dt(payload.occurred_at),
        location_text=payload.location_text,
        status="draft",
        created_by=user.user_id,
        updated_by=user.user_id,
    )
    db.add(row)
    db.flush()
    write_audit(
        db,
        user_id=user.user_id,
        action="fire_investigation.create",
        entity_type="fire_investigation_case",
        entity_id=row.fire_investigation_case_id,
        after=_case_out(row).model_dump(mode="json"),
    )
    db.commit()
    return _case_out(row)


@router.get("/{case_id}", response_model=FireInvestigationCaseDetailOut)
def get_case(
    case_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("fire_investigation.read")),
):
    return _case_detail(db, _require_case(db, case_id))


@router.patch("/{case_id}", response_model=FireInvestigationCaseOut)
def patch_case(
    case_id: str,
    payload: FireInvestigationCasePatch,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("fire_investigation.update")),
):
    current = _require_case(db, case_id)
    before = _case_out(current).model_dump(mode="json")
    values = payload.model_dump(exclude_unset=True, exclude={"expected_version"})
    if "occurred_at" in values:
        values["occurred_at"] = _dt(values["occurred_at"])
    if "building_id" in values and values["building_id"] and not db.get(Facility, values["building_id"]):
        raise HTTPException(status_code=422, detail="building_id not found")
    if "case_number" in values and values["case_number"]:
        duplicate = db.scalar(
            select(FireInvestigationCase).where(
                FireInvestigationCase.case_number == values["case_number"],
                FireInvestigationCase.fire_investigation_case_id != case_id,
            )
        )
        if duplicate:
            raise HTTPException(status_code=409, detail="case_number already exists")
    values["version"] = payload.expected_version + 1
    values["updated_by"] = user.user_id
    values["updated_at"] = datetime.now(timezone.utc)
    result = db.execute(
        update(FireInvestigationCase)
        .where(
            FireInvestigationCase.fire_investigation_case_id == case_id,
            FireInvestigationCase.version == payload.expected_version,
        )
        .values(**values)
    )
    if result.rowcount != 1:
        db.rollback()
        latest = db.get(FireInvestigationCase, case_id)
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"message": "case was updated by another user", "current": _case_out(latest).model_dump(mode="json") if latest else None},
        )
    row = db.get(FireInvestigationCase, case_id)
    out = _case_out(row)
    write_audit(
        db,
        user_id=user.user_id,
        action="fire_investigation.update",
        entity_type="fire_investigation_case",
        entity_id=case_id,
        before=before,
        after=out.model_dump(mode="json"),
    )
    db.commit()
    return out


@router.post("/{case_id}/media", response_model=FireInvestigationMediaOut, status_code=201)
def add_media(
    case_id: str,
    payload: FireInvestigationMediaCreate,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("fire_investigation.create")),
):
    case = _require_case(db, case_id)
    doc = db.get(Document, payload.document_id)
    if not doc:
        raise HTTPException(status_code=404, detail="document not found")
    if case.building_id and doc.building_id and doc.building_id != case.building_id:
        raise HTTPException(status_code=409, detail="document belongs to another facility")
    if case.building_id and not doc.building_id:
        doc.building_id = case.building_id
    if db.scalar(
        select(FireInvestigationMedia).where(
            FireInvestigationMedia.fire_investigation_case_id == case_id,
            FireInvestigationMedia.document_id == payload.document_id,
        )
    ):
        raise HTTPException(status_code=409, detail="document already linked to this case")
    row = FireInvestigationMedia(
        fire_investigation_case_id=case_id,
        document_id=payload.document_id,
        media_type=payload.media_type,
        sequence_no=payload.sequence_no,
        captured_at=_dt(payload.captured_at),
        location_label=payload.location_label,
        floor_number=payload.floor_number,
        notes=payload.notes,
        ai_metadata=payload.ai_metadata,
        created_by=user.user_id,
    )
    db.add(row)
    db.flush()
    write_audit(
        db,
        user_id=user.user_id,
        action="fire_investigation.media.add",
        entity_type="fire_investigation_media",
        entity_id=row.fire_investigation_media_id,
        after=_media_out(row).model_dump(mode="json"),
    )
    db.commit()
    return _media_out(row)


@router.get("/{case_id}/media", response_model=list[FireInvestigationMediaOut])
def list_media(
    case_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("fire_investigation.read")),
):
    _require_case(db, case_id)
    rows = db.scalars(
        select(FireInvestigationMedia)
        .where(FireInvestigationMedia.fire_investigation_case_id == case_id)
        .order_by(FireInvestigationMedia.sequence_no, FireInvestigationMedia.created_at)
    ).all()
    return [_media_out(x) for x in rows]


@router.post(
    "/media/{media_id}/photo-ai-manifest",
    response_model=FireAIManifestIngestOut,
)
def ingest_photo_ai_manifest(
    media_id: str,
    payload: FirePhotoAIManifest,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("fire_investigation.update")),
):
    media = _require_media(db, media_id, "photo")
    digest = _manifest_hash(payload)
    scope_key = f"media:{media_id}"
    existing = _existing_manifest(
        db,
        scope_key=scope_key,
        manifest_type="photo_analysis",
        manifest_sha256=digest,
    )
    if existing:
        ids = list(db.scalars(
            select(FirePhotoAnnotation.fire_photo_annotation_id).where(
                FirePhotoAnnotation.source_manifest_id == existing.fire_investigation_ai_manifest_id
            )
        ).all())
        return _manifest_out(existing, created=False, derived_ids=ids)

    manifest = FireInvestigationAIManifest(
        fire_investigation_case_id=media.fire_investigation_case_id,
        fire_investigation_media_id=media_id,
        scope_key=scope_key,
        manifest_type="photo_analysis",
        manifest_sha256=digest,
        model_version=payload.model_version,
        payload_metadata=payload.payload_metadata,
        created_by=user.user_id,
    )
    db.add(manifest)
    db.flush()

    ids: list[str] = []
    for item in payload.annotations:
        row = FirePhotoAnnotation(
            fire_investigation_media_id=media_id,
            source_manifest_id=manifest.fire_investigation_ai_manifest_id,
            description=item.description,
            tags=item.tags,
            map_position=item.map_position,
            confidence=item.confidence,
            source_kind="ai",
            model_version=payload.model_version,
            status="pending",
        )
        db.add(row)
        db.flush()
        ids.append(row.fire_photo_annotation_id)

    write_audit(
        db,
        user_id=user.user_id,
        action="fire_investigation.photo_ai_manifest.ingest",
        entity_type="fire_investigation_ai_manifest",
        entity_id=manifest.fire_investigation_ai_manifest_id,
        after={
            "manifest_sha256": digest,
            "media_id": media_id,
            "annotation_count": len(ids),
        },
        ai_used=True,
        ai_model_version=payload.model_version,
    )
    db.commit()
    return _manifest_out(manifest, created=True, derived_ids=ids)


@router.post("/media/{media_id}/photo-annotations", response_model=FirePhotoAnnotationOut, status_code=201)
def create_photo_annotation(
    media_id: str,
    payload: FirePhotoAnnotationCreate,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("fire_investigation.update")),
):
    _require_media(db, media_id, "photo")
    row = FirePhotoAnnotation(
        fire_investigation_media_id=media_id,
        description=payload.description,
        tags=payload.tags,
        map_position=payload.map_position,
        confidence=payload.confidence,
        source_kind=payload.source_kind,
        model_version=payload.model_version,
        status="pending",
    )
    db.add(row)
    db.flush()
    write_audit(
        db,
        user_id=user.user_id,
        action="fire_investigation.photo_annotation.create",
        entity_type="fire_photo_annotation",
        entity_id=row.fire_photo_annotation_id,
        after=_photo_out(row).model_dump(mode="json"),
        ai_used=payload.source_kind == "ai",
        ai_model_version=payload.model_version,
    )
    db.commit()
    return _photo_out(row)


@router.get("/media/{media_id}/photo-annotations", response_model=list[FirePhotoAnnotationOut])
def list_photo_annotations(
    media_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("fire_investigation.read")),
):
    _require_media(db, media_id, "photo")
    rows = db.scalars(
        select(FirePhotoAnnotation)
        .where(FirePhotoAnnotation.fire_investigation_media_id == media_id)
        .order_by(FirePhotoAnnotation.created_at)
    ).all()
    return [_photo_out(x) for x in rows]


@router.patch("/photo-annotations/{annotation_id}", response_model=FirePhotoAnnotationOut)
def review_photo_annotation(
    annotation_id: str,
    payload: FirePhotoAnnotationReview,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("fire_investigation.review")),
):
    row = db.get(FirePhotoAnnotation, annotation_id)
    if not row:
        raise HTTPException(status_code=404, detail="photo annotation not found")
    result = db.execute(
        update(FirePhotoAnnotation)
        .where(
            FirePhotoAnnotation.fire_photo_annotation_id == annotation_id,
            FirePhotoAnnotation.version == payload.expected_version,
            FirePhotoAnnotation.status == "pending",
        )
        .values(
            status=payload.status,
            version=payload.expected_version + 1,
            reviewed_by=user.user_id,
            reviewed_at=datetime.now(timezone.utc),
        )
    )
    if result.rowcount != 1:
        db.rollback()
        raise HTTPException(status_code=409, detail="photo annotation was updated or already reviewed")
    row = db.get(FirePhotoAnnotation, annotation_id)
    db.commit()
    return _photo_out(row)


@router.post(
    "/media/{media_id}/transcript-ai-manifest",
    response_model=FireAIManifestIngestOut,
)
def ingest_transcript_ai_manifest(
    media_id: str,
    payload: FireTranscriptAIManifest,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("fire_investigation.update")),
):
    media = _require_media(db, media_id, "audio")
    for item in payload.segments:
        if item.start_ms is not None and item.end_ms is not None and item.end_ms < item.start_ms:
            raise HTTPException(status_code=422, detail="end_ms must be >= start_ms")

    digest = _manifest_hash(payload)
    scope_key = f"media:{media_id}"
    existing = _existing_manifest(
        db,
        scope_key=scope_key,
        manifest_type="transcript",
        manifest_sha256=digest,
    )
    if existing:
        ids = list(db.scalars(
            select(FireTranscriptSegment.fire_transcript_segment_id).where(
                FireTranscriptSegment.source_manifest_id == existing.fire_investigation_ai_manifest_id
            ).order_by(FireTranscriptSegment.start_ms, FireTranscriptSegment.created_at)
        ).all())
        return _manifest_out(existing, created=False, derived_ids=ids)

    manifest = FireInvestigationAIManifest(
        fire_investigation_case_id=media.fire_investigation_case_id,
        fire_investigation_media_id=media_id,
        scope_key=scope_key,
        manifest_type="transcript",
        manifest_sha256=digest,
        model_version=payload.model_version,
        payload_metadata=payload.payload_metadata,
        created_by=user.user_id,
    )
    db.add(manifest)
    db.flush()

    ids: list[str] = []
    for item in payload.segments:
        row = FireTranscriptSegment(
            fire_investigation_media_id=media_id,
            source_manifest_id=manifest.fire_investigation_ai_manifest_id,
            start_ms=item.start_ms,
            end_ms=item.end_ms,
            speaker_label=item.speaker_label,
            text=item.text,
            confidence=item.confidence,
            source_kind="ai",
            model_version=payload.model_version,
            review_status="pending",
        )
        db.add(row)
        db.flush()
        ids.append(row.fire_transcript_segment_id)

    write_audit(
        db,
        user_id=user.user_id,
        action="fire_investigation.transcript_ai_manifest.ingest",
        entity_type="fire_investigation_ai_manifest",
        entity_id=manifest.fire_investigation_ai_manifest_id,
        after={
            "manifest_sha256": digest,
            "media_id": media_id,
            "segment_count": len(ids),
        },
        ai_used=True,
        ai_model_version=payload.model_version,
    )
    db.commit()
    return _manifest_out(manifest, created=True, derived_ids=ids)


@router.post("/media/{media_id}/transcript-segments", response_model=FireTranscriptSegmentOut, status_code=201)
def create_transcript_segment(
    media_id: str,
    payload: FireTranscriptSegmentCreate,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("fire_investigation.update")),
):
    _require_media(db, media_id, "audio")
    if payload.start_ms is not None and payload.end_ms is not None and payload.end_ms < payload.start_ms:
        raise HTTPException(status_code=422, detail="end_ms must be >= start_ms")
    row = FireTranscriptSegment(
        fire_investigation_media_id=media_id,
        start_ms=payload.start_ms,
        end_ms=payload.end_ms,
        speaker_label=payload.speaker_label,
        text=payload.text,
        confidence=payload.confidence,
        source_kind=payload.source_kind,
        model_version=payload.model_version,
        review_status="pending",
    )
    db.add(row)
    db.flush()
    write_audit(
        db,
        user_id=user.user_id,
        action="fire_investigation.transcript.create",
        entity_type="fire_transcript_segment",
        entity_id=row.fire_transcript_segment_id,
        after=_segment_out(row).model_dump(mode="json"),
        ai_used=payload.source_kind == "ai",
        ai_model_version=payload.model_version,
    )
    db.commit()
    return _segment_out(row)


@router.get("/media/{media_id}/transcript-segments", response_model=list[FireTranscriptSegmentOut])
def list_transcript_segments(
    media_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("fire_investigation.read")),
):
    _require_media(db, media_id, "audio")
    rows = db.scalars(
        select(FireTranscriptSegment)
        .where(FireTranscriptSegment.fire_investigation_media_id == media_id)
        .order_by(FireTranscriptSegment.start_ms, FireTranscriptSegment.created_at)
    ).all()
    return [_segment_out(x) for x in rows]


@router.patch("/transcript-segments/{segment_id}", response_model=FireTranscriptSegmentOut)
def review_transcript_segment(
    segment_id: str,
    payload: FireTranscriptSegmentReview,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("fire_investigation.review")),
):
    row = db.get(FireTranscriptSegment, segment_id)
    if not row:
        raise HTTPException(status_code=404, detail="transcript segment not found")
    result = db.execute(
        update(FireTranscriptSegment)
        .where(
            FireTranscriptSegment.fire_transcript_segment_id == segment_id,
            FireTranscriptSegment.version == payload.expected_version,
            FireTranscriptSegment.review_status == "pending",
        )
        .values(
            review_status=payload.status,
            version=payload.expected_version + 1,
            reviewed_by=user.user_id,
            reviewed_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
    )
    if result.rowcount != 1:
        db.rollback()
        raise HTTPException(status_code=409, detail="transcript segment was updated or already reviewed")
    row = db.get(FireTranscriptSegment, segment_id)
    db.commit()
    return _segment_out(row)


@router.post(
    "/{case_id}/statement-ai-manifest",
    response_model=FireAIManifestIngestOut,
)
def ingest_statement_ai_manifest(
    case_id: str,
    payload: FireStatementAIManifest,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("fire_investigation.update")),
):
    _require_case(db, case_id)
    digest = _manifest_hash(payload)
    scope_key = f"case:{case_id}"
    existing = _existing_manifest(
        db,
        scope_key=scope_key,
        manifest_type="statement_draft",
        manifest_sha256=digest,
    )
    if existing:
        ids = list(db.scalars(
            select(FireStatementDraft.fire_statement_draft_id).where(
                FireStatementDraft.source_manifest_id == existing.fire_investigation_ai_manifest_id
            ).order_by(FireStatementDraft.created_at)
        ).all())
        return _manifest_out(existing, created=False, derived_ids=ids)

    validated: list[tuple[object, list[FireTranscriptSegment]]] = []
    for item in payload.statements:
        if not item.evidence_segment_ids:
            raise HTTPException(
                status_code=422,
                detail="AI statement draft requires at least one accepted transcript segment",
            )
        selected_media = None
        if item.fire_investigation_media_id:
            selected_media = _require_media(db, item.fire_investigation_media_id, "audio")
            if selected_media.fire_investigation_case_id != case_id:
                raise HTTPException(status_code=422, detail="statement media belongs to another case")
        segments: list[FireTranscriptSegment] = []
        for segment_id in item.evidence_segment_ids:
            segment = db.get(FireTranscriptSegment, segment_id)
            if not segment:
                raise HTTPException(status_code=422, detail=f"evidence segment not found: {segment_id}")
            media = db.get(FireInvestigationMedia, segment.fire_investigation_media_id)
            if not media or media.fire_investigation_case_id != case_id:
                raise HTTPException(status_code=422, detail="evidence segment belongs to another case")
            if segment.review_status != "accepted":
                raise HTTPException(
                    status_code=409,
                    detail="AI statement draft can use only Human-accepted transcript segments",
                )
            if selected_media and segment.fire_investigation_media_id != selected_media.fire_investigation_media_id:
                raise HTTPException(status_code=422, detail="evidence segment does not belong to selected audio media")
            segments.append(segment)
        validated.append((item, segments))

    manifest = FireInvestigationAIManifest(
        fire_investigation_case_id=case_id,
        scope_key=scope_key,
        manifest_type="statement_draft",
        manifest_sha256=digest,
        model_version=payload.model_version,
        payload_metadata=payload.payload_metadata,
        created_by=user.user_id,
    )
    db.add(manifest)
    db.flush()

    ids: list[str] = []
    for item, _segments in validated:
        row = FireStatementDraft(
            fire_investigation_case_id=case_id,
            fire_investigation_media_id=item.fire_investigation_media_id,
            source_manifest_id=manifest.fire_investigation_ai_manifest_id,
            person_label=item.person_label,
            draft_text=item.draft_text,
            evidence_segment_ids=item.evidence_segment_ids,
            ai_generated=True,
            model_version=payload.model_version,
            status="draft",
            created_by=user.user_id,
        )
        db.add(row)
        db.flush()
        ids.append(row.fire_statement_draft_id)

    write_audit(
        db,
        user_id=user.user_id,
        action="fire_investigation.statement_ai_manifest.ingest",
        entity_type="fire_investigation_ai_manifest",
        entity_id=manifest.fire_investigation_ai_manifest_id,
        after={
            "manifest_sha256": digest,
            "case_id": case_id,
            "statement_count": len(ids),
        },
        ai_used=True,
        ai_model_version=payload.model_version,
    )
    db.commit()
    return _manifest_out(manifest, created=True, derived_ids=ids)


@router.post("/{case_id}/statements", response_model=FireStatementDraftOut, status_code=201)
def create_statement_draft(
    case_id: str,
    payload: FireStatementDraftCreate,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("fire_investigation.update")),
):
    _require_case(db, case_id)
    if payload.fire_investigation_media_id:
        media = _require_media(db, payload.fire_investigation_media_id)
        if media.fire_investigation_case_id != case_id:
            raise HTTPException(status_code=422, detail="statement media belongs to another case")
    for segment_id in payload.evidence_segment_ids:
        segment = db.get(FireTranscriptSegment, segment_id)
        if not segment:
            raise HTTPException(status_code=422, detail=f"evidence segment not found: {segment_id}")
        media = db.get(FireInvestigationMedia, segment.fire_investigation_media_id)
        if not media or media.fire_investigation_case_id != case_id:
            raise HTTPException(status_code=422, detail="evidence segment belongs to another case")
    row = FireStatementDraft(
        fire_investigation_case_id=case_id,
        fire_investigation_media_id=payload.fire_investigation_media_id,
        person_label=payload.person_label,
        draft_text=payload.draft_text,
        evidence_segment_ids=payload.evidence_segment_ids,
        ai_generated=payload.ai_generated,
        model_version=payload.model_version,
        status="draft",
        created_by=user.user_id,
    )
    db.add(row)
    db.flush()
    write_audit(
        db,
        user_id=user.user_id,
        action="fire_investigation.statement.create",
        entity_type="fire_statement_draft",
        entity_id=row.fire_statement_draft_id,
        after=_statement_out(row).model_dump(mode="json"),
        ai_used=payload.ai_generated,
        ai_model_version=payload.model_version,
    )
    db.commit()
    return _statement_out(row)


@router.patch("/statements/{statement_id}", response_model=FireStatementDraftOut)
def review_statement_draft(
    statement_id: str,
    payload: FireStatementDraftReview,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("fire_investigation.review")),
):
    row = db.get(FireStatementDraft, statement_id)
    if not row:
        raise HTTPException(status_code=404, detail="statement draft not found")
    result = db.execute(
        update(FireStatementDraft)
        .where(
            FireStatementDraft.fire_statement_draft_id == statement_id,
            FireStatementDraft.version == payload.expected_version,
            FireStatementDraft.status == "draft",
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
        raise HTTPException(status_code=409, detail="statement draft was updated or already reviewed")
    row = db.get(FireStatementDraft, statement_id)
    db.commit()
    return _statement_out(row)


@router.post("/{case_id}/timeline", response_model=FireTimelineEventOut, status_code=201)
def create_timeline_event(
    case_id: str,
    payload: FireTimelineEventCreate,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("fire_investigation.update")),
):
    _require_case(db, case_id)
    row = FireTimelineEvent(
        fire_investigation_case_id=case_id,
        event_time=_dt(payload.event_time),
        event_time_text=payload.event_time_text,
        event_type=payload.event_type,
        title=payload.title,
        description=payload.description,
        source_refs=payload.source_refs,
        confidence=payload.confidence,
        status="candidate",
        created_by=user.user_id,
    )
    db.add(row)
    db.flush()
    db.commit()
    return _timeline_out(row)


@router.patch("/timeline/{event_id}", response_model=FireTimelineEventOut)
def review_timeline_event(
    event_id: str,
    payload: FireTimelineEventReview,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("fire_investigation.review")),
):
    row = db.get(FireTimelineEvent, event_id)
    if not row:
        raise HTTPException(status_code=404, detail="timeline event not found")
    result = db.execute(
        update(FireTimelineEvent)
        .where(
            FireTimelineEvent.fire_timeline_event_id == event_id,
            FireTimelineEvent.version == payload.expected_version,
            FireTimelineEvent.status == "candidate",
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
        raise HTTPException(status_code=409, detail="timeline event was updated or already reviewed")
    row = db.get(FireTimelineEvent, event_id)
    db.commit()
    return _timeline_out(row)


@router.post("/{case_id}/cause-candidates", response_model=FireCauseCandidateOut, status_code=201)
def create_cause_candidate(
    case_id: str,
    payload: FireCauseCandidateCreate,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("fire_investigation.update")),
):
    _require_case(db, case_id)
    row = FireCauseCandidate(
        fire_investigation_case_id=case_id,
        cause_category=payload.cause_category,
        cause_text=payload.cause_text,
        hypothesis=payload.hypothesis,
        evidence_refs=payload.evidence_refs,
        confidence=payload.confidence,
        extraction_method=payload.extraction_method,
        model_version=payload.model_version,
        status="candidate",
        created_by=user.user_id,
    )
    db.add(row)
    db.flush()
    write_audit(
        db,
        user_id=user.user_id,
        action="fire_investigation.cause_candidate.create",
        entity_type="fire_cause_candidate",
        entity_id=row.fire_cause_candidate_id,
        after=_cause_out(row).model_dump(mode="json"),
        ai_used=payload.extraction_method == "ai",
        ai_model_version=payload.model_version,
    )
    db.commit()
    return _cause_out(row)


@router.patch("/cause-candidates/{candidate_id}", response_model=FireCauseCandidateOut)
def review_cause_candidate(
    candidate_id: str,
    payload: FireCauseCandidateReview,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("fire_investigation.review")),
):
    row = db.get(FireCauseCandidate, candidate_id)
    if not row:
        raise HTTPException(status_code=404, detail="cause candidate not found")
    result = db.execute(
        update(FireCauseCandidate)
        .where(
            FireCauseCandidate.fire_cause_candidate_id == candidate_id,
            FireCauseCandidate.version == payload.expected_version,
            FireCauseCandidate.status == "candidate",
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
        raise HTTPException(status_code=409, detail="cause candidate was updated or already reviewed")
    row = db.get(FireCauseCandidate, candidate_id)
    db.commit()
    return _cause_out(row)


@router.post("/{case_id}/official-cause", response_model=FireInvestigationCaseOut)
def approve_official_cause(
    case_id: str,
    payload: FireOfficialCauseApprove,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("fire_investigation.approve")),
):
    case = _require_case(db, case_id)
    candidate = db.get(FireCauseCandidate, payload.cause_candidate_id)
    if not candidate or candidate.fire_investigation_case_id != case_id:
        raise HTTPException(status_code=422, detail="cause candidate does not belong to case")
    if candidate.status != "reviewed":
        raise HTTPException(status_code=409, detail="cause candidate must be Human-reviewed before official approval")
    result = db.execute(
        update(FireInvestigationCase)
        .where(
            FireInvestigationCase.fire_investigation_case_id == case_id,
            FireInvestigationCase.version == payload.expected_case_version,
        )
        .values(
            official_cause_text=candidate.cause_text,
            official_cause_candidate_id=candidate.fire_cause_candidate_id,
            cause_approved_by=user.user_id,
            cause_approved_at=datetime.now(timezone.utc),
            version=payload.expected_case_version + 1,
            updated_by=user.user_id,
            updated_at=datetime.now(timezone.utc),
        )
    )
    if result.rowcount != 1:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="case was updated before official cause approval")
    row = db.get(FireInvestigationCase, case_id)
    write_audit(
        db,
        user_id=user.user_id,
        action="fire_investigation.official_cause.approve",
        entity_type="fire_investigation_case",
        entity_id=case_id,
        after={
            "official_cause_candidate_id": candidate.fire_cause_candidate_id,
            "official_cause_text": candidate.cause_text,
            "case_version": row.version,
        },
    )
    db.commit()
    return _case_out(row)


@router.post(
    "/{case_id}/evidence-snapshots",
    response_model=FireEvidenceSnapshotOut,
    status_code=201,
)
def create_evidence_snapshot(
    case_id: str,
    payload: FireEvidenceSnapshotCreate,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("fire_investigation.review")),
):
    case = _require_case(db, case_id)

    photo_rows = db.scalars(
        select(FirePhotoAnnotation)
        .join(
            FireInvestigationMedia,
            FireInvestigationMedia.fire_investigation_media_id
            == FirePhotoAnnotation.fire_investigation_media_id,
        )
        .where(
            FireInvestigationMedia.fire_investigation_case_id == case_id,
            FirePhotoAnnotation.status == "accepted",
        )
        .order_by(FirePhotoAnnotation.fire_photo_annotation_id)
    ).all()
    photo_ids = [x.fire_photo_annotation_id for x in photo_rows]

    transcript_rows = db.scalars(
        select(FireTranscriptSegment)
        .join(
            FireInvestigationMedia,
            FireInvestigationMedia.fire_investigation_media_id
            == FireTranscriptSegment.fire_investigation_media_id,
        )
        .where(
            FireInvestigationMedia.fire_investigation_case_id == case_id,
            FireTranscriptSegment.review_status == "accepted",
        )
        .order_by(FireTranscriptSegment.fire_transcript_segment_id)
    ).all()
    transcript_ids = [x.fire_transcript_segment_id for x in transcript_rows]

    statement_rows = db.scalars(
        select(FireStatementDraft)
        .where(
            FireStatementDraft.fire_investigation_case_id == case_id,
            FireStatementDraft.status == "reviewed",
        )
        .order_by(FireStatementDraft.fire_statement_draft_id)
    ).all()
    statement_ids = [x.fire_statement_draft_id for x in statement_rows]

    timeline_rows = db.scalars(
        select(FireTimelineEvent)
        .where(
            FireTimelineEvent.fire_investigation_case_id == case_id,
            FireTimelineEvent.status == "confirmed",
        )
        .order_by(FireTimelineEvent.fire_timeline_event_id)
    ).all()
    timeline_ids = [x.fire_timeline_event_id for x in timeline_rows]

    official_cause_id = case.official_cause_candidate_id

    if not (photo_ids or transcript_ids or statement_ids or timeline_ids or official_cause_id):
        raise HTTPException(
            status_code=409,
            detail="no Human-accepted/reviewed/confirmed evidence is available for a snapshot",
        )

    media_ids = {
        *(x.fire_investigation_media_id for x in photo_rows),
        *(x.fire_investigation_media_id for x in transcript_rows),
        *(x.fire_investigation_media_id for x in statement_rows if x.fire_investigation_media_id),
    }
    media_document_hashes: dict[str, dict] = {}
    if media_ids:
        media_rows = db.scalars(
            select(FireInvestigationMedia).where(
                FireInvestigationMedia.fire_investigation_media_id.in_(sorted(media_ids)),
                FireInvestigationMedia.fire_investigation_case_id == case_id,
            )
        ).all()
        for media in media_rows:
            doc = db.get(Document, media.document_id)
            if doc:
                media_document_hashes[media.fire_investigation_media_id] = {
                    "document_id": doc.document_id,
                    "sha256": doc.sha256,
                    "media_type": media.media_type,
                }

    canonical = {
        "case_id": case_id,
        "case_version": case.version,
        "photo_annotation_ids": sorted(photo_ids),
        "transcript_segment_ids": sorted(transcript_ids),
        "statement_draft_ids": sorted(statement_ids),
        "timeline_event_ids": sorted(timeline_ids),
        "official_cause_candidate_id": official_cause_id,
        "media_document_hashes": {
            key: media_document_hashes[key]
            for key in sorted(media_document_hashes)
        },
    }
    digest = hashlib.sha256(
        json.dumps(
            canonical,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()

    existing = db.scalar(
        select(FireEvidenceSnapshot).where(
            FireEvidenceSnapshot.fire_investigation_case_id == case_id,
            FireEvidenceSnapshot.snapshot_sha256 == digest,
        )
    )
    if existing:
        return _evidence_snapshot_out(existing)

    row = FireEvidenceSnapshot(
        fire_investigation_case_id=case_id,
        case_version=case.version,
        snapshot_sha256=digest,
        photo_annotation_ids=sorted(photo_ids),
        transcript_segment_ids=sorted(transcript_ids),
        statement_draft_ids=sorted(statement_ids),
        timeline_event_ids=sorted(timeline_ids),
        official_cause_candidate_id=official_cause_id,
        media_document_hashes=media_document_hashes,
        snapshot_metadata=payload.metadata,
        created_by=user.user_id,
    )
    db.add(row)
    db.flush()
    write_audit(
        db,
        user_id=user.user_id,
        action="fire_investigation.evidence_snapshot.create",
        entity_type="fire_evidence_snapshot",
        entity_id=row.fire_evidence_snapshot_id,
        after={
            "case_id": case_id,
            "case_version": case.version,
            "snapshot_sha256": digest,
            "photo_annotations": len(photo_ids),
            "transcript_segments": len(transcript_ids),
            "statements": len(statement_ids),
            "timeline_events": len(timeline_ids),
            "official_cause": bool(official_cause_id),
        },
    )
    db.commit()
    return _evidence_snapshot_out(row)


@router.get("/{case_id}/evidence-snapshots", response_model=list[FireEvidenceSnapshotOut])
def list_evidence_snapshots(
    case_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("fire_investigation.read")),
):
    _require_case(db, case_id)
    rows = db.scalars(
        select(FireEvidenceSnapshot)
        .where(FireEvidenceSnapshot.fire_investigation_case_id == case_id)
        .order_by(FireEvidenceSnapshot.created_at.desc())
    ).all()
    return [_evidence_snapshot_out(x) for x in rows]


@router.post(
    "/{case_id}/report-ai-manifest",
    response_model=FireAIManifestIngestOut,
)
def ingest_report_ai_manifest(
    case_id: str,
    payload: FireReportAIManifest,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("fire_investigation.update")),
):
    case = _require_case(db, case_id)
    snapshot = db.get(FireEvidenceSnapshot, payload.evidence_snapshot_id)
    if not snapshot or snapshot.fire_investigation_case_id != case_id:
        raise HTTPException(status_code=422, detail="evidence snapshot does not belong to case")
    if snapshot.case_version != case.version:
        raise HTTPException(
            status_code=409,
            detail="evidence snapshot is stale because the case version has changed; create a new snapshot",
        )

    _validate_report_template(
        db,
        case=case,
        form_template_id=payload.form_template_id,
    )

    refs = payload.evidence_refs or _snapshot_default_refs(snapshot)
    _validate_report_evidence_refs(snapshot, refs)

    digest = _manifest_hash(payload)
    scope_key = f"case:{case_id}:snapshot:{snapshot.fire_evidence_snapshot_id}"
    existing = _existing_manifest(
        db,
        scope_key=scope_key,
        manifest_type="report_draft",
        manifest_sha256=digest,
    )
    if existing:
        ids = list(db.scalars(
            select(FireReportDraft.fire_report_draft_id)
            .where(FireReportDraft.source_manifest_id == existing.fire_investigation_ai_manifest_id)
            .order_by(FireReportDraft.created_at)
        ).all())
        return _manifest_out(existing, created=False, derived_ids=ids)

    manifest = FireInvestigationAIManifest(
        fire_investigation_case_id=case_id,
        scope_key=scope_key,
        manifest_type="report_draft",
        manifest_sha256=digest,
        model_version=payload.model_version,
        payload_metadata={
            **(payload.payload_metadata or {}),
            "evidence_snapshot_id": snapshot.fire_evidence_snapshot_id,
            "evidence_snapshot_sha256": snapshot.snapshot_sha256,
            "report_type": payload.report_type,
            "form_template_id": payload.form_template_id,
        },
        created_by=user.user_id,
    )
    db.add(manifest)
    db.flush()

    report = FireReportDraft(
        fire_investigation_case_id=case_id,
        report_type=payload.report_type,
        form_template_id=payload.form_template_id,
        narrative_text=payload.narrative_text,
        structured_content=payload.structured_content,
        evidence_refs=refs,
        fire_evidence_snapshot_id=snapshot.fire_evidence_snapshot_id,
        source_manifest_id=manifest.fire_investigation_ai_manifest_id,
        ai_generated=True,
        model_version=payload.model_version,
        status="draft",
        created_by=user.user_id,
    )
    db.add(report)
    db.flush()

    write_audit(
        db,
        user_id=user.user_id,
        action="fire_investigation.report_ai_manifest.ingest",
        entity_type="fire_investigation_ai_manifest",
        entity_id=manifest.fire_investigation_ai_manifest_id,
        after={
            "case_id": case_id,
            "evidence_snapshot_id": snapshot.fire_evidence_snapshot_id,
            "report_draft_id": report.fire_report_draft_id,
            "report_type": payload.report_type,
            "form_template_id": payload.form_template_id,
        },
        ai_used=True,
        ai_model_version=payload.model_version,
    )
    db.commit()
    return _manifest_out(
        manifest,
        created=True,
        derived_ids=[report.fire_report_draft_id],
    )


@router.post("/{case_id}/report-drafts", response_model=FireReportDraftOut, status_code=201)
def create_report_draft(
    case_id: str,
    payload: FireReportDraftCreate,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("fire_investigation.update")),
):
    case = _require_case(db, case_id)
    if payload.ai_generated:
        raise HTTPException(
            status_code=422,
            detail="AI-generated report drafts must use the evidence-snapshot report-ai-manifest endpoint",
        )
    _validate_report_template(
        db,
        case=case,
        form_template_id=payload.form_template_id,
    )
    row = FireReportDraft(
        fire_investigation_case_id=case_id,
        report_type=payload.report_type,
        form_template_id=payload.form_template_id,
        narrative_text=payload.narrative_text,
        structured_content=payload.structured_content,
        evidence_refs=payload.evidence_refs,
        ai_generated=payload.ai_generated,
        model_version=payload.model_version,
        status="draft",
        created_by=user.user_id,
    )
    db.add(row)
    db.flush()
    write_audit(
        db,
        user_id=user.user_id,
        action="fire_investigation.report_draft.create",
        entity_type="fire_report_draft",
        entity_id=row.fire_report_draft_id,
        after=_report_out(row).model_dump(mode="json"),
        ai_used=payload.ai_generated,
        ai_model_version=payload.model_version,
    )
    db.commit()
    return _report_out(row)


@router.patch("/report-drafts/{draft_id}", response_model=FireReportDraftOut)
def review_report_draft(
    draft_id: str,
    payload: FireReportDraftReview,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("fire_investigation.review")),
):
    row = db.get(FireReportDraft, draft_id)
    if not row:
        raise HTTPException(status_code=404, detail="report draft not found")
    result = db.execute(
        update(FireReportDraft)
        .where(
            FireReportDraft.fire_report_draft_id == draft_id,
            FireReportDraft.version == payload.expected_version,
            FireReportDraft.status == "draft",
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
        raise HTTPException(status_code=409, detail="report draft was updated or already reviewed")
    row = db.get(FireReportDraft, draft_id)
    db.commit()
    return _report_out(row)


@router.post("/report-drafts/{draft_id}/approve", response_model=FireReportDraftOut)
def approve_report_draft(
    draft_id: str,
    payload: FireReportDraftApprove,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("fire_investigation.approve")),
):
    row = db.get(FireReportDraft, draft_id)
    if not row:
        raise HTTPException(status_code=404, detail="report draft not found")
    if row.status != "reviewed":
        raise HTTPException(status_code=409, detail="report draft must be Human-reviewed before approval")
    if row.ai_generated:
        if not row.fire_evidence_snapshot_id or not row.source_manifest_id:
            raise HTTPException(
                status_code=409,
                detail="AI-generated report is missing required evidence snapshot or AI manifest provenance",
            )
        snapshot = db.get(FireEvidenceSnapshot, row.fire_evidence_snapshot_id)
        manifest = db.get(FireInvestigationAIManifest, row.source_manifest_id)
        if not snapshot or not manifest or manifest.manifest_type != "report_draft":
            raise HTTPException(status_code=409, detail="AI report provenance is invalid")
        _validate_report_evidence_refs(snapshot, row.evidence_refs or [])
    result = db.execute(
        update(FireReportDraft)
        .where(
            FireReportDraft.fire_report_draft_id == draft_id,
            FireReportDraft.version == payload.expected_version,
            FireReportDraft.status == "reviewed",
        )
        .values(
            status="approved",
            version=payload.expected_version + 1,
            approved_by=user.user_id,
            approved_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
    )
    if result.rowcount != 1:
        db.rollback()
        raise HTTPException(status_code=409, detail="report draft was updated before approval")
    row = db.get(FireReportDraft, draft_id)
    write_audit(
        db,
        user_id=user.user_id,
        action="fire_investigation.report.approve",
        entity_type="fire_report_draft",
        entity_id=draft_id,
        after=_report_out(row).model_dump(mode="json"),
    )
    db.commit()
    return _report_out(row)
