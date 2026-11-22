"""Export authorization uses real sessions, scoped vault data and immutable runs."""
from copy import deepcopy
from datetime import timedelta
import json
from uuid import uuid4

import pymupdf as fitz
import pytest
from sqlalchemy import select

# Select the synthetic database before importing application modules.
from test_emergency_audit_api import P, client, create_profile, login, pdf, process_read, upload

from app import emergency_audit_service as svc, emergency_vault as vault
from app.db import SessionLocal
from app.emergency_audit_models import AuditConfiguration, AuditEvent, AuditReport, AuditRevision, AuditRun
from app.models import AuditLog, Employee, Permission, RolePermission, User, UserRole, UserSession, now_utc


def grant_export(who='owner'):
    with SessionLocal() as db:
        permission = db.scalar(select(Permission).where(Permission.code == 'emergency.report.export'))
        if permission is None:
            permission = Permission(code='emergency.report.export'); db.add(permission); db.flush()
        user = db.scalar(select(User).where(User.username == 'audit-' + who))
        role = db.scalar(select(UserRole.role_id).where(UserRole.user_id == user.user_id))
        db.add(RolePermission(role_id=role, permission_id=permission.permission_id)); db.commit()


def checked_report(client):
    profile = create_profile(client)
    saved = upload(client, profile_id=profile['config_id']).json(); process_read()
    saved = client.get(P + '/reports/' + saved['report_id']).json()
    response = client.post(P + '/revisions/' + saved['current_revision_id'] + '/checks', json={
        'expected_version': saved['version'], 'as_of': '2026-11-22', 'mode': 'candidate'})
    assert response.status_code == 200, response.text
    return response.json(), profile


def export(client, saved, **changes):
    return client.post(P + '/reports/' + saved['report_id'] + '/annotated-pdf', json={
        'run_id': saved['last_run']['run_id'], 'expected_version': saved['version'], **changes})


def pdf_text(response):
    with fitz.open(stream=response.content, filetype='pdf') as doc:
        return '\n'.join(page.get_text() for page in doc)


def revoke(code):
    with SessionLocal() as db:
        permission = db.scalar(select(Permission).where(Permission.code == code))
        owner = db.scalar(select(User).where(User.username == 'audit-owner'))
        roles = list(db.scalars(select(UserRole.role_id).where(UserRole.user_id == owner.user_id)))
        for row in db.scalars(select(RolePermission).where(RolePermission.role_id.in_(roles),
                RolePermission.permission_id == permission.permission_id)): db.delete(row)
        db.commit()


def test_current_run_exports_private_attachment_and_never_changes_original_or_report_version(client):
    saved, _ = checked_report(client); grant_export()
    revision = saved['current_revision_id']
    original = client.get(P + '/revisions/' + revision + '/original').content
    response = export(client, saved)
    assert response.status_code == 200, response.text
    assert response.headers['content-type'] == 'application/pdf'
    assert response.headers['content-disposition'] == 'attachment; filename="emergency-review.pdf"'
    assert response.headers['cache-control'] == 'no-store' and response.headers['x-content-type-options'] == 'nosniff'
    assert '訂正確認用' in pdf_text(response) and '未検査' in pdf_text(response)
    assert client.get(P + '/revisions/' + revision + '/original').content == original
    assert client.get(P + '/reports/' + saved['report_id']).json()['version'] == saved['version']
    with SessionLocal() as db:
        logs = list(db.scalars(select(AuditLog).where(AuditLog.action == 'emergency.audit.pdf_export')))
        assert len(logs) == 1 and 'SYNTHETIC ONLY' not in json.dumps(logs[0].after_data)


@pytest.mark.parametrize('code', ['emergency.report.export', 'emergency.report.read', 'emergency.patient.read', 'emergency.case.read'])
def test_export_requires_all_private_read_rights_and_export_permission(client, code):
    saved, _ = checked_report(client); grant_export(); revoke(code)
    assert export(client, saved).status_code == 403


def test_export_requires_current_employee_report_scope_and_non_cross_site_request(client):
    saved, _ = checked_report(client); grant_export('outsider'); login(client, 'outsider')
    assert export(client, saved).status_code == 404
    login(client); grant_export()
    response = client.post(P + '/reports/' + saved['report_id'] + '/annotated-pdf', json={
        'run_id': saved['last_run']['run_id'], 'expected_version': saved['version']}, headers={'Origin': 'https://outside.invalid'})
    assert response.status_code == 403


@pytest.mark.parametrize('change', ['report_version', 'revision_version', 'current_revision', 'latest_run',
    'other_report', 'retired_profile', 'retired_rules', 'approved_profile', 'approved_rules', 'source_hash'])
def test_stale_latest_source_or_configuration_blocks_export(client, change):
    saved, profile = checked_report(client); grant_export()
    with SessionLocal() as db:
        report = db.get(AuditReport, saved['report_id']); revision = db.get(AuditRevision, report.current_revision_id)
        run = db.get(AuditRun, saved['last_run']['run_id'])
        if change == 'report_version': report.version += 1
        elif change == 'revision_version': revision.version += 1
        elif change == 'current_revision': report.current_revision_id = str(uuid4())
        elif change == 'source_hash': revision.source_sha256 = 'f' * 64
        elif change == 'latest_run':
            replacement = AuditRun(run_id=str(uuid4()), report_id=report.report_id, revision_id=revision.revision_id,
                revision_version=revision.version, report_version=report.version, mode='candidate',
                payload_cipher=run.payload_cipher, created_by=report.owner_id, created_at=now_utc() + timedelta(seconds=1))
            db.add(replacement)
        elif change == 'other_report': run.report_id = str(uuid4())
        elif change == 'retired_profile': db.get(AuditConfiguration, profile['config_id']).status = 'retired'
        else:
            identity = str(uuid4())
            config = AuditConfiguration(config_id=identity, request_id=str(uuid4()), request_sha256='0'*64,
                kind='rules', label='Synthetic', form_key='synthetic-v1', status='approved',
                definition_cipher=vault.seal_json('config', identity, {}), created_by=report.owner_id)
            db.add(config); db.flush(); run.rule_set_id = identity
            if change == 'retired_rules': config.status = 'retired'
            else:
                run.mode = 'approved'
                db.get(AuditConfiguration, profile['config_id']).status = 'approved' if change == 'approved_rules' else 'draft'
                config.status = 'draft' if change == 'approved_rules' else 'approved'
        db.commit()
    response = export(client, saved)
    assert response.status_code == 409, response.text
    assert response.headers['content-type'].startswith('application/json')


@pytest.mark.parametrize('change,status', [('export_permission', 403), ('read_permission', 403), ('session', 401),
    ('employee_disabled', 403), ('employee_reassigned', 403), ('password', 403), ('scope', 404),
    ('version', 409), ('revision', 409), ('latest_run', 409), ('config_version', 409), ('config_retired', 409)])
def test_generation_rechecks_authority_and_frozen_context_before_returning_private_pdf(client, monkeypatch, change, status):
    from app.routers import emergency_audit as routes
    saved, profile = checked_report(client); grant_export()
    isolated = routes._isolated; rendered = []
    def render_then_change(mode, data, **kwargs):
        assert mode == 'review_pdf'
        result = isolated(mode, data, **kwargs); rendered.append(result)
        if change in {'export_permission', 'read_permission'}:
            revoke('emergency.report.export' if change == 'export_permission' else 'emergency.patient.read')
        else:
            with SessionLocal() as db:
                owner = db.scalar(select(User).where(User.username == 'audit-owner'))
                report = db.get(AuditReport, saved['report_id'])
                if change == 'session':
                    for session in db.scalars(select(UserSession).where(UserSession.user_id == owner.user_id)):
                        session.revoked_at = now_utc()
                elif change == 'employee_disabled': db.get(Employee, owner.employee_id).active = False
                elif change == 'employee_reassigned':
                    employee = Employee(display_name='Synthetic replacement'); db.add(employee); db.flush(); owner.employee_id = employee.employee_id
                elif change == 'password': owner.password_expires_at = now_utc() - timedelta(seconds=1)
                elif change == 'scope': report.owner_employee_id = str(uuid4())
                elif change == 'version': report.version += 1
                elif change == 'revision': db.get(AuditRevision, report.current_revision_id).version += 1
                elif change == 'latest_run':
                    run = db.get(AuditRun, saved['last_run']['run_id'])
                    db.add(AuditRun(report_id=report.report_id, revision_id=run.revision_id,
                        revision_version=run.revision_version, report_version=report.version, mode='candidate',
                        payload_cipher=run.payload_cipher, created_by=owner.user_id, created_at=now_utc() + timedelta(seconds=1)))
                elif change == 'config_retired': db.get(AuditConfiguration, profile['config_id']).status = 'retired'
                else: db.get(AuditConfiguration, profile['config_id']).version += 1
                db.commit()
        return result
    monkeypatch.setattr(routes, '_isolated', render_then_change)
    response = export(client, saved)
    assert rendered and rendered[0].startswith(b'%PDF-')
    assert response.status_code == status, response.text
    assert response.headers['cache-control'] == 'no-store' and response.headers['content-type'].startswith('application/json')
    assert response.content != rendered[0]


def test_export_uses_only_frozen_same_run_fields_findings_and_active_dispositions(client, monkeypatch):
    saved, _ = checked_report(client); grant_export()
    with SessionLocal() as db:
        run = db.get(AuditRun, saved['last_run']['run_id']); parent = db.get(AuditReport, saved['report_id'])
        body = vault.open_json('run', run.run_id, run.payload_cipher)
        body['findings'] = [{'rule_id': 'SYN-SAME-RUN', 'status': 'REVIEW_REQUIRED', 'message': 'SAME_RUN_MESSAGE',
            'fields': ['a'], 'source_reference': 'Synthetic source', 'rule_approval': 'PROVISIONAL_NOT_APPROVED'}]
        body['input_fields']['a']['label'] = 'SAME_RUN_LABEL'
        body['input_fields']['a']['value'] = 'VALUE_MUST_NOT_EXPORT'
        body['unsafe_extra'] = 'UNALLOWLISTED_SECRET'
        run.payload_cipher = vault.seal_json('run', run.run_id, body)
        previous_id = str(uuid4()); old = deepcopy(body)
        old['findings'][0]['message'] = 'HISTORIC_RUN_SECRET'
        db.add(AuditRun(run_id=previous_id, report_id=run.report_id, revision_id=run.revision_id,
            revision_version=run.revision_version, report_version=run.report_version, mode='ai',
            payload_cipher=vault.seal_json('run', previous_id, old), created_by=parent.owner_id,
            created_at=run.created_at - timedelta(seconds=1)))
        revision = db.get(AuditRevision, run.revision_id)
        revision.fields_cipher = vault.seal_json('fields', revision.revision_id, {'a': {'label': 'CURRENT_FIELDS_SECRET'}})
        revision.ai_cipher = vault.seal_json('ai', revision.revision_id, {'candidates': [{'reason': 'CURRENT_AI_SECRET'}]})
        replaced_id = str(uuid4())
        for identity, run_id, decision, supersedes in [(replaced_id, run.run_id, 'false_alarm', None),
            (str(uuid4()), run.run_id, 'correction_needed', replaced_id), (str(uuid4()), previous_id, 'exception', None)]:
            db.add(AuditEvent(event_id=identity, report_id=parent.report_id, kind='dispositions', supersedes_id=supersedes,
                request_sha256='0'*64, actor_id=parent.owner_id, actor_employee_id=parent.owner_employee_id,
                payload={'run_id': run_id, 'decisions': [{'rule_id': 'SYN-SAME-RUN', 'decision': decision, 'reason_code': 'missing'}]}))
        db.commit()
    monkeypatch.setattr(svc, 'output', lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError('whole history must not reach export')))
    response = export(client, saved)
    assert response.status_code == 200, response.text
    text = pdf_text(response)
    assert 'SAME_RUN_MESSAGE' in text and 'SAME_RUN_LABEL' in text and '要修正（担当者確認）' in text
    for forbidden in ('HISTORIC_RUN_SECRET', 'CURRENT_FIELDS_SECRET', 'CURRENT_AI_SECRET', 'UNALLOWLISTED_SECRET', 'VALUE_MUST_NOT_EXPORT'):
        assert forbidden not in text
    assert '誤警告として確認' not in text and '例外として確認' not in text


def test_ai_candidate_export_omits_generated_correct_answers_and_does_not_invent_coordinates(client):
    saved, _ = checked_report(client); grant_export()
    with SessionLocal() as db:
        run = db.get(AuditRun, saved['last_run']['run_id']); run.mode = 'ai'
        body = vault.open_json('run', run.run_id, run.payload_cipher)
        body['findings'] = [{'rule_id': 'AI-SYN', 'status': 'REVIEW_REQUIRED', 'message': 'SYNTHETIC_AI_REASON',
            'fields': [], 'source_reference': 'Synthetic page 1', 'origin': 'ai',
            'evidence': {'page': 1, 'quote': 'SYNTHETIC', 'reason': 'SYNTHETIC_AI_REASON',
                'state': 'unconfirmed', 'suggested_text': 'GENERATED_ANSWER_MUST_NOT_EXPORT'}}]
        run.payload_cipher = vault.seal_json('run', run.run_id, body); db.commit()
    response = export(client, saved)
    assert response.status_code == 200, response.text
    text = pdf_text(response)
    assert 'AI文章確認' in text and 'AI候補（未確認）' in text and '位置未特定' in text
    assert 'GENERATED_ANSWER_MUST_NOT_EXPORT' not in text


@pytest.mark.parametrize('code,status', [('PDF_OUTPUT_LIMIT', 413), ('PDF_APPENDIX_LIMIT', 413),
    ('PROCESS_OUTPUT_LIMIT', 413), ('PROCESS_TIMEOUT', 503), ('TOTAL_TIMEOUT', 503),
    ('PDF_FONT_UNAVAILABLE', 503), ('PROCESS_PLATFORM_UNSUPPORTED', 503), ('PDF_PLAN_INVALID', 422)])
def test_pdf_export_returns_whole_failure_with_safe_limit_or_unavailable_status(client, monkeypatch, code, status):
    from app import emergency_audit_worker as worker
    saved, _ = checked_report(client); grant_export()
    def unavailable(mode, data, **kwargs):
        assert mode == 'review_pdf'
        raise worker.WorkerError(code)
    monkeypatch.setattr(worker, 'run_isolated', unavailable)
    response = export(client, saved)
    assert response.status_code == status, response.text
    assert response.headers['content-type'].startswith('application/json')
    assert response.headers['cache-control'] == 'no-store'
    assert isinstance(response.json()['detail'], str) and not response.content.startswith(b'%PDF-')
    with SessionLocal() as db:
        assert db.scalar(select(AuditLog).where(AuditLog.action == 'emergency.audit.pdf_export')) is None
