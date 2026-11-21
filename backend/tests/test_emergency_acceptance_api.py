"""Synthetic-only API tests: no source document or patient values are persisted."""
import json
import os
from uuid import uuid4

os.environ['FIRE_AI_DATABASE_URL'] = 'sqlite+pysqlite:///:memory:'

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.db import Base, SessionLocal, engine
from app.main import app
from app.models import AuditLog, Document, Employee, Permission, Role, RolePermission, User, UserRole
from app.security import hash_password


PREFIX = '/emergency/acceptance'
CODES = ['emergency.case.read', 'emergency.patient.read', 'emergency.report.read',
         'emergency.report.create', 'emergency.report.review', 'document.read']


@pytest.fixture
def client(monkeypatch):
    from app.settings import settings
    if hasattr(settings, 'emergency_acceptance_internal_enabled'):
        monkeypatch.setattr(settings, 'emergency_acceptance_internal_enabled', False)
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    with SessionLocal() as db:
        role = Role(code='synthetic-acceptance', name='Synthetic acceptance')
        db.add(role); db.flush()
        for code in CODES:
            permission = Permission(code=code)
            db.add(permission); db.flush()
            db.add(RolePermission(role_id=role.role_id, permission_id=permission.permission_id))
        for name in ['author', 'reviewer']:
            employee = Employee(display_name='Synthetic ' + name)
            db.add(employee); db.flush()
            user = User(username='acceptance-' + name, employee_id=employee.employee_id,
                        password_hash=hash_password('synthetic-acceptance-password'))
            db.add(user); db.flush()
            db.add(UserRole(user_id=user.user_id, role_id=role.role_id))
        db.commit()
    with TestClient(app) as active:
        login(active)
        yield active


def login(client, who='author'):
    response = client.post('/auth/login', json={'username': 'acceptance-' + who,
                                               'password': 'synthetic-acceptance-password'})
    assert response.status_code == 200, response.text


def measurement():
    return {'dataset_kind': 'synthetic', 'reports': []}


def save(client, **extra):
    return client.post(PREFIX + '/evaluations', json={
        'request_id': str(uuid4()), 'measurement': measurement(), **extra})


def test_empty_preview_is_unmeasured_and_not_production_complete(client):
    response = client.post(PREFIX + '/preview', json=measurement())
    assert response.status_code == 200, response.text
    result = response.json()
    assert result['production_complete'] is False
    assert result['status'] == 'DEVELOPMENT_ONLY'
    assert result['metrics']['recall']['rate'] is None
    assert result['metrics']['corrections']['assisted']['rate'] is None
    assert response.headers['cache-control'] == 'no-store'


def test_save_survives_reload_and_retry_is_idempotent(client):
    from app.emergency_acceptance_models import EmergencyAcceptanceEvaluation
    payload = {'request_id': str(uuid4()), 'measurement': measurement()}
    first = client.post(PREFIX + '/evaluations', json=payload)
    assert first.status_code == 201, first.text
    again = client.post(PREFIX + '/evaluations', json=payload)
    assert again.status_code == 200
    assert again.json()['evaluation_id'] == first.json()['evaluation_id']
    listing = client.get(PREFIX + '/evaluations').json()
    assert len(listing) == 1 and 'measurement' not in listing[0]
    detail = client.get(PREFIX + '/evaluations/' + first.json()['evaluation_id']).json()
    assert detail['measurement']['dataset_kind'] == 'synthetic'
    assert len(detail['release_gates']) == 10
    assert all(item['status'] == 'MISSING' for item in detail['release_gates'])
    payload['measurement']['comparison_confirmed'] = True
    assert client.post(PREFIX + '/evaluations', json=payload).status_code == 409
    with SessionLocal() as db:
        assert db.scalar(select(func.count()).select_from(EmergencyAcceptanceEvaluation)) == 1
        assert db.scalar(select(func.count()).select_from(AuditLog).where(
            AuditLog.action == 'emergency.acceptance.create')) == 1


def test_corrected_measurement_creates_new_snapshot_and_rejects_stale_parent(client):
    old = save(client).json()
    created = save(client, supersedes_id=old['evaluation_id'], expected_previous_version=1)
    assert created.status_code == 201, created.text
    assert created.json()['supersedes_id'] == old['evaluation_id']
    assert client.get(PREFIX + '/evaluations/' + old['evaluation_id']).json()['version'] == 1
    assert save(client, supersedes_id=old['evaluation_id'], expected_previous_version=1).status_code == 409
    assert save(client, supersedes_id=created.json()['evaluation_id'], expected_previous_version=99).status_code == 409


def test_review_is_independent_versioned_and_cannot_approve_production(client):
    saved = save(client).json()
    url = PREFIX + '/evaluations/' + saved['evaluation_id'] + '/review'
    payload = {'expected_version': 1, 'decision': 'confirmed', 'evidence': []}
    assert client.post(url, json=payload).status_code == 403
    login(client, 'reviewer')
    checked = client.post(url, json=payload)
    assert checked.status_code == 200, checked.text
    assert checked.json()['version'] == 2
    assert checked.json()['review_decision'] == 'confirmed'
    assert checked.json()['production_complete'] is False
    assert all(gate['status'] == 'MISSING' for gate in checked.json()['release_gates'])
    assert client.post(url, json=payload).status_code == 409


def test_reassigned_account_cannot_review_its_own_employee_history(client):
    saved = save(client).json()
    with SessionLocal() as db:
        author = db.scalar(select(User).where(User.username == 'acceptance-author'))
        reviewer = db.scalar(select(User).where(User.username == 'acceptance-reviewer'))
        employee_id = author.employee_id
        author.employee_id = None
        db.flush()
        reviewer.employee_id = employee_id
        db.commit()
    login(client, 'reviewer')
    assert client.post(PREFIX + '/evaluations/' + saved['evaluation_id'] + '/review',
                       json={'expected_version': 1, 'decision': 'confirmed'}).status_code == 403


def test_internal_records_are_disabled_until_explicit_internal_configuration(client):
    payload = {'dataset_kind': 'internal_trial', 'reports': []}
    assert client.post(PREFIX + '/preview', json=payload).status_code == 403
    assert save(client, measurement=payload).status_code == 403


def test_private_input_is_not_reflected_in_validation_responses_or_audits(client, caplog):
    marker = 'SYNTHETIC_PRIVATE_SENTINEL_DO_NOT_ECHO'
    response = client.post(PREFIX + '/preview', json={**measurement(), marker: marker})
    assert response.status_code == 422
    assert marker not in response.text
    response = client.post(PREFIX + '/evaluations', json={'request_id': marker, 'measurement': measurement()})
    assert response.status_code == 422 and marker not in response.text
    malformed = client.post(PREFIX + '/preview', content='{"' + marker + '":',
                            headers={'Content-Type': 'application/json'})
    assert malformed.status_code == 422 and marker not in malformed.text
    with SessionLocal() as db:
        rows = db.scalars(select(AuditLog).where(AuditLog.action.like('emergency.acceptance.%'))).all()
        assert marker not in json.dumps([{'before': row.before_data, 'after': row.after_data} for row in rows])
    assert marker not in caplog.text


def test_authentication_detail_permission_revocation_and_no_cache(client):
    saved = save(client).json()
    url = PREFIX + '/evaluations/' + saved['evaluation_id']
    with TestClient(app) as anonymous:
        response = anonymous.get(url)
        assert response.status_code == 401
        assert response.headers['cache-control'] == 'no-store'
    with SessionLocal() as db:
        permission = db.scalar(select(Permission).where(Permission.code == 'emergency.patient.read'))
        for link in db.scalars(select(RolePermission).where(RolePermission.permission_id == permission.permission_id)):
            db.delete(link)
        db.commit()
    assert client.get(url).status_code == 403
    assert client.get(PREFIX + '/evaluations').status_code == 403
    assert client.post(PREFIX + '/preview', json=measurement()).status_code == 403
    assert save(client).status_code == 403


def test_evidence_requires_existing_typed_internal_document_and_does_not_become_certification(client):
    saved = save(client).json()
    login(client, 'reviewer')
    url = PREFIX + '/evaluations/' + saved['evaluation_id'] + '/review'
    payload = {'expected_version': 1, 'decision': 'confirmed', 'evidence': [
        {'gate': 'network_egress', 'document_id': str(uuid4()), 'result': 'passed'}]}
    assert client.post(url, json=payload).status_code == 422
    with SessionLocal() as db:
        document = Document(storage_path='synthetic/evidence.txt', original_filename='synthetic',
                            sha256='0' * 64, size_bytes=0, mime_type='text/plain',
                            document_type='emergency_acceptance_evidence')
        db.add(document); db.commit(); identity = document.document_id
    payload['evidence'][0]['document_id'] = identity
    result = client.post(url, json=payload)
    assert result.status_code == 200, result.text
    assert result.json()['production_complete'] is False
    status = {item['gate']: item['status'] for item in result.json()['release_gates']}
    assert status['network_egress'] == 'RECORDED_PASS'
    assert status['access_control'] == 'MISSING'
    assert '0' * 64 not in result.text and 'synthetic/evidence.txt' not in result.text


def test_body_limits_and_media_type_reject_without_reflection(client):
    response = client.post(PREFIX + '/preview', content=b'x' * (2 * 1024 * 1024 + 1),
                           headers={'Content-Type': 'application/json'})
    assert response.status_code == 413
    assert len(response.content) < 300
    assert client.post(PREFIX + '/preview', content=b'%PDF-synthetic',
                       headers={'Content-Type': 'application/pdf'}).status_code == 415


def test_candidate_core_connection_retains_unreadable_and_non_approval(client):
    payload = {'fields': {'transported': {'state': 'confirmed', 'value': False},
                          'urgency': {'state': 'unreadable'}}}
    result = client.post(PREFIX + '/candidate-checks', json=payload)
    assert result.status_code == 200, result.text
    body = result.json()
    assert body['production_complete'] is False
    assert body['counts']['NOT_TESTED'] > 0
    assert body['reading_counts']['unreadable'] == 1
    assert all(row['rule_approval'] == 'PROVISIONAL_NOT_APPROVED' for row in body['findings'])
    assert 'value' not in body
    assert client.post(PREFIX + '/candidate-checks', json={'fields': {
        'patient_name': {'state': 'confirmed', 'value': 'SYNTHETIC_PRIVATE_SENTINEL'}}}).status_code == 422


def test_candidate_values_and_identifiers_are_not_written_to_audit(client):
    marker = 'SYNTHETIC_PRIVATE_SENTINEL'
    response = client.post(PREFIX + '/candidate-checks', json={'fields': {
        'place_major': {'state': 'confirmed', 'value': marker}}})
    assert response.status_code == 200
    assert marker not in response.text
    with SessionLocal() as db:
        rows = db.scalars(select(AuditLog).where(AuditLog.action == 'emergency.acceptance.candidate_check')).all()
        assert len(rows) == 1
        assert marker not in json.dumps(rows[0].after_data)


def test_new_snapshot_invalidates_old_review_even_when_parent_version_is_unchanged(client):
    old = save(client).json()
    new = save(client, supersedes_id=old['evaluation_id'], expected_previous_version=1).json()
    login(client, 'reviewer')
    detail = client.get(PREFIX + '/evaluations/' + old['evaluation_id']).json()
    assert detail['can_review'] is False
    assert detail['superseded_by'] == new['evaluation_id']
    checked = client.post(PREFIX + '/evaluations/' + old['evaluation_id'] + '/review',
                          json={'expected_version': 1, 'decision': 'confirmed'})
    assert checked.status_code == 409


@pytest.mark.parametrize('body', [b'{"dataset_kind":"\xff"}', b'{"value":' + b'1' * 5000 + b'}'])
def test_parser_errors_are_private_no_store_responses(client, body):
    response = client.post(PREFIX + '/preview', content=body, headers={'Content-Type': 'application/json'})
    assert response.status_code in (400, 422)
    assert response.headers.get('cache-control') == 'no-store'
    assert len(response.content) < 400


@pytest.mark.parametrize('value', [False, 123, 1.5])
def test_wrong_category_types_never_reach_candidate_clear(client, value):
    response = client.post(PREFIX + '/candidate-checks', json={'fields': {
        'place_major': {'state': 'confirmed', 'value': '住宅'},
        'place_minor': {'state': 'confirmed', 'value': value}}})
    assert response.status_code == 422


def test_sample_is_valid_in_real_preview_and_still_incomplete(client):
    response = client.get(PREFIX + '/sample')
    assert response.status_code == 200
    result = client.post(PREFIX + '/preview', json=response.json())
    assert result.status_code == 200
    assert result.json()['production_complete'] is False
    assert result.json()['metrics']['read_states']['unreadable'] == 1
