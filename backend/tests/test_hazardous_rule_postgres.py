"""Synthetic approved-rule mechanics on a disposable actual PostgreSQL database."""
from concurrent.futures import ThreadPoolExecutor
import os
from pathlib import Path
import shutil
from threading import Barrier
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select, func, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session


def test_hazardous_authoring_upgrade_and_competing_human_approval(tmp_path, monkeypatch):
    url = os.environ.get('FIRE_AI_TEST_POSTGRES_URL')
    if not url:
        pytest.skip('actual PostgreSQL upgrade/competing approval runs in CI')
    from app.main import app
    from app.db import get_db
    from app.migrations import apply_migrations
    from app.models import User, UserRole, LegalRule, LegalRuleVersion, AuditLog
    from app.rbac_seed import seed_rbac
    from app.security import hash_password
    from app.settings import settings
    from app.hazardous_rule_models import HazardousRuleApproval
    from test_hazardous_rule_authoring import structured_rule
    root = Path(__file__).resolve().parents[2]
    baseline = tmp_path / 'baseline'; baseline.mkdir()
    authoring_bound = tmp_path / 'authoring-bound'; authoring_bound.mkdir()
    for path in (root / 'db/migrations').glob('*.sql'):
        if path.name < '057_hazardous_evaluations.sql':
            shutil.copy2(path, authoring_bound / path.name)
        if path.name < '056_hazardous_rule_authoring.sql':
            shutil.copy2(path, baseline / path.name)
    name = 'fi_hz_rule_' + uuid4().hex[:16]
    admin = create_engine(make_url(url).set(database='postgres'), isolation_level='AUTOCOMMIT')
    target = None
    previous = dict(app.dependency_overrides)
    monkeypatch.setattr(settings, 'storage_root', str(tmp_path))
    try:
        with admin.connect() as connection:
            connection.exec_driver_sql('CREATE DATABASE ' + name)
        target_url = make_url(url).set(database=name).render_as_string(hide_password=False)
        apply_migrations(target_url, baseline)
        target = create_engine(target_url)
        with Session(target) as db:
            roles = seed_rbac(db)
            actor = User(username='native-hazardous-author', password_hash=hash_password('synthetic-rule-password'))
            legacy = LegalRule(rule_code='SYN-LEGACY-PRESERVED', name='Synthetic old rule', domain='submission_requirement')
            db.add_all([actor, legacy]); db.flush()
            db.add(UserRole(user_id=actor.user_id, role_id=roles['system_admin'].role_id))
            db.commit(); legacy_id = legacy.rule_id
        assert apply_migrations(target_url, authoring_bound) == ['056_hazardous_rule_authoring.sql']
        assert apply_migrations(target_url, authoring_bound) == []
        with Session(target) as db:
            assert db.get(LegalRule, legacy_id).domain == 'submission_requirement'
        identity = structured_rule(target, with_citation=False)
        def sessions():
            with Session(target, expire_on_commit=False) as db:
                yield db
        app.dependency_overrides[get_db] = sessions
        with TestClient(app) as client:
            assert client.post('/auth/login', json={'username': 'native-hazardous-author',
                'password': 'synthetic-rule-password'}).status_code == 200
            from app.models import LegalProvision
            with Session(target) as db:
                provision_id = db.scalar(select(LegalProvision)).legal_provision_id
            citation = client.post('/legal-rules/versions/' + identity + '/citations',
                json={'legal_provision_id': provision_id, 'citation_role': 'primary'})
            assert citation.status_code == 201, citation.text
            cookies = dict(client.cookies); barrier = Barrier(2)
            def approve():
                with TestClient(app) as contender:
                    contender.cookies.update(cookies); barrier.wait(timeout=10)
                    response = contender.post('/legal-rules/versions/' + identity + '/approve',
                        json={'expected_version': 2})
                    return response.status_code, response.text
            with ThreadPoolExecutor(max_workers=2) as pool:
                futures = [pool.submit(approve) for _ in range(2)]
                results = [future.result(timeout=30) for future in futures]
            assert sorted(status for status, _ in results) == [200, 409], results
            with Session(target) as db:
                saved = db.get(LegalRuleVersion, identity)
                assert saved.status == 'approved' and saved.version == 3
                assert db.scalar(select(func.count()).select_from(AuditLog).where(
                    AuditLog.action == 'legal_rule_version.approve', AuditLog.entity_id == identity)) == 1
                approval = db.get(HazardousRuleApproval, identity)
                assert approval is not None and approval.rule_snapshot['version'] == 3
                assert len(approval.citations) == 1
            for statement in ('UPDATE hazardous_rule_approvals SET citations=\'[]\' WHERE legal_rule_version_id=:identity',
                'DELETE FROM hazardous_rule_approvals WHERE legal_rule_version_id=:identity'):
                with pytest.raises(IntegrityError):
                    with target.begin() as connection:
                        connection.execute(text(statement), {'identity': identity})
    finally:
        app.dependency_overrides.clear(); app.dependency_overrides.update(previous)
        if target is not None:
            target.dispose()
        with admin.connect() as connection:
            connection.exec_driver_sql('DROP DATABASE IF EXISTS ' + name + ' WITH (FORCE)')
        admin.dispose()
