"""Primary-source checks for hazardous candidates; never supplies approved policy."""
from fastapi import HTTPException
from sqlalchemy import select
from hashlib import sha256
import json

from .hazardous_service import document_access, get, legal_access, legal_snapshot
from .models import (LegalJurisdiction, LegalProvision, LegalRule, LegalRuleVersion, LegalRuleCitation,
    LegalRuleDraftCandidate, LegalRuleDraftCitation)
from .legal_structure import ProvisionRecord
from .authz import require_mutation_permission


def authoring_guard(db, user, row, permission):
    """Reuse account/session exclusion and reload the hazardous candidate for CAS."""
    fresh = require_mutation_permission(permission)(user=user, db=db)
    key = list(row.__table__.primary_key.columns)[0]
    locked = get(db, type(row), getattr(row, key.name), lock=True)
    authoring_access(db, fresh, locked, authoring_citations(db, locked), lock=True)
    return fresh, locked


def authoring_citations(db, row):
    if isinstance(row, LegalRuleVersion):
        model, key, identity = LegalRuleCitation, LegalRuleCitation.legal_rule_version_id, row.legal_rule_version_id
    elif isinstance(row, LegalRuleDraftCandidate):
        model, key, identity = LegalRuleDraftCitation, LegalRuleDraftCitation.legal_rule_draft_candidate_id, row.legal_rule_draft_candidate_id
    else:
        return []
    return db.scalars(select(model).where(key == identity).order_by(model.legal_provision_id)).all()


def authoring_access(db, user, row, citations=(), *, lock=False):
    """Traverse every cited original, including incomplete source-less drafts."""
    document_id = getattr(row, 'source_document_id', None)
    if document_id:
        document_access(db, user, document_id, lock)
    versions = set()
    selected = row.source_legal_document_version_id
    if selected:
        versions.add(selected)
    for citation in citations:
        provision = get(db, LegalProvision, citation.legal_provision_id, lock)
        versions.add(provision.legal_source_document_version_id)
    for identity in sorted(versions):
        legal_access(db, user, identity, lock)


def source_has_hazardous_authoring(db, identity):
    direct_rules = select(LegalRuleVersion.legal_rule_version_id).join(LegalRule).where(
        LegalRule.domain == 'hazardous_requirement', LegalRuleVersion.source_legal_document_version_id == identity)
    direct_drafts = select(LegalRuleDraftCandidate.legal_rule_draft_candidate_id).where(
        LegalRuleDraftCandidate.domain == 'hazardous_requirement', LegalRuleDraftCandidate.source_legal_document_version_id == identity)
    cited_rules = select(LegalRuleCitation.legal_provision_id).join(LegalRuleVersion).join(LegalRule).join(
        LegalProvision, LegalProvision.legal_provision_id == LegalRuleCitation.legal_provision_id).where(
        LegalRule.domain == 'hazardous_requirement', LegalProvision.legal_source_document_version_id == identity)
    cited_drafts = select(LegalRuleDraftCitation.legal_provision_id).join(LegalRuleDraftCandidate).join(
        LegalProvision, LegalProvision.legal_provision_id == LegalRuleDraftCitation.legal_provision_id).where(
        LegalRuleDraftCandidate.domain == 'hazardous_requirement', LegalProvision.legal_source_document_version_id == identity)
    return any(db.scalar(statement.limit(1)) is not None for statement in (direct_rules, direct_drafts, cited_rules, cited_drafts))


def audit_data(domain, data):
    if domain != 'hazardous_requirement':
        return data
    return {'schema_version': 'hazardous-rule-audit-v1',
        'change_sha256': sha256(json.dumps(data, sort_keys=True, ensure_ascii=False,
            separators=(',', ':')).encode()).hexdigest()}


def primary_source_snapshot(db, user, source_version_id, *, lock=False):
    version, document, source = legal_access(db, user, source_version_id, lock)
    jurisdiction = get(db, LegalJurisdiction, source.jurisdiction_id, lock)
    if source.trust_level != 'official' or not jurisdiction.active:
        raise HTTPException(409, 'active jurisdiction and official primary source required')
    snapshot = legal_snapshot(db, user, source_version_id, lock)
    snapshot['jurisdiction_id'] = jurisdiction.jurisdiction_id
    snapshot['legal_profile_id'] = source.legal_profile_id
    return snapshot


def citation_snapshot(db, citation, source_version_id, *, lock=False):
    provision = get(db, LegalProvision, citation.legal_provision_id, lock)
    cited_text = '\n'.join(x for x in (provision.display_label, provision.heading_text, provision.body_text) if x)
    record = ProvisionRecord(provision_key=provision.provision_key, parent_key=None,
        provision_type=provision.provision_type, sequence_no=provision.sequence_no,
        display_label=provision.display_label, heading_text=provision.heading_text,
        body_text=provision.body_text)
    if (not provision.present_in_source or
            provision.legal_source_document_version_id != source_version_id or
            getattr(citation, 'cited_text_snapshot', cited_text) != cited_text or
            provision.content_sha256 != record.content_sha256):
        raise HTTPException(409, 'hazardous citation text or source integrity changed')
    return {'legal_provision_id': provision.legal_provision_id,
        'provision_key': provision.provision_key, 'display_label': provision.display_label,
        'content_sha256': provision.content_sha256, 'cited_text': cited_text,
        'citation_role': citation.citation_role}
