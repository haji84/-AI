"""Native PostgreSQL upgrade, privacy, approval and competing audit operations.

All originals, accounts and rules are synthetic. This test creates and drops a
dedicated database only when FIRE_AI_TEST_POSTGRES_URL explicitly permits it;
a local skip is not evidence of successful PostgreSQL verification.
"""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from hashlib import sha256
import os
from pathlib import Path
import shutil
from threading import Barrier, Event, Lock
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, func, select, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker


PREFIX = '/emergency/audit'
MIGRATION = '060_emergency_audit_pipeline.sql'
PASSWORD = 'synthetic-native-audit-password'
DETAIL = {'emergency.case.read', 'emergency.patient.read', 'emergency.report.read'}


def _pdf(value):
    import pymupdf
    with pymupdf.open() as document:
        page = document.new_page(width=400, height=200)
        page.insert_text((35, 45), value, fontsize=10)
        return document.tobytes()


def _login(client, who='author'):
    response = client.post('/auth/login', json={'username': 'native-audit-' + who, 'password': PASSWORD})
    assert response.status_code == 200, response.text


def _post(client, suffix, payload, expected=200):
    response = client.post(PREFIX + suffix, json=payload)
    assert response.status_code == expected, response.text
    assert response.headers.get('cache-control') == 'no-store'
    return response.json()


def _upload(client, value, profile_id, *, report=None):
    data = {'request_id': str(uuid4()), 'profile_id': profile_id}
    suffix = '/reports'
    if report:
        suffix += '/' + report['report_id'] + '/revisions'
        data['expected_version'] = str(report['version'])
    else:
        data['dataset_kind'] = 'synthetic'
    response = client.post(PREFIX + suffix, data=data,
        files={'file': ('synthetic-private-original.pdf', value, 'application/pdf')})
    assert response.status_code == 201, response.text
    assert response.headers.get('cache-control') == 'no-store'
    return response.json()


def _get_report(client, identity):
    response = client.get(PREFIX + '/reports/' + identity)
    assert response.status_code == 200, response.text
    return response.json()


def _reading(mode, data, **kwargs):
    from app.emergency_reader import extract_source
    assert mode == 'read'
    return extract_source(data)


def _rejected_sql(engine, statement, identity):
    with pytest.raises(IntegrityError) as error:
        with engine.begin() as connection:
            connection.execute(text(statement), {'identity': identity})
    assert error.value.orig.sqlstate == '23514'


def test_audit_native_upgrade_private_approval_workers_and_competing_writes(tmp_path, monkeypatch):
    url = os.environ.get('FIRE_AI_TEST_POSTGRES_URL')
    if not url:
        pytest.skip('actual PostgreSQL 059-to-060 upgrade/worker/approval/CAS checks require FIRE_AI_TEST_POSTGRES_URL')
    assert make_url(url).get_backend_name() == 'postgresql', 'PostgreSQL test URL is required'

    from app.db import BoundSession, get_db
    from app.emergency_acceptance_models import EmergencyAcceptanceEvaluation
    from app.emergency_audit_models import AuditConfiguration, AuditEvent, AuditJob, AuditReport, AuditRevision, AuditRun, AuditSource
    from app.emergency_audit_worker import process_one
    from app import emergency_vault as vault
    from app.main import app
    from app.migrations import apply_migrations
    from app.models import AuditLog, Document, Employee, Facility, Permission, Role, RolePermission, User, UserRole
    from app.security import hash_password
    from app.settings import settings

    root = Path(__file__).resolve().parents[2]
    baseline = tmp_path / 'through_059'; baseline.mkdir()
    upgraded = tmp_path / 'through_060'; upgraded.mkdir()
    for path in (root / 'db/migrations').glob('*.sql'):
        if path.name < MIGRATION: shutil.copy2(path, baseline / path.name)
        if path.name <= MIGRATION: shutil.copy2(path, upgraded / path.name)
    assert (baseline / '059_emergency_acceptance.sql').exists()
    assert (upgraded / MIGRATION).exists()

    key = tmp_path / 'external-key'; key.write_bytes(os.urandom(32)); key.chmod(0o600)
    monkeypatch.setattr(settings, 'emergency_audit_enabled', True)
    monkeypatch.setattr(settings, 'emergency_audit_internal_enabled', False)
    monkeypatch.setattr(settings, 'emergency_audit_key_file', str(key))
    monkeypatch.setattr(settings, 'emergency_audit_ai_model', None)
    monkeypatch.setattr(settings, 'storage_root', str(tmp_path / 'storage'))
    monkeypatch.setattr(settings, 'tenant_id', None)
    monkeypatch.setattr(settings, 'production_mode', False)
    monkeypatch.setattr(settings, 'cookie_secure', False)

    name = 'fi_em_audit_' + uuid4().hex[:16]
    admin = create_engine(make_url(url).set(database='postgres'), isolation_level='AUTOCOMMIT')
    target = None
    database_created = False
    previous_overrides = dict(app.dependency_overrides)
    try:
        with admin.connect() as connection:
            connection.exec_driver_sql('CREATE DATABASE ' + name)
        database_created = True
        target_url = make_url(url).set(database=name).render_as_string(hide_password=False)
        assert apply_migrations(target_url, baseline)[-1] == '059_emergency_acceptance.sql'
        target = create_engine(target_url, pool_pre_ping=True)

        with Session(target) as db:
            codes = DETAIL | {'emergency.report.create', 'emergency.report.review',
                'emergency.audit.configure', 'emergency.audit.approve', 'emergency.audit.read_all'}
            permissions = {row.code: row for row in db.scalars(select(Permission).where(Permission.code.in_(codes)))}
            for code in codes - permissions.keys():
                permissions[code] = Permission(code=code); db.add(permissions[code])
            db.flush()
            identities = {}
            for name_part, rights in {
                'author': DETAIL | {'emergency.report.create', 'emergency.audit.configure', 'emergency.audit.approve'},
                'reviewer': codes,
            }.items():
                employee = Employee(display_name='Synthetic native audit ' + name_part)
                role = Role(code='native-audit-' + name_part, name='Synthetic native audit ' + name_part)
                db.add_all([employee, role]); db.flush()
                user = User(username='native-audit-' + name_part, employee_id=employee.employee_id,
                            password_hash=hash_password(PASSWORD))
                db.add(user); db.flush()
                db.add(UserRole(user_id=user.user_id, role_id=role.role_id))
                db.add_all(RolePermission(role_id=role.role_id, permission_id=permissions[code].permission_id) for code in rights)
                identities[name_part] = (user.user_id, employee.employee_id)
            facility = Facility(name='Synthetic preserved audit facility', status='active')
            evaluation = EmergencyAcceptanceEvaluation(request_id=str(uuid4()), request_sha256='a' * 64,
                dataset_kind='synthetic', measurement={'reports': []}, summary={'production_complete': False},
                created_by=identities['author'][0], created_employee_id=identities['author'][1])
            db.add_all([facility, evaluation]); db.commit()
            facility_id, evaluation_id = facility.building_id, evaluation.evaluation_id

        assert apply_migrations(target_url, upgraded) == [MIGRATION]
        assert apply_migrations(target_url, upgraded) == []
        with Session(target) as db:
            assert db.get(Facility, facility_id).name == 'Synthetic preserved audit facility'
            previous_evaluation = db.get(EmergencyAcceptanceEvaluation, evaluation_id)
            assert previous_evaluation.measurement == {'reports': []}
            assert previous_evaluation.summary == {'production_complete': False}
            assert previous_evaluation.created_employee_id == identities['author'][1]
            assert db.scalar(select(func.count()).select_from(AuditReport)) == 0
            assert db.execute(text('SELECT count(*) FROM schema_migrations WHERE version=:version'),
                {'version': MIGRATION}).scalar_one() == 1

        factory = sessionmaker(bind=target, class_=BoundSession, expire_on_commit=False, autoflush=False)
        def sessions():
            with factory() as db:
                yield db
        app.dependency_overrides[get_db] = sessions

        with TestClient(app) as client:
            _login(client)
            raw_source = _pdf('SYNTHETIC_POLICY_PRIVATE_ONLY')
            source_response = client.post(PREFIX + '/sources', data={'request_id': str(uuid4())},
                files={'file': ('synthetic-policy.pdf', raw_source, 'application/pdf')})
            assert source_response.status_code == 201, source_response.text
            source = source_response.json()
            assert source['sha256'] == sha256(raw_source).hexdigest()
            profile = _post(client, '/profiles', {'request_id': str(uuid4()), 'source_id': source['source_id'],
                'definition': {'label': 'SYNTHETIC_CONFIG_PRIVATE', 'form_key': 'synthetic-native',
                    'valid_from': '2026-01-01', 'fields': [{
                        'field_id': 'sample', 'label': 'Synthetic sample', 'value_type': 'text', 'page': 1,
                        'bbox': [0.0, 0.0, 1.0, 1.0], 'extraction': 'region'}]}}, expected=201)
            profile_id = profile['config_id']
            # Draft definitions are frozen too; this must fail independently
            # of the separate restriction on editing already-approved rows.
            _rejected_sql(target, "UPDATE emergency_audit_configurations SET definition_cipher=decode('00','hex'), version=version+1 WHERE config_id=:identity", profile_id)
            with factory() as db:
                draft = db.get(AuditConfiguration, profile_id)
                assert draft.status == 'draft' and draft.version == 1
            raw_report = _pdf('SYNTHETIC_REPORT_PRIVATE_123')
            saved = _upload(client, raw_report, profile_id)
            report_id, revision_id = saved['report_id'], saved['current_revision_id']

            # Two real worker invocations start together. The winner holds its
            # lease while the other observes that no job remains claimable.
            barrier = Barrier(2); started = Event(); release = Event(); loser_done = Event()
            calls = []; calls_lock = Lock()
            def held_reader(mode, data, **kwargs):
                with calls_lock: calls.append(mode)
                started.set()
                assert release.wait(20), 'synthetic worker release timed out'
                return _reading(mode, data, **kwargs)
            def contender():
                barrier.wait(timeout=10)
                result = process_one(session_factory=factory, worker_id=str(uuid4()), executor=held_reader)
                if not result: loser_done.set()
                return result
            with ThreadPoolExecutor(max_workers=2) as pool:
                futures = [pool.submit(contender) for _ in range(2)]
                try:
                    assert started.wait(10), 'no worker claimed the synthetic job'
                    assert loser_done.wait(10), 'second worker did not respect the live lease'
                finally:
                    release.set()
                results = [future.result(timeout=30) for future in futures]
            assert sorted(results) == [False, True] and calls == ['read']
            saved = _get_report(client, report_id)
            assert saved['version'] == 2
            assert saved['revision']['fields']['sample']['state'] == 'unconfirmed'
            with factory() as db:
                job = db.scalar(select(AuditJob).where(AuditJob.revision_id == revision_id))
                assert job.status == 'done' and job.attempts == 1
                revision = db.get(AuditRevision, revision_id)
                assert revision.version == 2
                config = db.get(AuditConfiguration, profile_id)
                assert b'SYNTHETIC_REPORT_PRIVATE_123' not in revision.reading_cipher
                assert b'SYNTHETIC_REPORT_PRIVATE_123' not in revision.fields_cipher
                assert b'SYNTHETIC_CONFIG_PRIVATE' not in config.definition_cipher
                assert vault.read_original('revision', revision_id) == raw_report
                assert vault.read_original('source', source['source_id']) == raw_source
                assert 'SYNTHETIC_REPORT_PRIVATE_123' in vault.open_json('reading', revision_id, revision.reading_cipher)['pages'][0]['text']
                assert db.scalar(select(func.count()).select_from(Document)) == 0
            stored_files = list((tmp_path / 'storage' / 'emergency-audit').rglob('*.bin'))
            assert len(stored_files) == 2 and all(path.read_bytes().startswith(vault.MAGIC) for path in stored_files)
            assert all(raw_report not in path.read_bytes() and raw_source not in path.read_bytes() for path in stored_files)

            # Independent HTTP requests carry the same report version. This
            # verifies PostgreSQL locking and real mutation/session guards.
            cookies = dict(client.cookies); barrier = Barrier(2)
            expected_version = saved['version']
            def confirm(value):
                with TestClient(app) as contender_client:
                    contender_client.cookies.update(cookies)
                    barrier.wait(timeout=10)
                    response = contender_client.post(PREFIX + '/revisions/' + revision_id + '/fields', json={
                        'expected_version': expected_version, 'confirmed_from_original': True,
                        'fields': [{'field_id': 'sample', 'state': 'confirmed', 'value': value}]})
                    return response.status_code, response.json()
            with ThreadPoolExecutor(max_workers=2) as pool:
                futures = [pool.submit(confirm, 'Synthetic confirmed ' + str(index)) for index in range(2)]
                confirmations = [future.result(timeout=30) for future in futures]
            assert sorted(code for code, _ in confirmations) == [200, 409], confirmations
            saved = next(body for code, body in confirmations if code == 200)
            assert saved['version'] == 3
            with factory() as db:
                assert db.get(AuditRevision, revision_id).version == 3

            profile = _post(client, '/configurations/' + profile_id + '/impact', {'report_ids': [report_id]})
            assert profile['version'] == 2 and profile['impact']['can_approve'] is True
            approve_payload = {'expected_version': 2, 'source_verified': True, 'mapping_verified': True}
            denied = client.post(PREFIX + '/configurations/' + profile_id + '/approve', json=approve_payload)
            assert denied.status_code == 403
            _login(client, 'reviewer')
            approved_profile = _post(client, '/configurations/' + profile_id + '/approve', approve_payload)
            assert approved_profile['status'] == 'approved' and approved_profile['version'] == 3
            assert approved_profile['approval_version'] == 3
            assert approved_profile['approved_employee_id'] == identities['reviewer'][1]

            _login(client)
            rules = _post(client, '/rule-sets', {'request_id': str(uuid4()), 'source_id': source['source_id'],
                'definition': {'label': 'Synthetic native rule', 'form_key': 'synthetic-native', 'valid_from': '2026-01-01',
                    'rules': [{'rule_id': 'synthetic-only', 'label': 'Synthetic presence check', 'severity': 'review',
                        'message': 'Synthetic check only', 'source': {'document_title': 'Synthetic policy',
                            'version': '1', 'page': '1', 'sha256': source['sha256']},
                        'assertion': {'kind': 'field', 'field': 'sample', 'operator': 'not_blank'}}]}}, expected=201)
            rule_id = rules['config_id']
            rules = _post(client, '/configurations/' + rule_id + '/impact', {'report_ids': [report_id]})
            assert rules['impact']['tested_opportunities'] == 1 and rules['impact']['can_approve'] is True
            _login(client, 'reviewer')
            approved_rules = _post(client, '/configurations/' + rule_id + '/approve', approve_payload)
            assert approved_rules['status'] == 'approved' and approved_rules['version'] == 3
            _login(client)
            saved = _get_report(client, report_id)
            saved = _post(client, '/revisions/' + revision_id + '/checks', {'expected_version': saved['version'],
                'rule_set_id': rule_id, 'mode': 'approved', 'as_of': '2026-01-01'})
            run_id = saved['last_run']['run_id']
            assert saved['last_run']['approval'] == 'APPROVED_RULE'
            assert saved['last_run']['findings'][0]['status'] == 'NO_ISSUE_DETECTED'
            event_id = str(uuid4())
            saved = _post(client, '/reports/' + report_id + '/events', {'event_id': event_id,
                'expected_version': saved['version'], 'kind': 'submitted',
                'payload': {'occurred_at': datetime.now(timezone.utc).isoformat()}})

            # Direct SQL cannot rewrite any private original/history, even when
            # a config mutation also attempts the required version increment.
            for table, key, identity, mutation in [
                ('emergency_audit_sources', 'source_id', source['source_id'], "source_sha256=repeat('f',64)"),
                ('emergency_audit_runs', 'run_id', run_id, "payload_cipher=decode('00','hex')"),
                ('emergency_audit_events', 'event_id', event_id, "payload='{}'::json"),
                ('emergency_audit_configurations', 'config_id', profile_id, "definition_cipher=decode('00','hex'), version=version+1"),
                ('emergency_audit_revisions', 'revision_id', revision_id, "source_sha256=repeat('f',64)"),
            ]:
                _rejected_sql(target, 'UPDATE ' + table + ' SET ' + mutation + ' WHERE ' + key + '=:identity', identity)
                _rejected_sql(target, 'DELETE FROM ' + table + ' WHERE ' + key + '=:identity', identity)
            with factory() as db:
                assert db.get(AuditConfiguration, profile_id).status == 'approved'
                assert db.get(AuditConfiguration, profile_id).version == 3
                assert db.get(AuditEvent, event_id).kind == 'submitted'
                assert db.get(AuditSource, source['source_id']).source_sha256 == source['sha256']
                assert vault.open_json('run', run_id, db.get(AuditRun, run_id).payload_cipher)['approval'] == 'APPROVED_RULE'

            # A replacement revision arriving while native reading runs must
            # keep the superseded worker from publishing stale fields.
            second = _upload(client, _pdf('SYNTHETIC_SECOND_REVISION'), profile_id, report=saved)
            second_revision_id = second['current_revision_id']
            started = Event(); release = Event()
            def delayed_reader(mode, data, **kwargs):
                started.set()
                assert release.wait(20), 'synthetic replacement release timed out'
                return _reading(mode, data, **kwargs)
            with ThreadPoolExecutor(max_workers=1) as pool:
                future = pool.submit(process_one, session_factory=factory, worker_id=str(uuid4()), executor=delayed_reader)
                try:
                    assert started.wait(10)
                    third = _upload(client, _pdf('SYNTHETIC_THIRD_REVISION'), profile_id, report=second)
                finally:
                    release.set()
                assert future.result(timeout=30) is True
            with factory() as db:
                assert db.get(AuditReport, report_id).current_revision_id == third['current_revision_id']
                assert db.get(AuditRevision, second_revision_id).reading_cipher is None
                old_job = db.scalar(select(AuditJob).where(AuditJob.revision_id == second_revision_id))
                assert old_job.status == 'cancelled'
                assert db.get(AuditRevision, revision_id).fields_cipher is not None
            assert process_one(session_factory=factory, worker_id=str(uuid4()), executor=_reading)
            saved = _get_report(client, report_id)
            third_revision_id = saved['current_revision_id']
            assert saved['revision']['processing_status'] == 'ready'

            # A human confirmation invalidates the exact field version used by
            # an in-flight AI candidate job. The new fact must remain intact.
            queued = _post(client, '/revisions/' + third_revision_id + '/ai', {'expected_version': saved['version']})
            started = Event(); release = Event()
            def delayed_ai(mode, data, **kwargs):
                assert mode == 'ai'; started.set()
                assert release.wait(20), 'synthetic AI release timed out'
                return {'status': 'NOT_CONFIGURED', 'candidates': []}
            with ThreadPoolExecutor(max_workers=1) as pool:
                future = pool.submit(process_one, session_factory=factory, worker_id=str(uuid4()), executor=delayed_ai)
                try:
                    assert started.wait(10)
                    confirmed = _post(client, '/revisions/' + third_revision_id + '/fields', {
                        'expected_version': queued['version'], 'confirmed_from_original': True,
                        'fields': [{'field_id': 'sample', 'state': 'confirmed', 'value': 'Synthetic current confirmed fact'}]})
                finally:
                    release.set()
                assert future.result(timeout=30) is True
            with factory() as db:
                revision = db.get(AuditRevision, third_revision_id)
                assert revision.version == 3 and revision.ai_cipher is None
                assert db.get(AuditReport, report_id).version == confirmed['version']
                assert vault.open_json('fields', third_revision_id, revision.fields_cipher)['sample']['value'] == 'Synthetic current confirmed fact'
                ai_job = db.scalar(select(AuditJob).where(AuditJob.revision_id == third_revision_id, AuditJob.kind == 'ai'))
                assert ai_job.status == 'cancelled' and ai_job.error_code == 'STALE_REVISION'
                logs = db.scalars(select(AuditLog).where(AuditLog.action.like('emergency.audit.%'))).all()
                assert 'SYNTHETIC_REPORT_PRIVATE_123' not in str([item.after_data for item in logs])
                assert db.scalar(select(func.count()).select_from(Document)) == 0

            # The approved source/config record remains immutable after an
            # explicit retirement; this transition uses native config triggers.
            _login(client, 'reviewer')
            retired = _post(client, '/configurations/' + rule_id + '/retire', {'expected_version': 3})
            assert retired['status'] == 'retired' and retired['version'] == 4 and retired['approval_version'] == 3
            _rejected_sql(target, "UPDATE emergency_audit_configurations SET status='approved', version=version+1 WHERE config_id=:identity", rule_id)
    finally:
        app.dependency_overrides.clear()
        app.dependency_overrides.update(previous_overrides)
        if target is not None:
            target.dispose()
        if database_created:
            with admin.connect() as connection:
                connection.exec_driver_sql('DROP DATABASE IF EXISTS ' + name + ' WITH (FORCE)')
        admin.dispose()
