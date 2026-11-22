"""Synthetic reports only: public API privacy, workflow, and measurement contracts."""
import json
import os
from datetime import datetime, timedelta, timezone
from uuid import uuid4

os.environ['FIRE_AI_DATABASE_URL'] = 'sqlite+pysqlite:///:memory:'

import pymupdf
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.db import Base, SessionLocal, engine
from app.main import app
from app.models import AuditLog, Document, Employee, Permission, Role, RolePermission, User, UserRole
from app.emergency_audit_models import AuditEvent, AuditReport, AuditRevision, AuditRun
from app.security import hash_password

P = '/emergency/audit'
DETAIL = {'emergency.case.read', 'emergency.patient.read', 'emergency.report.read'}


def pdf(text='SYNTHETIC ONLY 123'):
    doc = pymupdf.open(); page = doc.new_page(); page.insert_text((40, 60), text)
    value = doc.tobytes(); doc.close(); return value


@pytest.fixture
def client(tmp_path, monkeypatch):
    from app.settings import settings
    key = tmp_path / 'private-key'; key.write_bytes(os.urandom(32)); key.chmod(0o600)
    monkeypatch.setattr(settings, 'emergency_audit_enabled', True)
    monkeypatch.setattr(settings, 'emergency_audit_key_file', str(key))
    monkeypatch.setattr(settings, 'emergency_audit_internal_enabled', False)
    monkeypatch.setattr(settings, 'storage_root', str(tmp_path / 'storage'))
    monkeypatch.setattr(settings, 'emergency_audit_ai_model', None)
    Base.metadata.drop_all(engine); Base.metadata.create_all(engine)
    with SessionLocal() as db:
        codes = DETAIL | {'emergency.report.create', 'emergency.report.review', 'emergency.audit.configure',
            'emergency.audit.approve', 'emergency.audit.read_all', 'document.read', 'intake.read', 'drawing.read'}
        permissions = {code: Permission(code=code) for code in codes}
        db.add_all(permissions.values()); db.flush()
        for name, rights in {
            'owner': DETAIL | {'emergency.report.create', 'emergency.audit.configure'},
            'reviewer': DETAIL | {'emergency.report.create', 'emergency.report.review',
                                 'emergency.audit.configure', 'emergency.audit.approve', 'emergency.audit.read_all'},
            'outsider': DETAIL | {'emergency.report.create'},
            'generic': {'document.read', 'intake.read', 'drawing.read'},
        }.items():
            role = Role(code='audit-' + name, name='Synthetic audit ' + name)
            employee = Employee(display_name='Synthetic ' + name)
            db.add_all([role, employee]); db.flush()
            user = User(username='audit-' + name, employee_id=employee.employee_id,
                        password_hash=hash_password('synthetic-audit-password'))
            db.add(user); db.flush(); db.add(UserRole(user_id=user.user_id, role_id=role.role_id))
            db.add_all([RolePermission(role_id=role.role_id, permission_id=permissions[code].permission_id) for code in rights])
        db.commit()
    with TestClient(app) as active:
        login(active)
        yield active


def login(client, who='owner'):
    result = client.post('/auth/login', json={'username': 'audit-' + who, 'password': 'synthetic-audit-password'})
    assert result.status_code == 200, result.text


def upload(client, *, content=None, profile_id=None, request_id=None, dataset_kind='synthetic'):
    data = {'request_id': request_id or str(uuid4()), 'dataset_kind': dataset_kind}
    if profile_id: data['profile_id'] = profile_id
    return client.post(P + '/reports', data=data, files={'file': ('private-do-not-echo.pdf', content or pdf(), 'application/pdf')})


def create_profile(client):
    response = client.post(P + '/profiles', json={'request_id': str(uuid4()), 'definition': {
        'label': 'Synthetic form', 'form_key': 'synthetic-v1', 'valid_from': '2026-01-01',
        'fields': [{'field_id': 'a', 'label': 'Synthetic value', 'value_type': 'text', 'page': 1,
                    'bbox': [0, 0, 1, 0.2], 'extraction': 'region'}]}})
    assert response.status_code == 201, response.text
    return response.json()


def process_read():
    from app.emergency_audit_worker import process_one
    from app.emergency_reader import extract_source
    def executor(mode, data, **kwargs):
        assert mode == 'read'
        return extract_source(data)
    assert process_one(session_factory=SessionLocal, executor=executor)


def test_upload_retains_encrypted_immutable_original_and_is_idempotent(client):
    request_id = str(uuid4()); content = pdf('SYNTHETIC_PRIVATE_SOURCE_MARKER')
    response = upload(client, content=content, request_id=request_id)
    assert response.status_code == 201, response.text
    saved = response.json(); identity = saved['current_revision_id']
    assert saved['revision']['processing_status'] == 'queued'
    assert saved['revision']['reading'] is None
    assert 'private-do-not-echo' not in response.text
    assert upload(client, content=content, request_id=request_id).status_code == 200
    assert upload(client, content=pdf('SYNTHETIC DIFFERENT'), request_id=request_id).status_code == 409
    downloaded = client.get(P + f'/revisions/{identity}/original')
    assert downloaded.content == content
    assert downloaded.headers['cache-control'] == 'no-store'
    assert downloaded.headers['content-disposition'].startswith('attachment;')
    with SessionLocal() as db:
        assert list(db.scalars(select(Document))) == []
        logs = list(db.scalars(select(AuditLog).where(AuditLog.action.like('emergency.audit.%'))))
        assert 'SYNTHETIC_PRIVATE_SOURCE_MARKER' not in json.dumps([row.after_data for row in logs])
        assert 'private-do-not-echo' not in json.dumps([row.after_data for row in logs])


def test_maintenance_refusal_is_private_and_does_not_echo_internal_details(client, monkeypatch):
    from app.department_maintenance import MaintenanceUnavailable
    from app import emergency_audit_service
    upload(client)
    def unavailable(*args, **kwargs):
        raise MaintenanceUnavailable('SYNTHETIC_PRIVATE_MAINTENANCE_DETAIL')
    monkeypatch.setattr(emergency_audit_service, 'summary', unavailable)
    response = client.get(P + '/reports')
    assert response.status_code == 503
    assert response.headers.get('cache-control') == 'no-store'
    assert response.headers.get('retry-after') == '30'
    assert 'SYNTHETIC_PRIVATE_MAINTENANCE_DETAIL' not in response.text


def test_scope_revocation_internal_gate_safe_validation_and_origin(client):
    saved = upload(client).json(); path = P + '/reports/' + saved['report_id']
    login(client, 'outsider')
    assert client.get(path).status_code == 404
    assert client.get(P + '/reports').json() == []
    assert client.get(P + '/revisions/' + saved['current_revision_id'] + '/pages/1.png').status_code == 404
    login(client, 'generic')
    assert client.get(P + '/reports').status_code == 403
    login(client)
    assert upload(client, dataset_kind='internal_trial').status_code == 403
    bad = client.post(P + '/reports', files={'file': ('private.txt', b'PRIVATE_SENTINEL', 'application/pdf')},
                      data={'request_id': str(uuid4()), 'dataset_kind': 'synthetic'})
    assert bad.status_code == 422 and 'PRIVATE_SENTINEL' not in bad.text
    denied = client.post(P + '/measurement-export', json={'report_ids': [saved['report_id']]},
                         headers={'Origin': 'https://outside.invalid'})
    assert denied.status_code == 403
    invalid = client.post(P + '/measurement-export', json={'report_ids': ['PRIVATE_SENTINEL']})
    assert invalid.status_code == 422 and 'PRIVATE_SENTINEL' not in invalid.text
    with SessionLocal() as db:
        user = db.scalar(select(User).where(User.username == 'audit-owner'))
        employee = Employee(display_name='Synthetic reassignment'); db.add(employee); db.flush()
        user.employee_id = employee.employee_id; db.commit()
    assert client.get(path).status_code == 404


def test_read_confirm_check_correct_recheck_and_historical_snapshot(client):
    profile = create_profile(client)
    saved = upload(client, profile_id=profile['config_id']).json()
    process_read()
    saved = client.get(P + '/reports/' + saved['report_id']).json()
    rev = saved['current_revision_id']; field = saved['revision']['fields']['a']
    assert field['state'] == 'unconfirmed' and field['value'] is None
    assert field['candidate'] and field['evidence'][0]['page'] == 1
    response = client.post(P + f'/revisions/{rev}/fields', json={'expected_version': saved['version'],
        'confirmed_from_original': True, 'fields': [{'field_id': 'a', 'state': 'confirmed', 'value': 'synthetic'}]})
    assert response.status_code == 200, response.text
    saved = response.json()
    checked = client.post(P + f'/revisions/{rev}/checks', json={'expected_version': saved['version'],
        'mode': 'candidate', 'as_of': '2026-11-21'})
    assert checked.status_code == 200, checked.text
    saved = checked.json(); run_id = saved['last_run']['run_id']
    assert len(saved['last_run']['findings']) == 10
    assert saved['last_run']['approval'] == 'PROVISIONAL_NOT_APPROVED'
    assert all(item['status'] == 'NOT_TESTED' for item in saved['last_run']['findings'])
    assert saved['measurement']['independent_review_complete'] is False
    correction = client.post(P + '/reports/' + saved['report_id'] + '/revisions',
        files={'file': ('corrected.pdf', pdf('SYNTHETIC CORRECTED'), 'application/pdf')},
        data={'request_id': str(uuid4()), 'expected_version': saved['version'], 'profile_id': profile['config_id']})
    assert correction.status_code == 201, correction.text
    new = correction.json(); assert new['revision_number'] == 2
    historical = client.get(P + f'/revisions/{rev}').json()
    assert historical['last_run']['run_id'] == run_id and historical['last_run']['stale']
    assert historical['revision']['fields']['a']['value'] == 'synthetic'
    assert client.post(P + f'/revisions/{rev}/fields', json={'expected_version': new['version'],
        'confirmed_from_original': True, 'fields': [{'field_id': 'a', 'state': 'confirmed', 'value': 'bad'}]}).status_code == 409
    assert client.get(P + f'/revisions/{rev}/original').content != client.get(P + '/revisions/' + new['current_revision_id'] + '/original').content


def test_baseline_cannot_receive_ai_checks_and_time_is_not_invented(client):
    saved = upload(client).json(); path = P + '/reports/' + saved['report_id']
    event_id = str(uuid4()); payload = {'event_id': event_id, 'expected_version': saved['version'],
        'kind': 'study', 'payload': {'cohort': 'baseline', 'activity_kind': 'unknown'}}
    response = client.post(path + '/events', json=payload)
    assert response.status_code == 200, response.text
    saved = response.json()
    assert client.post(path + '/events', json=payload).status_code == 200
    process_read(); saved = client.get(path).json()
    assert client.post(P + '/revisions/' + saved['current_revision_id'] + '/checks', json={
        'expected_version': saved['version'], 'mode': 'candidate', 'as_of': '2026-11-21'}).status_code == 409
    assert client.post(P + '/revisions/' + saved['current_revision_id'] + '/ai', json={
        'expected_version': saved['version']}).status_code == 409
    exported = client.post(P + '/measurement-export', json={'report_ids': [saved['report_id']]}).json()
    assert exported['reports'][0]['cohort'] == 'baseline'
    assert exported['reports'][0]['work_complete'] is False
    assert exported['reports'][0]['work'] == []
    assert exported['comparison_confirmed'] is False and exported['targets'] == {}


def test_ai_job_prevents_relabel_as_baseline_even_before_rule_checks(client):
    saved = upload(client).json(); process_read()
    path = P + '/reports/' + saved['report_id']; saved = client.get(path).json()
    queued = client.post(P + '/revisions/' + saved['current_revision_id'] + '/ai', json={'expected_version': saved['version']})
    assert queued.status_code == 200, queued.text
    saved = queued.json()
    result = client.post(path + '/events', json={'event_id': str(uuid4()), 'expected_version': saved['version'],
        'kind': 'study', 'payload': {'cohort': 'baseline', 'activity_kind': 'unknown'}})
    assert result.status_code == 409


def test_all_rechecks_remain_in_independent_measurement_and_unknown_timing_is_not_late(client):
    profile = create_profile(client)
    rules = client.post(P + '/rule-sets', json={'request_id': str(uuid4()), 'definition': {
        'label': 'Synthetic rule', 'form_key': 'synthetic-v1', 'valid_from': '2026-01-01',
        'rules': [{'rule_id': 'SYN:VALUE', 'label': 'Synthetic value check', 'message': 'Synthetic mismatch',
            'severity': 'warning', 'source': {'document_title': 'Synthetic source', 'version': '1', 'page': '1'},
            'assertion': {'kind': 'field', 'field': 'a', 'operator': 'eq', 'value': 'expected'}}]}})
    assert rules.status_code == 201, rules.text
    saved = upload(client, profile_id=profile['config_id']).json(); process_read()
    path = P + '/reports/' + saved['report_id']; saved = client.get(path).json(); rev = saved['current_revision_id']
    saved = client.post(P + f'/revisions/{rev}/fields', json={'expected_version': saved['version'],
        'confirmed_from_original': True, 'fields': [{'field_id': 'a', 'state': 'confirmed', 'value': 'observed'}]}).json()
    run_ids = []
    for _ in range(2):
        response = client.post(P + f'/revisions/{rev}/checks', json={'expected_version': saved['version'],
            'rule_set_id': rules.json()['config_id'], 'mode': 'candidate', 'as_of': '2026-11-21'})
        assert response.status_code == 200, response.text
        saved = response.json(); run_ids.append(saved['last_run']['run_id'])
    assert saved['measurement'] is None and saved['measurement_pending'] == ['SUBMISSION_NOT_RECORDED']
    assert client.post(P + '/measurement-export', json={'report_ids': [saved['report_id']]}).status_code == 409
    response = client.post(path + '/events', json={'event_id': str(uuid4()), 'expected_version': saved['version'],
        'kind': 'submitted', 'payload': {'occurred_at': datetime.now(timezone.utc).isoformat()}})
    assert response.status_code == 200, response.text
    saved = response.json()
    assert len(saved['measurement']['opportunities']) == 2
    assert all(item['before_submission'] is True for item in saved['measurement']['opportunities'])
    login(client, 'reviewer'); saved = client.get(path).json()
    for index, run_id in enumerate(run_ids):
        response = client.post(path + '/events', json={'event_id': str(uuid4()), 'expected_version': saved['version'],
            'kind': 'truth_review', 'payload': {'run_id': run_id, 'complete': True, 'whole_report_checked': True,
                'items': [{'rule_id': 'SYN:VALUE', 'truth': 'correct', 'verified_read_state': 'confirmed'}]}})
        assert response.status_code == 200, response.text
        saved = response.json()
        assert saved['measurement']['independent_review_complete'] is (index == 1)
    exported = client.post(P + '/measurement-export', json={'report_ids': [saved['report_id']]}).json()
    from app.emergency_acceptance import evaluate_acceptance
    from app.emergency_acceptance_schemas import EvaluationInput
    measured = evaluate_acceptance(EvaluationInput.model_validate(exported))
    assert measured['metrics']['false_alerts']['count'] == 2
    assert measured['metrics']['false_alerts']['per_report'] == 2
    # A new original first created after submission cannot introduce errors
    # retroactively into the pre-submission recall denominator.
    correction = client.post(path + '/revisions', files={'file': ('post-submit.pdf', pdf('SYNTHETIC AFTER SUBMISSION'), 'application/pdf')},
        data={'request_id': str(uuid4()), 'expected_version': saved['version'], 'profile_id': profile['config_id']})
    assert correction.status_code == 201, correction.text
    process_read(); saved = client.get(path).json()
    later = client.post(P + '/revisions/' + saved['current_revision_id'] + '/checks', json={
        'expected_version': saved['version'], 'rule_set_id': rules.json()['config_id'],
        'mode': 'candidate', 'as_of': '2026-11-21'})
    assert later.status_code == 200, later.text
    saved = later.json()
    assert len(saved['runs']) == 3
    assert len(saved['measurement']['opportunities']) == 2
    assert saved['measurement']['independent_review_complete'] is True
    assert saved['measurement_scope']['post_submission_revision_runs'] == 1


def test_measurement_event_correction_preserves_history_and_rejects_forks(client):
    saved = upload(client).json(); path = P + '/reports/' + saved['report_id']
    ended = datetime.now(timezone.utc) - timedelta(seconds=10)
    started = ended - timedelta(seconds=120)
    first_id = str(uuid4())
    first = client.post(path + '/events', json={'event_id': first_id, 'expected_version': saved['version'],
        'kind': 'work_interval', 'payload': {'stage': 'check', 'started_at': started.isoformat(), 'ended_at': ended.isoformat()}})
    assert first.status_code == 200, first.text
    original_version = first.json()['version']
    changed_id = str(uuid4())
    replacement = {'event_id': changed_id, 'supersedes_event_id': first_id,
        'expected_version': original_version, 'kind': 'work_interval',
        'payload': {'stage': 'check', 'started_at': (started + timedelta(seconds=60)).isoformat(), 'ended_at': ended.isoformat()}}
    changed = client.post(path + '/events', json=replacement)
    assert changed.status_code == 200, changed.text
    work = changed.json()['measurement']['work']; assert len(work) == 1
    assert work[0]['end_seconds'] - work[0]['start_seconds'] == 60
    assert len([item for item in changed.json()['events'] if item['kind'] == 'work_interval']) == 2
    assert client.post(path + '/events', json=replacement).status_code == 200
    fork = {**replacement, 'event_id': str(uuid4()), 'expected_version': changed.json()['version']}
    assert client.post(path + '/events', json=fork).status_code == 409
    with SessionLocal() as db:
        old = db.get(AuditEvent, first_id)
        assert old.payload['started_at'] == started.isoformat().replace('+00:00', 'Z')


def test_shared_config_does_not_disclose_private_impact_sources_to_other_readers(client):
    profile = create_profile(client)
    saved = upload(client, profile_id=profile['config_id']).json(); process_read()
    impact = client.post(P + '/configurations/' + profile['config_id'] + '/impact', json={'report_ids': [saved['report_id']]})
    assert impact.status_code == 200, impact.text
    assert impact.json()['impact']['report_count'] == 1
    login(client, 'outsider')
    for path in ['/profiles', '/configurations/' + profile['config_id']]:
        response = client.get(P + path)
        assert response.status_code == 200
        item = response.json()[0] if isinstance(response.json(), list) else response.json()
        assert item['impact'] is None
        assert saved['report_id'] not in response.text
        assert saved['current_revision_id'] not in response.text


def test_rule_candidate_catalog_retains_holds_without_activating_them(client):
    first = client.get(P + '/rule-candidates')
    assert first.status_code == 200, first.text
    assert first.json()['total'] == 433
    assert all(item['executable'] is False for item in first.json()['items'])
    assert client.get(P + '/rule-candidates?group=CR').json()['total'] == 64


def test_new_sensitive_audit_permissions_are_never_automatically_granted():
    from app.rbac_seed import ROLE_POLICY
    rights = {'emergency.audit.configure', 'emergency.audit.approve', 'emergency.audit.read_all'}
    assert all(not rights & policy['permissions'] for policy in ROLE_POLICY.values())


def test_confirmed_blank_requires_explicit_null_and_boolean_attestation(client):
    profile = create_profile(client)
    saved = upload(client, profile_id=profile['config_id']).json(); process_read()
    saved = client.get(P + '/reports/' + saved['report_id']).json()
    url = P + '/revisions/' + saved['current_revision_id'] + '/fields'
    body = {'expected_version': saved['version'], 'confirmed_from_original': True,
            'fields': [{'field_id': 'a', 'state': 'confirmed'}]}
    assert client.post(url, json=body).status_code == 422
    body['fields'][0]['value'] = None
    assert client.post(url, json={**body, 'confirmed_from_original': 1}).status_code == 422
    explicit = client.post(url, json=body)
    assert explicit.status_code == 200, explicit.text
    assert explicit.json()['revision']['fields']['a']['value'] is None


def test_same_worker_cannot_double_count_overlapping_time_across_reports(client):
    one = upload(client).json(); two = upload(client).json()
    end = datetime.now(timezone.utc) - timedelta(seconds=1)
    work = {'stage': 'import', 'started_at': (end - timedelta(seconds=120)).isoformat(), 'ended_at': end.isoformat()}
    assert client.post(P + '/reports/' + one['report_id'] + '/events', json={
        'event_id': str(uuid4()), 'expected_version': one['version'], 'kind': 'work_interval', 'payload': work}).status_code == 200
    assert client.post(P + '/reports/' + two['report_id'] + '/events', json={
        'event_id': str(uuid4()), 'expected_version': two['version'], 'kind': 'work_interval', 'payload': work}).status_code == 409
