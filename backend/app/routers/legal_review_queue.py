from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..audit import write_audit
from ..authz import require_permission
from ..db import get_db
from ..models import (
    LegalProvision,
    LegalProvisionReviewCandidate,
    LegalSourceDocument,
    LegalSourceDocumentVersion,
    User,
)
from ..schemas import (
    LegalProvisionOut,
    LegalProvisionReviewCandidateOut,
    LegalProvisionReviewCandidatePatch,
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
        reasons=row.reasons,
        extraction_method=row.extraction_method,
        model_version=row.model_version,
        status=row.status,
        version=row.version,
        legal_rule_draft_candidate_id=row.legal_rule_draft_candidate_id,
        document_title=document.title if document else "(source document missing)",
        provision=_provision_out(provision),
    )


@router.get("", response_model=list[LegalProvisionReviewCandidateOut])
def list_review_candidates(
    queue_status: str | None = "pending",
    category: str | None = None,
    min_score: float = 0,
    offset: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("legal_rule.read")),
):
    stmt = select(LegalProvisionReviewCandidate)
    if queue_status:
        stmt = stmt.where(LegalProvisionReviewCandidate.status == queue_status)
    if category:
        stmt = stmt.where(LegalProvisionReviewCandidate.category == category)
    stmt = stmt.where(LegalProvisionReviewCandidate.relevance_score >= min_score)
    rows = db.scalars(
        stmt.order_by(
            LegalProvisionReviewCandidate.relevance_score.desc(),
            LegalProvisionReviewCandidate.created_at,
        )
        .offset(max(0, offset))
        .limit(max(1, min(limit, 500)))
    ).all()
    return [_out(db, x) for x in rows]


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
            "version": row.version,
        },
    )
    db.commit()
    return _out(db, row)
