from datetime import date
import os
os.environ.setdefault("FIRE_AI_DATABASE_URL", "sqlite+pysqlite:///:memory:")
from io import BytesIO

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db import Base, get_db
from app.main import app
from app.models import AuditLog, EmergencyCase, EmergencyPatient, User, UserRole
from app.rbac_seed import seed_rbac
from app.security import hash_password


@pytest.fixture
def report_client():
    engine = create_engine('sqlite+pysqlite:///:memory:', connect_args={'check_same_thread': False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    sessions = sessionmaker(bind=engine, expire_on_commit=False)
    with sessions() as db:
        roles = seed_rbac(db)
        for name, role in [('reporter', 'emergency_reporter'), ('editor', 'prevention_editor')]:
            user = User(username=name, password_hash=hash_password('long-test-password'))
            db.add(user)
            db.flush()
            db.add(UserRole(user_id=user.user_id, role_id=roles[role].role_id))
        cases = [EmergencyCase(source_case_key=str(i), call_date=day, incident_area_code=region)
                 for i, day, region in [(1, date(2026, 1, 1), 'north'), (2, date(2026, 1, 31), 'south'),
                                        (3, date(2026, 2, 1), 'north'), (4, None, None)]]
        db.add_all(cases)
        db.flush()
        for case, no, hospital, severity in [(cases[0], 1, 'H1', 'S1'), (cases[0], 2, 'H1', 'S2'),
                (cases[1], 1, None, None), (cases[2], 1, '=H2', 'S1'), (cases[3], 1, 'H1', 'S1')]:
            db.add(EmergencyPatient(emergency_case_id=case.emergency_case_id, patient_number=no,
                hospital_code=hospital, severity_code=severity, diagnosis_text='PRIVATE_DIAGNOSIS',
                raw_payload={'name': 'PRIVATE_NAME'}))
        db.commit()
    def dependency():
        with sessions() as db:
            yield db
    previous = dict(app.dependency_overrides)
    app.dependency_overrides[get_db] = dependency
    with TestClient(app) as client:
        yield client, sessions
    app.dependency_overrides.clear()
    app.dependency_overrides.update(previous)
    engine.dispose()


def login(client, name='reporter'):
    assert client.post('/auth/login', json={'username': name, 'password': 'long-test-password'}).status_code == 200


def test_report_requires_dedicated_permission(report_client):
    client, _ = report_client
    assert client.get('/emergency/reports/summary').status_code == 401
    login(client, 'editor')
    assert client.get('/emergency/reports/summary').status_code == 403
    assert client.get('/emergency/reports/export?format=xlsx').status_code == 403


def test_summary_distinguishes_cases_patients_and_missing_dates(report_client):
    client, sessions = report_client
    login(client)
    response = client.get('/emergency/reports/summary?start_date=2026-01-01&end_date=2026-01-31&group_by=hospital')
    assert response.status_code == 200
    data = response.json()
    assert data['totals'] == {'cases': 2, 'patients': 3, 'patients_with_hospital': 2}
    assert data['undated_cases_excluded'] == 1
    assert data['groups'] == [
        {'code': None, 'patients': 1, 'cases': 1, 'patient_share': pytest.approx(1/3)},
        {'code': 'H1', 'patients': 2, 'cases': 1, 'patient_share': pytest.approx(2/3)}]
    assert 'PRIVATE' not in response.text
    assert 'raw_payload' not in response.text
    with sessions() as db:
        log = db.scalar(select(AuditLog).where(AuditLog.action == 'emergency.report.read'))
        assert log is not None
        assert 'PRIVATE' not in str(log.after_data)


def test_region_aggregation_includes_cases_without_patients(report_client):
    client, sessions = report_client
    login(client)
    with sessions() as db:
        db.add(EmergencyCase(source_case_key='empty', call_date=date(2026, 1, 10), incident_area_code='east'))
        db.commit()
    data = client.get('/emergency/reports/summary?start_date=2026-01-01&end_date=2026-01-31&group_by=region').json()
    assert data['totals']['cases'] == 3
    assert next(x for x in data['groups'] if x['code'] == 'east') == {
        'code': 'east', 'cases': 1, 'patients': 0, 'patient_share': 0.0}


@pytest.mark.parametrize('query', ['start_date=2026-02-01&end_date=2026-01-01', 'group_by=diagnosis', 'start_date=bad'])
def test_invalid_report_parameters_are_rejected(report_client, query):
    client, _ = report_client
    login(client)
    assert client.get('/emergency/reports/summary?' + query).status_code == 422


def test_exports_share_same_counts_and_disable_spreadsheet_formulas(report_client):
    from openpyxl import load_workbook
    client, sessions = report_client
    login(client)
    params = 'start_date=2026-02-01&end_date=2026-02-01&group_by=hospital'
    response = client.get('/emergency/reports/export?format=xlsx&' + params)
    assert response.status_code == 200
    wb = load_workbook(BytesIO(response.content), data_only=False)
    assert wb['内訳']['A2'].value == '=H2'
    assert wb['内訳']['A2'].data_type == 's'
    assert list(wb['合計'].values)[1][:3] == (1, 1, 1)
    csv = client.get('/emergency/reports/export?format=csv&' + params)
    assert csv.status_code == 200
    assert "'=H2" in csv.content.decode('utf-8-sig')
    assert 'PRIVATE' not in csv.text
    with sessions() as db:
        assert len(db.scalars(select(AuditLog).where(AuditLog.action == 'emergency.report.export')).all()) == 2


def test_permissions_endpoint_returns_only_current_user_codes(report_client):
    client, _ = report_client
    assert client.get('/auth/permissions').status_code == 401
    login(client)
    data = client.get('/auth/permissions').json()
    assert 'emergency.report.read' in data['permissions']
    assert 'emergency.patient.read' not in data['permissions']
