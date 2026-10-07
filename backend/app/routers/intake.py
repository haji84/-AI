from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from ..audit import write_audit
from ..authz import require_permission, require_mutation_permission, permission_codes
from ..db import get_db
from ..document_intake import build_difference_candidates, classify_submission, detect_fields, extract_document, find_facility_candidates
from ..models import Document, DocumentAnalysis, Facility, FacilityChangeProposal, Submission, SubmissionType, User
from ..schemas import (
    DocumentAnalysisCreate,
    DocumentAnalysisOut,
    DocumentAnalysisReview,
    FacilityChangeProposalApply,
    FacilityChangeProposalOut,
    IntakeConfirmReceipt,
    SubmissionOut,
)
from .submissions import _date, _link_documents, _submission_out, _sync_specialized, _validate_official_number

router = APIRouter(tags=["document-intake"])


def _guard_inquiry_analysis(db,user,analysis):
    from ..inquiries_service import guard_document
    doc=db.get(Document,analysis.document_id)
    if doc:guard_document(db,user,doc)


def _claim_analysis(db: Session, row: DocumentAnalysis, expected_version: int, allowed_statuses: tuple[str, ...], **values):
    """Gate every review/receipt/proposal write on the same lifecycle row.

    Every successful transition consumes a revision and locks this row until
    commit. A racing review must finish before a stale proposal can proceed;
    failed claims roll back the entire transaction.
    """
    result = db.execute(
        update(DocumentAnalysis)
        .where(DocumentAnalysis.document_analysis_id == row.document_analysis_id,
               DocumentAnalysis.version == expected_version,
               DocumentAnalysis.status.in_(allowed_statuses))
        .values(**values)
        .execution_options(synchronize_session=False)
    )
    if result.rowcount != 1:
        db.rollback()
        raise HTTPException(status_code=409, detail="analysis changed or is no longer in the required review state")
    db.refresh(row)


def _analysis_out(row: DocumentAnalysis) -> DocumentAnalysisOut:
    return DocumentAnalysisOut(
        document_analysis_id=row.document_analysis_id,
        document_id=row.document_id,
        status=row.status,
        extraction_method=row.extraction_method,
        extracted_text=row.extracted_text,
        page_count=row.page_count,
        detected_submission_type_code=row.detected_submission_type_code,
        detected_fields=row.detected_fields or {},
        facility_candidates=row.facility_candidates or [],
        difference_candidates=row.difference_candidates or {},
        confidence=row.confidence,
        evidence=row.evidence or {},
        selected_building_id=row.selected_building_id,
        selected_submission_type_code=row.selected_submission_type_code,
        version=row.version,
    )


def _proposal_out(row: FacilityChangeProposal) -> FacilityChangeProposalOut:
    return FacilityChangeProposalOut(
        facility_change_proposal_id=row.facility_change_proposal_id,
        document_analysis_id=row.document_analysis_id,
        building_id=row.building_id,
        expected_facility_version=row.expected_facility_version,
        changes=row.changes or {},
        status=row.status,
        version=row.version,
    )


@router.get("/document-analyses", response_model=list[DocumentAnalysisOut])
def list_analyses(
    status_filter: str | None = None,
    limit: int = 50,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("intake.read")),
):
    stmt = select(DocumentAnalysis)
    if 'hazardous.read' not in permission_codes(db, user.user_id):
        protected = select(Document.document_id).where(Document.document_type == 'hazardous_evidence')
        stmt = stmt.where(DocumentAnalysis.document_id.not_in(protected))
    if status_filter:
        stmt = stmt.where(DocumentAnalysis.status == status_filter)
    rows = db.scalars(stmt.order_by(DocumentAnalysis.created_at.desc()).limit(max(1, min(limit, 200)))).all()
    allowed=[]
    for row in rows:
        try:_guard_inquiry_analysis(db,user,row)
        except HTTPException as exc:
            if exc.status_code==403:continue
            raise
        allowed.append(_analysis_out(row))
    return allowed


@router.post("/document-analyses", response_model=DocumentAnalysisOut, status_code=201)
def analyze_document(
    payload: DocumentAnalysisCreate,
    db: Session = Depends(get_db),
    user: User = Depends(require_mutation_permission("intake.analyze")),
):
    doc = db.get(Document, payload.document_id)
    if not doc:
        raise HTTPException(status_code=404, detail="document not found")
    from ..inquiries_service import guard_document
    guard_document(db,user,doc)
    try:
        text, method, page_count, extraction_evidence = extract_document(doc, payload.force_ocr)
    except (ValueError, FileNotFoundError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    type_code, confidence, classification_evidence = classify_submission(text)
    fields, field_evidence = detect_fields(text, type_code)
    candidates = find_facility_candidates(db, text, fields)
    diffs = build_difference_candidates(db, candidates[0]["building_id"], fields) if candidates else {}
    row = DocumentAnalysis(
        document_id=doc.document_id,
        extraction_method=method,
        extracted_text=text,
        page_count=page_count,
        detected_submission_type_code=type_code,
        detected_fields=fields,
        facility_candidates=candidates,
        difference_candidates=diffs,
        confidence=confidence,
        evidence={"extraction": extraction_evidence, "classification": classification_evidence, "fields": field_evidence},
        created_by=user.user_id,
    )
    db.add(row)
    db.flush()
    out = _analysis_out(row)
    write_audit(db, user_id=user.user_id, action="document_analysis.create", entity_type="document_analysis", entity_id=row.document_analysis_id, after={"document_id": doc.document_id, "method": method, "detected_type": type_code, "candidate_count": len(candidates), "confidence": confidence}, ai_used=False)
    db.commit()
    return out


@router.get("/document-analyses/{analysis_id}", response_model=DocumentAnalysisOut)
def get_analysis(
    analysis_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("intake.read")),
):
    row = db.get(DocumentAnalysis, analysis_id)
    if not row:
        raise HTTPException(status_code=404, detail="analysis not found")
    _guard_inquiry_analysis(db,user,row)
    return _analysis_out(row)


@router.post("/document-analyses/{analysis_id}/review", response_model=DocumentAnalysisOut)
def review_analysis(
    analysis_id: str,
    payload: DocumentAnalysisReview,
    db: Session = Depends(get_db),
    user: User = Depends(require_mutation_permission("intake.review")),
):
    row = db.get(DocumentAnalysis, analysis_id)
    if not row:
        raise HTTPException(status_code=404, detail="analysis not found")
    _guard_inquiry_analysis(db,user,row)
    facility = db.get(Facility, payload.building_id)
    if not facility:
        raise HTTPException(status_code=404, detail="facility not found")
    type_code = payload.submission_type_code or row.detected_submission_type_code
    if type_code and not db.scalar(select(SubmissionType).where(SubmissionType.code == type_code, SubmissionType.active.is_(True))):
        raise HTTPException(status_code=404, detail="submission type not found")
    if row.version != payload.expected_version:
        raise HTTPException(status_code=409, detail={"message": "analysis was updated by another user", "current": _analysis_out(row).model_dump(mode="json")})
    before = {"status": row.status, "version": row.version, "selected_building_id": row.selected_building_id}
    now = datetime.now(timezone.utc)
    _claim_analysis(db, row, payload.expected_version, ("analyzed", "reviewed"),
                    status="reviewed", version=payload.expected_version + 1, updated_at=now)
    diffs = build_difference_candidates(db, facility.building_id, row.detected_fields or {})
    row.selected_building_id = facility.building_id
    row.selected_submission_type_code = type_code
    row.difference_candidates = diffs
    row.reviewed_by = user.user_id
    row.reviewed_at = now
    # Preserve the old review's evidence, including an empty replacement review.
    # Never repurpose its proposal ID for a different target or source revision.
    obsolete = db.scalars(select(FacilityChangeProposal).where(
        FacilityChangeProposal.document_analysis_id == row.document_analysis_id,
        FacilityChangeProposal.status == "pending")).all()
    for existing in obsolete:
        previous_version = existing.version
        existing.status = "superseded"
        existing.version += 1
        existing.updated_at = now
        write_audit(db, user_id=user.user_id, action="facility_change_proposal.supersede",
                    entity_type="facility_change_proposal", entity_id=existing.facility_change_proposal_id,
                    before={"status": "pending", "version": previous_version, "building_id": existing.building_id, "changes": existing.changes},
                    after={"status": "superseded", "version": existing.version, "analysis_id": row.document_analysis_id, "review_version": row.version}, ai_used=False)
    if diffs:
        db.add(FacilityChangeProposal(document_analysis_id=row.document_analysis_id, building_id=facility.building_id, expected_facility_version=facility.version, changes=diffs))
    db.flush()
    out = _analysis_out(row)
    write_audit(db, user_id=user.user_id, action="document_analysis.review", entity_type="document_analysis", entity_id=row.document_analysis_id, before=before, after={"status": row.status, "version": row.version, "selected_building_id": facility.building_id, "selected_submission_type_code": type_code, "difference_paths": sorted(diffs)}, ai_used=False)
    db.commit()
    return out


@router.get("/document-analyses/{analysis_id}/change-proposals", response_model=list[FacilityChangeProposalOut])
def list_change_proposals(
    analysis_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("intake.read")),
):
    analysis=db.get(DocumentAnalysis,analysis_id)
    if analysis:_guard_inquiry_analysis(db,user,analysis)
    rows = db.scalars(select(FacilityChangeProposal).where(FacilityChangeProposal.document_analysis_id == analysis_id).order_by(FacilityChangeProposal.created_at)).all()
    return [_proposal_out(x) for x in rows]


@router.post("/document-analyses/{analysis_id}/confirm-receipt", response_model=SubmissionOut, status_code=201)
def confirm_receipt(
    analysis_id: str,
    payload: IntakeConfirmReceipt,
    db: Session = Depends(get_db),
    user: User = Depends(require_mutation_permission("submission.create")),
):
    analysis = db.get(DocumentAnalysis, analysis_id)
    if not analysis:
        raise HTTPException(status_code=404, detail="analysis not found")
    _guard_inquiry_analysis(db,user,analysis)
    if analysis.version != payload.expected_version:
        raise HTTPException(status_code=409, detail={"message": "analysis was updated by another user", "current": _analysis_out(analysis).model_dump(mode="json")})
    if analysis.status != "reviewed" or not analysis.selected_building_id or not analysis.selected_submission_type_code:
        raise HTTPException(status_code=409, detail="human review is required before receipt confirmation")
    st = db.scalar(select(SubmissionType).where(SubmissionType.code == analysis.selected_submission_type_code, SubmissionType.active.is_(True)))
    if not st:
        raise HTTPException(status_code=404, detail="submission type not found")
    _validate_official_number(payload.official_number)
    submitted_at = _date(payload.submitted_at)
    before = {"status": analysis.status, "version": analysis.version}
    _claim_analysis(db, analysis, payload.expected_version, ("reviewed",),
                    status="receipt_confirmed", version=payload.expected_version + 1,
                    updated_at=datetime.now(timezone.utc))
    submission = Submission(
        building_id=analysis.selected_building_id,
        submission_type_id=st.submission_type_id,
        official_number=payload.official_number,
        submitted_at=submitted_at,
        submitted_by=payload.submitted_by,
        notes=payload.notes,
        payload_data=payload.payload_data,
        created_by=user.user_id,
    )
    db.add(submission)
    db.flush()
    _link_documents(db, submission, [analysis.document_id], st.requires_document)
    _sync_specialized(db, submission, st.code)
    db.flush()
    out = _submission_out(db, submission)
    write_audit(db, user_id=user.user_id, action="document_analysis.confirm_receipt", entity_type="submission", entity_id=submission.submission_id, before=before, after={"analysis_id": analysis.document_analysis_id, "analysis_version": analysis.version, "status": analysis.status, "building_id": submission.building_id, "submission_type_code": st.code, "document_id": analysis.document_id}, ai_used=False)
    db.commit()
    return out


@router.post("/facility-change-proposals/{proposal_id}/apply", response_model=FacilityChangeProposalOut)
def apply_change_proposal(
    proposal_id: str,
    payload: FacilityChangeProposalApply,
    db: Session = Depends(get_db),
    user: User = Depends(require_mutation_permission("intake.apply")),
):
    proposal = db.get(FacilityChangeProposal, proposal_id)
    if not proposal:
        raise HTTPException(status_code=404, detail="change proposal not found")
    analysis=db.get(DocumentAnalysis,proposal.document_analysis_id)
    if not analysis:
        raise HTTPException(status_code=409, detail="proposal analysis is no longer available")
    _guard_inquiry_analysis(db,user,analysis)
    _claim_analysis(db, analysis, analysis.version, ("reviewed", "receipt_confirmed"),
                    version=analysis.version + 1, updated_at=datetime.now(timezone.utc))
    # Also reject inconsistent proposals persisted by older versions of intake.
    if proposal.building_id != analysis.selected_building_id or proposal.changes != analysis.difference_candidates:
        db.rollback()
        raise HTTPException(status_code=409, detail="proposal no longer matches the current Human review")
    if proposal.status != "pending":
        raise HTTPException(status_code=409, detail="proposal is not pending")
    if proposal.version != payload.expected_version:
        raise HTTPException(status_code=409, detail={"message": "proposal was updated by another user", "current": _proposal_out(proposal).model_dump(mode="json")})
    facility = db.get(Facility, proposal.building_id)
    if not facility:
        raise HTTPException(status_code=404, detail="facility not found")
    if facility.version != payload.expected_facility_version or facility.version != proposal.expected_facility_version:
        raise HTTPException(status_code=409, detail={"message": "facility was updated after proposal creation", "current_version": facility.version})
    allowed = {"facility.name": "name", "facility.address": "address", "facility.phone": "phone"}
    accepted = [p for p in payload.accepted_paths if p in allowed and p in (proposal.changes or {})]
    if not accepted:
        raise HTTPException(status_code=422, detail="no approved change paths")
    values = {allowed[path]: proposal.changes[path]["proposed"] for path in accepted}
    before = {k: getattr(facility, k) for k in values}
    values["version"] = facility.version + 1
    values["updated_at"] = datetime.now(timezone.utc)
    proposal_version = proposal.version
    claimed = db.execute(update(FacilityChangeProposal).where(
        FacilityChangeProposal.facility_change_proposal_id == proposal.facility_change_proposal_id,
        FacilityChangeProposal.version == payload.expected_version,
        FacilityChangeProposal.status == "pending").values(
            status="applied", version=proposal_version + 1, reviewed_by=user.user_id,
            reviewed_at=values["updated_at"], applied_at=values["updated_at"], updated_at=values["updated_at"])
        .execution_options(synchronize_session=False))
    if claimed.rowcount != 1:
        db.rollback()
        raise HTTPException(status_code=409, detail="proposal update conflict")
    result = db.execute(update(Facility).where(Facility.building_id == facility.building_id, Facility.version == facility.version).values(**values))
    if result.rowcount != 1:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="facility update conflict")
    db.refresh(proposal)
    db.flush()
    out = _proposal_out(proposal)
    write_audit(db, user_id=user.user_id, action="facility_change_proposal.apply", entity_type="facility", entity_id=facility.building_id, before=before, after={**{k: values[k] for k in before}, "accepted_paths": accepted, "analysis_id": proposal.document_analysis_id, "analysis_version": analysis.version, "proposal_id": proposal.facility_change_proposal_id}, ai_used=False)
    db.commit()
    return out
