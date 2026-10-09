"""Approved synthetic Rule candidates never create formal legal decisions."""
from datetime import date
from pathlib import Path

import pytest
from sqlalchemy.orm import Session

from test_hazardous_rule_authoring import author, structured_rule
from app.models import (Facility, LegalProfile, LegalProfileJurisdiction, LegalJurisdiction,
    LegalRuleVersion, LegalSourceDocumentVersion, LegalSource, LegalRuleCitation)


@pytest.fixture
def evaluation_env(author):
    client, engine = author
    version_id = structured_rule(engine)
    approved = client.post('/legal-rules/versions/' + version_id + '/approve', json={'expected_version': 1})
    assert approved.status_code == 200, approved.text
    with Session(engine) as db:
        facility = Facility(name='Synthetic hazardous evaluation facility', status='active')
        profile = LegalProfile(code='SYN-EVAL', name='Synthetic jurisdiction profile', active=True)
        db.add_all([facility, profile]); db.flush()
        db.add(LegalProfileJurisdiction(legal_profile_id=profile.legal_profile_id,
            jurisdiction_id=db.query(LegalJurisdiction).one().jurisdiction_id))
        db.commit(); building_id = facility.building_id; profile_id = profile.legal_profile_id
    installation = client.post('/hazardous/installations', json={'building_id': building_id,
        'name': 'Synthetic evaluation installation', 'category_label': 'Recorded explicit category',
        'materials': [{'name': 'Synthetic material', 'quantity': '100.000000', 'quantity_unit': 'L'},
            {'name': 'Separate unknown-unit material', 'quantity': '100', 'quantity_unit': 'kg'}]})
    assert installation.status_code == 201, installation.text
    return client, engine, installation.json(), profile_id, version_id


def create_evaluation(env):
    client, _, installation, profile_id, _ = env
    response = client.post('/hazardous/installations/' + installation['installation_id'] + '/evaluations',
        json={'expected_installation_version': installation['version'],
            'legal_profile_id': profile_id, 'evaluation_date': '2026-10-09'})
    assert response.status_code == 201, response.text
    return response.json()


def test_each_material_has_traceable_candidate_without_formal_decision(evaluation_env):
    client, engine, installation, profile_id, version_id = evaluation_env
    candidate = create_evaluation(evaluation_env)
    assert candidate['status'] == 'candidate'
    assert candidate['formal_decision'] is False
    assert candidate['coverage_complete'] is False
    assert candidate['coverage_status'] == 'evaluated'
    assert [row['state'] for row in candidate['results']] == ['matched', 'unresolved']
    assert candidate['results'][0]['material_index'] == 0
    assert candidate['results'][0]['rule_version_id'] == version_id
    assert candidate['rules_snapshot'][0]['citations'][0]['citation_role'] == 'primary'
    assert candidate['input_snapshot']['installation']['materials'][0]['quantity'] == '100.000000'
    from app.violation_models import ViolationCase
    from app.hazardous_models import HazardousRecord
    with Session(engine) as db:
        assert db.query(ViolationCase).count() == 0
        assert db.query(HazardousRecord).count() == 0
    listed = client.get('/hazardous/installations/' + installation['installation_id'] + '/evaluations')
    assert listed.status_code == 200 and len(listed.json()) == 1, listed.text
    assert listed.headers['cache-control'] == 'no-store'


def test_human_review_is_independent_cas_and_requires_literal_acknowledgement(evaluation_env):
    client, _, _, _, _ = evaluation_env
    candidate = create_evaluation(evaluation_env)
    endpoint = '/hazardous/evaluations/' + candidate['evaluation_id'] + '/review'
    for ack in (False, 1, 'true'):
        rejected = client.post(endpoint, json={'expected_version': 1, 'acknowledged': ack,
            'reason': 'Synthetic independent review'})
        assert rejected.status_code == 422, rejected.text
    response = client.post(endpoint, json={'expected_version': 1, 'acknowledged': True,
        'reason': 'Synthetic independent review'})
    assert response.status_code == 200, response.text
    assert response.json()['status'] == 'reviewed' and response.json()['formal_decision'] is False
    duplicate = client.post(endpoint, json={'expected_version': 1, 'acknowledged': True,
        'reason': 'Synthetic stale duplicate'})
    assert duplicate.status_code == 409, duplicate.text


@pytest.mark.parametrize('change', ['draft', 'future', 'expired', 'outside_profile'])
def test_inapplicable_rules_never_imply_compliance(evaluation_env, change):
    client, engine, _, profile_id, identity = evaluation_env
    with Session(engine) as db:
        row = db.get(LegalRuleVersion, identity)
        if change == 'draft':
            row.status = 'draft'
        elif change == 'future':
            row.effective_from = date(2027, 1, 1)
        elif change == 'expired':
            row.effective_to = date(2026, 10, 8)
        else:
            profile = LegalProfile(code='SYN-OTHER', name='Synthetic other profile')
            db.add(profile); db.flush()
            db.query(LegalSource).one().legal_profile_id = profile.legal_profile_id
        db.commit()
    candidate = create_evaluation(evaluation_env)
    assert candidate['coverage_status'] == 'unavailable'
    assert candidate['results'] == []
    assert candidate['formal_decision'] is False and candidate['coverage_complete'] is False


@pytest.mark.parametrize('change', ['source_context', 'conditions', 'citation', 'installation'])
def test_stale_evidence_cannot_pass_independent_human_review(evaluation_env, change):
    client, engine, installation, profile_id, identity = evaluation_env
    candidate = create_evaluation(evaluation_env)
    with Session(engine) as db:
        if change == 'source_context':
            db.query(LegalSourceDocumentVersion).one().source_url = 'https://example.invalid/changed'
        elif change == 'conditions':
            db.get(LegalRuleVersion, identity).conditions = {'all': [{'field': 'quantity', 'op': 'gte', 'value': '99', 'unit': 'L'}]}
        elif change == 'citation':
            db.query(LegalRuleCitation).one().cited_text_snapshot = 'Changed exact quote'
        else:
            from app.hazardous_models import HazardousInstallation
            db.get(HazardousInstallation, installation['installation_id']).version += 1
        db.commit()
    response = client.post('/hazardous/evaluations/' + candidate['evaluation_id'] + '/review',
        json={'expected_version': 1, 'acknowledged': True, 'reason': 'Synthetic stale review'})
    assert response.status_code == 409, response.text
    from app.hazardous_evaluation_models import HazardousEvaluation
    with Session(engine) as db:
        assert db.get(HazardousEvaluation, candidate['evaluation_id']).status == 'candidate'


def test_current_source_rights_protect_candidate_and_counts(evaluation_env):
    client, engine, installation, _, _ = evaluation_env
    candidate = create_evaluation(evaluation_env)
    from test_hazardous_rule_authoring import revoke_original_access
    revoke_original_access(engine)
    for path in ('/hazardous/evaluations/' + candidate['evaluation_id'],
        '/hazardous/installations/' + installation['installation_id'] + '/evaluations'):
        response = client.get(path)
        assert response.status_code == 403, response.text


def test_empty_evaluation_list_still_requires_current_source_rights(evaluation_env):
    client, engine, installation, _, _ = evaluation_env
    from test_hazardous_rule_authoring import revoke_original_access
    revoke_original_access(engine)
    response = client.get('/hazardous/installations/' + installation['installation_id'] + '/evaluations')
    assert response.status_code == 403, response.text


def test_missing_source_rights_cannot_probe_candidate_identity(evaluation_env):
    from uuid import uuid4
    from test_hazardous_rule_authoring import revoke_original_access
    client, engine, _, _, _ = evaluation_env
    candidate = create_evaluation(evaluation_env)
    revoke_original_access(engine)
    for identity in (candidate['evaluation_id'], str(uuid4())):
        path = '/hazardous/evaluations/' + identity
        assert client.get(path).status_code == 403
        assert client.post(path + '/review', json={'expected_version': 1, 'acknowledged': True,
            'reason': 'Synthetic unauthorized probe'}).status_code == 403


def test_newly_approved_rule_coverage_requires_new_candidate(evaluation_env):
    from copy import deepcopy
    from app.models import LegalRule
    client, engine, _, _, version_id = evaluation_env
    candidate = create_evaluation(evaluation_env)
    with Session(engine) as db:
        prior = db.get(LegalRuleVersion, version_id)
        rule = LegalRule(rule_code='SYN-NEW-COVERAGE', name='Synthetic newly applicable Rule', domain='hazardous_requirement')
        db.add(rule); db.flush()
        version = LegalRuleVersion(rule_id=rule.rule_id, version_no=1, effective_from=date(2026, 1, 1),
            conditions=deepcopy(prior.conditions), outcome=deepcopy(prior.outcome),
            source_legal_document_version_id=prior.source_legal_document_version_id)
        db.add(version); db.flush()
        citation = db.query(LegalRuleCitation).filter_by(legal_rule_version_id=version_id).one()
        db.add(LegalRuleCitation(legal_rule_version_id=version.legal_rule_version_id,
            legal_provision_id=citation.legal_provision_id, citation_role='primary', cited_text_snapshot=citation.cited_text_snapshot))
        db.commit(); new_id = version.legal_rule_version_id
    approved = client.post('/legal-rules/versions/' + new_id + '/approve', json={'expected_version': 1})
    assert approved.status_code == 200, approved.text
    path = '/hazardous/evaluations/' + candidate['evaluation_id']
    current = client.get(path)
    assert current.status_code == 200 and current.json()['is_stale'] is True, current.text
    rejected = client.post(path + '/review', json={'expected_version': 1, 'acknowledged': True,
        'reason': 'Synthetic outdated coverage'})
    assert rejected.status_code == 409, rejected.text


@pytest.mark.parametrize('change', ['original', 'trust', 'citation_hash', 'rule_outcome'])
def test_changed_approval_evidence_cannot_create_candidate_or_audit(evaluation_env, change):
    from app.hazardous_evaluation_models import HazardousEvaluation
    from app.models import AuditLog, LegalProvision
    from app.settings import settings
    client, engine, installation, profile_id, identity = evaluation_env
    if change == 'original':
        (Path(settings.storage_root) / 'synthetic-law.txt').write_bytes(b'Synthetic changed original')
    else:
        with Session(engine) as db:
            if change == 'trust':
                db.query(LegalSource).one().trust_level = 'unverified'
            elif change == 'citation_hash':
                db.query(LegalProvision).one().content_sha256 = '0' * 64
            else:
                db.get(LegalRuleVersion, identity).outcome = {'decision': 'hazardous_requirement_candidate',
                    'requirement': 'Synthetic substituted approved outcome', 'human_review_required': True}
            db.commit()
    response = client.post('/hazardous/installations/' + installation['installation_id'] + '/evaluations',
        json={'expected_installation_version': installation['version'], 'legal_profile_id': profile_id,
            'evaluation_date': '2026-10-09'})
    assert response.status_code == 409, response.text
    with Session(engine) as db:
        assert db.query(HazardousEvaluation).count() == 0
        assert db.query(AuditLog).filter_by(action='hazardous.evaluation.create').count() == 0


def test_module_registration_describes_candidate_only_and_preserves_disabled_choice(evaluation_env):
    from app.module_seed import seed_modules
    from app.models import FeatureFlag
    client, engine, installation, profile_id, _ = evaluation_env
    with Session(engine) as db:
        seed_modules(db)
        flag = db.query(FeatureFlag).filter_by(key='module.hazardous_materials.enabled').one()
        flag.enabled = False
        db.commit()
        registered = seed_modules(db)['hazardous_materials']
        assert registered.manifest['legal_evaluation'] is True
        assert registered.manifest['legal_evaluation_mode'] == 'candidate_only'
        assert registered.manifest['formal_legal_decision'] is False
        db.commit()
        assert db.query(FeatureFlag).filter_by(key='module.hazardous_materials.enabled').one().enabled is False
    path = '/hazardous/installations/' + installation['installation_id'] + '/evaluations'
    assert client.get(path).status_code == 503
    assert client.post(path, json={'expected_installation_version': 1,
        'legal_profile_id': profile_id, 'evaluation_date': '2026-10-09'}).status_code == 503


def test_oversized_source_evidence_stops_before_comparison_and_persistence(evaluation_env, monkeypatch):
    from app import hazardous_evaluation_service as service
    from app.hazardous_evaluation_models import HazardousEvaluation
    client, engine, installation, profile_id, _ = evaluation_env
    monkeypatch.setattr(service, 'MAX_EVIDENCE_BYTES', 1024, raising=False)
    called = []
    original = service.evaluate_conditions
    def compare(*args):
        called.append(True)
        return original(*args)
    monkeypatch.setattr(service, 'evaluate_conditions', compare)
    response = client.post('/hazardous/installations/' + installation['installation_id'] + '/evaluations',
        json={'expected_installation_version': 1, 'legal_profile_id': profile_id, 'evaluation_date': '2026-10-09'})
    assert response.status_code == 409, response.text
    assert called == []
    with Session(engine) as db:
        assert db.query(HazardousEvaluation).count() == 0


def test_result_growth_stops_before_remaining_materials_without_partial_save(evaluation_env, monkeypatch):
    import json
    from copy import deepcopy
    from app import hazardous_evaluation_service as service
    from app.hazardous_models import HazardousInstallation
    from app.hazardous_evaluation_models import HazardousEvaluation
    from app.models import AuditLog
    client, engine, installation, profile_id, _ = evaluation_env
    with Session(engine) as db:
        row = db.get(HazardousInstallation, installation['installation_id'])
        row.materials = deepcopy(row.materials) + deepcopy(row.materials)
        db.commit()
    first = create_evaluation(evaluation_env)
    assert len(first['results']) == 4
    # The wire evidence budget allows one result, then must stop further work.
    base = {'input': first['input_snapshot'], 'rules': first['rules_snapshot'], 'results': []}
    limit = len(json.dumps(base, ensure_ascii=False).encode()) + len(json.dumps(first['results'][0], ensure_ascii=False).encode()) + 2
    monkeypatch.setattr(service, 'MAX_EVIDENCE_BYTES', limit)
    called = []
    original = service.evaluate_conditions
    def compare(*args):
        called.append(True)
        return original(*args)
    monkeypatch.setattr(service, 'evaluate_conditions', compare)
    response = client.post('/hazardous/installations/' + installation['installation_id'] + '/evaluations',
        json={'expected_installation_version': 1, 'legal_profile_id': profile_id, 'evaluation_date': '2026-10-09'})
    assert response.status_code == 409, response.text
    assert len(called) == 2
    with Session(engine) as db:
        assert db.query(HazardousEvaluation).count() == 1
        assert db.query(AuditLog).filter_by(action='hazardous.evaluation.create').count() == 1
