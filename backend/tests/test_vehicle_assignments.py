"""Synthetic Human-recorded placement references, not verified original evidence."""
import json
from uuid import uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import AuditLog, Permission, RolePermission, User
from app.operations_models import Vehicle
from app.personnel import OrganizationUnit
from app.routers import operations
from test_learning import learning_environment


@pytest.fixture
def assignment_env(learning_environment):
    client, engine = learning_environment
    client.app.include_router(operations.router)
    with Session(engine) as db:
        vehicle = Vehicle(code='SYN-V1', name='Synthetic vehicle')
        first = OrganizationUnit(code='SYN-A', name='Synthetic first organization')
        second = OrganizationUnit(code='SYN-B', name='Synthetic second organization')
        inactive = OrganizationUnit(code='SYN-C', name='Synthetic inactive', active=False)
        db.add_all([vehicle, first, second, inactive]); db.commit()
        refs = {'vehicle_id': vehicle.vehicle_id, 'first': first.organization_id,
                'second': second.organization_id, 'inactive': inactive.organization_id,
                'user_id': db.scalar(select(User.user_id).where(User.username == 'learning-admin'))}
    return client, engine, refs


def payload(refs, **changes):
    return {'expected_version': 1, 'action': 'assign', 'organization_id': refs['first'],
            'expected_organization_version': 1, 'reason': 'Synthetic Human allocation',
            'source_evidence': 'Synthetic allocation instruction reference A-1',
            'human_acknowledged': True, **changes}


def path(refs):
    return '/operations/vehicles/' + refs['vehicle_id'] + '/assignments'


def assign(client, refs, status=201, **changes):
    response = client.post(path(refs), json=payload(refs, **changes))
    assert response.status_code == status, response.text
    return response.json()


def unassign(client, refs, version, **changes):
    response = client.post(path(refs), json={
        'expected_version': version, 'action': 'unassign', 'reason': 'Synthetic release',
        'source_evidence': 'Synthetic release instruction R-1', 'human_acknowledged': True, **changes})
    assert response.status_code == 201, response.text
    return response.json()


def detail(client, refs, **params):
    response = client.get(path(refs), params=params)
    assert response.status_code == 200, response.text
    return response.json()


def revoke(engine, code):
    with Session(engine) as db:
        permission = db.scalar(select(Permission).where(Permission.code == code))
        for link in db.scalars(select(RolePermission).where(RolePermission.permission_id == permission.permission_id)):
            db.delete(link)
        db.commit()


def test_assignment_sequence_snapshots_confirmation_and_version(assignment_env):
    client, engine, refs = assignment_env
    before = detail(client, refs)
    assert before == {'vehicle_id': refs['vehicle_id'], 'vehicle_version': 1,
                      'current': None, 'items': [], 'total': 0, 'limit': 50, 'offset': 0}
    first = assign(client, refs)
    assert first['vehicle_version'] == 2
    current, change = first['current'], first['change']
    assert current['state'] == 'assigned'
    assert current['organization'] == current['recorded_organization']
    assert current['organization'] == {'organization_id': refs['first'], 'code': 'SYN-A',
                                       'name': 'Synthetic first organization', 'version': 1, 'active': True}
    assert change['before_organization'] is None
    assert change['after_organization'] == current['organization']
    assert (change['vehicle_version_before'], change['vehicle_version_after']) == (1, 2)
    assert change['changed_by'] == refs['user_id']
    assert change['human_confirmation'] == {'acknowledged': True, 'user_id': refs['user_id'], 'at': change['changed_at']}
    assert change['source_evidence'] == payload(refs)['source_evidence']
    second = assign(client, refs, expected_version=2, organization_id=refs['second'])
    assert second['change']['before_organization'] == change['after_organization']
    released = unassign(client, refs, 3)
    assert released['vehicle_version'] == 4
    assert released['current']['state'] == 'unassigned'
    assert released['current']['organization'] is None
    assert released['current']['recorded_organization'] is None
    final = detail(client, refs, limit=2, offset=1)
    assert final['current'] == released['current'] and final['total'] == 3
    assert final['items'] == [second['change'], first['change']]
    assert final['items'][1] == change
    with Session(engine) as db:
        audits = list(db.scalars(select(AuditLog).where(AuditLog.action.like('fleet.assignment.%'))))
        assert len(audits) == 3
        text = json.dumps([{'before': row.before_data, 'after': row.after_data} for row in audits])
        assert payload(refs)['reason'] not in text and payload(refs)['source_evidence'] not in text
        assert change['assignment_change_id'] in text and 'sha256' in text


def test_explicit_unassigned_is_distinct_from_never_recorded(assignment_env):
    client, _, refs = assignment_env
    assert detail(client, refs)['current'] is None
    result = unassign(client, refs, 1)
    assert result['current']['state'] == 'unassigned'
    assert result['change']['before_organization'] is None
    assert detail(client, refs)['total'] == 1


def test_repeated_stale_and_unchanged_commands_do_not_create_events(assignment_env):
    client, _, refs = assignment_env
    assign(client, refs)
    assign(client, refs, status=409)
    assign(client, refs, status=409, expected_version=2)
    correction = assign(client, refs, expected_version=2, reason='Synthetic corrected reason')
    assert correction['vehicle_version'] == 3
    correction = assign(client, refs, expected_version=3, reason='Synthetic corrected reason', source_evidence='Synthetic corrected reference')
    assert correction['vehicle_version'] == 4
    assert detail(client, refs)['total'] == 3
    unassign(client, refs, 4)
    response = client.post(path(refs), json={'expected_version': 5, 'action': 'unassign',
        'reason': 'Synthetic release', 'source_evidence': 'Synthetic release instruction R-1', 'human_acknowledged': True})
    assert response.status_code == 409
    assert detail(client, refs)['total'] == 4


@pytest.mark.parametrize('changes', [
    {'reason': ''}, {'reason': ' \n '}, {'source_evidence': ''}, {'source_evidence': ' \t'},
    {'human_acknowledged': False}, {'human_acknowledged': 1}, {'human_acknowledged': 'true'},
    {'changed_by': str(uuid4())}, {'changed_at': '2020-01-01T00:00:00Z'},
    {'tenant_id': str(uuid4())}, {'human_confirmation': {'acknowledged': True}},
    {'organization_id': None}, {'expected_organization_version': None},
    {'expected_version': 0}, {'expected_version': True}, {'action': 'transfer'},
    {'action': 'unassign'}, {'document_id': str(uuid4())},
])
def test_malformed_commands_are_rejected_atomically(assignment_env, changes):
    client, _, refs = assignment_env
    assign(client, refs, status=422, **changes)
    assert detail(client, refs)['total'] == 0
    assert client.get('/operations/vehicles/' + refs['vehicle_id']).json()['version'] == 1


def test_missing_confirmation_and_unassign_null_target_are_rejected(assignment_env):
    client, _, refs = assignment_env
    body = payload(refs); body.pop('human_acknowledged')
    assert client.post(path(refs), json=body).status_code == 422
    body = {'expected_version': 1, 'action': 'unassign', 'reason': 'Synthetic',
            'source_evidence': 'Synthetic reference', 'human_acknowledged': True, 'organization_id': None}
    assert client.post(path(refs), json=body).status_code == 422


def test_unknown_ids_stale_and_inactive_organization_are_rejected(assignment_env):
    client, _, refs = assignment_env
    for key in ('not-a-uuid', str(uuid4())):
        assert client.get('/operations/vehicles/' + key + '/assignments').status_code == 404
        assert client.post('/operations/vehicles/' + key + '/assignments', json=payload(refs)).status_code == 404
        assign(client, refs, status=404, organization_id=key)
    assign(client, refs, status=409, expected_organization_version=2)
    assign(client, refs, status=409, organization_id=refs['inactive'])
    assert detail(client, refs)['total'] == 0


def test_picker_exposes_only_active_minimal_fleet_projection(assignment_env):
    client, _, refs = assignment_env
    response = client.get('/operations/fleet-organizations', params={'q': 'SYN-', 'limit': 1, 'offset': 1})
    assert response.status_code == 200, response.text
    assert response.headers['cache-control'] == 'no-store'
    assert response.json() == {'items': [{'organization_id': refs['second'], 'code': 'SYN-B',
        'name': 'Synthetic second organization', 'version': 1}], 'total': 2, 'limit': 1, 'offset': 1}
    assert client.get('/operations/fleet-organizations?q=inactive').json()['items'] == []
    for query in ('limit=0', 'limit=201', 'offset=-1'):
        assert client.get('/operations/fleet-organizations?' + query).status_code == 422
        assert client.get(path(refs) + '?' + query).status_code == 422


@pytest.mark.parametrize('permission', ['fleet.update', 'fleet.read'])
def test_fleet_write_and_read_permissions_are_both_required(assignment_env, permission):
    client, engine, refs = assignment_env
    revoke(engine, permission)
    assign(client, refs, status=403)
    expected = 403 if permission == 'fleet.read' else 200
    assert client.get(path(refs)).status_code == expected
    assert client.get('/operations/fleet-organizations').status_code == expected
    with Session(engine) as db:
        assert db.get(Vehicle, refs['vehicle_id']).version == 1


def test_fleet_only_permissions_do_not_require_hr_incident_or_document_access(assignment_env):
    client, engine, refs = assignment_env
    with Session(engine) as db:
        for link in db.scalars(select(RolePermission).join(Permission).where(Permission.code.not_in(['fleet.read', 'fleet.update']))):
            db.delete(link)
        db.commit()
    assert client.get('/operations/fleet-organizations').status_code == 200
    assign(client, refs)
    assert detail(client, refs)['total'] == 1
    assert client.get('/operations/employees').status_code == 403


def test_master_rename_deactivation_and_vehicle_pause_preserve_recorded_assignment(assignment_env):
    client, engine, refs = assignment_env
    original = assign(client, refs)
    with Session(engine) as db:
        org = db.get(OrganizationUnit, refs['first'])
        org.name = 'Synthetic renamed'; org.active = False; org.version = 2
        db.commit()
    response = client.patch('/operations/vehicles/' + refs['vehicle_id'], json={'expected_version': 2, 'active': False})
    assert response.status_code == 200, response.text
    shown = detail(client, refs)
    assert shown['vehicle_version'] == 3
    assert shown['items'] == [original['change']]
    assert shown['current']['recorded_organization'] == original['current']['recorded_organization']
    assert shown['current']['organization']['name'] == 'Synthetic renamed'
    assert shown['current']['organization']['active'] is False
    unassign(client, refs, 3)
    assigned = assign(client, refs, expected_version=4, organization_id=refs['second'])
    assert assigned['vehicle_version'] == 5, 'paused Vehicle remains an editable registry record'
    assert client.get('/operations/vehicles/' + refs['vehicle_id']).json()['active'] is False


def test_changed_master_snapshot_can_be_explicitly_reconfirmed(assignment_env):
    client, engine, refs = assignment_env
    original = assign(client, refs)
    with Session(engine) as db:
        org = db.get(OrganizationUnit, refs['first']); org.name = 'Synthetic renamed'; org.version = 2; db.commit()
    assign(client, refs, status=409, expected_version=2)
    changed = assign(client, refs, expected_version=2, expected_organization_version=2)
    assert changed['change']['before_organization'] == original['change']['after_organization']
    assert changed['change']['after_organization']['name'] == 'Synthetic renamed'


def test_current_and_history_use_vehicle_versions_instead_of_timestamps(assignment_env, monkeypatch):
    from datetime import datetime, timezone
    from app import vehicle_assignment_service
    client, _, refs = assignment_env
    times = iter([datetime(2026, 10, 3, tzinfo=timezone.utc), datetime(2026, 10, 2, tzinfo=timezone.utc), datetime(2026, 10, 2, tzinfo=timezone.utc)])
    monkeypatch.setattr(vehicle_assignment_service, 'now_utc', lambda: next(times))
    assign(client, refs)
    assign(client, refs, expected_version=2, organization_id=refs['second'])
    unassign(client, refs, 3)
    shown = detail(client, refs)
    assert shown['current']['state'] == 'unassigned'
    assert [row['vehicle_version_after'] for row in shown['items']] == [4, 3, 2]


def test_assignments_do_not_mutate_operational_history_or_export_shape(assignment_env):
    client, _, refs = assignment_env
    vehicle_path = '/operations/vehicles/' + refs['vehicle_id']
    incident = client.post('/operations/incidents', json={'kind': 'watch', 'title': 'Synthetic watch'}).json()
    dispatched = client.post('/operations/incidents/' + incident['incident_id'] + '/dispatches', json={
        'expected_version': 1, 'unit': 'Synthetic crew unit', 'vehicle_id': refs['vehicle_id']})
    assert dispatched.status_code == 201, dispatched.text
    assert client.post(vehicle_path + '/trips', json={'expected_version': 1, 'started_at': '2026-10-01T10:00:00Z',
        'ended_at': '2026-10-01T11:00:00Z', 'start_odometer': '0', 'end_odometer': '10', 'purpose': 'Synthetic'}).status_code == 201
    assert client.post(vehicle_path + '/fuel', json={'expected_version': 2, 'kind': 'receipt', 'liters': '5',
        'amount': '10', 'occurred_at': '2026-10-01T12:00:00Z'}).status_code == 201
    assert client.post(vehicle_path + '/services', json={'expected_version': 3, 'kind': 'inspection',
        'performed_on': '2026-10-01', 'description': 'Synthetic check'}).status_code == 201
    old_vehicle = client.get(vehicle_path).json()
    old_history = client.get(vehicle_path + '/history').json()
    old_dispatch = client.get('/operations/dispatches/' + dispatched.json()['dispatch_id']).json()
    old_export_header = client.get('/operations/export/vehicles').text.splitlines()[0]
    assign(client, refs, expected_version=4)
    assert client.get(vehicle_path + '/history').json() == old_history
    assert client.get('/operations/dispatches/' + dispatched.json()['dispatch_id']).json() == old_dispatch
    new_vehicle = client.get(vehicle_path).json()
    assert {k: v for k, v in new_vehicle.items() if k not in ('version', 'updated_at')} == {
        k: v for k, v in old_vehicle.items() if k not in ('version', 'updated_at')}
    assert client.get('/operations/export/vehicles').text.splitlines()[0] == old_export_header
    assert set(old_history) == {'trips', 'fuel', 'services'}
