"""Existing DB upgrade and competing Human application on actual PostgreSQL."""
from concurrent.futures import ThreadPoolExecutor
from datetime import date
import json
import os
from pathlib import Path
import shutil
from threading import Barrier
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select, func
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session


def test_postgres_notice_upgrade_and_competing_apply(tmp_path, monkeypatch):
    url = os.environ.get('FIRE_AI_TEST_POSTGRES_URL')
    if not url: pytest.skip('actual PostgreSQL upgrade and competing apply run in CI')
    from app.main import app
    from app.db import get_db
    from app.migrations import apply_migrations
    from app.models import Employee, User, UserRole, AuditLog
    from app.personnel import OrganizationUnit, EmployeeAssignment, AssignmentRole
    from app.personnel_intake_models import PersonnelDocumentProposal
    from app.rbac_seed import seed_rbac
    from app.security import hash_password
    from app.settings import settings
    root = Path(__file__).resolve().parents[2]
    baseline = tmp_path / 'baseline'; baseline.mkdir()
    for path in (root / 'db/migrations').glob('*.sql'):
        if path.name != '055_personnel_document_intake.sql': shutil.copy2(path, baseline / path.name)
    name = 'fi_notice_' + uuid4().hex[:16]
    admin = create_engine(make_url(url).set(database='postgres'), isolation_level='AUTOCOMMIT')
    target = None; previous = dict(app.dependency_overrides)
    monkeypatch.setattr(settings, 'storage_root', str(tmp_path / 'storage'))
    try:
        with admin.connect() as connection: connection.exec_driver_sql('CREATE DATABASE ' + name)
        target_url = make_url(url).set(database=name).render_as_string(hide_password=False)
        apply_migrations(target_url, baseline)
        target = create_engine(target_url)
        with Session(target) as db:
            roles = seed_rbac(db)
            actor = User(username='native-notice', password_hash=hash_password('synthetic-native-password'))
            crew = Employee(employee_code='SYN01', display_name='Synthetic native crew', title='Captain')
            old = OrganizationUnit(code='OLD', name='Synthetic old station')
            new = OrganizationUnit(code='NEW', name='Synthetic new station')
            db.add_all([actor, crew, old, new]); db.flush()
            db.add(UserRole(user_id=actor.user_id, role_id=roles['system_admin'].role_id))
            db.add(EmployeeAssignment(employee_id=crew.employee_id, organization_id=old.organization_id,
                title='Captain', kind='primary', valid_from=date(2026, 1, 1)))
            db.commit(); employee_id = crew.employee_id
        assert apply_migrations(target_url, root / 'db/migrations') == ['055_personnel_document_intake.sql']
        assert apply_migrations(target_url, root / 'db/migrations') == []
        def sessions():
            with Session(target, expire_on_commit=False) as db: yield db
        app.dependency_overrides[get_db] = sessions
        with TestClient(app) as client:
            assert client.post('/auth/login', json={'username': 'native-notice', 'password': 'synthetic-native-password'}).status_code == 200
            raw = json.dumps({'employee_code': 'SYN01', 'organization_code': 'NEW', 'title': 'Captain',
                'kind': 'primary', 'valid_from': '2026-11-01', 'mode': 'transfer'}).encode()
            uploaded = client.post('/documents/upload', data={'document_type': 'personnel_notice'},
                files={'file': ('synthetic-native-notice.txt', raw, 'text/plain')})
            assert uploaded.status_code == 201, uploaded.text
            created = client.post('/personnel-intake/proposals', json={'document_id': uploaded.json()['document_id']})
            assert created.status_code == 201, created.text
            row = created.json(); path = '/personnel-intake/proposals/' + row['proposal_id']
            reviewed = client.post(path + '/review', json={'expected_version': row['version'],
                'reason': 'Synthetic native Human review', 'acknowledged': True})
            assert reviewed.status_code == 200, reviewed.text
            with Session(target) as db:
                assert db.scalar(select(func.count()).select_from(EmployeeAssignment)) == 1
                assert db.get(Employee, employee_id).version == 1
            payload = {'expected_version': reviewed.json()['version'], 'reason': 'Synthetic competing Human application', 'acknowledged': True}
            barrier = Barrier(2); cookies = dict(client.cookies)
            def apply():
                with TestClient(app) as contender:
                    contender.cookies.update(cookies); barrier.wait(timeout=10)
                    response = contender.post(path + '/apply', json=payload)
                    return response.status_code, response.text
            with ThreadPoolExecutor(max_workers=2) as pool:
                futures = [pool.submit(apply) for _ in range(2)]
                results = [future.result(timeout=30) for future in futures]
            assert sorted(status for status, _ in results) == [200, 409], results
            with Session(target) as db:
                assert db.scalar(select(func.count()).select_from(EmployeeAssignment)) == 2
                assert db.scalar(select(func.count()).select_from(AssignmentRole)) == 0
                assert db.get(Employee, employee_id).version == 2
                saved = db.get(PersonnelDocumentProposal, row['proposal_id'])
                assert saved.status == 'applied' and saved.version == 3
                assert db.scalar(select(func.count()).select_from(AuditLog).where(AuditLog.action == 'personnel.intake.apply')) == 1
                history = db.scalars(select(EmployeeAssignment).order_by(EmployeeAssignment.valid_from)).all()
                assert history[0].valid_to == date(2026, 10, 31) and history[1].valid_from == date(2026, 11, 1)
    finally:
        app.dependency_overrides.clear(); app.dependency_overrides.update(previous)
        if target is not None: target.dispose()
        with admin.connect() as connection:
            connection.exec_driver_sql('DROP DATABASE IF EXISTS ' + name + ' WITH (FORCE)')
        admin.dispose()
