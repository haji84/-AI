from __future__ import annotations

from datetime import date, datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from ..audit import write_audit
from ..authz import require_permission
from ..db import get_db
from ..legal_rule_validation import validate_rule_conditions
from ..legal_requirement_engine import evaluate_approved_requirement_rules
from ..models import (
    Document,
    Facility,
    FacilityDetail,
    FacilityFloor,
    LegalProvision,
    LegalProvisionReviewCandidate,
    LegalRule,
    LegalRuleCitation,
    LegalRuleDraftCandidate,
    LegalRuleVersion,
    LegalSourceDocumentVersion,
    RequirementEvaluation,
    User,
)
from ..schemas import (
    LegalProvisionOut,
    LegalRuleCitationCreate,
    LegalRuleCitationOut,
    LegalRuleCoverageOut,
    LegalRuleCreate,
    LegalRuleOut,
    LegalRuleVersionApprove,
    LegalRuleVersionCreate,
    LegalRuleVersionOut,
    RequirementEvaluationCreate,
    RequirementEvaluationOut,
)

router = APIRouter(prefix="/legal-rules", tags=["legal-rules"])

ALLOWED_FIELDS = {
    "status",
    "classification_code",
    "structure",
    "above_ground_floors",
    "basement_floors",
    "building_area",
    "total_floor_area",
    "occupancy_total",
    "employee_total",
    "floor_count",
}
ALLOWED_OPS = {"eq", "ne", "in", "contains", "gte", "lte", "gt", "lt", "exists"}


def _date(value: str | None, *, required: bool = False) -> date | None:
    if value in (None, ""):
        if required:
            raise HTTPException(status_code=422, detail="date is required")
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        raise HTTPException(status_code=422, detail=f"invalid ISO date: {value}")


def _rule_out(row: LegalRule) -> LegalRuleOut:
    return LegalRuleOut(
        rule_id=row.rule_id,
        rule_code=row.rule_code,
        name=row.name,
        domain=row.domain,
        description=row.description,
        active=row.active,
    )


def _version_out(row: LegalRuleVersion) -> LegalRuleVersionOut:
    return LegalRuleVersionOut(
        legal_rule_version_id=row.legal_rule_version_id,
        rule_id=row.rule_id,
        version_no=row.version_no,
        effective_from=row.effective_from.isoformat(),
        effective_to=row.effective_to.isoformat() if row.effective_to else None,
        conditions=row.conditions,
        outcome=row.outcome,
        source_document_id=row.source_document_id,
        source_reference=row.source_reference,
        source_legal_document_version_id=row.source_legal_document_version_id,
        status=row.status,
        version=row.version,
    )



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


def _citation_out(db: Session, row: LegalRuleCitation) -> LegalRuleCitationOut:
    provision = db.get(LegalProvision, row.legal_provision_id)
    return LegalRuleCitationOut(
        legal_rule_version_id=row.legal_rule_version_id,
        legal_provision_id=row.legal_provision_id,
        citation_role=row.citation_role,
        cited_text_snapshot=row.cited_text_snapshot,
        provision=_provision_out(provision),
    )


def _evaluation_out(row: RequirementEvaluation) -> RequirementEvaluationOut:
    return RequirementEvaluationOut(
        evaluation_id=row.evaluation_id,
        building_id=row.building_id,
        domain=row.domain,
        evaluation_date=row.evaluation_date.isoformat(),
        facility_version=row.facility_version,
        engine_version=row.engine_version,
        input_snapshot=row.input_snapshot,
        results=row.results,
        status=row.status,
    )


def _validate_conditions(payload: dict) -> None:
    try:
        validate_rule_conditions(payload)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))


def _snapshot(db: Session, facility: Facility) -> dict:
    detail = db.get(FacilityDetail, facility.building_id)
    floor_count = db.scalar(
        select(func.count()).select_from(FacilityFloor).where(FacilityFloor.building_id == facility.building_id)
    ) or 0

    def val(name: str):
        value = getattr(detail, name, None) if detail else None
        if hasattr(value, "as_integer_ratio"):
            return float(value)
        return value

    return {
        "status": facility.status,
        "classification_code": val("classification_code"),
        "structure": val("structure"),
        "above_ground_floors": val("above_ground_floors"),
        "basement_floors": val("basement_floors"),
        "building_area": val("building_area"),
        "total_floor_area": val("total_floor_area"),
        "occupancy_total": val("occupancy_total"),
        "employee_total": val("employee_total"),
        "floor_count": int(floor_count),
    }


def _clause_result(clause: dict, snapshot: dict) -> dict:
    field = clause["field"]
    op = clause["op"]
    expected = clause.get("value")
    actual = snapshot.get(field)
    matched = False
    try:
        if op == "exists":
            matched = actual not in (None, "")
        elif op == "eq":
            matched = actual == expected
        elif op == "ne":
            matched = actual != expected
        elif op == "in":
            matched = actual in expected if isinstance(expected, list) else False
        elif op == "contains":
            matched = str(expected) in str(actual) if actual is not None else False
        elif op == "gte":
            matched = actual is not None and actual >= expected
        elif op == "lte":
            matched = actual is not None and actual <= expected
        elif op == "gt":
            matched = actual is not None and actual > expected
        elif op == "lt":
            matched = actual is not None and actual < expected
    except (TypeError, ValueError):
        matched = False
    return {
        "field": field,
        "op": op,
        "expected": expected,
        "actual": actual,
        "matched": matched,
    }


def _match_conditions(conditions: dict, snapshot: dict) -> tuple[bool, dict]:
    all_results = [_clause_result(x, snapshot) for x in conditions.get("all", [])]
    any_results = [_clause_result(x, snapshot) for x in conditions.get("any", [])]
    all_ok = all(x["matched"] for x in all_results) if all_results else True
    any_ok = any(x["matched"] for x in any_results) if any_results else True
    return all_ok and any_ok, {"all": all_results, "any": any_results}


def _ranges_overlap(a_from: date, a_to: date | None, b_from: date, b_to: date | None) -> bool:
    a_end = a_to or date.max
    b_end = b_to or date.max
    return a_from <= b_end and b_from <= a_end


@router.get("", response_model=list[LegalRuleOut])
def list_rules(
    domain: str | None = None,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("legal_rule.read")),
):
    stmt = select(LegalRule).order_by(LegalRule.rule_code)
    if domain:
        stmt = stmt.where(LegalRule.domain == domain)
    return [_rule_out(x) for x in db.scalars(stmt).all()]


@router.post("", response_model=LegalRuleOut, status_code=201)
def create_rule(
    payload: LegalRuleCreate,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("legal_rule.manage")),
):
    if db.scalar(select(LegalRule).where(LegalRule.rule_code == payload.rule_code)):
        raise HTTPException(status_code=409, detail="rule_code already exists")
    row = LegalRule(
        rule_code=payload.rule_code,
        name=payload.name,
        domain=payload.domain,
        description=payload.description,
        created_by=user.user_id,
    )
    db.add(row)
    db.flush()
    write_audit(
        db,
        user_id=user.user_id,
        action="legal_rule.create",
        entity_type="legal_rule",
        entity_id=row.rule_id,
        after=_rule_out(row).model_dump(mode="json"),
    )
    db.commit()
    return _rule_out(row)


@router.get("/coverage", response_model=LegalRuleCoverageOut)
def legal_rule_coverage(
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("legal_rule.read")),
):
    tracked_domains = ("equipment_requirement", "submission_requirement")

    def nested(rows):
        out: dict[str, dict[str, int]] = {domain: {} for domain in tracked_domains}
        for domain, state, count in rows:
            if domain in out:
                out[domain][str(state)] = int(count)
        return out

    review_rows = db.execute(
        select(
            LegalProvisionReviewCandidate.category,
            LegalProvisionReviewCandidate.status,
            func.count(),
        )
        .where(LegalProvisionReviewCandidate.category.in_(tracked_domains))
        .group_by(
            LegalProvisionReviewCandidate.category,
            LegalProvisionReviewCandidate.status,
        )
    ).all()

    draft_rows = db.execute(
        select(
            LegalRuleDraftCandidate.domain,
            LegalRuleDraftCandidate.status,
            func.count(),
        )
        .where(LegalRuleDraftCandidate.domain.in_(tracked_domains))
        .group_by(
            LegalRuleDraftCandidate.domain,
            LegalRuleDraftCandidate.status,
        )
    ).all()

    rule_version_rows = db.execute(
        select(
            LegalRule.domain,
            LegalRuleVersion.status,
            func.count(),
        )
        .join(
            LegalRuleVersion,
            LegalRuleVersion.rule_id == LegalRule.rule_id,
        )
        .where(LegalRule.domain.in_(tracked_domains))
        .group_by(LegalRule.domain, LegalRuleVersion.status)
    ).all()

    approved_rows = db.execute(
        select(LegalRule.domain, func.count(func.distinct(LegalRule.rule_id)))
        .join(
            LegalRuleVersion,
            LegalRuleVersion.rule_id == LegalRule.rule_id,
        )
        .where(
            LegalRule.domain.in_(tracked_domains),
            LegalRuleVersion.status == "approved",
        )
        .group_by(LegalRule.domain)
    ).all()
    approved = {domain: 0 for domain in tracked_domains}
    approved.update({str(domain): int(count) for domain, count in approved_rows})

    citation_count = db.scalar(
        select(func.count()).select_from(LegalRuleCitation)
    ) or 0

    return LegalRuleCoverageOut(
        review_queue_by_domain_status=nested(review_rows),
        draft_candidates_by_domain_status=nested(draft_rows),
        rule_versions_by_domain_status=nested(rule_version_rows),
        approved_rule_count_by_domain=approved,
        exact_citation_count=int(citation_count),
        note=(
            "Counts show workflow progress only. They are not a percentage of legal completeness "
            "and do not imply that all applicable legal requirements have been authored."
        ),
    )


@router.get("/{rule_id}/versions", response_model=list[LegalRuleVersionOut])
def list_versions(
    rule_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("legal_rule.read")),
):
    if not db.get(LegalRule, rule_id):
        raise HTTPException(status_code=404, detail="legal rule not found")
    rows = db.scalars(
        select(LegalRuleVersion)
        .where(LegalRuleVersion.rule_id == rule_id)
        .order_by(LegalRuleVersion.version_no.desc())
    ).all()
    return [_version_out(x) for x in rows]


@router.post("/{rule_id}/versions", response_model=LegalRuleVersionOut, status_code=201)
def create_version(
    rule_id: str,
    payload: LegalRuleVersionCreate,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("legal_rule.manage")),
):
    rule = db.get(LegalRule, rule_id)
    if not rule:
        raise HTTPException(status_code=404, detail="legal rule not found")
    _validate_conditions(payload.conditions)
    if not payload.outcome:
        raise HTTPException(status_code=422, detail="outcome must not be empty")
    start = _date(payload.effective_from, required=True)
    end = _date(payload.effective_to)
    if end and end < start:
        raise HTTPException(status_code=422, detail="effective_to must not be before effective_from")
    if payload.source_document_id and not db.get(Document, payload.source_document_id):
        raise HTTPException(status_code=422, detail="source_document_id not found")
    if payload.source_legal_document_version_id and not db.get(
        LegalSourceDocumentVersion, payload.source_legal_document_version_id
    ):
        raise HTTPException(status_code=422, detail="source_legal_document_version_id not found")
    if db.scalar(
        select(LegalRuleVersion).where(
            LegalRuleVersion.rule_id == rule_id,
            LegalRuleVersion.version_no == payload.version_no,
        )
    ):
        raise HTTPException(status_code=409, detail="rule version already exists")
    row = LegalRuleVersion(
        rule_id=rule_id,
        version_no=payload.version_no,
        effective_from=start,
        effective_to=end,
        conditions=payload.conditions,
        outcome=payload.outcome,
        source_document_id=payload.source_document_id,
        source_reference=payload.source_reference,
        source_legal_document_version_id=payload.source_legal_document_version_id,
        created_by=user.user_id,
    )
    db.add(row)
    db.flush()
    write_audit(
        db,
        user_id=user.user_id,
        action="legal_rule_version.create",
        entity_type="legal_rule_version",
        entity_id=row.legal_rule_version_id,
        after=_version_out(row).model_dump(mode="json"),
    )
    db.commit()
    return _version_out(row)


@router.post("/versions/{version_id}/approve", response_model=LegalRuleVersionOut)
def approve_version(
    version_id: str,
    payload: LegalRuleVersionApprove,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("legal_rule.approve")),
):
    row = db.get(LegalRuleVersion, version_id)
    if not row:
        raise HTTPException(status_code=404, detail="legal rule version not found")
    if row.version != payload.expected_version:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="rule version was updated")
    if row.status != "draft":
        raise HTTPException(status_code=409, detail="only draft rule versions can be approved")
    if (
        not row.source_document_id
        and not row.source_legal_document_version_id
        and not (row.source_reference or "").strip()
    ):
        raise HTTPException(status_code=409, detail="verified source reference is required before approval")
    if row.source_legal_document_version_id:
        citations = db.scalars(
            select(LegalRuleCitation).where(
                LegalRuleCitation.legal_rule_version_id == row.legal_rule_version_id
            )
        ).all()
        if not citations:
            raise HTTPException(
                status_code=409,
                detail="at least one structured provision citation is required for a structured legal source",
            )
        for citation in citations:
            provision = db.get(LegalProvision, citation.legal_provision_id)
            if (
                provision is None
                or not provision.present_in_source
                or provision.legal_source_document_version_id != row.source_legal_document_version_id
            ):
                raise HTTPException(status_code=409, detail="citation does not belong to the active source version")
    others = db.scalars(
        select(LegalRuleVersion).where(
            LegalRuleVersion.rule_id == row.rule_id,
            LegalRuleVersion.status == "approved",
            LegalRuleVersion.legal_rule_version_id != row.legal_rule_version_id,
        )
    ).all()
    for other in others:
        if _ranges_overlap(row.effective_from, row.effective_to, other.effective_from, other.effective_to):
            raise HTTPException(status_code=409, detail="approved rule effective periods must not overlap")
    before = _version_out(row).model_dump(mode="json")
    row.status = "approved"
    row.approved_by = user.user_id
    row.approved_at = datetime.now(timezone.utc)
    row.version += 1
    row.updated_at = datetime.now(timezone.utc)
    db.flush()
    write_audit(
        db,
        user_id=user.user_id,
        action="legal_rule_version.approve",
        entity_type="legal_rule_version",
        entity_id=row.legal_rule_version_id,
        before=before,
        after=_version_out(row).model_dump(mode="json"),
    )
    db.commit()
    return _version_out(row)




@router.get("/source-versions/{source_version_id}/provisions", response_model=list[LegalProvisionOut])
def list_source_provisions(
    source_version_id: str,
    q: str | None = None,
    provision_type: str | None = None,
    offset: int = 0,
    limit: int = 200,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("legal_rule.read")),
):
    if not db.get(LegalSourceDocumentVersion, source_version_id):
        raise HTTPException(status_code=404, detail="legal source document version not found")
    stmt = select(LegalProvision).where(
        LegalProvision.legal_source_document_version_id == source_version_id,
        LegalProvision.present_in_source.is_(True),
    )
    if provision_type:
        stmt = stmt.where(LegalProvision.provision_type == provision_type)
    if q:
        needle = f"%{q}%"
        stmt = stmt.where(
            or_(
                LegalProvision.display_label.ilike(needle),
                LegalProvision.heading_text.ilike(needle),
                LegalProvision.body_text.ilike(needle),
                LegalProvision.provision_key.ilike(needle),
            )
        )
    rows = db.scalars(
        stmt.order_by(LegalProvision.sequence_no)
        .offset(max(0, offset))
        .limit(max(1, min(limit, 1000)))
    ).all()
    return [_provision_out(x) for x in rows]


@router.get("/versions/{version_id}/citations", response_model=list[LegalRuleCitationOut])
def list_rule_citations(
    version_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("legal_rule.read")),
):
    if not db.get(LegalRuleVersion, version_id):
        raise HTTPException(status_code=404, detail="legal rule version not found")
    rows = db.scalars(
        select(LegalRuleCitation)
        .where(LegalRuleCitation.legal_rule_version_id == version_id)
        .order_by(LegalRuleCitation.citation_role, LegalRuleCitation.legal_provision_id)
    ).all()
    return [_citation_out(db, x) for x in rows]


@router.post("/versions/{version_id}/citations", response_model=LegalRuleCitationOut, status_code=201)
def add_rule_citation(
    version_id: str,
    payload: LegalRuleCitationCreate,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("legal_rule.manage")),
):
    version = db.get(LegalRuleVersion, version_id)
    if not version:
        raise HTTPException(status_code=404, detail="legal rule version not found")
    if version.status != "draft":
        raise HTTPException(status_code=409, detail="citations can only be changed while Rule Version is draft")
    provision = db.get(LegalProvision, payload.legal_provision_id)
    if not provision or not provision.present_in_source:
        raise HTTPException(status_code=422, detail="legal provision not found in current source")
    if (
        version.source_legal_document_version_id
        and provision.legal_source_document_version_id != version.source_legal_document_version_id
    ):
        raise HTTPException(status_code=422, detail="legal provision belongs to a different source version")
    existing = db.get(
        LegalRuleCitation,
        (version_id, payload.legal_provision_id, payload.citation_role),
    )
    if existing:
        raise HTTPException(status_code=409, detail="citation already exists")
    snapshot = "\n".join(
        x for x in [provision.display_label, provision.heading_text, provision.body_text] if x
    )
    row = LegalRuleCitation(
        legal_rule_version_id=version_id,
        legal_provision_id=payload.legal_provision_id,
        citation_role=payload.citation_role,
        cited_text_snapshot=snapshot,
        created_by=user.user_id,
    )
    db.add(row)
    write_audit(
        db,
        user_id=user.user_id,
        action="legal_rule_citation.create",
        entity_type="legal_rule_version",
        entity_id=version_id,
        after={
            "legal_provision_id": payload.legal_provision_id,
            "citation_role": payload.citation_role,
        },
    )
    db.commit()
    return _citation_out(db, row)


@router.post("/evaluate/{building_id}", response_model=RequirementEvaluationOut, status_code=201)
def evaluate_requirements(
    building_id: str,
    payload: RequirementEvaluationCreate,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("legal_rule.evaluate")),
):
    facility = db.get(Facility, building_id)
    if not facility:
        raise HTTPException(status_code=404, detail="facility not found")
    evaluation_date = _date(payload.evaluation_date) or date.today()
    snapshot, results = evaluate_approved_requirement_rules(
        db,
        facility=facility,
        domain=payload.domain,
        evaluation_date=evaluation_date,
    )
    evaluation = RequirementEvaluation(
        building_id=building_id,
        domain=payload.domain,
        evaluation_date=evaluation_date,
        facility_version=facility.version,
        input_snapshot=snapshot,
        results=results,
        status="candidate",
        created_by=user.user_id,
    )
    db.add(evaluation)
    db.flush()
    write_audit(
        db,
        user_id=user.user_id,
        action="legal_rule.evaluate",
        entity_type="requirement_evaluation",
        entity_id=evaluation.evaluation_id,
        after={
            "building_id": building_id,
            "domain": payload.domain,
            "evaluation_date": evaluation_date.isoformat(),
            "matched_rule_count": len(results),
            "facility_version": facility.version,
        },
    )
    db.commit()
    return _evaluation_out(evaluation)


@router.get("/evaluations/{building_id}", response_model=list[RequirementEvaluationOut])
def evaluation_history(
    building_id: str,
    limit: int = 50,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("legal_rule.read")),
):
    if not db.get(Facility, building_id):
        raise HTTPException(status_code=404, detail="facility not found")
    rows = db.scalars(
        select(RequirementEvaluation)
        .where(RequirementEvaluation.building_id == building_id)
        .order_by(RequirementEvaluation.created_at.desc())
        .limit(max(1, min(limit, 200)))
    ).all()
    return [_evaluation_out(x) for x in rows]
