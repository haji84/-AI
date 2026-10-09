"""Actual HTTP authoring uses synthetic rules, never approved real policy."""
import pytest
from datetime import date
from hashlib import sha256
from pathlib import Path
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.db import Base, get_db
from app.main import app
from app.models import (User, UserRole, LegalRule, LegalRuleVersion, Document,
    LegalJurisdiction, LegalSource, LegalSourceDocument, LegalSourceDocumentVersion,
    LegalProvision, LegalRuleCitation, LegalRuleDraftCandidate, LegalRuleDraftCitation,
    Permission, RolePermission)
from app.settings import settings
from app.legal_structure import ProvisionRecord
from app.rbac_seed import seed_rbac
from app.security import hash_password


CONDITIONS = {'all': [{'field': 'quantity', 'op': 'gte', 'value': '100', 'unit': 'L'}]}
OUTCOME = {'decision': 'hazardous_requirement_candidate', 'requirement': 'Synthetic requirement',
    'human_review_required': True}


@pytest.fixture
def author(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, 'storage_root', str(tmp_path))
    engine = create_engine('sqlite+pysqlite:///:memory:', connect_args={'check_same_thread': False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        roles = seed_rbac(db)
        user = User(username='synthetic-rule-author', password_hash=hash_password('synthetic-rule-password'))
        db.add(user); db.flush()
        db.add(UserRole(user_id=user.user_id, role_id=roles['system_admin'].role_id)); db.commit()
    def dependency():
        with Session(engine) as db:
            yield db
    previous = dict(app.dependency_overrides)
    app.dependency_overrides[get_db] = dependency
    with TestClient(app) as client:
        assert client.post('/auth/login', json={'username': 'synthetic-rule-author',
            'password': 'synthetic-rule-password'}).status_code == 200
        yield client, engine
    app.dependency_overrides.clear(); app.dependency_overrides.update(previous)
    engine.dispose()


def structured_rule(engine, *, trust='official', with_citation=True):
    body = b'Synthetic primary provision requiring Human approval.'
    (Path(settings.storage_root) / 'synthetic-law.txt').write_bytes(body)
    with Session(engine) as db:
        jurisdiction = LegalJurisdiction(code='SYN-J', name='Synthetic jurisdiction', jurisdiction_type='national')
        db.add(jurisdiction); db.flush()
        source = LegalSource(jurisdiction_id=jurisdiction.jurisdiction_id, source_code='SYN-S',
            name='Synthetic primary source', source_type='law', adapter_type='manual',
            base_url='https://example.invalid/', trust_level=trust)
        db.add(source); db.flush()
        raw = Document(storage_path='synthetic-law.txt', original_filename='synthetic-law.txt',
            sha256=sha256(body).hexdigest(), size_bytes=len(body), document_type='legal_source')
        db.add(raw); db.flush()
        document = LegalSourceDocument(legal_source_id=source.legal_source_id, external_id='SYN-LAW',
            document_type='law', title='Synthetic law')
        db.add(document); db.flush()
        version = LegalSourceDocumentVersion(legal_source_document_id=document.legal_source_document_id,
            raw_document_id=raw.document_id, sha256=raw.sha256,
            source_url='https://example.invalid/synthetic-law', normalized_text=body.decode())
        db.add(version); db.flush()
        provision = LegalProvision(legal_source_document_version_id=version.legal_source_document_version_id,
            provision_type='article', provision_key='article:1', sequence_no=1,
            display_label='Synthetic Article 1', body_text=body.decode(),
            content_sha256=ProvisionRecord(provision_key='article:1', parent_key=None,
                provision_type='article', sequence_no=1, display_label='Synthetic Article 1',
                body_text=body.decode()).content_sha256)
        db.add(provision); db.flush()
        rule = LegalRule(rule_code='SYN-STRUCTURED', name='Synthetic structured rule', domain='hazardous_requirement')
        db.add(rule); db.flush()
        candidate = LegalRuleVersion(rule_id=rule.rule_id, version_no=1, effective_from=date(2026, 1, 1),
            conditions=CONDITIONS, outcome=OUTCOME, source_legal_document_version_id=version.legal_source_document_version_id)
        db.add(candidate); db.flush()
        if with_citation:
            db.add(LegalRuleCitation(legal_rule_version_id=candidate.legal_rule_version_id,
                legal_provision_id=provision.legal_provision_id, citation_role='primary',
                cited_text_snapshot='Synthetic Article 1\n' + body.decode()))
        db.commit()
        return candidate.legal_rule_version_id


def test_structured_official_original_can_pass_explicit_human_approval(author):
    client, engine = author
    key = structured_rule(engine, with_citation=False)
    with Session(engine) as db:
        provision_id = db.query(LegalProvision).one().legal_provision_id
    citation = client.post('/legal-rules/versions/' + key + '/citations',
        json={'legal_provision_id': provision_id, 'citation_role': 'primary'})
    assert citation.status_code == 201, citation.text
    assert citation.headers['cache-control'] == 'no-store'
    stale = client.post('/legal-rules/versions/' + key + '/approve', json={'expected_version': 1})
    assert stale.status_code == 409, stale.text
    response = client.post('/legal-rules/versions/' + key + '/approve', json={'expected_version': 2})
    assert response.status_code == 200, response.text
    assert response.json()['status'] == 'approved'


@pytest.mark.parametrize('change', ['unofficial', 'tampered', 'disabled', 'citation_changed', 'inactive_jurisdiction'])
def test_hazardous_rule_approval_requires_current_primary_original(author, change):
    client, engine = author
    key = structured_rule(engine, trust='unverified' if change == 'unofficial' else 'official')
    if change == 'tampered':
        (Path(settings.storage_root) / 'synthetic-law.txt').write_bytes(b'Changed original')
    if change == 'disabled':
        with Session(engine) as db:
            db.query(LegalSource).one().enabled = False
            db.commit()
    if change in ('citation_changed', 'inactive_jurisdiction'):
        with Session(engine) as db:
            if change == 'citation_changed':
                db.query(LegalRuleCitation).one().cited_text_snapshot = 'Unverified substituted text'
            else:
                db.query(LegalJurisdiction).one().active = False
            db.commit()
    response = client.post('/legal-rules/versions/' + key + '/approve', json={'expected_version': 1})
    assert response.status_code == 409, response.text
    with Session(engine) as db:
        assert db.get(LegalRuleVersion, key).status == 'draft'


def test_hazardous_version_uses_domain_conditions_and_stays_draft(author):
    client, _ = author
    created = client.post('/legal-rules', json={'rule_code': 'SYN-HZ', 'name': 'Synthetic Rule',
        'domain': 'hazardous_requirement'})
    assert created.status_code == 201, created.text
    version = client.post('/legal-rules/' + created.json()['rule_id'] + '/versions', json={
        'version_no': 1, 'effective_from': '2026-01-01', 'conditions': CONDITIONS, 'outcome': OUTCOME})
    assert version.status_code == 201, version.text
    assert version.json()['status'] == 'draft'
    invalid = client.post('/legal-rules/' + created.json()['rule_id'] + '/versions', json={
        'version_no': 2, 'effective_from': '2026-01-01',
        'conditions': {'all': [{'field': 'quantity', 'op': 'gte', 'value': '100'}]}, 'outcome': OUTCOME})
    assert invalid.status_code == 422, invalid.text


def test_free_text_source_reference_cannot_approve_hazardous_rule(author):
    client, engine = author
    with Session(engine) as db:
        rule = LegalRule(rule_code='SYN-LEGACY', name='Synthetic no-source rule', domain='hazardous_requirement')
        db.add(rule); db.flush()
        version = LegalRuleVersion(rule_id=rule.rule_id, version_no=1, effective_from=date(2026, 1, 1),
            conditions=CONDITIONS, outcome=OUTCOME, source_reference='Synthetic unverified reference')
        db.add(version); db.commit(); key = version.legal_rule_version_id
    response = client.post('/legal-rules/versions/' + key + '/approve', json={'expected_version': 1})
    assert response.status_code == 409, response.text
    with Session(engine) as db:
        assert db.get(LegalRuleVersion, key).status == 'draft'


def test_hazardous_draft_without_structured_source_cannot_pass_human_review(author):
    client, _ = author
    created = client.post('/legal-rule-drafts', json={'domain': 'hazardous_requirement',
        'proposed_rule_code': 'SYN-NO-SOURCE', 'proposed_name': 'Synthetic incomplete rule',
        'proposed_conditions': CONDITIONS, 'proposed_outcome': OUTCOME, 'extraction_method': 'manual'})
    assert created.status_code == 201, created.text
    row = created.json()
    blocked = client.post('/legal-rule-drafts/' + row['legal_rule_draft_candidate_id'] + '/review',
        json={'expected_version': row['version'], 'status': 'reviewed'})
    assert blocked.status_code == 409, blocked.text
    assert 'structured primary-source citations' in blocked.json()['detail']


@pytest.mark.parametrize('trust, expected', [('official', 200), ('unverified', 409)])
def test_draft_human_review_checks_official_original(author, trust, expected):
    client, engine = author
    key = structured_rule(engine, trust=trust)
    with Session(engine) as db:
        source_version_id = db.get(LegalRuleVersion, key).source_legal_document_version_id
        provision = db.query(LegalProvision).one()
        draft = LegalRuleDraftCandidate(domain='hazardous_requirement', proposed_rule_code='SYN-DRAFT',
            proposed_name='Synthetic draft', proposed_conditions=CONDITIONS, proposed_outcome=OUTCOME,
            extraction_method='manual', source_legal_document_version_id=source_version_id)
        db.add(draft); db.flush()
        db.add(LegalRuleDraftCitation(legal_rule_draft_candidate_id=draft.legal_rule_draft_candidate_id,
            legal_provision_id=provision.legal_provision_id, citation_role='primary'))
        db.commit(); identity = draft.legal_rule_draft_candidate_id
    response = client.post('/legal-rule-drafts/' + identity + '/review',
        json={'expected_version': 1, 'status': 'reviewed'})
    assert response.status_code == expected, response.text


@pytest.mark.parametrize('permission', ['legal_source.read', 'document.read'])
def test_rule_approver_without_original_source_access_is_denied(author, permission):
    client, engine = author
    key = structured_rule(engine)
    with Session(engine) as db:
        identity = db.query(Permission).filter(Permission.code == permission).one().permission_id
        db.query(RolePermission).filter(RolePermission.permission_id == identity).delete()
        db.commit()
    response = client.post('/legal-rules/versions/' + key + '/approve', json={'expected_version': 1})
    assert response.status_code == 403, response.text
    with Session(engine) as db:
        assert db.get(LegalRuleVersion, key).status == 'draft'


def test_hazardous_rule_is_visible_in_shared_authoring_coverage(author):
    client, engine = author
    structured_rule(engine)
    response = client.get('/legal-rules/coverage')
    assert response.status_code == 200, response.text
    body = response.json()
    assert body['rule_versions_by_domain_status']['hazardous_requirement']['draft'] == 1
    assert body['approved_rule_count_by_domain']['hazardous_requirement'] == 0


def revoke_original_access(engine):
    with Session(engine) as db:
        identities = [p.permission_id for p in db.query(Permission).filter(
            Permission.code.in_(['document.read', 'legal_source.read']))]
        db.query(RolePermission).filter(RolePermission.permission_id.in_(identities)).delete()
        db.commit()


def test_citation_add_and_list_recheck_original_access(author):
    client, engine = author
    key = structured_rule(engine)
    with Session(engine) as db:
        provision_id = db.query(LegalProvision).one().legal_provision_id
    revoke_original_access(engine)
    listed = client.get('/legal-rules/versions/' + key + '/citations')
    assert listed.status_code == 403, listed.text
    added = client.post('/legal-rules/versions/' + key + '/citations',
        json={'legal_provision_id': provision_id, 'citation_role': 'reference'})
    assert added.status_code == 403, added.text
    with Session(engine) as db:
        source_id = db.query(LegalProvision).one().legal_source_document_version_id
    source = client.get('/legal-rules/source-versions/' + source_id + '/provisions')
    assert source.status_code == 403, source.text


def test_source_less_hazardous_draft_citations_cannot_bypass_original_access(author):
    client, engine = author
    structured_rule(engine)
    with Session(engine) as db:
        provision_id = db.query(LegalProvision).one().legal_provision_id
    revoke_original_access(engine)
    created = client.post('/legal-rule-drafts', json={'domain': 'hazardous_requirement',
        'proposed_rule_code': 'SYN-CITATION-BYPASS', 'proposed_name': 'Synthetic private citation',
        'proposed_conditions': CONDITIONS, 'proposed_outcome': OUTCOME, 'extraction_method': 'manual',
        'citations': [{'legal_provision_id': provision_id, 'citation_role': 'primary'}]})
    assert created.status_code == 403, created.text
    with Session(engine) as db:
        assert db.query(LegalRuleDraftCandidate).count() == 0


def test_draft_list_patch_and_reject_fail_before_mutation_after_source_revocation(author):
    client, engine = author
    structured_rule(engine)
    with Session(engine) as db:
        provision_id = db.query(LegalProvision).one().legal_provision_id
    created = client.post('/legal-rule-drafts', json={'domain': 'hazardous_requirement',
        'proposed_rule_code': 'SYN-REVOKED', 'proposed_name': 'Synthetic protected draft',
        'proposed_conditions': CONDITIONS, 'proposed_outcome': OUTCOME, 'extraction_method': 'manual',
        'citations': [{'legal_provision_id': provision_id, 'citation_role': 'primary'}]})
    assert created.status_code == 201, created.text
    assert created.headers['cache-control'] == 'no-store'
    identity = created.json()['legal_rule_draft_candidate_id']
    listed = client.get('/legal-rule-drafts')
    assert listed.status_code == 200 and listed.headers['cache-control'] == 'no-store'
    revoke_original_access(engine)
    for response in [client.get('/legal-rule-drafts'), client.get('/legal-rules/coverage'), client.get('/legal-rules'),
        client.patch('/legal-rule-drafts/' + identity,
            json={'expected_version': 1, 'proposed_name': 'Unpermitted change'}),
        client.post('/legal-rule-drafts/' + identity + '/review',
            json={'expected_version': 1, 'status': 'rejected'})]:
        assert response.status_code == 403, response.text
    with Session(engine) as db:
        saved = db.get(LegalRuleDraftCandidate, identity)
        assert saved.status == 'pending' and saved.version == 1
        assert saved.proposed_name == 'Synthetic protected draft'


def test_human_approval_freezes_exact_rule_and_primary_citation_evidence(author):
    client, engine = author
    identity = structured_rule(engine)
    response = client.post('/legal-rules/versions/' + identity + '/approve', json={'expected_version': 1})
    assert response.status_code == 200, response.text
    from app.hazardous_rule_models import HazardousRuleApproval
    with Session(engine) as db:
        approval = db.get(HazardousRuleApproval, identity)
        assert approval is not None
        assert approval.rule_snapshot['conditions'] == CONDITIONS
        assert approval.rule_snapshot['outcome'] == OUTCOME
        assert approval.rule_snapshot['version'] == 2
        assert approval.source_snapshot['sha256'] == db.query(Document).one().sha256
        assert approval.citations[0]['cited_text'].endswith('Synthetic primary provision requiring Human approval.')
        frozen = approval.source_snapshot['source_url']
        db.query(LegalSourceDocumentVersion).one().source_url = 'https://example.invalid/changed-context'
        db.commit()
        assert db.get(HazardousRuleApproval, identity).source_snapshot['source_url'] == frozen


def test_reference_only_citation_does_not_replace_primary_basis(author):
    client, engine = author
    identity = structured_rule(engine)
    with Session(engine) as db:
        db.query(LegalRuleCitation).one().citation_role = 'reference'
        db.commit()
    response = client.post('/legal-rules/versions/' + identity + '/approve', json={'expected_version': 1})
    assert response.status_code == 409, response.text


def test_audit_only_reader_cannot_retrieve_hazardous_rule_prose(author):
    client, engine = author
    identity = structured_rule(engine)
    approved = client.post('/legal-rules/versions/' + identity + '/approve', json={'expected_version': 1})
    assert approved.status_code == 200, approved.text
    with Session(engine) as db:
        allowed = db.query(Permission).filter(Permission.code == 'audit.read').one().permission_id
        db.query(RolePermission).filter(RolePermission.permission_id != allowed).delete()
        db.commit()
    audits = client.get('/administration/audit', params={'action': 'legal_rule_version.approve'})
    assert audits.status_code == 200, audits.text
    assert 'Synthetic requirement' not in audits.text
    assert 'human_review_required' not in audits.text


def test_source_less_draft_link_alone_protects_shared_provision_endpoint(author):
    client, engine = author
    identity = structured_rule(engine)
    with Session(engine) as db:
        provision = db.query(LegalProvision).one()
        source_id = provision.legal_source_document_version_id
        db.query(LegalRuleCitation).delete()
        rule_id = db.get(LegalRuleVersion, identity).rule_id
        db.delete(db.get(LegalRuleVersion, identity)); db.flush()
        db.delete(db.get(LegalRule, rule_id)); db.flush()
        draft = LegalRuleDraftCandidate(domain='hazardous_requirement', proposed_name='Synthetic source-less draft',
            proposed_conditions=CONDITIONS, proposed_outcome=OUTCOME, extraction_method='manual')
        db.add(draft); db.flush()
        db.add(LegalRuleDraftCitation(legal_rule_draft_candidate_id=draft.legal_rule_draft_candidate_id,
            legal_provision_id=provision.legal_provision_id, citation_role='primary'))
        db.commit()
    endpoint = '/legal-rules/source-versions/' + source_id + '/provisions'
    assert client.get(endpoint).status_code == 200
    revoke_original_access(engine)
    denied = client.get(endpoint)
    assert denied.status_code == 403, denied.text
