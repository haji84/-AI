"""Disposable PostgreSQL upgrade, competing Human review, immutable evidence."""
from concurrent.futures import ThreadPoolExecutor
from datetime import date
import os
from pathlib import Path
import shutil
from threading import Barrier
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select, func, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session


def test_evaluation_upgrade_retry_concurrent_review_and_immutable_evidence(tmp_path, monkeypatch):
    url = os.environ.get('FIRE_AI_TEST_POSTGRES_URL')
    if not url:
        pytest.skip('actual PostgreSQL upgrade/competing review runs in CI')
    from app.main import app
    from app.db import get_db
    from app.migrations import apply_migrations
    from app.models import User, UserRole, Facility, LegalProfile, LegalProfileJurisdiction, LegalJurisdiction, AuditLog
    from app.hazardous_evaluation_models import HazardousEvaluation
    from app.rbac_seed import seed_rbac
    from app.security import hash_password
    from app.settings import settings
    from test_hazardous_rule_authoring import structured_rule
    root = Path(__file__).resolve().parents[2]
    baseline = tmp_path / 'baseline'; baseline.mkdir()
    bounded = tmp_path / 'bounded'; bounded.mkdir()
    for path in (root / 'db/migrations').glob('*.sql'):
        if path.name <= '057_hazardous_evaluations.sql':
            shutil.copy2(path, bounded / path.name)
        if path.name < '057_hazardous_evaluations.sql':
            shutil.copy2(path, baseline / path.name)
    name = 'fi_hz_eval_' + uuid4().hex[:16]
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
            actor = User(username='native-evaluation-reviewer', password_hash=hash_password('synthetic-evaluation-password'))
            facility = Facility(name='Synthetic preserved facility', status='active')
            db.add_all([actor, facility]); db.flush()
            db.add(UserRole(user_id=actor.user_id, role_id=roles['system_admin'].role_id))
            db.commit(); building_id = facility.building_id
        assert apply_migrations(target_url, bounded) == ['057_hazardous_evaluations.sql']
        assert apply_migrations(target_url, bounded) == []
        identity = structured_rule(target)
        def sessions():
            with Session(target, expire_on_commit=False) as db:
                yield db
        app.dependency_overrides[get_db] = sessions
        with TestClient(app) as client:
            assert client.post('/auth/login', json={'username': 'native-evaluation-reviewer',
                'password': 'synthetic-evaluation-password'}).status_code == 200
            approved = client.post('/legal-rules/versions/' + identity + '/approve', json={'expected_version': 1})
            assert approved.status_code == 200, approved.text
            with Session(target) as db:
                assert db.get(Facility, building_id).name == 'Synthetic preserved facility'
                profile = LegalProfile(code='SYN-NATIVE-EVAL', name='Synthetic native evaluation profile')
                db.add(profile); db.flush()
                db.add(LegalProfileJurisdiction(legal_profile_id=profile.legal_profile_id,
                    jurisdiction_id=db.scalar(select(LegalJurisdiction)).jurisdiction_id))
                db.commit(); profile_id = profile.legal_profile_id
            installation = client.post('/hazardous/installations', json={'building_id': building_id,
                'name': 'Synthetic native installation', 'category_label': 'Explicit synthetic category', 'materials': [
                    {'name': 'Synthetic material', 'quantity': '100', 'quantity_unit': 'L'}]})
            assert installation.status_code == 201, installation.text
            candidate = client.post('/hazardous/installations/' + installation.json()['installation_id'] + '/evaluations',
                json={'expected_installation_version': 1, 'legal_profile_id': profile_id, 'evaluation_date': '2026-10-09'})
            assert candidate.status_code == 201, candidate.text
            evaluation_id = candidate.json()['evaluation_id']
            assert candidate.json()['results'][0]['state'] == 'matched'
            cookies = dict(client.cookies); barrier = Barrier(2)
            def review():
                with TestClient(app) as contender:
                    contender.cookies.update(cookies); barrier.wait(timeout=10)
                    response = contender.post('/hazardous/evaluations/' + evaluation_id + '/review',
                        json={'expected_version': 1, 'acknowledged': True, 'reason': 'Synthetic independent Human review'})
                    return response.status_code, response.text
            with ThreadPoolExecutor(max_workers=2) as pool:
                futures = [pool.submit(review) for _ in range(2)]
                results = [future.result(timeout=30) for future in futures]
            assert sorted(status for status, _ in results) == [200, 409], results
            with Session(target) as db:
                saved = db.get(HazardousEvaluation, evaluation_id)
                assert saved.status == 'reviewed' and saved.version == 2
                assert saved.results == candidate.json()['results']
                assert db.scalar(select(func.count()).select_from(AuditLog).where(
                    AuditLog.action == 'hazardous.evaluation.review', AuditLog.entity_id == evaluation_id)) == 1
            for statement in ("UPDATE hazardous_evaluations SET results='[]' WHERE evaluation_id=:identity",
                'DELETE FROM hazardous_evaluations WHERE evaluation_id=:identity'):
                with pytest.raises(IntegrityError):
                    with target.begin() as connection:
                        connection.execute(text(statement), {'identity': evaluation_id})
    finally:
        app.dependency_overrides.clear(); app.dependency_overrides.update(previous)
        if target is not None:
            target.dispose()
        with admin.connect() as connection:
            connection.exec_driver_sql('DROP DATABASE IF EXISTS ' + name + ' WITH (FORCE)')
        admin.dispose()
