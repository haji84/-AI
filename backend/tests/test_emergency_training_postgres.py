"""Disposable native PostgreSQL; synthetic data, not ZBook/accuracy evidence."""
from concurrent.futures import ThreadPoolExecutor
import os
from pathlib import Path
import shutil
from threading import Barrier
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from test_emergency_audit_api import DETAIL, login, pdf, upload
from test_emergency_training import T, prepared, dataset_input


def test_native_training_upgrade_immutable_registry_and_competing_duplicate_families(tmp_path, monkeypatch):
    base = os.environ.get('FIRE_AI_TEST_POSTGRES_URL')
    if not base:
        pytest.skip('actual PostgreSQL training registry upgrade/immutability/concurrency requires FIRE_AI_TEST_POSTGRES_URL')
    from app.db import get_db
    from app.main import app
    from app.migrations import apply_migrations
    from app.models import Employee, Permission, Role, RolePermission, User, UserRole
    from app.security import hash_password
    from app.settings import settings
    from app.emergency_training_models import TrainingFamilyMember

    root = Path(__file__).resolve().parents[2]
    before = tmp_path / 'through_060'
    before.mkdir()
    for path in (root / 'db/migrations').glob('*.sql'):
        if path.name < '061_emergency_training_registry.sql':
            shutil.copy2(path, before / path.name)
    admin = create_engine(make_url(base).set(database='postgres'), isolation_level='AUTOCOMMIT')
    name = 'fi_train_' + uuid4().hex[:16]
    with admin.connect() as db:
        db.exec_driver_sql('CREATE DATABASE '+name)
    target = None
    overrides = dict(app.dependency_overrides)
    try:
        url = make_url(base).set(database=name).render_as_string(hide_password=False)
        apply_migrations(url, before)
        assert apply_migrations(url, root / 'db/migrations') == ['061_emergency_training_registry.sql']
        assert apply_migrations(url, root / 'db/migrations') == []
        target = create_engine(url)
        key = tmp_path / 'external-key'
        key.write_bytes(os.urandom(32)); key.chmod(0o600)
        monkeypatch.setattr(settings, 'emergency_audit_enabled', True)
        monkeypatch.setattr(settings, 'emergency_audit_key_file', str(key))
        monkeypatch.setattr(settings, 'storage_root', str(tmp_path / 'storage'))
        monkeypatch.setattr(settings, 'emergency_audit_internal_enabled', False)
        monkeypatch.setattr(settings, 'emergency_audit_ai_model', None)
        with Session(target) as db:
            codes = DETAIL | {'emergency.report.create', 'emergency.report.review',
                              'emergency.audit.configure', 'emergency.audit.read_all'}
            permissions = {c: db.scalar(select(Permission).where(Permission.code == c)) or Permission(code=c)
                           for c in codes}
            db.add_all(permissions.values()); db.flush()
            for who in ['owner', 'reviewer']:
                employee = Employee(display_name='Synthetic training '+who)
                role = Role(code='synthetic-training-'+who, name='Synthetic training')
                db.add_all([employee, role]); db.flush()
                user = User(username='audit-'+who, employee_id=employee.employee_id,
                            password_hash=hash_password('synthetic-audit-password'))
                db.add(user); db.flush()
                db.add(UserRole(user_id=user.user_id, role_id=role.role_id))
                db.add_all(RolePermission(role_id=role.role_id, permission_id=p.permission_id)
                           for p in permissions.values())
            db.commit()
        def sessions():
            with Session(target, expire_on_commit=False, autoflush=False) as db:
                yield db
        app.dependency_overrides[get_db] = sessions
        with TestClient(app) as client:
            login(client)
            reports, families, truths = prepared(client)
            r = client.post(T + '/datasets', json=dataset_input(families, truths))
            assert r.status_code == 201, r.text
            dataset = r.json()
            statements = [
                ("UPDATE emergency_training_family_members SET family_id='00000000-0000-4000-8000-000000000001' WHERE report_id=:id", reports[0]['report_id']),
                ('DELETE FROM emergency_training_family_members WHERE report_id=:id', reports[0]['report_id']),
                ("UPDATE emergency_training_family_partitions SET split='holdout' WHERE family_id=:id", families[0]),
                ('DELETE FROM emergency_training_family_partitions WHERE family_id=:id', families[0]),
                ("UPDATE emergency_training_truths SET payload_cipher='changed' WHERE truth_id=:id", truths[0]['truth_id']),
                ('DELETE FROM emergency_training_truths WHERE truth_id=:id', truths[0]['truth_id']),
                ("UPDATE emergency_training_datasets SET manifest_sha256=repeat('0',64) WHERE dataset_id=:id", dataset['dataset_id']),
                ('DELETE FROM emergency_training_datasets WHERE dataset_id=:id', dataset['dataset_id']),
            ]
            for statement, identity in statements:
                with pytest.raises(IntegrityError) as error:
                    with target.begin() as db:
                        db.execute(text(statement), {'id': identity})
                assert error.value.orig.sqlstate == '23514'
            content = pdf('SYNTHETIC DUPLICATE FAMILY RACE')
            copies = [upload(client, content=content).json() for _ in range(2)]
            barrier = Barrier(2)
            cookies = dict(client.cookies)
            def attach(index):
                with TestClient(app) as contender:
                    contender.cookies.update(cookies)
                    barrier.wait(timeout=10)
                    return contender.post(T+'/families', json={'family_id': str(uuid4()),
                        'report_ids': [copies[index]['report_id']]}).status_code
            with ThreadPoolExecutor(max_workers=2) as pool:
                jobs = [pool.submit(attach, i) for i in range(2)]
                assert sorted(job.result(timeout=30) for job in jobs) == [201, 409]
            with Session(target) as db:
                rows = db.scalars(select(TrainingFamilyMember).where(
                    TrainingFamilyMember.report_id.in_([c['report_id'] for c in copies]))).all()
                assert len(rows) == 1
    finally:
        app.dependency_overrides.clear(); app.dependency_overrides.update(overrides)
        if target:
            target.dispose()
        with admin.connect() as db:
            db.exec_driver_sql('DROP DATABASE '+name+' WITH (FORCE)')
        admin.dispose()
