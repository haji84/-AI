from __future__ import annotations

from datetime import date, datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..audit import write_audit
from ..authz import require_permission
from ..db import get_db
from ..legal_rule_validation import validate_rule_conditions
from ..legal_outcome_validation import validate_rule_outcome_references
from ..models import (
    LegalProvision,
    LegalRule,
    LegalRuleCitation,
    LegalRuleDraftCandidate,
    LegalRuleDraftCitation,
    LegalRuleVersion,
    LegalSourceDocumentVersion,
    User,
)
from ..schemas import (
    LegalProvisionOut,
    LegalRuleDraftCandidateCreate,
    LegalRuleDraftCandidateOut,
    LegalRuleDraftCandidatePatch,
    LegalRuleDraftCandidatePromote,
    LegalRuleDraftCandidateReview,
    LegalRuleDraftCitationOut,
)

router = APIRouter(prefix="/legal-rule-drafts", tags=["legal-rule-drafts"])


def _date(value: str | None, *, required: bool = False) -> date | None:
    if value in (None, ""):
        if required:
            raise HTTPException(status_code=422, detail="date is required")
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        raise HTTPException(status_code=422, detail=f"invalid ISO date: {value}")


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


def _out(db: Session, row: LegalRuleDraftCandidate) -> LegalRuleDraftCandidateOut:
    citations = db.scalars(
        select(LegalRuleDraftCitation)
        .where(LegalRuleDraftCitation.legal_rule_draft_candidate_id == row.legal_rule_draft_candidate_id)
        .order_by(LegalRuleDraftCitation.citation_role, LegalRuleDraftCitation.legal_provision_id)
    ).all()
    citation_out = []
    for citation in citations:
        provision = db.get(LegalProvision, citation.legal_provision_id)
        if provision:
            citation_out.append(
                LegalRuleDraftCitationOut(
                    legal_provision_id=citation.legal_provision_id,
                    citation_role=citation.citation_role,
                    provision=_provision_out(provision),
                )
            )
    return LegalRuleDraftCandidateOut(
        legal_rule_draft_candidate_id=row.legal_rule_draft_candidate_id,
        source_legal_document_version_id=row.source_legal_document_version_id,
        domain=row.domain,
        proposed_rule_code=row.proposed_rule_code,
        proposed_name=row.proposed_name,
        proposed_conditions=row.proposed_conditions,
        proposed_outcome=row.proposed_outcome,
        extraction_method=row.extraction_method,
        model_version=row.model_version,
        confidence=row.confidence,
        rationale=row.rationale,
        status=row.status,
        version=row.version,
        promoted_rule_id=row.promoted_rule_id,
        promoted_rule_version_id=row.promoted_rule_version_id,
        citations=citation_out,
    )


def _validate_ready_for_review(db: Session, row: LegalRuleDraftCandidate) -> None:
    if not (row.proposed_rule_code or "").strip():
        raise HTTPException(status_code=409, detail="proposed_rule_code is required before review")
    if not row.proposed_conditions:
        raise HTTPException(status_code=409, detail="proposed_conditions must be completed before review")
    if not row.proposed_outcome:
        raise HTTPException(status_code=409, detail="proposed_outcome must be completed before review")
    try:
        validate_rule_conditions(row.proposed_conditions)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=f"invalid proposed_conditions: {exc}")
    try:
        validate_rule_outcome_references(
            db,
            domain=row.domain,
            outcome=row.proposed_outcome,
        )
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=f"invalid proposed_outcome: {exc}")
    if row.source_legal_document_version_id:
        citations = db.scalars(
            select(LegalRuleDraftCitation).where(
                LegalRuleDraftCitation.legal_rule_draft_candidate_id == row.legal_rule_draft_candidate_id
            )
        ).all()
        if not citations:
            raise HTTPException(status_code=409, detail="structured-source draft requires at least one citation")
        for citation in citations:
            provision = db.get(LegalProvision, citation.legal_provision_id)
            if (
                provision is None
                or not provision.present_in_source
                or provision.legal_source_document_version_id != row.source_legal_document_version_id
            ):
                raise HTTPException(status_code=409, detail="draft citation is not valid for the selected source version")


def _validate_citations(
    db: Session,
    source_version_id: str | None,
    citations,
) -> list[LegalProvision]:
    rows: list[LegalProvision] = []
    for item in citations:
        provision = db.get(LegalProvision, item.legal_provision_id)
        if not provision or not provision.present_in_source:
            raise HTTPException(status_code=422, detail="draft citation provision not found")
        if source_version_id and provision.legal_source_document_version_id != source_version_id:
            raise HTTPException(status_code=422, detail="draft citation belongs to another source version")
        rows.append(provision)
    return rows


@router.get("", response_model=list[LegalRuleDraftCandidateOut])
def list_drafts(
    draft_status: str | None = None,
    domain: str | None = None,
    limit: int = 100,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("legal_rule.read")),
):
    stmt = select(LegalRuleDraftCandidate)
    if draft_status:
        stmt = stmt.where(LegalRuleDraftCandidate.status == draft_status)
    if domain:
        stmt = stmt.where(LegalRuleDraftCandidate.domain == domain)
    rows = db.scalars(
        stmt.order_by(LegalRuleDraftCandidate.created_at.desc())
        .limit(max(1, min(limit, 500)))
    ).all()
    return [_out(db, x) for x in rows]


@router.post("", response_model=LegalRuleDraftCandidateOut, status_code=201)
def create_draft(
    payload: LegalRuleDraftCandidateCreate,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("legal_rule.manage")),
):
    if payload.source_legal_document_version_id and not db.get(
        LegalSourceDocumentVersion, payload.source_legal_document_version_id
    ):
        raise HTTPException(status_code=422, detail="source legal document version not found")
    if not payload.proposed_conditions or not payload.proposed_outcome:
        raise HTTPException(status_code=422, detail="proposed conditions and outcome are required")
    provisions = _validate_citations(db, payload.source_legal_document_version_id, payload.citations)
    row = LegalRuleDraftCandidate(
        source_legal_document_version_id=payload.source_legal_document_version_id,
        domain=payload.domain,
        proposed_rule_code=payload.proposed_rule_code,
        proposed_name=payload.proposed_name,
        proposed_conditions=payload.proposed_conditions,
        proposed_outcome=payload.proposed_outcome,
        extraction_method=payload.extraction_method,
        model_version=payload.model_version,
        confidence=payload.confidence,
        rationale=payload.rationale,
        created_by=user.user_id,
    )
    db.add(row)
    db.flush()
    for item, provision in zip(payload.citations, provisions):
        db.add(
            LegalRuleDraftCitation(
                legal_rule_draft_candidate_id=row.legal_rule_draft_candidate_id,
                legal_provision_id=provision.legal_provision_id,
                citation_role=item.citation_role,
            )
        )
    write_audit(
        db,
        user_id=user.user_id,
        action="legal_rule_draft.create",
        entity_type="legal_rule_draft_candidate",
        entity_id=row.legal_rule_draft_candidate_id,
        after={
            "domain": row.domain,
            "extraction_method": row.extraction_method,
            "citation_count": len(provisions),
        },
        ai_used=row.extraction_method == "ai",
        ai_model_version=row.model_version,
    )
    db.commit()
    return _out(db, row)


@router.patch("/{draft_id}", response_model=LegalRuleDraftCandidateOut)
def patch_draft(
    draft_id: str,
    payload: LegalRuleDraftCandidatePatch,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("legal_rule.manage")),
):
    row = db.get(LegalRuleDraftCandidate, draft_id)
    if not row:
        raise HTTPException(status_code=404, detail="legal Rule draft not found")
    if row.version != payload.expected_version:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="draft was updated")
    if row.status != "pending":
        raise HTTPException(status_code=409, detail="only pending drafts can be edited")
    changes = payload.model_dump(exclude={"expected_version"}, exclude_unset=True)
    for key, value in changes.items():
        setattr(row, key, value)
    row.version += 1
    row.updated_at = datetime.now(timezone.utc)
    write_audit(
        db,
        user_id=user.user_id,
        action="legal_rule_draft.update",
        entity_type="legal_rule_draft_candidate",
        entity_id=row.legal_rule_draft_candidate_id,
        after={"changed_fields": sorted(changes), "version": row.version},
    )
    db.commit()
    return _out(db, row)


@router.post("/{draft_id}/review", response_model=LegalRuleDraftCandidateOut)
def review_draft(
    draft_id: str,
    payload: LegalRuleDraftCandidateReview,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("legal_rule.manage")),
):
    row = db.get(LegalRuleDraftCandidate, draft_id)
    if not row:
        raise HTTPException(status_code=404, detail="legal Rule draft not found")
    if row.version != payload.expected_version:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="draft was updated")
    if row.status != "pending":
        raise HTTPException(status_code=409, detail="only pending drafts can be reviewed")
    if payload.status == "reviewed":
        _validate_ready_for_review(db, row)
    row.status = payload.status
    row.reviewed_by = user.user_id
    row.reviewed_at = datetime.now(timezone.utc)
    row.version += 1
    row.updated_at = datetime.now(timezone.utc)
    write_audit(
        db,
        user_id=user.user_id,
        action=f"legal_rule_draft.{payload.status}",
        entity_type="legal_rule_draft_candidate",
        entity_id=row.legal_rule_draft_candidate_id,
        after={"status": row.status, "version": row.version},
    )
    db.commit()
    return _out(db, row)


@router.post("/{draft_id}/promote", response_model=LegalRuleDraftCandidateOut)
def promote_draft(
    draft_id: str,
    payload: LegalRuleDraftCandidatePromote,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("legal_rule.approve")),
):
    row = db.get(LegalRuleDraftCandidate, draft_id)
    if not row:
        raise HTTPException(status_code=404, detail="legal Rule draft not found")
    if row.version != payload.expected_version:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="draft was updated")
    if row.status != "reviewed":
        raise HTTPException(status_code=409, detail="draft must be reviewed before promotion")
    _validate_ready_for_review(db, row)
    citations = db.scalars(
        select(LegalRuleDraftCitation).where(
            LegalRuleDraftCitation.legal_rule_draft_candidate_id == row.legal_rule_draft_candidate_id
        )
    ).all()
    if row.source_legal_document_version_id and not citations:
        raise HTTPException(status_code=409, detail="structured-source draft requires at least one citation")

    start = _date(payload.effective_from, required=True)
    end = _date(payload.effective_to)
    if end and end < start:
        raise HTTPException(status_code=422, detail="effective_to must not be before effective_from")

    rule = db.scalar(select(LegalRule).where(LegalRule.rule_code == row.proposed_rule_code))
    if rule is None:
        rule = LegalRule(
            rule_code=row.proposed_rule_code,
            name=row.proposed_name,
            domain=row.domain,
            description=f"Promoted from legal Rule draft {row.legal_rule_draft_candidate_id}",
            created_by=user.user_id,
        )
        db.add(rule)
        db.flush()
    elif rule.domain != row.domain:
        raise HTTPException(status_code=409, detail="existing rule_code belongs to a different domain")

    max_version = db.scalar(
        select(func.max(LegalRuleVersion.version_no)).where(LegalRuleVersion.rule_id == rule.rule_id)
    ) or 0
    rv = LegalRuleVersion(
        rule_id=rule.rule_id,
        version_no=max_version + 1,
        effective_from=start,
        effective_to=end,
        conditions=row.proposed_conditions,
        outcome=row.proposed_outcome,
        source_legal_document_version_id=row.source_legal_document_version_id,
        source_reference=f"draft-candidate:{row.legal_rule_draft_candidate_id}",
        status="draft",
        created_by=user.user_id,
    )
    db.add(rv)
    db.flush()

    for citation in citations:
        provision = db.get(LegalProvision, citation.legal_provision_id)
        if not provision or not provision.present_in_source:
            raise HTTPException(status_code=409, detail="draft citation is no longer present in source")
        snapshot = "\n".join(
            x for x in [provision.display_label, provision.heading_text, provision.body_text] if x
        )
        db.add(
            LegalRuleCitation(
                legal_rule_version_id=rv.legal_rule_version_id,
                legal_provision_id=provision.legal_provision_id,
                citation_role=citation.citation_role,
                cited_text_snapshot=snapshot,
                created_by=user.user_id,
            )
        )

    row.status = "promoted"
    row.promoted_rule_id = rule.rule_id
    row.promoted_rule_version_id = rv.legal_rule_version_id
    row.version += 1
    row.updated_at = datetime.now(timezone.utc)
    write_audit(
        db,
        user_id=user.user_id,
        action="legal_rule_draft.promote",
        entity_type="legal_rule_draft_candidate",
        entity_id=row.legal_rule_draft_candidate_id,
        after={
            "promoted_rule_id": rule.rule_id,
            "promoted_rule_version_id": rv.legal_rule_version_id,
            "rule_version_status": "draft",
        },
    )
    db.commit()
    return _out(db, row)
