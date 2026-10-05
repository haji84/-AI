from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from ..audit import write_audit
from ..authz import require_permission
from ..db import get_db
from ..equipment_authoring_batch import (
    equipment_requirement_batch_coverage,
    import_equipment_requirement_batch,
)
from ..legal_rule_candidate_generation import candidate_fingerprint
from ..models import (
    LegalProvision,
    LegalProvisionReviewCandidate,
    LegalRuleDraftCandidate,
    LegalRuleDraftCitation,
    LegalSourceDocument,
    LegalSourceDocumentVersion,
    User,
)
from ..schemas import (
    LegalProvisionOut,
    LegalProvisionReviewCandidateDraft,
    LegalProvisionReviewCandidateOut,
    LegalProvisionReviewCandidatePatch,
    LegalReviewQueueSummaryOut,
    EquipmentRequirementBatchImportRequest,
    EquipmentRequirementBatchImportOut,
    EquipmentRequirementBatchCoverageOut,
)

router = APIRouter(prefix="/legal-review-queue", tags=["legal-review-queue"])


def _provision_out(row: LegalProvision) -> LegalProvisionOut:
    return LegalProvisionOut(
        legal_provision_id=row.legal_provision_id,
        legal_source_document_version_id=row.legal_source_document_version_id,
        parent_provision_id=row.parent_provision_id,
        provision_type=row.provision_type,
        provision_key=row.provision_key,
        sequence_no=row.sequence_no,
        display_label=row.display_label,
        heading_text=row.heading_text,
        body_text=row.body_text,
        source_anchor=row.source_anchor,
        source_path=row.source_path,
        present_in_source=row.present_in_source,
    )


def _out(db: Session, row: LegalProvisionReviewCandidate) -> LegalProvisionReviewCandidateOut:
    provision = db.get(LegalProvision, row.legal_provision_id)
    if not provision:
        raise HTTPException(status_code=500, detail="review candidate provision missing")
    version = db.get(
        LegalSourceDocumentVersion,
        provision.legal_source_document_version_id,
    )
    document = db.get(LegalSourceDocument, version.legal_source_document_id) if version else None
    return LegalProvisionReviewCandidateOut(
        legal_provision_review_candidate_id=row.legal_provision_review_candidate_id,
        legal_provision_id=row.legal_provision_id,
        category=row.category,
        relevance_score=row.relevance_score,
        priority_lane=row.priority_lane,
        source_priority_score=row.source_priority_score,
        provision_context=row.provision_context,
        context_priority_score=row.context_priority_score,
        review_priority_score=row.relevance_score + row.source_priority_score + row.context_priority_score,
        reasons=row.reasons,
        extraction_method=row.extraction_method,
        model_version=row.model_version,
        status=row.status,
        version=row.version,
        legal_rule_draft_candidate_id=row.legal_rule_draft_candidate_id,
        document_title=document.title if document else "(source document missing)",
        provision=_provision_out(provision),
    )


def _review_query(
    *,
    queue_status: str | None = None,
    category: str | None = None,
    priority_lane: str | None = None,
    provision_context: str | None = None,
    q: str | None = None,
    min_score: float = 0,
    min_review_priority: float = 0,
):
    score_expr = (
        LegalProvisionReviewCandidate.relevance_score
        + LegalProvisionReviewCandidate.source_priority_score
        + LegalProvisionReviewCandidate.context_priority_score
    )
    stmt = (
        select(LegalProvisionReviewCandidate)
        .join(
            LegalProvision,
            LegalProvision.legal_provision_id
            == LegalProvisionReviewCandidate.legal_provision_id,
        )
        .join(
            LegalSourceDocumentVersion,
            LegalSourceDocumentVersion.legal_source_document_version_id
            == LegalProvision.legal_source_document_version_id,
        )
        .join(
            LegalSourceDocument,
            LegalSourceDocument.legal_source_document_id
            == LegalSourceDocumentVersion.legal_source_document_id,
        )
    )
    if queue_status:
        stmt = stmt.where(LegalProvisionReviewCandidate.status == queue_status)
    if category:
        stmt = stmt.where(LegalProvisionReviewCandidate.category == category)
    if priority_lane:
        stmt = stmt.where(LegalProvisionReviewCandidate.priority_lane == priority_lane)
    if provision_context:
        stmt = stmt.where(LegalProvisionReviewCandidate.provision_context == provision_context)
    if min_score:
        stmt = stmt.where(LegalProvisionReviewCandidate.relevance_score >= min_score)
    if min_review_priority:
        stmt = stmt.where(score_expr >= min_review_priority)
    if q:
        needle=f"%{q.strip()}%"
        stmt=stmt.where(
            or_(
                LegalSourceDocument.title.ilike(needle),
                LegalProvision.display_label.ilike(needle),
                LegalProvision.heading_text.ilike(needle),
                LegalProvision.body_text.ilike(needle),
            )
        )
    return stmt, score_expr




@router.post(
    "/imports/equipment-requirement-worklist",
    response_model=EquipmentRequirementBatchImportOut,
)
def import_equipment_requirement_worklist(
    payload: EquipmentRequirementBatchImportRequest,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("legal_rule.manage")),
):
    try:
        result = import_equipment_requirement_batch(
            db,
            items=payload.items,
            source_metadata=payload.source_metadata,
            apply=payload.apply,
            created_by=user.user_id,
        )
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=422, detail=str(exc))

    if payload.apply and result.get("applied"):
        write_audit(
            db,
            user_id=user.user_id,
            action="equipment_requirement_worklist.import",
            entity_type="equipment_requirement_authoring_batch",
            entity_id=result.get("batch_id"),
            after={
                "worklist_sha256": result.get("worklist_sha256"),
                "expected_candidate_count": result.get("expected_candidate_count"),
                "linked_candidate_count": result.get("linked_candidate_count"),
                "source_metadata": payload.source_metadata,
            },
        )
        db.commit()
    elif payload.apply:
        db.rollback()

    return EquipmentRequirementBatchImportOut(result=result)


@router.get(
    "/equipment-requirement/coverage",
    response_model=EquipmentRequirementBatchCoverageOut,
)
def equipment_requirement_coverage(
    worklist_sha256: str | None = None,
    evaluation_date: str | None = None,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("legal_rule.read")),
):
    from datetime import date

    day = date.today()
    if evaluation_date:
        try:
            day = date.fromisoformat(evaluation_date)
        except ValueError:
            raise HTTPException(status_code=422, detail="invalid evaluation_date")

    return EquipmentRequirementBatchCoverageOut(
        coverage=equipment_requirement_batch_coverage(
            db,
            worklist_sha256=worklist_sha256,
            evaluation_date=day,
        )
    )


@router.get("", response_model=list[LegalProvisionReviewCandidateOut])
def list_review_candidates(
    queue_status: str | None = "pending",
    category: str | None = None,
    priority_lane: str | None = None,
    provision_context: str | None = None,
    q: str | None = None,
    min_score: float = 0,
    min_review_priority: float = 0,
    offset: int = 0,
    limit: int = 50,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("legal_rule.read")),
):
    stmt, score_expr = _review_query(
        queue_status=queue_status,
        category=category,
        priority_lane=priority_lane,
        provision_context=provision_context,
        q=q,
        min_score=min_score,
        min_review_priority=min_review_priority,
    )
    rows = db.scalars(
        stmt.order_by(
            score_expr.desc(),
            LegalProvisionReviewCandidate.source_priority_score.desc(),
            LegalProvisionReviewCandidate.context_priority_score.desc(),
            LegalProvisionReviewCandidate.relevance_score.desc(),
            LegalProvisionReviewCandidate.created_at,
        )
        .offset(max(0, offset))
        .limit(max(1, min(limit, 500)))
    ).all()
    return [_out(db, x) for x in rows]


@router.get("/summary", response_model=LegalReviewQueueSummaryOut)
def review_queue_summary(
    category: str | None = None,
    priority_lane: str | None = None,
    provision_context: str | None = None,
    q: str | None = None,
    min_score: float = 0,
    min_review_priority: float = 0,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("legal_rule.read")),
):
    stmt, _score_expr = _review_query(
        queue_status=None,
        category=category,
        priority_lane=priority_lane,
        provision_context=provision_context,
        q=q,
        min_score=min_score,
        min_review_priority=min_review_priority,
    )
    sub = stmt.order_by(None).subquery()
    total = db.scalar(select(func.count()).select_from(sub)) or 0

    def grouped(column):
        return {
            str(key): int(count)
            for key, count in db.execute(
                select(column, func.count()).select_from(sub).group_by(column)
            ).all()
            if key is not None
        }

    return LegalReviewQueueSummaryOut(
        total=int(total),
        by_status=grouped(sub.c.status),
        by_category=grouped(sub.c.category),
        by_priority_lane=grouped(sub.c.priority_lane),
        by_provision_context=grouped(sub.c.provision_context),
    )


@router.patch("/{candidate_id}", response_model=LegalProvisionReviewCandidateOut)
def patch_review_candidate(
    candidate_id: str,
    payload: LegalProvisionReviewCandidatePatch,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("legal_rule.manage")),
):
    row = db.get(LegalProvisionReviewCandidate, candidate_id)
    if not row:
        raise HTTPException(status_code=404, detail="legal review candidate not found")
    if row.version != payload.expected_version:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="review candidate was updated")
    if row.status != "pending":
        raise HTTPException(status_code=409, detail="only pending review candidates can be updated")
    row.status = payload.status
    row.reviewed_by = user.user_id
    row.reviewed_at = datetime.now(timezone.utc)
    row.version += 1
    row.updated_at = datetime.now(timezone.utc)
    write_audit(
        db,
        user_id=user.user_id,
        action=f"legal_review_candidate.{payload.status}",
        entity_type="legal_provision_review_candidate",
        entity_id=row.legal_provision_review_candidate_id,
        after={
            "status": row.status,
            "category": row.category,
            "relevance_score": row.relevance_score,
            "priority_lane": row.priority_lane,
            "source_priority_score": row.source_priority_score,
            "provision_context": row.provision_context,
            "context_priority_score": row.context_priority_score,
            "review_priority_score": row.relevance_score + row.source_priority_score + row.context_priority_score,
            "version": row.version,
        },
    )
    db.commit()
    return _out(db, row)


@router.post("/{candidate_id}/draft", response_model=LegalProvisionReviewCandidateOut)
def create_rule_draft_from_review_candidate(
    candidate_id: str,
    payload: LegalProvisionReviewCandidateDraft,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("legal_rule.manage")),
):
    row = db.get(LegalProvisionReviewCandidate, candidate_id)
    if not row:
        raise HTTPException(status_code=404, detail="legal review candidate not found")
    if row.version != payload.expected_version:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="review candidate was updated")
    if row.status != "reviewed":
        raise HTTPException(status_code=409, detail="review candidate must be reviewed before Rule draft creation")
    if row.legal_rule_draft_candidate_id:
        raise HTTPException(status_code=409, detail="Rule draft already created from this review candidate")
    if row.category not in {"equipment_requirement", "submission_requirement"}:
        raise HTTPException(
            status_code=409,
            detail="review category is not directly promotable to the current requirement Rule engine",
        )

    provision = db.get(LegalProvision, row.legal_provision_id)
    if not provision or not provision.present_in_source:
        raise HTTPException(status_code=409, detail="source provision is no longer present")

    fingerprint = candidate_fingerprint(
        source_version_id=provision.legal_source_document_version_id,
        provision_id=provision.legal_provision_id,
        domain=row.category,
        generator_version="review-queue-handoff-v1",
    )
    duplicate = db.scalar(
        select(LegalRuleDraftCandidate).where(
            LegalRuleDraftCandidate.candidate_fingerprint == fingerprint
        )
    )
    if duplicate:
        row.status = "drafted"
        row.legal_rule_draft_candidate_id = duplicate.legal_rule_draft_candidate_id
        row.version += 1
        row.updated_at = datetime.now(timezone.utc)
        db.commit()
        return _out(db, row)

    draft = LegalRuleDraftCandidate(
        source_legal_document_version_id=provision.legal_source_document_version_id,
        domain=row.category,
        proposed_rule_code=None,
        proposed_name=payload.proposed_name
        or f"要レビュー: {provision.display_label or provision.provision_key}",
        proposed_conditions={},
        proposed_outcome={},
        extraction_method="deterministic",
        model_version=row.model_version,
        confidence=min(0.75, max(0.0, row.relevance_score / 10.0)),
        rationale=(
            "Created from a Human-reviewed legal relevance candidate. "
            "Conditions and outcome intentionally left blank for Human interpretation."
        ),
        candidate_fingerprint=fingerprint,
        generation_context={
            "source_review_candidate_id": row.legal_provision_review_candidate_id,
            "relevance_category": row.category,
            "relevance_score": row.relevance_score,
            "reasons": row.reasons,
            "interpretation_status": "required",
        },
        created_by=user.user_id,
    )
    db.add(draft)
    db.flush()
    db.add(
        LegalRuleDraftCitation(
            legal_rule_draft_candidate_id=draft.legal_rule_draft_candidate_id,
            legal_provision_id=provision.legal_provision_id,
            citation_role="primary",
        )
    )
    row.status = "drafted"
    row.legal_rule_draft_candidate_id = draft.legal_rule_draft_candidate_id
    row.version += 1
    row.updated_at = datetime.now(timezone.utc)
    write_audit(
        db,
        user_id=user.user_id,
        action="legal_review_candidate.create_rule_draft",
        entity_type="legal_provision_review_candidate",
        entity_id=row.legal_provision_review_candidate_id,
        after={
            "legal_rule_draft_candidate_id": draft.legal_rule_draft_candidate_id,
            "domain": draft.domain,
            "conditions_completed": False,
            "outcome_completed": False,
        },
    )
    db.commit()
    return _out(db, row)
