"""Approved-source deterministic candidates; Human review never finalizes legal decisions."""
from copy import deepcopy
from datetime import datetime, timezone
import json

from fastapi import HTTPException
from sqlalchemy import or_, select, update

from . import hazardous_service as facts
from .audit import write_audit
from .hazardous_evaluation_models import HazardousEvaluation
from .hazardous_rule_engine import evaluate_conditions
from .hazardous_rule_models import HazardousRuleApproval
from .hazardous_rule_sources import authoring_access, authoring_citations, audit_data, citation_snapshot, primary_source_snapshot
from .models import (Facility, LegalJurisdiction, LegalProfile, LegalProfileJurisdiction,
    LegalRule, LegalRuleVersion, LegalSource, LegalSourceDocument, LegalSourceDocumentVersion)

MAX_EVIDENCE_BYTES = 8 * 1024 * 1024


def authority(db, user):
    facts.authority(db, user)
    facts.need(db, user, 'legal_rule.read', 'legal_source.read', 'document.read')


def profile_snapshot(db, identity, *, lock=False):
    profile = facts.get(db, LegalProfile, identity, lock)
    if not profile.active:
        raise HTTPException(409, 'active explicit legal profile required')
    statement = select(LegalProfileJurisdiction).where(
        LegalProfileJurisdiction.legal_profile_id == identity).order_by(LegalProfileJurisdiction.jurisdiction_id)
    if lock:
        statement = statement.with_for_update()
    jurisdictions = []
    for membership in db.scalars(statement):
        jurisdiction = facts.get(db, LegalJurisdiction, membership.jurisdiction_id, lock)
        jurisdictions.append({'jurisdiction': facts.serial(jurisdiction),
            'applicability': membership.applicability, 'priority': membership.priority})
    return {'profile': facts.serial(profile), 'jurisdictions': jurisdictions}


def inputs(db, user, identity, profile_id, *, expected=None, lock=False):
    authority(db, user)
    parent = facts.installation(db, user, identity, expected)
    facility = facts.get(db, Facility, parent.building_id, lock)
    context = profile_snapshot(db, profile_id, lock=lock)
    return {'installation': facts.serial(parent),
        'facility': {'building_id': facility.building_id, 'version': facility.version,
            'status': facility.status, 'deleted_at': str(facility.deleted_at) if facility.deleted_at else None},
        **context}


def current_rule(db, version, rule):
    # Use the existing canonical authoring representation that approval freezes.
    from .routers.legal_rules import _rule_out, _version_out
    snapshot = _version_out(version).model_dump(mode='json')
    snapshot['rule'] = _rule_out(rule).model_dump(mode='json')
    return snapshot


def rule_evidence(db, user, version, rule, *, lock=False):
    citations = authoring_citations(db, version)
    authoring_access(db, user, version, citations, lock=lock)
    frozen = facts.get(db, HazardousRuleApproval, version.legal_rule_version_id, lock)
    source = primary_source_snapshot(db, user, version.source_legal_document_version_id, lock=lock)
    canonical = [citation_snapshot(db, item, version.source_legal_document_version_id, lock=lock) for item in citations]
    # Stable ordering is independent of citation insertion order at approval.
    canonical.sort(key=lambda item: (item['legal_provision_id'], item['citation_role']))
    approved_citations = sorted(frozen.citations, key=lambda item: (item['legal_provision_id'], item['citation_role']))
    snapshot = current_rule(db, version, rule)
    if snapshot != frozen.rule_snapshot or source != frozen.source_snapshot or canonical != approved_citations:
        raise HTTPException(409, 'approved hazardous Rule/source/citation changed; new Human approval required')
    return {'rule_version_id': version.legal_rule_version_id, 'rule': deepcopy(snapshot),
        'source': deepcopy(source), 'citations': deepcopy(canonical),
        'approved_by': frozen.approved_by, 'approved_at': facts.serial(frozen)['approved_at']}


def selected_rules(db, user, context, evaluation_date, *, lock=False):
    profile_id = context['profile']['legal_profile_id']
    jurisdictions = [item['jurisdiction']['jurisdiction_id'] for item in context['jurisdictions']
        if item['applicability'] == 'applicable' and item['jurisdiction']['active']]
    if not jurisdictions:
        return []
    statement = (select(LegalRuleVersion, LegalRule).join(LegalRule)
        .join(LegalSourceDocumentVersion, LegalRuleVersion.source_legal_document_version_id == LegalSourceDocumentVersion.legal_source_document_version_id)
        .join(LegalSourceDocument, LegalSourceDocumentVersion.legal_source_document_id == LegalSourceDocument.legal_source_document_id)
        .join(LegalSource, LegalSourceDocument.legal_source_id == LegalSource.legal_source_id)
        .where(LegalRule.domain == 'hazardous_requirement', LegalRule.active.is_(True),
            LegalRuleVersion.status == 'approved', LegalRuleVersion.effective_from <= evaluation_date,
            or_(LegalRuleVersion.effective_to.is_(None), LegalRuleVersion.effective_to >= evaluation_date),
            LegalSource.jurisdiction_id.in_(jurisdictions),
            or_(LegalSource.legal_profile_id.is_(None), LegalSource.legal_profile_id == profile_id),
            or_(LegalSourceDocumentVersion.effective_from.is_(None), LegalSourceDocumentVersion.effective_from <= evaluation_date),
            or_(LegalSourceDocumentVersion.effective_to.is_(None), LegalSourceDocumentVersion.effective_to >= evaluation_date))
        .order_by(LegalRule.rule_code, LegalRuleVersion.version_no).limit(51))
    if lock:
        statement = statement.with_for_update()
    rows = db.execute(statement).all()
    if len(rows) > 50:
        raise HTTPException(409, 'hazardous evaluation exceeds bounded Rule count')
    return [rule_evidence(db, user, version, rule, lock=lock) for version, rule in rows]


def audit(db, user, action, row):
    write_audit(db, user_id=user.user_id, action='hazardous.evaluation.' + action,
        entity_type='hazardous_evaluation', entity_id=row.evaluation_id,
        after=audit_data('hazardous_requirement', facts.serial(row)))


def create(db, user, identity, payload):
    facts.need(db, user, 'hazardous.create', 'legal_rule.evaluate')
    context = inputs(db, user, identity, str(payload.legal_profile_id),
        expected=payload.expected_installation_version, lock=True)
    rules = selected_rules(db, user, context, payload.evaluation_date, lock=True)
    materials = context['installation']['materials']
    cells = len(materials) * len(rules)
    clauses = sum(sum(len(rule['rule']['conditions'].get(group, [])) for group in ('all', 'any')) for rule in rules) * len(materials)
    if cells > 2000 or clauses > 20000:
        raise HTTPException(409, 'hazardous evaluation exceeds bounded explicit material/condition count')
    evidence_bytes = len(json.dumps({'input': context, 'rules': rules, 'results': []}, ensure_ascii=False).encode())
    if evidence_bytes > MAX_EVIDENCE_BYTES:
        raise HTTPException(409, 'hazardous evaluation exceeds bounded evidence size')
    results = []
    for index, material in enumerate(materials):
        material_facts = {**material, 'material_name': material['name'],
            'material_category_label': material.get('category_label'),
            'installation_category_label': context['installation']['category_label']}
        for rule in rules:
            evaluated = evaluate_conditions(rule['rule']['conditions'], material_facts)
            result = {'material_index': index, 'material_name': material['name'],
                'rule_version_id': rule['rule_version_id'], **evaluated,
                'outcome': deepcopy(rule['rule']['outcome']), 'formal_decision': False}
            evidence_bytes += len(json.dumps(result, ensure_ascii=False).encode()) + 2
            if evidence_bytes > MAX_EVIDENCE_BYTES:
                raise HTTPException(409, 'hazardous evaluation exceeds bounded evidence size')
            results.append(result)
    row = HazardousEvaluation(installation_id=identity, legal_profile_id=str(payload.legal_profile_id),
        evaluation_date=payload.evaluation_date, input_snapshot=deepcopy(context), rules_snapshot=deepcopy(rules),
        results=results, coverage_status='evaluated' if rules and materials else 'unavailable', created_by=user.user_id)
    db.add(row); db.flush(); audit(db, user, 'create', row)
    return row


def output(db, user, row):
    authority(db, user)
    parent = facts.installation(db, user, row.installation_id)
    # Recheck both the current and frozen references before exposing any history.
    for evidence in row.rules_snapshot:
        original = evidence['source']['original']['document_id']
        facts.document_snapshot(db, user, original)
        version = facts.get(db, LegalRuleVersion, evidence['rule_version_id'])
        rule = facts.get(db, LegalRule, version.rule_id)
        rule_evidence(db, user, version, rule)
    context = inputs(db, user, row.installation_id, row.legal_profile_id)
    selected = selected_rules(db, user, context, row.evaluation_date)
    return {**facts.serial(row), 'formal_decision': False, 'coverage_complete': False,
        'coverage_note': 'selected_approved_rules_only; not a complete legal-compliance assessment',
        'is_stale': context != row.input_snapshot or selected != row.rules_snapshot or parent.status != 'active'}


def detail(db, user, identity):
    authority(db, user)
    return output(db, user, facts.get(db, HazardousEvaluation, identity))


def listing(db, user, identity, limit=100, offset=0):
    authority(db, user)
    facts.installation(db, user, identity)
    rows = db.scalars(select(HazardousEvaluation).where(HazardousEvaluation.installation_id == identity)
        .order_by(HazardousEvaluation.created_at.desc(), HazardousEvaluation.evaluation_id).offset(offset).limit(limit)).all()
    return [output(db, user, row) for row in rows]


def review(db, user, identity, payload):
    authority(db, user)
    facts.need(db, user, 'hazardous.review')
    row = facts.get(db, HazardousEvaluation, identity, lock=True)
    if row.status != 'candidate' or row.version != payload.expected_version:
        raise HTTPException(409, 'evaluation version/status changed')
    context = inputs(db, user, row.installation_id, row.legal_profile_id,
        expected=row.input_snapshot['installation']['version'], lock=True)
    selected = selected_rules(db, user, context, row.evaluation_date, lock=True)
    if context != row.input_snapshot or selected != row.rules_snapshot:
        raise HTTPException(409, 'evaluation input or approved Rule coverage changed; create a new candidate')
    now = datetime.now(timezone.utc)
    changed = db.execute(update(HazardousEvaluation).where(HazardousEvaluation.evaluation_id == identity,
        HazardousEvaluation.version == payload.expected_version, HazardousEvaluation.status == 'candidate')
        .values(status='reviewed', version=payload.expected_version + 1, reason=payload.reason,
            reviewed_by=user.user_id, reviewed_at=now).execution_options(synchronize_session=False))
    if changed.rowcount != 1:
        raise HTTPException(409, 'concurrent evaluation review')
    db.refresh(row); audit(db, user, 'review', row)
    return row
