"""Synthetic assignment isolation and actual PostgreSQL transaction evidence.

SQLite verifies deterministic rollback and server-selected tenant isolation.
Lock interleavings and migration guards require FIRE_AI_TEST_POSTGRES_URL;
a skip is not PostgreSQL evidence.
"""
import os
from pathlib import Path
import shutil
import threading
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event, func, select, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from test_learning import learning_environment
from test_run_b_operations_tenant_integration import VEHICLE_ID, departments, login


def assignment_payload(organization_id, **changes):
    return {
        'expected_version': 1,
        'action': 'assign',
        'organization_id': organization_id,
        'expected_organization_version': 1,
        'reason': 'Synthetic Human-approved vehicle placement',
        'source_evidence': 'Synthetic placement order 2026-10-07',
        'human_acknowledged': True,
        **changes,
    }


def assignment_path(vehicle_id):
    return f'/operations/vehicles/{vehicle_id}/assignments'


@pytest.fixture
def assignment_environment(learning_environment):
    from app.operations_models import Vehicle
    from app.personnel import OrganizationUnit
    from app.routers import operations
    client, engine = learning_environment
    client.app.include_router(operations.router)
    with Session(engine) as db:
        first = OrganizationUnit(code='SYN-FIRST', name='Synthetic first organization')
        second = OrganizationUnit(code='SYN-SECOND', name='Synthetic second organization')
        vehicle = Vehicle(code='SYN-ASSIGN', name='Synthetic vehicle for assignment')
        db.add_all([first, second, vehicle])
        db.commit()
        refs = {'vehicle_id': vehicle.vehicle_id, 'first': first.organization_id, 'second': second.organization_id}
    return client, engine, refs


@pytest.fixture
def assignment_pg(assignment_environment):
    client, engine, refs = assignment_environment
    if engine.dialect.name != 'postgresql':
        pytest.skip('real PostgreSQL assignment transaction interleaving required')
    return client, engine, refs


def race_requests(client, requests):
    barrier = threading.Barrier(len(requests))
    responses = [None] * len(requests)
    failures = []

    def send(index, method, path, payload):
        try:
            with TestClient(client.app) as other:
                other.cookies.update(client.cookies)
                barrier.wait(timeout=10)
                responses[index] = other.request(method, path, json=payload)
        except BaseException as error:
            failures.append(error)

    workers = [threading.Thread(target=send, args=(index, *request)) for index, request in enumerate(requests)]
    for worker in workers:
        worker.start()
    for worker in workers:
        worker.join(timeout=20)
    assert not failures and all(not worker.is_alive() for worker in workers), failures
    return responses


def queued_request(client, path, payload):
    responses, failures = [], []

    def send():
        try:
            with TestClient(client.app) as other:
                other.cookies.update(client.cookies)
                responses.append(other.post(path, json=payload))
        except BaseException as error:
            failures.append(error)

    return threading.Thread(target=send), responses, failures


def assignment_events(engine, vehicle_id):
    from app.operations_models import Vehicle, VehicleAssignmentChange
    with Session(engine) as db:
        vehicle = db.get(Vehicle, vehicle_id)
        count = db.scalar(select(func.count()).select_from(VehicleAssignmentChange).where(VehicleAssignmentChange.vehicle_id == vehicle_id))
        return vehicle.version, count


def test_competing_assignment_targets_have_one_winner(assignment_pg):
    from app.models import AuditLog
    client, engine, refs = assignment_pg
    path = assignment_path(refs['vehicle_id'])
    responses = race_requests(client, [('POST', path, assignment_payload(refs[key])) for key in ('first', 'second')])
    assert sorted(response.status_code for response in responses) == [201, 409], [response.text for response in responses]
    winner = next(response.json() for response in responses if response.status_code == 201)
    shown = client.get(path).json()
    assert shown['vehicle_version'] == 2 and shown['total'] == 1
    assert shown['current']['assignment_change_id'] == winner['current']['assignment_change_id']
    assert shown['current']['organization']['organization_id'] in (refs['first'], refs['second'])
    assert assignment_events(engine, refs['vehicle_id']) == (2, 1)
    with Session(engine) as db:
        assert db.scalar(select(func.count()).select_from(AuditLog).where(AuditLog.action == 'fleet.assignment.assign')) == 1


@pytest.mark.parametrize('other_operation', ['patch', 'fuel'])
def test_assignment_and_existing_vehicle_mutation_share_one_version(assignment_pg, other_operation):
    from app.operations_models import FuelEntry, Vehicle
    client, engine, refs = assignment_pg
    base = f"/operations/vehicles/{refs['vehicle_id']}"
    if other_operation == 'patch':
        request = ('PATCH', base, {'expected_version': 1, 'name': 'Synthetic renamed vehicle'})
    else:
        request = ('POST', base + '/fuel', {'expected_version': 1, 'kind': 'receipt', 'liters': '2.50', 'amount': '10.25', 'occurred_at': '2026-10-07T10:00:00Z'})
    assigned, existing = race_requests(client, [('POST', base + '/assignments', assignment_payload(refs['first'])), request])
    assert sum(response.status_code == 409 for response in (assigned, existing)) == 1, (assigned.text, existing.text)
    assigned_won = assigned.status_code == 201
    assert assigned.status_code == (201 if assigned_won else 409)
    assert existing.status_code == (409 if assigned_won else (200 if other_operation == 'patch' else 201)), existing.text
    assert assignment_events(engine, refs['vehicle_id']) == (2, int(assigned_won))
    with Session(engine) as db:
        vehicle = db.get(Vehicle, refs['vehicle_id'])
        assert vehicle.name == ('Synthetic renamed vehicle' if other_operation == 'patch' and not assigned_won else 'Synthetic vehicle for assignment')
        assert str(vehicle.fuel_stock) == ('2.50' if other_operation == 'fuel' and not assigned_won else '0.00')
        assert db.scalar(select(func.count()).select_from(FuelEntry)) == int(other_operation == 'fuel' and not assigned_won)


@pytest.mark.parametrize('revocation', ['session', 'role', 'fleet_read'])
def test_queued_assignment_revalidates_session_and_authority(assignment_pg, monkeypatch, revocation):
    from app import authz
    from app.models import AuditLog, Permission, RolePermission, User, UserRole, UserSession, now_utc
    client, engine, refs = assignment_pg
    waiting = threading.Event()
    original_lock = authz.account_change_lock

    def observed_lock(db):
        waiting.set()
        return original_lock(db)

    monkeypatch.setattr(authz, 'account_change_lock', observed_lock)
    worker, responses, failures = queued_request(client, assignment_path(refs['vehicle_id']), assignment_payload(refs['first']))
    with Session(engine) as db:
        original_lock(db)
        worker.start()
        try:
            assert waiting.wait(timeout=15), 'assignment did not queue behind the account-change lock'
            user = db.scalar(select(User).where(User.username == 'learning-admin'))
            if revocation == 'session':
                for row in db.scalars(select(UserSession).where(UserSession.user_id == user.user_id)):
                    row.revoked_at = now_utc()
            elif revocation == 'role':
                for row in db.scalars(select(UserRole).where(UserRole.user_id == user.user_id)):
                    db.delete(row)
            else:
                permission = db.scalar(select(Permission).where(Permission.code == 'fleet.read'))
                for row in db.scalars(select(RolePermission).where(RolePermission.permission_id == permission.permission_id)):
                    db.delete(row)
            db.commit()
        finally:
            db.rollback()
            worker.join(timeout=20)
    assert not failures and not worker.is_alive(), failures
    assert len(responses) == 1 and responses[0].status_code == (401 if revocation == 'session' else 403), [response.text for response in responses]
    assert assignment_events(engine, refs['vehicle_id']) == (1, 0)
    with Session(engine) as db:
        assert db.scalar(select(func.count()).select_from(AuditLog).where(AuditLog.action.like('fleet.assignment.%'))) == 0


@pytest.mark.parametrize('change', ['rename', 'deactivate'])
def test_assignment_rechecks_organization_after_waiting_for_its_row_lock(assignment_pg, monkeypatch, change):
    from app import operations_service as ops
    from app.personnel import OrganizationUnit
    client, engine, refs = assignment_pg
    waiting = threading.Event()
    original_get = ops.get_row

    def observed_get(db, model, key, lock=False):
        if model is OrganizationUnit and key == refs['first'] and lock:
            waiting.set()
        return original_get(db, model, key, lock)

    monkeypatch.setattr(ops, 'get_row', observed_get)
    worker, responses, failures = queued_request(client, assignment_path(refs['vehicle_id']), assignment_payload(refs['first']))
    with Session(engine) as db:
        organization = db.scalar(select(OrganizationUnit).where(OrganizationUnit.organization_id == refs['first']).with_for_update())
        worker.start()
        try:
            assert waiting.wait(timeout=15), 'assignment did not acquire the target organization row lock'
            organization.version += 1
            if change == 'rename':
                organization.name = 'Synthetic name changed during Human confirmation'
            else:
                organization.active = False
            db.commit()
        finally:
            db.rollback()
            worker.join(timeout=20)
    assert not failures and not worker.is_alive(), failures
    assert len(responses) == 1 and responses[0].status_code == 409, [response.text for response in responses]
    assert assignment_events(engine, refs['vehicle_id']) == (1, 0)
    shown = client.get(assignment_path(refs['vehicle_id'])).json()
    assert shown['current'] is None and shown['items'] == []


def test_assignment_event_insert_failure_rolls_back_vehicle_and_audit(assignment_environment):
    from app.models import AuditLog
    from app.operations_models import Vehicle, VehicleAssignmentChange
    client, engine, refs = assignment_environment
    attempted = []

    def fail_insert(mapper, connection, target):
        attempted.append((target.vehicle_id, connection.execute(select(Vehicle.version).where(Vehicle.vehicle_id == target.vehicle_id)).scalar_one()))
        raise IntegrityError('Synthetic assignment event insert failure', None, RuntimeError('synthetic rollback probe'))

    event.listen(VehicleAssignmentChange, 'before_insert', fail_insert)
    try:
        with TestClient(client.app, raise_server_exceptions=False) as failing:
            failing.cookies.update(client.cookies)
            response = failing.post(assignment_path(refs['vehicle_id']), json=assignment_payload(refs['first']))
    finally:
        event.remove(VehicleAssignmentChange, 'before_insert', fail_insert)
    assert attempted == [(refs['vehicle_id'], 2)], 'the rollback probe must run after the vehicle version update'
    assert response.status_code == 409, response.text
    assert assignment_events(engine, refs['vehicle_id']) == (1, 0)
    with Session(engine) as db:
        assert db.scalar(select(func.count()).select_from(AuditLog).where(AuditLog.action.like('fleet.assignment.%'))) == 0
    shown = client.get(assignment_path(refs['vehicle_id'])).json()
    assert shown['current'] is None and shown['items'] == []


def test_migration053_rejects_sql_update_and_delete_of_assignment_history(assignment_pg):
    client, engine, refs = assignment_pg
    path = assignment_path(refs['vehicle_id'])
    created = client.post(path, json=assignment_payload(refs['first']))
    assert created.status_code == 201, created.text
    original = client.get(path).json()
    for statement in (
        "UPDATE operation_vehicle_assignment_changes SET reason='Synthetic tampering attempt'",
        'DELETE FROM operation_vehicle_assignment_changes',
    ):
        with pytest.raises(IntegrityError) as rejected:
            with engine.begin() as connection:
                connection.execute(text(statement))
        assert getattr(rejected.value.orig, 'sqlstate', None) == '23514'
    assert client.get(path).json() == original


def test_migration053_upgrades_existing_fleet_without_invented_assignment_and_reruns(tmp_path):
    base = os.environ.get('FIRE_AI_TEST_POSTGRES_URL')
    if not base:
        pytest.skip('real PostgreSQL migration053 upgrade/rerun required')
    from app.migrations import apply_migrations
    migrations = Path(__file__).resolve().parents[2] / 'db/migrations'
    historical = tmp_path / 'historical'
    through_053 = tmp_path / 'through_053'
    historical.mkdir()
    through_053.mkdir()
    for source in migrations.glob('*.sql'):
        if source.name < '053':
            shutil.copy(source, historical / source.name)
        if source.name[:3] <= '053':
            shutil.copy(source, through_053 / source.name)
    new_migrations = sorted(path.name for path in migrations.glob('053*.sql'))
    assert len(new_migrations) == 1, 'exactly one migration053 must implement assignment history'
    database = 'fi_vehicle_assignment_' + uuid4().hex[:16]
    cluster = create_engine(make_url(base).set(database='postgres'), isolation_level='AUTOCOMMIT')
    target = make_url(base).set(database=database).render_as_string(hide_password=False)
    engine = None
    with cluster.connect() as connection:
        connection.exec_driver_sql('CREATE DATABASE ' + database)
    try:
        apply_migrations(target, historical)
        engine = create_engine(target)
        vehicle_id = str(uuid4())
        with engine.begin() as connection:
            connection.execute(text("INSERT INTO operation_vehicles(vehicle_id,code,name,version,odometer,fuel_stock) VALUES (:id,'SYN-PRE-053','Synthetic legacy vehicle',7,123.4,15.25)"), {'id': vehicle_id})
        assert apply_migrations(target, through_053) == new_migrations
        assert apply_migrations(target, through_053) == []
        with engine.connect() as connection:
            row = connection.execute(text('SELECT version,odometer,fuel_stock FROM operation_vehicles WHERE vehicle_id=:id'), {'id': vehicle_id}).one()
            assert row.version == 7 and str(row.odometer) == '123.4' and str(row.fuel_stock) == '15.25'
            assert connection.execute(text('SELECT COUNT(*) FROM operation_vehicle_assignment_changes')).scalar_one() == 0
    finally:
        if engine:
            engine.dispose()
        with cluster.connect() as connection:
            connection.exec_driver_sql('DROP DATABASE ' + database + ' WITH (FORCE)')
        cluster.dispose()


def test_assignments_and_minimal_choices_use_server_selected_department(tmp_path):
    from app.personnel import OrganizationUnit
    organization_id = str(uuid4())
    alpha_only_id = str(uuid4())
    with departments(tmp_path) as [(alpha, _, alpha_cfg, alpha_sessions), (beta, _, beta_cfg, beta_sessions)]:
        for sessions, slug in [(alpha_sessions, 'alpha'), (beta_sessions, 'beta')]:
            with sessions() as db:
                db.add(OrganizationUnit(organization_id=organization_id, code='SYN-ORG', name=f'Synthetic {slug} organization'))
                if slug == 'alpha':
                    db.add(OrganizationUnit(organization_id=alpha_only_id, code='SYN-ALPHA', name='Synthetic alpha-only organization'))
                db.commit()
        login(alpha, 'alpha')
        token = alpha.cookies.get('fire_ai_session')
        assert beta.get(assignment_path(VEHICLE_ID), headers={'Cookie': 'fire_ai_session=' + token}).status_code == 401
        login(beta, 'beta')
        for client, slug, other in [(alpha, 'alpha', 'beta'), (beta, 'beta', 'alpha')]:
            response = client.get('/operations/fleet-organizations')
            assert response.status_code == 200, response.text
            assert f'Synthetic {slug} organization' in response.text
            assert f'Synthetic {other} organization' not in response.text
            empty = client.get(assignment_path(VEHICLE_ID))
            assert empty.status_code == 200, empty.text
            assert empty.json()['current'] is None and empty.json()['total'] == 0
        response = alpha.post(
            assignment_path(VEHICLE_ID),
            params={'tenant_id': beta_cfg.tenant_id, 'database_url': 'beta'},
            headers={'X-Tenant-ID': beta_cfg.tenant_id},
            json=assignment_payload(organization_id),
        )
        assert response.status_code == 201, response.text
        assert response.json()['current']['organization']['name'] == 'Synthetic alpha organization'
        shown = alpha.get(assignment_path(VEHICLE_ID), params={'tenant_id': beta_cfg.tenant_id}, headers={'X-Tenant-ID': beta_cfg.tenant_id})
        assert shown.status_code == 200 and shown.json()['total'] == 1
        assert 'Synthetic beta organization' not in shown.text
        untouched = beta.get(assignment_path(VEHICLE_ID)).json()
        assert untouched['current'] is None and untouched['items'] == [] and untouched['vehicle_version'] == 1
        assert beta.post(assignment_path(VEHICLE_ID), json=assignment_payload(alpha_only_id)).status_code == 404
        assert alpha.get(assignment_path(VEHICLE_ID), headers={'Host': 'beta.test'}).status_code == 421
        for field in ('tenant_id', 'database_url', 'user_id'):
            rejected = beta.post(assignment_path(VEHICLE_ID), json={**assignment_payload(organization_id), field: alpha_cfg.tenant_id})
            assert rejected.status_code == 422, rejected.text
