"""Independent review regressions; synthetic originals and rules only."""
from uuid import uuid4

import pytest
from sqlalchemy import select

# Import the fixture first: it selects the isolated in-memory test database
# before importing app.db. Never let this file initialize a default dev DB.
from test_emergency_audit_api import P, client, create_profile, login, pdf, process_read, upload

from app.db import SessionLocal
from app.models import Employee, Permission, RolePermission, User, UserRole, UserSession, now_utc


def _post(client, path, body, status=200):
    response = client.post(P + path, json=body)
    assert response.status_code == status, response.text
    return response.json()


def _revoke(username, code):
    with SessionLocal() as db:
        user = db.scalar(select(User).where(User.username == username))
        permission = db.scalar(select(Permission).where(Permission.code == code))
        roles = list(db.scalars(select(UserRole.role_id).where(UserRole.user_id == user.user_id)))
        for row in db.scalars(select(RolePermission).where(RolePermission.role_id.in_(roles),
                                                        RolePermission.permission_id == permission.permission_id)):
            db.delete(row)
        db.commit()


def _profile_and_private_impact(client):
    profile = create_profile(client)
    saved = upload(client, profile_id=profile['config_id']).json()
    process_read()
    result = _post(client, '/configurations/' + profile['config_id'] + '/impact', {'report_ids': [saved['report_id']]})
    assert result['impact']['report_count'] == 1
    return profile, saved


def test_shared_impact_requires_management_right_even_if_private_report_is_owned(client):
    profile, saved = _profile_and_private_impact(client)
    _revoke('audit-owner', 'emergency.audit.configure')
    assert client.get(P + '/reports/' + saved['report_id']).status_code == 200
    for path in ('/profiles', '/configurations/' + profile['config_id']):
        response = client.get(P + path)
        assert response.status_code == 200, response.text
        result = response.json()[0] if isinstance(response.json(), list) else response.json()
        assert result['impact'] is None
        assert saved['report_id'] not in response.text and saved['current_revision_id'] not in response.text


def test_config_approver_losing_read_all_needs_current_employee_assignment_for_impact(client):
    profile, saved = _profile_and_private_impact(client)
    path = P + '/configurations/' + profile['config_id']
    login(client, 'reviewer')
    response = client.get(path)
    assert response.status_code == 200 and response.json()['impact']['report_count'] == 1
    _revoke('audit-reviewer', 'emergency.audit.read_all')
    response = client.get(path)
    assert response.status_code == 200 and response.json()['impact'] is None
    assert saved['report_id'] not in response.text
    with SessionLocal() as db:
        reviewer = db.scalar(select(User).where(User.username == 'audit-reviewer'))
        reviewer_id = reviewer.user_id
    login(client)
    current = client.get(P + '/reports/' + saved['report_id']).json()
    _post(client, '/reports/' + saved['report_id'] + '/reviewer', {
        'expected_version': current['version'], 'reviewer_id': reviewer_id})
    login(client, 'reviewer')
    response = client.get(path)
    assert response.status_code == 200 and response.json()['impact']['report_count'] == 1
    with SessionLocal() as db:
        employee = Employee(display_name='Synthetic replacement account holder')
        db.add(employee); db.flush()
        db.get(User, reviewer_id).employee_id = employee.employee_id
        db.commit()
    assert client.get(P + '/reports/' + saved['report_id']).status_code == 404
    response = client.get(path)
    assert response.status_code == 200 and response.json()['impact'] is None
    assert saved['report_id'] not in response.text


def test_retired_approved_profile_invalidates_existing_approved_run(client):
    response = client.post(P + '/sources', data={'request_id': str(uuid4())},
        files={'file': ('synthetic-policy.pdf', pdf('SYNTHETIC POLICY'), 'application/pdf')})
    assert response.status_code == 201, response.text
    source = response.json()
    profile = _post(client, '/profiles', {'request_id': str(uuid4()), 'source_id': source['source_id'],
        'definition': {'label': 'Synthetic approved profile', 'form_key': 'synthetic-reviewed',
            'valid_from': '2026-01-01', 'fields': [{'field_id': 'a', 'label': 'Synthetic text',
                'value_type': 'text', 'page': 1, 'bbox': [0.0, 0.0, 1.0, 1.0], 'extraction': 'region'}]}}, 201)
    saved = upload(client, profile_id=profile['config_id']).json(); process_read()
    saved = client.get(P + '/reports/' + saved['report_id']).json()
    revision_id, report_id = saved['current_revision_id'], saved['report_id']
    saved = _post(client, '/revisions/' + revision_id + '/fields', {
        'expected_version': saved['version'], 'confirmed_from_original': True,
        'fields': [{'field_id': 'a', 'state': 'confirmed', 'value': 'Synthetic verified'}]})
    impacted = _post(client, '/configurations/' + profile['config_id'] + '/impact', {'report_ids': [report_id]})
    login(client, 'reviewer')
    profile = _post(client, '/configurations/' + profile['config_id'] + '/approve', {
        'expected_version': impacted['version'], 'source_verified': True, 'mapping_verified': True})
    login(client)
    rules = _post(client, '/rule-sets', {'request_id': str(uuid4()), 'source_id': source['source_id'],
        'definition': {'label': 'Synthetic approved rule', 'form_key': 'synthetic-reviewed',
            'valid_from': '2026-01-01', 'rules': [{'rule_id': 'SYN-REVIEW', 'label': 'Synthetic presence',
                'message': 'Synthetic review', 'severity': 'review', 'source': {'document_title': 'Synthetic policy',
                    'version': '1', 'page': '1', 'sha256': source['sha256']},
                'assertion': {'kind': 'field', 'field': 'a', 'operator': 'not_blank'}}]}}, 201)
    impacted = _post(client, '/configurations/' + rules['config_id'] + '/impact', {'report_ids': [report_id]})
    login(client, 'reviewer')
    rules = _post(client, '/configurations/' + rules['config_id'] + '/approve', {
        'expected_version': impacted['version'], 'source_verified': True, 'mapping_verified': True})
    login(client)
    saved = client.get(P + '/reports/' + report_id).json()
    checked = _post(client, '/revisions/' + revision_id + '/checks', {'expected_version': saved['version'],
        'rule_set_id': rules['config_id'], 'mode': 'approved', 'as_of': '2026-01-01'})
    assert checked['last_run']['stale'] is False and checked['last_run']['approval'] == 'APPROVED_RULE'
    run_id = checked['last_run']['run_id']
    login(client, 'reviewer')
    retired = _post(client, '/configurations/' + profile['config_id'] + '/retire', {'expected_version': profile['version']})
    assert retired['status'] == 'retired'
    login(client)
    response = client.get(P + '/reports/' + report_id)
    assert response.status_code == 200, response.text
    saved = response.json()
    assert saved['last_run']['run_id'] == run_id and saved['last_run']['stale'] is True
    assert saved['initial_run']['stale'] is True
    # The immutable historic result remains available but cannot authorize a
    # new approved check after its mapping's approval has been withdrawn.
    blocked = client.post(P + '/revisions/' + revision_id + '/checks', json={
        'expected_version': saved['version'], 'rule_set_id': rules['config_id'],
        'mode': 'approved', 'as_of': '2026-01-01'})
    assert blocked.status_code == 409


@pytest.mark.parametrize('change,expected_status', [('permission', 403), ('employee', 404), ('session', 401)])
def test_render_rechecks_authority_before_returning_private_page(client, monkeypatch, change, expected_status):
    from app.routers import emergency_audit as routes
    saved = upload(client).json()
    original = routes._isolated
    rendered = []
    def render_then_revoke(mode, data, **kwargs):
        assert mode == 'render'
        result = original(mode, data, **kwargs)
        rendered.append(result)
        if change == 'permission':
            _revoke('audit-owner', 'emergency.patient.read')
        else:
            with SessionLocal() as db:
                owner = db.scalar(select(User).where(User.username == 'audit-owner'))
                if change == 'employee':
                    employee = Employee(display_name='Synthetic reassignment during render')
                    db.add(employee); db.flush(); owner.employee_id = employee.employee_id
                else:
                    for session in db.scalars(select(UserSession).where(UserSession.user_id == owner.user_id)):
                        session.revoked_at = now_utc()
                db.commit()
        return result
    monkeypatch.setattr(routes, '_isolated', render_then_revoke)
    response = client.get(P + '/revisions/' + saved['current_revision_id'] + '/pages/1.png')
    assert rendered and rendered[0].startswith(b'\x89PNG')
    assert response.status_code == expected_status, response.text
    assert response.headers['cache-control'] == 'no-store'
    assert response.headers['content-type'].startswith('application/json')
    assert response.content != rendered[0]
