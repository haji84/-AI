"""Failed authentication evidence must survive HTTP errors without identity leakage."""
from contextlib import contextmanager
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event, select
from sqlalchemy.orm import Session
from sqlalchemy import text
from test_learning import learning_environment

from app.db import Base, get_db
from app.models import AuditLog, Employee, User, UserSession
from app.routers import auth
from app.security import hash_password
from app.settings import Settings
from app.tenant import TenantBoundaryMiddleware, initialize_tenant


@contextmanager
def authentication_environment(tmp_path, host='alpha.test', bound=False):
    engine = create_engine('sqlite+pysqlite:///' + str(tmp_path / 'auth.db'),
                           connect_args={'check_same_thread': False})
    Base.metadata.create_all(engine)
    cfg = Settings(_env_file=None, storage_root=str(tmp_path / 'storage'),
                   tenant_id=str(uuid4()) if bound else None,
                   trusted_hosts=[host] if bound else [])
    if bound:
        initialize_tenant(engine, cfg, 'Synthetic department')
    with Session(engine) as db:
        employee = Employee(display_name='Synthetic authentication subject')
        db.add(employee)
        db.flush()
        user = User(employee_id=employee.employee_id, username='synthetic-login-subject',
                    password_hash=hash_password('synthetic-valid-password'))
        db.add(user)
        db.commit()
        identity = user.user_id
    app = FastAPI()
    if bound:
        app.add_middleware(TenantBoundaryMiddleware, engine=engine, config=cfg)
    app.include_router(auth.router)
    def database():
        with Session(engine) as db:
            yield db
    app.dependency_overrides[get_db] = database
    try:
        with TestClient(app, base_url='http://' + host, raise_server_exceptions=False) as client:
            yield client, engine, identity
    finally:
        engine.dispose()


@pytest.mark.parametrize('condition', ['unknown', 'wrong_password', 'inactive', 'unavailable'])
def test_failed_login_is_durable_anonymous_evidence(tmp_path, condition):
    with authentication_environment(tmp_path) as (client, engine, identity):
        username, password = 'synthetic-login-subject', 'synthetic-valid-password'
        with Session(engine) as db:
            user = db.get(User, identity)
            if condition == 'unknown':
                username = 'synthetic-unknown-user'
            elif condition == 'wrong_password':
                password = 'synthetic-wrong-password'
            elif condition == 'inactive':
                user.active = False
            else:
                db.get(Employee, user.employee_id).active = False
            db.commit()
        response = client.post('/auth/login', json={'username': username, 'password': password},
                               headers={'X-Forwarded-For': '192.0.2.13',
                                        'Cookie': 'untrusted=synthetic-token'})
        assert response.status_code == 401
        assert response.json() == {'detail': 'invalid credentials'}
        assert 'set-cookie' not in response.headers
        # Fresh session proves persistence despite the request's HTTPException.
        with Session(engine) as db:
            events = db.scalars(select(AuditLog)).all()
            assert len(events) == 1
            failed = events[0]
            assert failed.action == 'auth.login_failed'
            assert failed.success is False
            assert failed.user_id is None and failed.entity_id is None
            assert failed.entity_type == 'user'
            assert failed.before_data is None and failed.after_data is None
            assert failed.client_info is None and failed.request_id is None
            assert failed.ai_used is False and failed.ai_model_version is None
            assert not db.scalars(select(UserSession)).all()
            assert db.get(User, identity).last_login_at is None


def test_successful_login_keeps_existing_audit_and_session(tmp_path):
    with authentication_environment(tmp_path) as (client, engine, identity):
        response = client.post('/auth/login', json={'username': 'synthetic-login-subject',
                                                    'password': 'synthetic-valid-password'})
        assert response.status_code == 200 and 'set-cookie' in response.headers
        with Session(engine) as db:
            events = db.scalars(select(AuditLog)).all()
            assert len(events) == 1 and events[0].action == 'auth.login'
            assert events[0].success is True and events[0].user_id == identity
            assert len(db.scalars(select(UserSession)).all()) == 1
            assert db.get(User, identity).last_login_at is not None


def test_audit_storage_failure_cannot_claim_recorded_rejection(tmp_path):
    with authentication_environment(tmp_path) as (client, engine, identity):
        def fail_audit(mapper, connection, target):
            if target.action == 'auth.login_failed':
                raise RuntimeError('Synthetic audit storage failure')
        event.listen(AuditLog, 'before_insert', fail_audit)
        try:
            response = client.post('/auth/login', json={'username': 'synthetic-login-subject',
                                                        'password': 'synthetic-wrong-password'})
        finally:
            event.remove(AuditLog, 'before_insert', fail_audit)
        assert response.status_code == 500
        assert 'set-cookie' not in response.headers
        assert 'Synthetic audit storage failure' not in response.text
        with Session(engine) as db:
            assert not db.scalars(select(AuditLog)).all()
            assert not db.scalars(select(UserSession)).all()
            assert db.get(User, identity).last_login_at is None


def test_repeated_failed_logins_create_individual_evidence(tmp_path):
    with authentication_environment(tmp_path) as (client, engine, _):
        for _ in range(3):
            assert client.post('/auth/login', json={'username': 'synthetic-unknown-user',
                                                    'password': 'synthetic-wrong-password'}).status_code == 401
        with Session(engine) as db:
            assert len(db.scalars(select(AuditLog).where(AuditLog.action == 'auth.login_failed')).all()) == 3


def test_failed_login_evidence_stays_in_selected_department(tmp_path):
    alpha_path, beta_path = tmp_path / 'alpha', tmp_path / 'beta'
    alpha_path.mkdir()
    beta_path.mkdir()
    with authentication_environment(alpha_path, bound=True) as (alpha, alpha_db, _):
        with authentication_environment(beta_path, host='beta.test', bound=True) as (beta, beta_db, _):
            payload = {'username': 'synthetic-unknown-user', 'password': 'synthetic-wrong-password'}
            assert alpha.post('/auth/login', json=payload).status_code == 401
            assert beta.post('/auth/login', json=payload, headers={'Host': 'alpha.test'}).status_code == 421
            with Session(alpha_db) as db:
                assert len(db.scalars(select(AuditLog).where(AuditLog.action == 'auth.login_failed')).all()) == 1
            with Session(beta_db) as db:
                assert not db.scalars(select(AuditLog).where(AuditLog.action == 'auth.login_failed')).all()
            assert beta.post('/auth/login', json=payload).status_code == 401
            with Session(beta_db) as db:
                assert len(db.scalars(select(AuditLog).where(AuditLog.action == 'auth.login_failed')).all()) == 1


def test_failed_login_holds_account_lock_until_durable_audit(learning_environment):
    client, engine = learning_environment
    if engine.dialect.name != 'postgresql':
        pytest.skip('actual PostgreSQL advisory-lock lifecycle runs in CI')
    observed = []
    def inspect_lock(mapper, connection, target):
        if target.action == 'auth.login_failed':
            with engine.begin() as competing:
                observed.append(competing.execute(text(
                    "SELECT pg_try_advisory_xact_lock(hashtext('fire-ai-personnel-administration'))"
                )).scalar_one())
    event.listen(AuditLog, 'before_insert', inspect_lock)
    try:
        response = client.post('/auth/login', json={'username': 'learning-admin',
                                                    'password': 'synthetic-wrong-password'})
    finally:
        event.remove(AuditLog, 'before_insert', inspect_lock)
    assert response.status_code == 401
    assert observed == [False]
    with engine.begin() as connection:
        assert connection.execute(text(
            "SELECT pg_try_advisory_xact_lock(hashtext('fire-ai-personnel-administration'))"
        )).scalar_one() is True
    with Session(engine) as db:
        failed = db.scalars(select(AuditLog).where(AuditLog.action == 'auth.login_failed')).all()
        assert len(failed) == 1 and failed[0].success is False
        assert failed[0].user_id is None and failed[0].entity_id is None
