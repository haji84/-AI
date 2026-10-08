"""Synthetic notices enter the real app; Human gates never auto-apply them."""
from datetime import date, timedelta
from hashlib import sha256
import json

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select, func, delete
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.main import app
from app.db import Base, get_db
from app.models import Employee, User, UserRole, RolePermission, Permission, Document, AuditLog
from app.personnel import OrganizationUnit, EmployeeAssignment
from app.rbac_seed import seed_rbac
from app.security import hash_password
from app.settings import settings


@pytest.fixture
def notice(tmp_path, monkeypatch):
    engine = create_engine('sqlite+pysqlite:///:memory:', connect_args={'check_same_thread': False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    monkeypatch.setattr(settings, 'storage_root', str(tmp_path))
    with Session(engine, expire_on_commit=False) as db:
        roles = seed_rbac(db)
        actor = User(username='notice-admin', password_hash=hash_password('synthetic-notice-password'))
        person = Employee(employee_code='S001', display_name='PRIVATE synthetic employee', title='Captain')
        old = OrganizationUnit(code='OLD', name='PRIVATE old station')
        new = OrganizationUnit(code='NEW', name='PRIVATE new station')
        db.add_all([actor, person, old, new]); db.flush()
        db.add(UserRole(user_id=actor.user_id, role_id=roles['system_admin'].role_id))
        assignment = EmployeeAssignment(employee_id=person.employee_id, organization_id=old.organization_id,
            title='Captain', kind='primary', valid_from=date(2026, 1, 1))
        db.add(assignment); db.commit()
        identities = dict(user_id=actor.user_id, employee_id=person.employee_id, old_id=old.organization_id,
            new_id=new.organization_id, assignment_id=assignment.assignment_id, role_id=roles['system_admin'].role_id)
    def dependency():
        with Session(engine, expire_on_commit=False) as db:
            yield db
    previous = dict(app.dependency_overrides)
    app.dependency_overrides[get_db] = dependency
    with TestClient(app) as client:
        assert client.post('/auth/login', json={'username': 'notice-admin', 'password': 'synthetic-notice-password'}).status_code == 200
        def document(**changes):
            content = dict(employee_code='S001', organization_code='NEW', title='Captain', kind='primary',
                valid_from='2026-11-01', valid_to=None, mode='transfer')
            content.update(changes)
            raw = json.dumps(content).encode()
            response = client.post('/documents/upload', data={'document_type': 'personnel_notice'},
                files={'file': ('synthetic-notice.txt', raw, 'text/plain')})
            assert response.status_code == 201, response.text
            return response.json(), raw
        def candidate(**changes):
            original, raw = document(**changes)
            response = client.post('/personnel-intake/proposals', json={'document_id': original['document_id']})
            assert response.status_code == 201, response.text
            return response.json(), original, raw
        yield client, engine, identities, document, candidate, tmp_path
    app.dependency_overrides.clear(); app.dependency_overrides.update(previous)
    engine.dispose()


def decide(client, row, action, **changes):
    return client.post('/personnel-intake/proposals/'+row['proposal_id']+'/'+action,
        json={'expected_version': row['version'], 'reason': 'Synthetic Human notice verification', 'acknowledged': True, **changes})


def test_candidate_does_not_change_assignment(notice):
    client, engine, ids, _, candidate, _ = notice
    row, doc, raw = candidate()
    assert row['status'] == 'candidate' and row['version'] == 1
    assert row['source_sha256'] == sha256(raw).hexdigest()
    assert row['source_document_id'] == doc['document_id']
    assert row['before_snapshot']['employee_version'] == 1
    assert row['after_snapshot']['organization_id'] == ids['new_id']
    assert row['after_snapshot']['valid_from'] == '2026-11-01'
    assert row['errors'] == []
    with Session(engine) as db:
        assert db.scalar(select(func.count()).select_from(EmployeeAssignment)) == 1
        assert db.get(Employee, ids['employee_id']).version == 1
    assert decide(client, row, 'apply').status_code == 409


def test_apply_reason_stays_protected_from_audit_only_reader(notice):
    from app.personnel_intake_models import PersonnelDocumentProposal
    client, engine, ids, _, candidate, _ = notice
    row, _, _ = candidate()
    reviewed = decide(client, row, 'review').json()
    reason = 'PRIVATE SYNTHETIC PERSONNEL NOTICE REASON'
    applied = decide(client, reviewed, 'apply', reason=reason)
    assert applied.status_code == 200, applied.text
    with Session(engine) as db:
        assert db.get(PersonnelDocumentProposal, row['proposal_id']).reason == reason
        allowed = db.scalar(select(Permission).where(Permission.code == 'audit.read'))
        db.execute(delete(RolePermission).where(RolePermission.role_id == ids['role_id'],
            RolePermission.permission_id != allowed.permission_id)); db.commit()
    assert client.get('/personnel-intake/proposals').status_code == 403
    visible = client.get('/administration/audit')
    assert visible.status_code == 200, visible.text
    assert reason not in visible.text
    assignments = [entry for entry in visible.json() if entry['action'] in ('personnel.transfer', 'personnel.assignment.close')]
    assert len(assignments) == 2
    assert all(row['proposal_id'] in json.dumps(entry) for entry in assignments)


@pytest.mark.parametrize('changes,error', [
    ({'employee_code': 'UNKNOWN'}, 'employee_code'), ({'organization_code': 'UNKNOWN'}, 'organization_code'),
    ({'title': 'UNKNOWN'}, 'title'), ({'title_code': 'UNKNOWN'}, 'unsupported'),
])
def test_unknown_codes(notice, changes, error):
    client, engine, _, _, candidate, _ = notice
    row, _, _ = candidate(**changes)
    assert error in json.dumps(row['errors'])
    assert decide(client, row, 'review').status_code == 422
    with Session(engine) as db:
        assert db.scalar(select(func.count()).select_from(EmployeeAssignment)) == 1


def test_source_permissions(notice):
    client, engine, ids, _, candidate, _ = notice
    row, doc, _ = candidate()
    with Session(engine) as db:
        permitted = db.scalar(select(Permission).where(Permission.code == 'document.read'))
        db.execute(delete(RolePermission).where(RolePermission.role_id == ids['role_id'], RolePermission.permission_id != permitted.permission_id))
        db.commit()
    assert client.get('/documents/'+doc['document_id']).status_code == 403
    assert client.get('/documents/'+doc['document_id']+'/download').status_code == 403
    response = client.get('/personnel-intake/proposals')
    assert response.status_code == 403 and 'PRIVATE' not in response.text
    assert client.get('/personnel-intake/proposals/'+row['proposal_id']).status_code == 403
    assert decide(client, row, 'review').status_code == 403


def test_source_integrity(notice):
    client, engine, ids, _, candidate, root = notice
    row, doc, _ = candidate()
    reviewed = decide(client, row, 'review')
    assert reviewed.status_code == 200, reviewed.text
    with Session(engine) as db:
        original = db.get(Document, doc['document_id'])
        path = root / original.storage_path
    path.write_bytes(b'changed synthetic notice')
    assert decide(client, reviewed.json(), 'apply').status_code == 409
    with Session(engine) as db:
        assert db.get(Employee, ids['employee_id']).version == 1
        assert db.scalar(select(func.count()).select_from(EmployeeAssignment)) == 1


@pytest.mark.parametrize('target', ['employee', 'organization', 'assignment'])
def test_stale_and_atomic(notice, target):
    client, engine, ids, _, candidate, _ = notice
    row, _, _ = candidate()
    reviewed = decide(client, row, 'review')
    assert reviewed.status_code == 200, reviewed.text
    with Session(engine) as db:
        model, key = {'employee': (Employee, ids['employee_id']), 'organization': (OrganizationUnit, ids['new_id']),
            'assignment': (EmployeeAssignment, ids['assignment_id'])}[target]
        db.get(model, key).version += 1; db.commit()
    assert decide(client, reviewed.json(), 'apply').status_code == 409
    with Session(engine) as db:
        assert db.scalar(select(func.count()).select_from(EmployeeAssignment)) == 1
        assert db.get(EmployeeAssignment, ids['assignment_id']).valid_to is None


def test_future_and_idempotence(notice):
    client, engine, ids, _, candidate, _ = notice
    row, _, _ = candidate()
    assert decide(client, row, 'review', acknowledged=False).status_code == 422
    reviewed = decide(client, row, 'review'); assert reviewed.status_code == 200, reviewed.text
    applied = decide(client, reviewed.json(), 'apply'); assert applied.status_code == 200, applied.text
    assert applied.json()['status'] == 'applied'
    assert applied.json()['applied_assignment_id']
    assert decide(client, reviewed.json(), 'apply').status_code == 409
    history = client.get('/administration/staff/'+ids['employee_id']+'/assignments').json()
    assert len(history) == 2
    old = next(item for item in history if item['assignment_id'] == ids['assignment_id'])
    new = next(item for item in history if item['assignment_id'] == applied.json()['applied_assignment_id'])
    assert old['valid_to'] == '2026-10-31' and new['valid_from'] == '2026-11-01'
    assert new['role_ids'] == []
    with Session(engine) as db:
        assert db.get(Employee, ids['employee_id']).version == 2
        actions = set(db.scalars(select(AuditLog.action)))
        assert {'personnel.intake.create', 'personnel.intake.review', 'personnel.intake.apply', 'personnel.transfer'} <= actions


def test_ambiguous_duplicate_source_fields_never_select_a_winning_code(notice):
    client, engine, _, _, _, _ = notice
    raw = b'{"employee_code":"UNKNOWN","employee_code":"S001","organization_code":"NEW","title":"Captain","kind":"primary","valid_from":"2026-11-01","mode":"transfer"}'
    doc = client.post('/documents/upload', data={'document_type': 'personnel_notice'},
        files={'file': ('synthetic-ambiguous.txt', raw, 'text/plain')}).json()
    response = client.post('/personnel-intake/proposals', json={'document_id': doc['document_id']})
    assert response.status_code == 201, response.text
    row = response.json()
    assert row['errors'], 'duplicate code must remain unresolved, not last-value-wins'
    assert decide(client, row, 'review').status_code == 422


@pytest.mark.parametrize('value', [1, 'true', None])
def test_human_acknowledgement_requires_literal_boolean_true(notice, value):
    client, _, _, _, candidate, _ = notice
    row, _, _ = candidate()
    assert decide(client, row, 'review', acknowledged=value).status_code == 422


def test_assignment_failure_rolls_back_notice_and_employee_together(notice):
    client, engine, ids, _, candidate, _ = notice
    row, _, _ = candidate(mode='assignment')
    reviewed = decide(client, row, 'review'); assert reviewed.status_code == 200, reviewed.text
    # Existing primary assignment is open-ended: non-transfer must conflict.
    assert decide(client, reviewed.json(), 'apply').status_code == 409
    with Session(engine) as db:
        assert db.get(Employee, ids['employee_id']).version == 1
        assert db.get(EmployeeAssignment, ids['assignment_id']).valid_to is None
        from app.personnel_intake_models import PersonnelDocumentProposal
        saved = db.get(PersonnelDocumentProposal, row['proposal_id'])
        assert saved.status == 'reviewed' and saved.version == 2 and saved.applied_assignment_id is None


def test_original_postflight_failure_rolls_back_new_and_closed_assignments(notice, monkeypatch):
    from app import personnel_intake_service as svc
    from app.personnel_intake_models import PersonnelDocumentProposal
    client, engine, ids, _, candidate, root = notice
    row, doc, _ = candidate()
    reviewed = decide(client, row, 'review'); assert reviewed.status_code == 200, reviewed.text
    real = svc.original
    calls = []
    def concurrent_original_change(*args, **kwargs):
        calls.append(True)
        if len(calls) == 2:
            with Session(engine) as other:
                path = root / other.get(Document, doc['document_id']).storage_path
            path.write_bytes(b'concurrent synthetic original change')
        return real(*args, **kwargs)
    monkeypatch.setattr(svc, 'original', concurrent_original_change)
    assert decide(client, reviewed.json(), 'apply').status_code == 409
    with Session(engine) as db:
        assert db.get(Employee, ids['employee_id']).version == 1
        assert db.get(EmployeeAssignment, ids['assignment_id']).valid_to is None
        assert db.scalar(select(func.count()).select_from(EmployeeAssignment)) == 1
        assert db.get(PersonnelDocumentProposal, row['proposal_id']).status == 'reviewed'


def test_extraction_runs_outside_database_transaction(notice, monkeypatch):
    from sqlalchemy import event
    from app import personnel_intake_service as svc
    client, _, _, document, _, _ = notice
    doc, _ = document()
    sessions = []
    def begun(session, transaction, connection):
        sessions.append(session)
    real = svc.extract_document
    def extract_without_transaction(source):
        assert sessions, 'actual application DB was not exercised'
        assert not any(session.in_transaction() for session in sessions), 'OCR must not hold administration transaction'
        return real(source)
    event.listen(Session, 'after_begin', begun)
    monkeypatch.setattr(svc, 'extract_document', extract_without_transaction)
    try:
        response = client.post('/personnel-intake/proposals', json={'document_id': doc['document_id']})
        assert response.status_code == 201, response.text
    finally:
        event.remove(Session, 'after_begin', begun)
