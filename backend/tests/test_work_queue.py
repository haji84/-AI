"""Synthetic work-list contracts against the real source models and authorization."""
from contextlib import contextmanager
from datetime import date, datetime, timedelta, timezone
import importlib.util
import json
import os
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, delete, select, text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

# Import the canonical application to register all source tables, without changing it.
from app.main import app as canonical_app
from app.db import Base, get_db
from app.models import (
    Document, EmergencyCase, Employee, Facility, FeatureFlag, Permission,
    Role, RolePermission, User, UserRole, UserSession,
)
from app.assets_models import OperationalAsset, AssetBalance, AssetLoan, AssetLocation, AssetLot
from app.operations_models import Incident, Vehicle, VehicleService
from app.inquiries_models import Inquiry, InquiryEvidence
from app.violation_models import ViolationCase, CorrectiveAction
from app.routers import auth
from app.security import hash_password

AS_OF = date(2026, 10, 7)
ALL_PERMISSIONS = {
    'asset.read', 'asset.borrower.read', 'fleet.read', 'violation.read',
    'inquiry.read', 'inquiry.review', 'inquiry.approve', 'incident.read',
    'document.read', 'emergency.case.read', 'emergency.patient.read',
}


class QueueFixture:
    def __init__(self, sessions, client, user_id, other_id, employee_id, other_employee_id, role_id):
        self.sessions, self.client = sessions, client
        self.user_id, self.other_id = user_id, other_id
        self.employee_id, self.other_employee_id = employee_id, other_employee_id
        self.role_id = role_id

    def permissions(self, *codes):
        with self.sessions() as db:
            db.execute(delete(RolePermission).where(RolePermission.role_id == self.role_id))
            for permission in db.scalars(select(Permission).where(Permission.code.in_(codes))):
                db.add(RolePermission(role_id=self.role_id, permission_id=permission.permission_id))
            db.commit()

    def add(self, row):
        with self.sessions() as db:
            db.add(row)
            db.commit()
            db.refresh(row)
            db.expunge(row)
        return row

    def update(self, model, identity, **values):
        with self.sessions() as db:
            row = db.get(model, identity)
            for key, value in values.items():
                setattr(row, key, value)
            db.commit()

    def asset(self, **fields):
        return self.add(OperationalAsset(code=uuid4().hex, name='Synthetic asset', category='durable', unit='item', **fields))

    def vehicle(self, **fields):
        return self.add(Vehicle(code=uuid4().hex, name='Synthetic vehicle', **fields))

    def inquiry(self, **fields):
        return self.add(Inquiry(year=2026, question='Synthetic private question', draft='PRIVATE inquiry original', created_by=fields.pop('created_by', self.user_id), **fields))

    def case(self, **fields):
        facility = self.add(Facility(name='Synthetic facility', address='PRIVATE facility address'))
        return self.add(ViolationCase(building_id=facility.building_id, observed_on=AS_OF, possible_issue='PRIVATE possible issue', created_by=self.other_id, **fields))

    def correction(self, case=None, **fields):
        case = case or self.case()
        return self.add(CorrectiveAction(case_id=case.case_id, description='PRIVATE corrective text', created_by=fields.pop('created_by', self.user_id), **fields))

    def loan(self, asset=None, **fields):
        asset = asset or self.asset()
        location = self.add(AssetLocation(code=uuid4().hex, name='Synthetic location'))
        lot = self.add(AssetLot(asset_id=asset.asset_id, batch_code=uuid4().hex, provenance='PRIVATE provenance'))
        return self.add(AssetLoan(asset_id=asset.asset_id, lot_id=lot.lot_id, location_id=location.location_id,
            borrower_employee_id=fields.pop('borrower_employee_id', self.employee_id), quantity=1,
            outstanding_quantity=fields.pop('outstanding_quantity', 1), loaned_on=AS_OF-timedelta(days=5),
            reason='PRIVATE loan reason', created_by=fields.pop('created_by', self.other_id), **fields))

    def queue(self, **params):
        response = self.client.get('/work-queue', params={'as_of': AS_OF.isoformat(), **params})
        assert response.status_code == 200, response.text
        assert response.headers.get('cache-control') == 'no-store'
        return response.json()


@contextmanager
def queue_application(engine):
    Base.metadata.create_all(engine)
    sessions = sessionmaker(bind=engine, expire_on_commit=False, autoflush=False)
    with sessions() as db:
        employee = Employee(display_name='PRIVATE borrower name')
        other_employee = Employee(display_name='PRIVATE other borrower')
        db.add_all([employee, other_employee])
        db.flush()
        user = User(username='queue-user', password_hash=hash_password('synthetic-password'), employee_id=employee.employee_id)
        other = User(username='queue-other', password_hash='not-a-login', employee_id=other_employee.employee_id)
        role = Role(code='queue-role', name='Synthetic queue role')
        db.add_all([user, other, role])
        db.flush()
        db.add(UserRole(user_id=user.user_id, role_id=role.role_id))
        for code in sorted(ALL_PERMISSIONS):
            permission = Permission(code=code)
            db.add(permission)
            db.flush()
            db.add(RolePermission(role_id=role.role_id, permission_id=permission.permission_id))
        db.commit()
        ids = user.user_id, other.user_id, employee.employee_id, other_employee.employee_id, role.role_id
    application = FastAPI()
    application.include_router(auth.router)
    # Before implementation this fixture deliberately exposes a missing endpoint,
    # producing an HTTP assertion failure rather than an import/collection error.
    if importlib.util.find_spec('app.routers.work_queue') is not None:
        from app.routers.work_queue import router
        application.include_router(router)

    def database():
        with sessions() as db:
            yield db
    application.dependency_overrides[get_db] = database
    with TestClient(application) as client:
        response = client.post('/auth/login', json={'username': 'queue-user', 'password': 'synthetic-password'})
        assert response.status_code == 200, response.text
        yield QueueFixture(sessions, client, *ids)


@pytest.fixture
def queue():
    engine = create_engine('sqlite+pysqlite:///:memory:', connect_args={'check_same_thread': False}, poolclass=StaticPool)
    try:
        with queue_application(engine) as fixture:
            yield fixture
    finally:
        engine.dispose()


def test_provider_permissions_filter_counts_before_pagination(queue):
    asset = queue.asset(next_calibration_on=AS_OF)
    vehicle = queue.vehicle(next_inspection_on=AS_OF-timedelta(days=1))
    correction = queue.correction(due_on=AS_OF)
    inquiry = queue.inquiry()
    queue.permissions('asset.read', 'inquiry.read')
    result = queue.queue(limit=1)
    assert result['total'] == 2
    assert result['counts'] == {'operational_assets': 1, 'inquiries': 1}
    assert result['items'][0]['source_id'] == asset.asset_id
    rest = queue.queue(limit=1, offset=1)
    assert rest['items'][0]['source_id'] == inquiry.inquiry_id
    assert vehicle.vehicle_id not in json.dumps(result) + json.dumps(rest)
    assert correction.action_id not in json.dumps(result) + json.dumps(rest)
    queue.permissions()
    empty = queue.queue()
    assert empty['total'] == 0 and empty['counts'] == {} and empty['items'] == []


def test_transitive_inquiry_source_authorization_precedes_count_and_page(queue):
    emergency = queue.add(EmergencyCase(source_case_key='synthetic', incident_address='PRIVATE patient source'))
    incident = queue.add(Incident(kind='emergency_support', title='PRIVATE source incident', emergency_case_id=emergency.emergency_case_id))
    forbidden = queue.inquiry()
    queue.add(InquiryEvidence(inquiry_id=forbidden.inquiry_id, source_type='incident', source_id=incident.incident_id,
        excerpt='PRIVATE source excerpt', snapshot={}, created_by=queue.user_id))
    allowed = queue.inquiry()
    queue.permissions('inquiry.read', 'incident.read')
    result = queue.queue(scope='related', limit=1)
    assert result['total'] == 1 and result['counts'] == {'inquiries': 1}
    assert result['items'][0]['source_id'] == allowed.inquiry_id
    serialized = json.dumps(result)
    for secret in (forbidden.inquiry_id, incident.incident_id, emergency.emergency_case_id, 'PRIVATE'):
        assert secret not in serialized
    queue.permissions('inquiry.read', 'incident.read', 'emergency.case.read')
    assert queue.queue()['total'] == 2


def test_newly_restricted_inquiry_evidence_is_filtered_at_final_authorization_boundary(queue, monkeypatch):
    from app import inquiries_service
    source = queue.add(EmergencyCase(source_case_key='synthetic-race', incident_address='PRIVATE new source'))
    restricted = queue.inquiry()
    allowed = queue.inquiry()
    queue.permissions('inquiry.read')
    original = inquiries_service.list_rows

    def evidence_added_after_authorized_list(*args, **kwargs):
        rows = original(*args, **kwargs)
        queue.add(InquiryEvidence(inquiry_id=restricted.inquiry_id, source_type='emergency',
            source_id=source.emergency_case_id, excerpt='PRIVATE newly added evidence', snapshot={}, created_by=queue.user_id))
        return rows
    monkeypatch.setattr(inquiries_service, 'list_rows', evidence_added_after_authorized_list)
    result = queue.queue(limit=1)
    assert result['total'] == 1 and result['counts'] == {'inquiries': 1}
    assert result['items'][0]['source_id'] == allowed.inquiry_id
    assert restricted.inquiry_id not in json.dumps(result) and source.emergency_case_id not in json.dumps(result)


def test_asset_deadlines_exact_versions_and_no_copied_business_payload(queue):
    asset = queue.asset(next_pressure_test_on=AS_OF-timedelta(days=1), next_calibration_on=AS_OF,
        next_use_on=AS_OF+timedelta(days=3), next_service_on=AS_OF+timedelta(days=4), version=7, notes='PRIVATE asset note')
    queue.permissions('asset.read')
    result = queue.queue(days=3)
    assert result['schema_version'] == 'work-queue-v1'
    assert (result['as_of'], result['through'], result['business_timezone'], result['scope'], result['limit'], result['offset']) == (
        '2026-10-07', '2026-10-10', 'Asia/Tokyo', 'all', 50, 0)
    assert [(i['kind'], i['due_on'], i['overdue']) for i in result['items']] == [
        ('pressure_test', '2026-10-06', True), ('calibration', '2026-10-07', False), ('use', '2026-10-10', False)]
    for item in result['items']:
        assert item['source_id'] == asset.asset_id and item['source_version'] == 7
        assert item['source_type'] == 'asset' and item['status'] == 'active'
        assert item['relationships'] == ['shared_deadline']
        assert item['required_permissions'] == ['asset.read']
        assert item['navigation'] == {'surface': 'asset', 'id': asset.asset_id}
        assert item['provenance']['source_api'] == '/assets/alerts'
        assert item['provenance']['source_version'] == 7 and item['provenance']['as_of'] == '2026-10-07'
    assert 'PRIVATE' not in json.dumps(result)
    assert len({i['key'] for i in result['items']}) == 3
    assert queue.queue(days=0)['total'] == 2
    assert queue.queue(scope='related')['total'] == 0


def test_lot_and_loan_pointers_and_honest_personal_relationships(queue):
    asset = queue.asset(version=4)
    own = queue.loan(asset, due_on=AS_OF, version=8)
    created = queue.loan(asset, due_on=AS_OF, borrower_employee_id=queue.other_employee_id, created_by=queue.user_id)
    unrelated = queue.loan(asset, due_on=AS_OF, borrower_employee_id=queue.other_employee_id)
    queue.loan(asset, due_on=AS_OF, outstanding_quantity=0)
    queue.loan(asset, due_on=None)
    queue.loan(queue.asset(active=False), due_on=AS_OF)
    lot = queue.add(AssetLot(asset_id=asset.asset_id, batch_code='expiry', provenance='PRIVATE lot origin',
        expires_on=AS_OF, expiry_approved_by=queue.user_id, expiry_approved_at=datetime.now(timezone.utc), version=6))
    location = queue.add(AssetLocation(code='expiry-location', name='Synthetic'))
    queue.add(AssetBalance(asset_id=asset.asset_id, lot_id=lot.lot_id, location_id=location.location_id, quantity=1))
    queue.permissions('asset.read', 'asset.borrower.read')
    result = queue.queue()
    assert result['total'] == 4
    items = {i['source_id']: i for i in result['items']}
    assert items[own.loan_id]['source_version'] == 8
    assert items[own.loan_id]['relationships'] == ['borrowed_by_me']
    assert items[created.loan_id]['relationships'] == ['created_by_me']
    assert items[unrelated.loan_id]['relationships'] == ['shared_deadline']
    assert items[own.loan_id]['required_permissions'] == ['asset.borrower.read', 'asset.read']
    assert items[lot.lot_id]['source_type'] == 'asset_lot' and items[lot.lot_id]['source_version'] == 6
    assert items[lot.lot_id]['provenance']['parent_source_id'] == asset.asset_id
    assert items[lot.lot_id]['provenance']['parent_source_version'] == 4
    assert items[own.loan_id]['navigation'] == {'surface': 'asset', 'id': asset.asset_id}
    assert {i['source_id'] for i in queue.queue(scope='related')['items']} == {own.loan_id, created.loan_id}
    assert 'PRIVATE' not in json.dumps(result) and queue.employee_id not in json.dumps(result)
    queue.permissions('asset.read')
    result = queue.queue()
    assert result['total'] == 1 and result['items'][0]['source_id'] == lot.lot_id


def test_fleet_preserves_recorded_deadline_mileage_and_fault_semantics(queue):
    vehicle = queue.vehicle(next_inspection_on=AS_OF, next_service_on=AS_OF+timedelta(days=2),
        odometer=120, next_service_odometer=100, version=5)
    fault = queue.add(VehicleService(vehicle_id=vehicle.vehicle_id, kind='fault', performed_on=AS_OF,
        description='PRIVATE fault detail', created_by=queue.user_id, version=3))
    queue.add(VehicleService(vehicle_id=vehicle.vehicle_id, kind='fault', performed_on=AS_OF,
        description='PRIVATE cancelled fault', created_by=queue.user_id, status='cancelled'))
    queue.vehicle(active=False, next_inspection_on=AS_OF)
    queue.permissions('fleet.read')
    items = queue.queue(days=0)['items']
    assert [(i['kind'], i['overdue']) for i in items] == [('service_mileage', True), ('inspection', False), ('unresolved_fault', False)]
    fault_item = next(i for i in items if i['kind'] == 'unresolved_fault')
    assert fault_item['source_id'] == fault.service_id and fault_item['source_type'] == 'vehicle_service'
    assert fault_item['source_version'] == 3 and fault_item['status'] == 'draft' and fault_item['due_on'] is None
    assert fault_item['navigation'] == {'surface': 'vehicle', 'id': vehicle.vehicle_id}
    assert fault_item['provenance']['parent_source_version'] == 5
    assert fault_item['provenance']['source_api'] == '/operations/alerts'
    assert fault_item['relationships'] == ['created_by_me']
    assert queue.queue(days=2)['total'] == 4
    assert 'PRIVATE' not in json.dumps(items)


def test_unowned_undated_fault_is_role_work_without_claiming_a_deadline(queue):
    vehicle = queue.vehicle()
    queue.add(VehicleService(vehicle_id=vehicle.vehicle_id, kind='fault', performed_on=AS_OF,
        description='PRIVATE fault detail', created_by=queue.other_id))
    queue.permissions('fleet.read')
    item = queue.queue()['items'][0]
    assert item['due_on'] is None
    assert item['relationships'] == ['available_to_my_role']
    assert queue.queue(scope='related')['total'] == 0


@pytest.mark.parametrize('module', ['operational_assets', 'fleet', 'violations', 'inquiries'])
def test_each_provider_flag_hides_existing_records_and_restores_on_enable(queue, module):
    queue.asset(next_service_on=AS_OF)
    queue.vehicle(next_inspection_on=AS_OF)
    queue.correction(due_on=AS_OF)
    queue.inquiry()
    assert queue.queue()['total'] == 4
    flag = queue.add(FeatureFlag(key=f'module.{module}.enabled', module_code=module, enabled=False))
    result = queue.queue(limit=1)
    assert result['total'] == 3 and module not in result['counts']
    assert all(item['module'] != module for item in queue.queue()['items'])
    queue.update(FeatureFlag, flag.feature_flag_id, enabled=True)
    assert queue.queue()['total'] == 4


def test_card_titles_identify_authorized_source_and_permission_lists_include_closure(queue):
    asset = queue.asset(next_service_on=AS_OF)
    vehicle = queue.vehicle(next_inspection_on=AS_OF)
    inquiry = queue.inquiry(provenance={'required_permissions': ['emergency.patient.read']})
    items = {item['source_id']: item for item in queue.queue()['items']}
    assert asset.name in items[asset.asset_id]['title']
    assert vehicle.code in items[vehicle.vehicle_id]['title']
    assert inquiry.question in items[inquiry.inquiry_id]['title']
    assert 'emergency.patient.read' in items[inquiry.inquiry_id]['required_permissions']
    assert inquiry.draft not in json.dumps(items)


@pytest.mark.parametrize('provider', ['asset', 'fleet'])
def test_source_version_and_deadline_stay_together_if_source_changes_during_aggregation(queue, monkeypatch, provider):
    from app import assets_service, operations_service
    service = assets_service if provider == 'asset' else operations_service
    source = queue.asset(next_service_on=AS_OF) if provider == 'asset' else queue.vehicle(next_service_on=AS_OF)
    model, identity = (OperationalAsset, source.asset_id) if provider == 'asset' else (Vehicle, source.vehicle_id)
    original = service.alerts

    def changed_after_alerts(*args, **kwargs):
        alerts = original(*args, **kwargs)
        queue.update(model, identity, next_service_on=AS_OF+timedelta(days=2), version=2)
        return alerts
    monkeypatch.setattr(service, 'alerts', changed_after_alerts)
    result = queue.queue(days=3)
    assert result['items'][0]['source_version'] == 2
    assert result['items'][0]['due_on'] == '2026-10-09'
    assert queue.queue(days=0)['items'] == []


def test_corrective_queue_reuses_active_cases_and_redaction(queue):
    case = queue.case(version=9)
    action = queue.correction(case, due_on=AS_OF, version=3,
        verification_snapshot={'proof_document_ids': ['PRIVATE proof'], 'finding_text': 'PRIVATE finding'})
    queue.correction(case, due_on=None)
    queue.correction(case, due_on=AS_OF, status='completed')
    queue.correction(case, due_on=AS_OF, status='cancelled')
    queue.correction(case, due_on=AS_OF+timedelta(days=31))
    for status in ('completed', 'resolved_candidate', 'withdrawn', 'superseded'):
        queue.correction(queue.case(status=status), due_on=AS_OF)
    queue.permissions('violation.read')
    items = queue.queue()['items']
    assert len(items) == 1
    item = items[0]
    assert item['source_type'] == 'corrective_action' and item['source_id'] == action.action_id
    assert item['source_version'] == 3 and item['status'] == 'open'
    assert item['navigation'] == {'surface': 'violation', 'id': case.case_id}
    assert item['relationships'] == ['created_by_me']
    assert item['provenance']['parent_source_version'] == 9
    assert 'PRIVATE' not in json.dumps(item) and case.building_id not in json.dumps(item)


def test_inquiry_creator_review_and_approval_are_distinct_and_undated(queue):
    own = queue.inquiry(version=4)
    own_reviewed = queue.inquiry(status='reviewed')
    other_draft = queue.inquiry(created_by=queue.other_id)
    other_reviewed = queue.inquiry(created_by=queue.other_id, status='reviewed')
    queue.inquiry(deleted=True)
    queue.inquiry(status='approved', reviewed_by=queue.user_id, approved_by=queue.user_id,
        reviewed_at=datetime.now(timezone.utc), approved_at=datetime.now(timezone.utc))
    queue.permissions('inquiry.read')
    items = queue.queue()['items']
    assert {i['source_id'] for i in items} == {own.inquiry_id, own_reviewed.inquiry_id}
    assert all(i['relationships'] == ['created_by_me'] and i['due_on'] is None and not i['overdue'] for i in items)
    assert next(i for i in items if i['source_id'] == own.inquiry_id)['source_version'] == 4
    queue.permissions('inquiry.read', 'inquiry.review')
    items = queue.queue()['items']
    assert {i['source_id'] for i in items} == {own.inquiry_id, own_reviewed.inquiry_id, other_draft.inquiry_id}
    role_item = next(i for i in items if i['source_id'] == other_draft.inquiry_id)
    assert role_item['kind'] == 'review' and role_item['relationships'] == ['available_to_my_role']
    assert role_item['required_permissions'] == ['inquiry.read', 'inquiry.review']
    assert queue.queue(scope='related')['total'] == 2
    queue.permissions('inquiry.read', 'inquiry.approve')
    items = queue.queue()['items']
    assert {i['source_id'] for i in items} == {own.inquiry_id, own_reviewed.inquiry_id, other_reviewed.inquiry_id}
    role_item = next(i for i in items if i['source_id'] == other_reviewed.inquiry_id)
    assert role_item['kind'] == 'approval' and role_item['relationships'] == ['available_to_my_role']
    assert role_item['required_permissions'] == ['inquiry.approve', 'inquiry.read']


def test_source_flags_and_live_source_mutations_remove_stale_tasks(queue):
    asset = queue.asset(next_service_on=AS_OF)
    loan = queue.loan(asset, due_on=AS_OF)
    vehicle = queue.vehicle(next_inspection_on=AS_OF)
    correction = queue.correction(due_on=AS_OF)
    inquiry = queue.inquiry()
    assert queue.queue()['total'] == 5
    queue.update(OperationalAsset, asset.asset_id, next_service_on=AS_OF+timedelta(days=1), version=2)
    assert next(i for i in queue.queue()['items'] if i['source_id'] == asset.asset_id)['source_version'] == 2
    queue.update(AssetLoan, loan.loan_id, outstanding_quantity=0, version=2)
    queue.update(Vehicle, vehicle.vehicle_id, active=False, version=2)
    queue.update(CorrectiveAction, correction.action_id, status='cancelled', version=2)
    queue.update(Inquiry, inquiry.inquiry_id, deleted=True, version=2)
    assert queue.queue()['total'] == 1
    for module in ('operational_assets', 'fleet', 'violations', 'inquiries'):
        queue.add(FeatureFlag(key=f'module.{module}.enabled', module_code=module, enabled=False))
    assert queue.queue()['total'] == 0
    queue.add(FeatureFlag(key='module.work_queue.enabled', module_code='work_queue', enabled=False))
    response = queue.client.get('/work-queue')
    assert response.status_code == 404


def test_deterministic_order_and_pages_do_not_write_business_records(queue):
    for _ in range(3):
        queue.asset(next_calibration_on=AS_OF)
    queue.vehicle(next_inspection_on=AS_OF-timedelta(days=2))
    queue.inquiry()
    models = (OperationalAsset, AssetLoan, AssetLot, AssetBalance, Vehicle, VehicleService, ViolationCase, CorrectiveAction, Inquiry)

    def snapshot():
        with queue.sessions() as db:
            return {model.__tablename__: sorted((str(getattr(r, list(model.__table__.primary_key.columns)[0].name)), r.version)
                for r in db.scalars(select(model))) for model in models}
    before = snapshot()
    full = queue.queue()
    assert queue.queue() == full
    first, last = queue.queue(limit=2), queue.queue(limit=2, offset=2)
    tail = queue.queue(limit=2, offset=4)
    assert first['items'] + last['items'] + tail['items'] == full['items']
    assert all(page['total'] == 5 and page['counts'] == full['counts'] for page in (first, last, tail))
    assert queue.queue(offset=99)['items'] == []
    assert snapshot() == before


def test_business_date_uses_one_japan_clock_boundary(queue, monkeypatch):
    from app import assets_service
    monkeypatch.setattr(assets_service, 'now_utc', lambda: datetime(2026, 10, 6, 15, 0, tzinfo=timezone.utc))
    queue.asset(next_calibration_on=AS_OF)
    queue.vehicle(next_inspection_on=AS_OF)
    result = queue.client.get('/work-queue', params={'days': 0}).json()
    assert result['as_of'] == '2026-10-07' and result['through'] == '2026-10-07'
    assert all(i['due_on'] == result['as_of'] and not i['overdue'] for i in result['items'])


@pytest.mark.parametrize('params', [{'days': -1}, {'days': 31}, {'limit': 0}, {'limit': 101}, {'offset': -1}, {'scope': 'assigned'}, {'as_of': 'invalid'}, {'as_of': '9999-12-31', 'days': 1}])
def test_query_bounds(queue, params):
    assert queue.client.get('/work-queue', params=params).status_code == 422


def test_real_session_revocation_and_account_availability(queue):
    queue.asset(next_calibration_on=AS_OF)
    assert queue.queue()['total'] == 1
    queue.update(User, queue.user_id, active=False)
    assert queue.client.get('/work-queue').status_code == 403
    queue.update(User, queue.user_id, active=True)
    with queue.sessions() as db:
        for session in db.scalars(select(UserSession).where(UserSession.user_id == queue.user_id)):
            session.revoked_at = datetime.now(timezone.utc)
        db.commit()
    assert queue.client.get('/work-queue').status_code == 401
    queue.client.cookies.clear()
    assert queue.client.get('/work-queue').status_code == 401


def test_postgresql_work_queue_live_authorization_and_source_versions():
    url = os.environ.get('FIRE_AI_TEST_POSTGRES_URL')
    if not url:
        pytest.skip('actual PostgreSQL work-list aggregation is exercised in CI')
    engine = create_engine(url)
    schema = 'synthetic_work_queue_' + uuid4().hex
    scoped = engine.execution_options(schema_translate_map={None: schema})
    try:
        with engine.begin() as connection:
            connection.execute(text(f'CREATE SCHEMA "{schema}"'))
        with queue_application(scoped) as fixture:
            test_provider_permissions_filter_counts_before_pagination(fixture)
            # Reset only fixture permissions; existing sources remain deliberately.
            fixture.permissions(*ALL_PERMISSIONS)
            with fixture.sessions() as db:
                baseline = {i.inquiry_id for i in db.scalars(select(Inquiry))}
            private = fixture.inquiry(provenance={'required_permissions': ['emergency.patient.read']})
            fixture.permissions('inquiry.read')
            result = fixture.queue(scope='related', limit=1)
            assert result['total'] == len(baseline) and private.inquiry_id not in json.dumps(result)
            fixture.permissions('inquiry.read', 'emergency.patient.read')
            fixture.update(Inquiry, private.inquiry_id, version=3)
            result = fixture.queue(scope='related')
            assert next(i for i in result['items'] if i['source_id'] == private.inquiry_id)['source_version'] == 3
            fixture.update(Inquiry, private.inquiry_id, deleted=True, version=4)
            assert fixture.queue(scope='related')['total'] == len(baseline)
    finally:
        with engine.begin() as connection:
            connection.execute(text(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE'))
        engine.dispose()
