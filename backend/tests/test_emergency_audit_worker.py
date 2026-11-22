"""Private worker lifecycle and real isolated-reader tests, synthetic originals only."""
from datetime import timedelta
from hashlib import sha256
from importlib import import_module
from io import BytesIO
import json
import shutil
from pathlib import Path
import sys
from threading import Event
from uuid import uuid4

import pymupdf as fitz
from PIL import Image
import pytest
from sqlalchemy import create_engine, event, select
from sqlalchemy.orm import sessionmaker


def worker():
    return import_module('app.emergency_audit_worker')


def source():
    with fitz.open() as document:
        page = document.new_page(width=400, height=200)
        page.insert_text((40, 40), 'SYNTHETIC 123', fontsize=12)
        return document.tobytes()


@pytest.fixture
def environment(tmp_path, monkeypatch):
    from app import bootstrap  # registers all shared foreign-key targets
    from app.db import Base, BoundSession
    from app.emergency_audit_models import AuditConfiguration, AuditJob, AuditReport, AuditRevision
    from app.emergency_vault import seal_json, store_original
    from app.models import Employee, Permission, Role, RolePermission, User, UserRole
    from app.settings import settings
    monkeypatch.setattr(settings, 'emergency_audit_enabled', True)
    monkeypatch.setattr(settings, 'emergency_audit_internal_enabled', False)
    monkeypatch.setattr(settings, 'tenant_id', None)
    monkeypatch.setattr(settings, 'production_mode', False)
    monkeypatch.setattr(settings, 'storage_root', str(tmp_path / 'storage'))
    key = tmp_path / 'private.key'; key.write_bytes(b's' * 32); key.chmod(0o600)
    monkeypatch.setattr(settings, 'emergency_audit_key_file', str(key))
    engine = create_engine('sqlite+pysqlite:///' + str(tmp_path / 'worker.db'))
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, class_=BoundSession, expire_on_commit=False)
    raw = source(); identities = {'raw': raw, 'factory': factory, 'engine': engine}
    with factory() as db:
        employee = Employee(display_name='Synthetic worker'); role = Role(code='worker-synthetic', name='Synthetic')
        db.add_all([employee, role]); db.flush()
        actor = User(username='synthetic-worker', employee_id=employee.employee_id, password_hash='not-used-for-login')
        db.add(actor); db.flush(); db.add(UserRole(user_id=actor.user_id, role_id=role.role_id))
        for code in ('emergency.case.read', 'emergency.patient.read', 'emergency.report.read', 'emergency.report.create'):
            permission = Permission(code=code); db.add(permission); db.flush()
            db.add(RolePermission(role_id=role.role_id, permission_id=permission.permission_id))
        profile_id = str(uuid4())
        definition = {'label': 'Synthetic mapping', 'form_key': 'synthetic', 'valid_from': '2026-01-01', 'fields': [
            {'field_id': 'sample', 'label': 'Synthetic value', 'value_type': 'text', 'page': 1,
             'bbox': [0.0, 0.0, 1.0, 1.0], 'extraction': 'region', 'unit': 'unit', 'phase': 'initial'}]}
        config = AuditConfiguration(config_id=profile_id, request_id=str(uuid4()), request_sha256='0'*64,
            kind='profile', label='Synthetic mapping', form_key='synthetic', status='approved',
            definition_cipher=seal_json('config', profile_id, definition), created_by=actor.user_id)
        report = AuditReport(request_id=str(uuid4()), request_sha256='0'*64,
            owner_id=actor.user_id, owner_employee_id=employee.employee_id, dataset_kind='synthetic')
        db.add_all([config, report]); db.flush()
        revision = AuditRevision(report_id=report.report_id, number=1, request_id=str(uuid4()), request_sha256='0'*64,
            source_sha256=sha256(raw).hexdigest(), media_type='application/pdf', size_bytes=len(raw), page_count=1,
            profile_id=profile_id, created_by=actor.user_id)
        db.add(revision); db.flush(); report.current_revision_id = revision.revision_id
        job = AuditJob(revision_id=revision.revision_id, kind='read', source_sha256=revision.source_sha256,
            revision_version=1, requested_by=actor.user_id, requested_employee_id=employee.employee_id)
        db.add(job); db.flush(); store_original('revision', revision.revision_id, raw); db.commit()
        identities.update(report=report.report_id, revision=revision.revision_id, job=job.job_id,
                          user=actor.user_id, employee=employee.employee_id, profile=profile_id)
    yield identities
    engine.dispose()


def extract(mode, data, **kwargs):
    from app.emergency_reader import extract_source
    assert mode == 'read'
    return extract_source(data)


def test_read_publishes_encrypted_evidence_and_mapping_once_without_holding_transaction(environment):
    w = worker(); env = environment
    from app.emergency_audit_models import AuditJob, AuditReport, AuditRevision, AuditWorkerHeartbeat
    from app.emergency_vault import open_json
    from app.models import AuditLog
    checked_out = set()
    event.listen(env['engine'], 'checkout', lambda connection, record, proxy: checked_out.add(id(connection)))
    event.listen(env['engine'], 'checkin', lambda connection, record: checked_out.discard(id(connection)))
    def executor(mode, data, **kwargs):
        assert checked_out == set()
        return extract(mode, data, **kwargs)
    identity = str(uuid4())
    assert w.process_one(session_factory=env['factory'], worker_id=identity, executor=executor) is True
    assert w.process_one(session_factory=env['factory'], worker_id=identity, executor=executor) is False
    with env['factory']() as db:
        job, revision, report = (db.get(model, env[key]) for model, key in
            ((AuditJob, 'job'), (AuditRevision, 'revision'), (AuditReport, 'report')))
        assert job.status == 'done' and job.attempts == 1 and job.lease_token is None
        assert revision.processing_status == 'ready' and revision.version == 2 and report.version == 2
        assert b'SYNTHETIC' not in revision.reading_cipher
        reading = open_json('reading', revision.revision_id, revision.reading_cipher)
        assert 'SYNTHETIC 123' in reading['pages'][0]['text']
        fields = open_json('fields', revision.revision_id, revision.fields_cipher)
        assert fields['sample']['candidate'] == 'SYNTHETIC 123'
        assert fields['sample']['value'] is None and fields['sample']['state'] == 'unconfirmed'
        assert {k: fields['sample'][k] for k in ('label', 'value_type', 'unit', 'phase')} == {
            'label': 'Synthetic value', 'value_type': 'text', 'unit': 'unit', 'phase': 'initial'}
        assert db.get(AuditWorkerHeartbeat, identity) is not None
        logs = db.scalars(select(AuditLog)).all()
        assert 'SYNTHETIC 123' not in json.dumps([row.after_data for row in logs])


def test_live_lease_prevents_a_second_worker_from_processing_same_job(environment):
    w = worker(); env = environment
    def executor(mode, data, **kwargs):
        assert w.process_one(session_factory=env['factory'], executor=extract) is False
        return extract(mode, data, **kwargs)
    assert w.process_one(session_factory=env['factory'], executor=executor) is True


def test_restart_recovers_expired_lease_and_consumes_next_attempt(environment):
    w = worker(); env = environment
    from app.emergency_audit_models import AuditJob
    from app.models import now_utc
    with env['factory']() as db:
        job = db.get(AuditJob, env['job']); job.status = 'processing'; job.attempts = 1
        job.lease_token = str(uuid4()); job.lease_until = now_utc() - timedelta(seconds=1); db.commit()
    assert w.process_one(session_factory=env['factory'], executor=extract) is True
    with env['factory']() as db:
        job = db.get(AuditJob, env['job']); assert (job.status, job.attempts) == ('done', 2)


def test_transient_failure_is_bounded_to_three_attempts_and_safe(environment, caplog, capsys):
    w = worker(); env = environment
    from app.emergency_audit_models import AuditJob, AuditRevision
    def executor(*args, **kwargs):
        raise w.WorkerError('PROCESS_TIMEOUT')
    for _ in range(3): assert w.process_one(session_factory=env['factory'], executor=executor) is True
    assert w.process_one(session_factory=env['factory'], executor=executor) is False
    with env['factory']() as db:
        job = db.get(AuditJob, env['job']); revision = db.get(AuditRevision, env['revision'])
        assert (job.status, job.attempts, job.error_code) == ('failed', 3, 'PROCESS_TIMEOUT')
        assert revision.processing_status == 'failed' and revision.reading_cipher is None
    assert 'Traceback' not in capsys.readouterr().err + caplog.text


@pytest.mark.parametrize('change', ['permission', 'employee', 'actor_identity', 'revision', 'head', 'cancel', 'lease', 'source'])
def test_changed_authority_or_source_cannot_publish_stale_reading(environment, change):
    w = worker(); env = environment
    from app.emergency_audit_models import AuditJob, AuditReport, AuditRevision
    from app.models import Employee, Permission, RolePermission, User
    def executor(mode, data, **kwargs):
        with env['factory']() as db:
            if change == 'permission':
                permission = db.scalar(select(Permission).where(Permission.code == 'emergency.patient.read'))
                for row in db.scalars(select(RolePermission).where(RolePermission.permission_id == permission.permission_id)): db.delete(row)
            elif change == 'employee': db.get(Employee, env['employee']).active = False
            elif change == 'actor_identity': db.get(User, env['user']).employee_id = None
            elif change == 'revision': db.get(AuditRevision, env['revision']).version += 1
            elif change == 'head': db.get(AuditReport, env['report']).current_revision_id = str(uuid4())
            elif change == 'cancel': db.get(AuditJob, env['job']).status = 'cancelled'
            elif change == 'lease': db.get(AuditJob, env['job']).lease_token = str(uuid4())
            elif change == 'source': db.get(AuditRevision, env['revision']).source_sha256 = 'f'*64
            db.commit()
        return extract(mode, data, **kwargs)
    assert w.process_one(session_factory=env['factory'], executor=executor) is True
    with env['factory']() as db:
        assert db.get(AuditRevision, env['revision']).reading_cipher is None
        assert db.get(AuditJob, env['job']).status != 'done'


def test_independent_report_event_version_does_not_cancel_unchanged_reading(environment):
    w = worker(); env = environment
    from app.emergency_audit_models import AuditReport, AuditRevision
    def executor(mode, data, **kwargs):
        with env['factory']() as db:
            db.get(AuditReport, env['report']).version = 8; db.commit()
        return extract(mode, data, **kwargs)
    assert w.process_one(session_factory=env['factory'], executor=executor) is True
    with env['factory']() as db:
        assert db.get(AuditReport, env['report']).version == 9
        assert db.get(AuditRevision, env['revision']).processing_status == 'ready'


def test_modified_ciphertext_fails_without_processing_or_plaintext_logs(environment):
    w = worker(); env = environment
    from app.emergency_audit_models import AuditJob
    from app.settings import settings
    path = Path(settings.storage_root) / 'emergency-audit' / 'revision' / (env['revision'] + '.bin')
    data = bytearray(path.read_bytes()); data[-1] ^= 1; path.write_bytes(data)
    def forbidden(*args, **kwargs): raise AssertionError('corrupt source reached executor')
    assert w.process_one(session_factory=env['factory'], executor=forbidden) is True
    with env['factory']() as db:
        job = db.get(AuditJob, env['job']); assert job.status == 'failed'
        assert job.error_code == 'PRIVATE_CONTENT_INTEGRITY'


def test_ai_publish_preserves_reading_revision_and_cannot_approve_fact(environment):
    w = worker(); env = environment
    from app.emergency_audit_models import AuditJob, AuditReport, AuditRevision, AuditRun
    from app.emergency_vault import open_json
    assert w.process_one(session_factory=env['factory'], executor=extract)
    with env['factory']() as db:
        revision = db.get(AuditRevision, env['revision'])
        db.add(AuditJob(revision_id=revision.revision_id, kind='ai', source_sha256=revision.source_sha256,
            revision_version=revision.version, requested_by=env['user'], requested_employee_id=env['employee']))
        db.commit()
    def executor(mode, data, *, pages=None, **kwargs):
        assert mode == 'ai' and 'SYNTHETIC' in pages[0]['text']
        return {'status': 'NOT_CONFIGURED', 'candidates': []}
    assert w.process_one(session_factory=env['factory'], executor=executor)
    with env['factory']() as db:
        revision = db.get(AuditRevision, env['revision'])
        assert revision.version == 2 and revision.processing_status == 'ready'
        assert db.get(AuditReport, env['report']).version == 3
        assert open_json('ai', revision.revision_id, revision.ai_cipher)['status'] == 'NOT_CONFIGURED'
        assert db.scalar(select(AuditRun)) is None


def test_maintenance_refusal_does_not_claim_or_execute(environment):
    w = worker(); env = environment
    from app.department_maintenance import MaintenanceUnavailable
    from app.emergency_audit_models import AuditJob
    def unavailable(): raise MaintenanceUnavailable('Synthetic maintenance')
    def forbidden(*args, **kwargs): raise AssertionError('maintenance executed a job')
    with pytest.raises(MaintenanceUnavailable):
        w.process_one(session_factory=unavailable, executor=forbidden)
    with env['factory']() as db: assert db.get(AuditJob, env['job']).attempts == 0


def test_real_isolated_native_inspect_read_and_render_do_not_need_source_file():
    w = worker(); raw = source()
    assert w.run_isolated('inspect', raw) == {'media_type': 'application/pdf', 'page_count': 1}
    result = w.run_isolated('read', raw)
    assert result['pages'][0]['status'] == 'TEXT_EXTRACTED'
    assert 'SYNTHETIC 123' in result['pages'][0]['text']
    with Image.open(BytesIO(w.run_isolated('render', raw, page=1))) as image:
        assert image.size == (800, 400)


def test_isolation_timeout_kills_child_with_safe_code(monkeypatch):
    w = worker(); monkeypatch.setitem(w.MODE_TIMEOUTS, 'inspect', .001)
    with pytest.raises(w.WorkerError, match='PROCESS_TIMEOUT'):
        w.run_isolated('inspect', source())


def test_child_output_overflow_is_a_failure(monkeypatch):
    w = worker(); monkeypatch.setitem(w.OUTPUT_LIMITS, 'inspect', 8)
    with pytest.raises(w.WorkerError, match='PROCESS_OUTPUT_LIMIT'):
        w.run_isolated('inspect', source())


def test_malformed_child_output_never_becomes_success_or_echoes_input(monkeypatch, capsys):
    w = worker()
    monkeypatch.setattr(w, '_child_command', lambda: [sys.executable, '-c', "print('synthetic-private-sentinel')"])
    with pytest.raises(w.WorkerError, match='PROCESS_RESPONSE_INVALID') as caught:
        w.run_isolated('inspect', source())
    assert 'synthetic-private-sentinel' not in str(caught.value) + capsys.readouterr().err


def test_invalid_child_reading_cannot_publish(environment):
    w = worker(); env = environment
    from app.emergency_audit_models import AuditJob, AuditRevision
    assert w.process_one(session_factory=env['factory'], executor=lambda *a, **k: {'complete': True})
    with env['factory']() as db:
        assert db.get(AuditRevision, env['revision']).reading_cipher is None
        assert db.get(AuditJob, env['job']).error_code == 'PROCESS_RESPONSE_INVALID'


def test_long_job_heartbeat_uses_short_transactions_without_extending_lease(environment, monkeypatch):
    w = worker(); env = environment; identity = str(uuid4()); ticked = Event()
    from app.emergency_audit_models import AuditJob, AuditWorkerHeartbeat
    monkeypatch.setattr(w, 'HEARTBEAT_INTERVAL_SECONDS', .02)
    initial = {}
    def observed_tick(connection, cursor, statement, parameters, context, many):
        if statement.lstrip().upper().startswith('UPDATE EMERGENCY_AUDIT_WORKER_HEARTBEATS'):
            connection.info['synthetic_heartbeat_written'] = True
    def committed_tick(connection, record):
        if record.info.pop('synthetic_heartbeat_written', False): ticked.set()
    event.listen(env['engine'], 'after_cursor_execute', observed_tick)
    event.listen(env['engine'], 'checkin', committed_tick)
    def executor(mode, data, **kwargs):
        with env['factory']() as db:
            initial['seen'] = db.get(AuditWorkerHeartbeat, identity).seen_at
            initial['lease'] = db.get(AuditJob, env['job']).lease_until
        assert ticked.wait(2), 'long work must keep worker availability current'
        with env['factory']() as db:
            assert db.get(AuditWorkerHeartbeat, identity).seen_at > initial['seen']
            assert db.get(AuditJob, env['job']).lease_until == initial['lease']
        return extract(mode, data, **kwargs)
    assert w.process_one(session_factory=env['factory'], worker_id=identity, executor=executor)


def test_expired_old_worker_cannot_publish_and_recovery_uses_new_lease(environment):
    w = worker(); env = environment
    from app.emergency_audit_models import AuditJob, AuditRevision
    from app.models import now_utc
    def expires(mode, data, **kwargs):
        with env['factory']() as db:
            db.get(AuditJob, env['job']).lease_until = now_utc() - timedelta(seconds=1); db.commit()
        return extract(mode, data, **kwargs)
    assert w.process_one(session_factory=env['factory'], executor=expires)
    with env['factory']() as db:
        assert db.get(AuditRevision, env['revision']).reading_cipher is None
    assert w.process_one(session_factory=env['factory'], executor=extract)
    with env['factory']() as db:
        job = db.get(AuditJob, env['job']); assert (job.status, job.attempts) == ('done', 2)


def test_expired_third_attempt_is_terminal_without_fourth_execution(environment):
    w = worker(); env = environment
    from app.emergency_audit_models import AuditJob
    from app.models import now_utc
    with env['factory']() as db:
        job = db.get(AuditJob, env['job']); job.status = 'processing'; job.attempts = 3
        job.lease_token = str(uuid4()); job.lease_until = now_utc() - timedelta(seconds=1); db.commit()
    def forbidden(*args, **kwargs): raise AssertionError('fourth execution forbidden')
    assert w.process_one(session_factory=env['factory'], executor=forbidden)
    with env['factory']() as db:
        job = db.get(AuditJob, env['job']); assert (job.status, job.attempts) == ('failed', 3)


def test_partial_read_keeps_unavailable_page_and_never_reports_ready(environment):
    w = worker(); env = environment
    from app.emergency_audit_models import AuditRevision
    from app.emergency_vault import open_json
    def unreadable(mode, data, **kwargs):
        result = extract(mode, data)
        result.update(complete=False, issues=['OCR_LANGUAGE_UNAVAILABLE'])
        result['pages'][0].update(status='OCR_UNAVAILABLE', method='none', text='', words=[], issues=['OCR_LANGUAGE_UNAVAILABLE'])
        return result
    assert w.process_one(session_factory=env['factory'], executor=unreadable)
    with env['factory']() as db:
        revision = db.get(AuditRevision, env['revision']); assert revision.processing_status == 'partial'
        fields = open_json('fields', revision.revision_id, revision.fields_cipher)
        assert fields['sample']['state'] == 'unreadable' and fields['sample']['value'] is None


def test_revoked_scope_before_claim_never_decrypts_original(environment, monkeypatch):
    w = worker(); env = environment
    from app.emergency_audit_models import AuditJob, AuditReport
    with env['factory']() as db:
        db.get(AuditReport, env['report']).owner_employee_id = str(uuid4()); db.commit()
    def forbidden(*args, **kwargs): raise AssertionError('unauthorized source was opened')
    monkeypatch.setattr(w.vault, 'read_original', forbidden)
    assert w.process_one(session_factory=env['factory'], executor=forbidden)
    with env['factory']() as db:
        job = db.get(AuditJob, env['job']); assert (job.status, job.attempts) == ('cancelled', 0)


def test_profile_changed_during_extraction_cancels_old_mapping(environment):
    w = worker(); env = environment
    from app.emergency_audit_models import AuditConfiguration, AuditJob, AuditRevision
    def executor(mode, data, **kwargs):
        with env['factory']() as db:
            db.get(AuditConfiguration, env['profile']).version += 1; db.commit()
        return extract(mode, data)
    assert w.process_one(session_factory=env['factory'], executor=executor)
    with env['factory']() as db:
        assert db.get(AuditJob, env['job']).error_code == 'CONFIGURATION_CHANGED'
        assert db.get(AuditRevision, env['revision']).fields_cipher is None


def test_child_environment_drops_credentials_and_uses_private_temporary_folder(monkeypatch, tmp_path):
    w = worker()
    monkeypatch.setenv('FIRE_AI_DATABASE_URL', 'synthetic-private-credential')
    command = "import os,json,stat; good='FIRE_AI_DATABASE_URL' not in os.environ and stat.S_IMODE(os.stat(os.environ['TMPDIR']).st_mode)==448; print(json.dumps({'ok':True,'result':{'media_type':'application/pdf','page_count':1 if good else 2}}))"
    monkeypatch.setattr(w, '_child_command', lambda: [sys.executable, '-c', command])
    real_temp = w.tempfile.TemporaryDirectory
    monkeypatch.setattr(w.tempfile, 'TemporaryDirectory', lambda **kwargs: real_temp(dir=tmp_path, **kwargs))
    assert w.run_isolated('inspect', source())['page_count'] == 1
    assert list(tmp_path.iterdir()) == []


def test_vision_job_can_read_image_candidates_without_ocr_result(environment):
    w = worker(); env = environment
    from app.emergency_audit_models import AuditJob, AuditRevision, AuditRun
    from app.emergency_vault import open_json
    with env['factory']() as db:
        job = db.get(AuditJob, env['job']); job.kind = 'vision'; job.page_number = 1
        db.get(AuditRevision, env['revision']).processing_status = 'partial'; db.commit()
    def vision(mode, data, *, page=None, **kwargs):
        assert mode == 'vision' and data == env['raw'] and page == 1
        return {'status': 'REVIEW_REQUIRED', 'candidates': [
            {'page': 1, 'bbox': [.1, .1, .3, .2], 'text': 'Synthetic handwriting',
             'kind': 'handwritten', 'state': 'unconfirmed'}],
            'human_review_required': True, 'formal_decision': False, 'accuracy_measured': False,
            'width': 800, 'height': 400}
    assert w.process_one(session_factory=env['factory'], executor=vision)
    with env['factory']() as db:
        revision = db.get(AuditRevision, env['revision'])
        assert revision.version == 1 and revision.reading_cipher is None and revision.fields_cipher is None
        result = open_json('ai', revision.revision_id, revision.ai_cipher)
        assert result['mode'] == 'vision' and result['candidates'][0]['state'] == 'unconfirmed'
        assert result['formal_decision'] is False
        runs = db.scalars(select(AuditRun)).all()
        assert len(runs) == 1 and runs[0].mode == 'vision'


@pytest.mark.parametrize('changes', [
    {'page': 2}, {'bbox': [-.1, .1, .3, .2]}, {'state': 'confirmed'}, {'kind': 'diagnosis'},
])
def test_invalid_vision_provenance_cannot_publish(environment, changes):
    w = worker(); env = environment
    from app.emergency_audit_models import AuditJob, AuditRevision
    with env['factory']() as db:
        job = db.get(AuditJob, env['job']); job.kind = 'vision'; job.page_number = 1; db.commit()
    candidate = {'page': 1, 'bbox': [.1, .1, .3, .2], 'text': 'Synthetic',
                 'kind': 'handwritten', 'state': 'unconfirmed', **changes}
    def invalid(*args, **kwargs): return {'status': 'REVIEW_REQUIRED', 'candidates': [candidate]}
    assert w.process_one(session_factory=env['factory'], executor=invalid)
    with env['factory']() as db:
        assert db.get(AuditRevision, env['revision']).ai_cipher is None
        assert db.get(AuditJob, env['job']).error_code == 'PROCESS_RESPONSE_INVALID'


def test_real_vision_child_reports_not_configured_without_inventing_handwriting(monkeypatch):
    w = worker()
    monkeypatch.setattr(w.settings, 'emergency_audit_ai_model', None)
    result = w.run_isolated('vision', source(), page=1)
    assert result['status'] == 'NOT_CONFIGURED' and result['candidates'] == []
    assert result['mode'] == 'vision' and result['formal_decision'] is False


def test_text_ai_result_records_mode_without_changing_candidates(environment):
    w = worker(); env = environment
    from app.emergency_audit_models import AuditJob, AuditRevision, AuditRun
    from app.emergency_vault import open_json
    assert w.process_one(session_factory=env['factory'], executor=extract)
    with env['factory']() as db:
        revision = db.get(AuditRevision, env['revision'])
        db.add(AuditJob(revision_id=revision.revision_id, kind='ai', source_sha256=revision.source_sha256,
            revision_version=revision.version, requested_by=env['user'], requested_employee_id=env['employee']))
        db.commit()
    assert w.process_one(session_factory=env['factory'], executor=lambda *args, **kwargs: {'status': 'NO_CANDIDATE', 'candidates': []})
    with env['factory']() as db:
        revision = db.get(AuditRevision, env['revision'])
        assert open_json('ai', revision.revision_id, revision.ai_cipher)['mode'] == 'text'
        runs = db.scalars(select(AuditRun)).all()
        assert len(runs) == 1 and runs[0].mode == 'ai'


@pytest.mark.parametrize('kind', ['ai', 'vision'])
def test_baseline_cannot_receive_background_ai_assistance(environment, kind):
    w = worker(); env = environment
    from app.emergency_audit_models import AuditEvent, AuditJob, AuditRevision
    with env['factory']() as db:
        job = db.get(AuditJob, env['job']); job.kind = kind; job.page_number = 1 if kind == 'vision' else None
        db.add(AuditEvent(event_id=str(uuid4()), report_id=env['report'], kind='study', request_sha256='0'*64,
            payload={'cohort': 'baseline', 'activity_kind': 'unknown'}, actor_id=env['user'], actor_employee_id=env['employee']))
        db.commit()
    def forbidden(*args, **kwargs): raise AssertionError('baseline must not receive assistance')
    assert w.process_one(session_factory=env['factory'], executor=forbidden)
    with env['factory']() as db:
        assert db.get(AuditJob, env['job']).status == 'cancelled'
        assert db.get(AuditJob, env['job']).error_code == 'BASELINE_ASSISTANCE_BLOCKED'
        assert db.get(AuditRevision, env['revision']).ai_cipher is None


def test_native_ocr_inside_isolated_child_keeps_candidate_evidence_and_cleans_temp(monkeypatch, tmp_path):
    if not shutil.which('tesseract'): pytest.skip('native Tesseract unavailable')
    from PIL import ImageDraw, ImageFont
    w = worker(); picture = Image.new('RGB', (500, 160), 'white')
    ImageDraw.Draw(picture).text((15, 35), 'SYNTHETIC 123', fill='black', font=ImageFont.load_default(size=28))
    stream = BytesIO(); picture.save(stream, 'PNG'); picture.close()
    monkeypatch.setattr(w.settings, 'emergency_audit_ocr_language', 'eng')
    real_temp = w.tempfile.TemporaryDirectory
    monkeypatch.setattr(w.tempfile, 'TemporaryDirectory', lambda **kwargs: real_temp(dir=tmp_path, **kwargs))
    result = w.run_isolated('read', stream.getvalue())
    assert result['pages'][0]['status'] == 'OCR_CANDIDATE'
    assert 'SYNTHETIC' in result['pages'][0]['text']
    assert result['pages'][0]['words'][0]['confidence'] is not None
    assert list(tmp_path.iterdir()) == []


def test_native_parser_failure_cannot_print_private_content(monkeypatch, capfd):
    w = worker()
    with pytest.raises(w.WorkerError, match='SOURCE_INVALID'):
        w.run_isolated('inspect', b'%PDF-1.7\nSYNTHETIC_PRIVATE_SENTINEL\ninvalid xref')
    captured = capfd.readouterr()
    assert 'SYNTHETIC_PRIVATE_SENTINEL' not in captured.out + captured.err


def test_private_temporary_storage_failure_is_a_fixed_error(monkeypatch):
    w = worker()
    def unavailable(**kwargs): raise OSError('synthetic-private-storage-location')
    monkeypatch.setattr(w.tempfile, 'TemporaryDirectory', unavailable)
    with pytest.raises(w.WorkerError, match='PROCESS_FAILED') as caught:
        w.run_isolated('inspect', source())
    assert 'synthetic-private-storage-location' not in str(caught.value)


def test_non_posix_native_execution_fails_before_starting_process(monkeypatch):
    w = worker()
    monkeypatch.setattr(w, 'NATIVE_PLATFORM_SUPPORTED', False)
    def forbidden(*args, **kwargs): raise AssertionError('unsupported native process started')
    monkeypatch.setattr(w.subprocess, 'Popen', forbidden)
    with pytest.raises(w.WorkerError, match='PROCESS_PLATFORM_UNSUPPORTED'):
        w.run_isolated('inspect', source())


@pytest.mark.parametrize('kind', ['ai', 'vision'])
def test_exact_duplicate_ai_candidates_make_one_immutable_warning(environment, kind):
    w = worker(); env = environment
    from app.emergency_audit_models import AuditJob, AuditRevision, AuditRun
    from app.emergency_vault import open_json
    if kind == 'ai':
        assert w.process_one(session_factory=env['factory'], executor=extract)
        with env['factory']() as db:
            revision = db.get(AuditRevision, env['revision'])
            db.add(AuditJob(revision_id=revision.revision_id, kind='ai', source_sha256=revision.source_sha256,
                revision_version=revision.version, requested_by=env['user'], requested_employee_id=env['employee']))
            db.commit()
        candidate = {'page': 1, 'quote': 'SYNTHETIC', 'reason': 'Synthetic reason', 'state': 'unconfirmed'}
    else:
        with env['factory']() as db:
            job = db.get(AuditJob, env['job']); job.kind = 'vision'; job.page_number = 1; db.commit()
        candidate = {'page': 1, 'bbox': [.1, .1, .3, .2], 'text': 'Synthetic', 'kind': 'handwritten', 'state': 'unconfirmed'}
    def duplicate(*args, **kwargs):
        return {'status': 'REVIEW_REQUIRED', 'candidates': [candidate, dict(reversed(list(candidate.items())))]}
    assert w.process_one(session_factory=env['factory'], executor=duplicate)
    with env['factory']() as db:
        revision = db.get(AuditRevision, env['revision'])
        assert len(open_json('ai', revision.revision_id, revision.ai_cipher)['candidates']) == 1
        run = db.scalar(select(AuditRun).where(AuditRun.mode == kind))
        body = open_json('run', run.run_id, run.payload_cipher)
        warnings = [item for item in body['findings'] if item['status'] == 'REVIEW_REQUIRED']
        assert len(warnings) == 1
