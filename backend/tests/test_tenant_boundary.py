import os
os.environ.setdefault('FIRE_AI_DATABASE_URL', 'sqlite+pysqlite:///:memory:')
from pathlib import Path
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.db import Base
from app.models import Employee, Facility
from app.settings import Settings


def config(tmp_path, tenant_id=None, host='alpha.test'):
    return Settings(_env_file=None, database_url='sqlite+pysqlite:///:memory:',
        storage_root=str(tmp_path), tenant_id=tenant_id or str(uuid4()), trusted_hosts=[host])


def database():
    # Feature import belongs inside the test so absence is a test failure, not collection failure.
    from app.tenant import TenantIdentity
    engine = create_engine('sqlite+pysqlite:///:memory:', connect_args={'check_same_thread':False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    return engine


def test_initialize_binds_db_and_originals_idempotently(tmp_path):
    from app.tenant import initialize_tenant, validate_binding, TenantIdentity
    engine, cfg = database(), config(tmp_path / 'alpha')
    initialize_tenant(engine, cfg, 'Synthetic alpha')
    initialize_tenant(engine, cfg, 'Synthetic alpha')
    assert validate_binding(engine, cfg)['tenant_id'] == cfg.tenant_id
    with Session(engine) as db:
        assert len(db.scalars(select(TenantIdentity)).all()) == 1
    engine.dispose()


def test_no_identity_fails_without_writing_marker(tmp_path):
    from app.tenant import validate_binding, TenantBoundaryError
    engine, cfg = database(), config(tmp_path)
    with pytest.raises(TenantBoundaryError): validate_binding(engine, cfg)
    assert not (tmp_path / 'tenant-identity.json').exists()
    engine.dispose()


def test_wrong_tenant_db_rejected_and_not_reassigned(tmp_path):
    from app.tenant import initialize_tenant, validate_binding, TenantBoundaryError
    engine, alpha = database(), config(tmp_path / 'alpha')
    beta = config(tmp_path / 'beta')
    initialize_tenant(engine, alpha, 'Alpha')
    with pytest.raises(TenantBoundaryError): initialize_tenant(engine, beta, 'Beta', adopt_existing=True)
    with pytest.raises(TenantBoundaryError): validate_binding(engine, beta)
    assert validate_binding(engine, alpha)['tenant_id'] == alpha.tenant_id
    engine.dispose()


def test_wrong_storage_marker_rejected_before_db_association(tmp_path):
    from app.tenant import initialize_tenant, TenantBoundaryError, TenantIdentity
    first, second = database(), database()
    alpha, beta = config(tmp_path), config(tmp_path)
    initialize_tenant(first, alpha, 'Alpha')
    with pytest.raises(TenantBoundaryError): initialize_tenant(second, beta, 'Beta')
    with Session(second) as db: assert db.get(TenantIdentity, 1) is None
    first.dispose(); second.dispose()


def test_existing_records_need_explicit_adoption(tmp_path):
    from app.tenant import initialize_tenant, validate_binding, TenantBoundaryError
    engine, cfg = database(), config(tmp_path / 'alpha')
    with Session(engine) as db:
        db.add(Employee(display_name='Synthetic legacy'))
        db.commit()
    with pytest.raises(TenantBoundaryError): initialize_tenant(engine, cfg, 'Alpha')
    initialize_tenant(engine, cfg, 'Alpha', adopt_existing=True)
    assert validate_binding(engine, cfg)['tenant_id'] == cfg.tenant_id
    with Session(engine) as db: assert len(db.scalars(select(Employee)).all()) == 1
    engine.dispose()


def test_unmarked_originals_need_explicit_adoption(tmp_path):
    from app.tenant import initialize_tenant, TenantBoundaryError
    engine, cfg = database(), config(tmp_path)
    (tmp_path / 'original.pdf').write_bytes(b'synthetic original')
    with pytest.raises(TenantBoundaryError): initialize_tenant(engine, cfg, 'Alpha')
    initialize_tenant(engine, cfg, 'Alpha', adopt_existing=True)
    assert (tmp_path / 'original.pdf').read_bytes() == b'synthetic original'
    engine.dispose()


@pytest.mark.parametrize('kwargs', [dict(production_mode=True),
    dict(production_mode=True, tenant_id=str(uuid4()), cookie_secure=True, trusted_hosts=['*']),
    dict(tenant_id='invalid'), dict(production_mode=True, tenant_id=str(uuid4()), cookie_secure=True,
         trusted_hosts=['alpha.test'], database_url='sqlite+pysqlite:///test.db')])
def test_invalid_production_config_is_rejected(kwargs):
    from pydantic import ValidationError
    with pytest.raises(ValidationError): Settings(_env_file=None, **kwargs)


def test_unknown_host_and_wrong_cookie_cannot_access_other_tenant(tmp_path):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from sqlalchemy.orm import sessionmaker
    from app.tenant import initialize_tenant, TenantBoundaryMiddleware
    from app.db import get_db
    from app.models import User, UserRole
    from app.rbac_seed import seed_rbac
    from app.routers import auth, facilities
    from app.security import hash_password
    clients=[]; engines=[]
    shared_id=str(uuid4())
    for slug in ['alpha','beta']:
        engine, cfg=database(),config(tmp_path / slug, host=slug+'.test')
        initialize_tenant(engine,cfg,slug)
        sessions=sessionmaker(bind=engine,expire_on_commit=False)
        with sessions() as db:
            roles=seed_rbac(db)
            user=User(username='same-id',password_hash=hash_password(slug+'-long-password'))
            db.add(user);db.flush();db.add(UserRole(user_id=user.user_id,role_id=roles['system_admin'].role_id))
            db.add(Facility(building_id=shared_id,name=slug))
            db.commit()
        application=FastAPI()
        application.add_middleware(TenantBoundaryMiddleware, engine=engine, config=cfg)
        application.include_router(auth.router);application.include_router(facilities.router)
        def dependency_for(factory):
            def dependency():
                with factory() as db:yield db
            return dependency
        application.dependency_overrides[get_db]=dependency_for(sessions)
        clients.append(TestClient(application,base_url='http://'+slug+'.test'));engines.append(engine)
    alpha,beta=clients
    assert alpha.post('/auth/login',json={'username':'same-id','password':'alpha-long-password'}).status_code==200
    token=alpha.cookies.get('fire_ai_session')
    assert alpha.get('/facilities/'+shared_id).json()['name']=='alpha'
    assert beta.get('/facilities/'+shared_id,headers={'Cookie':'fire_ai_session='+token}).status_code==401
    assert beta.post('/auth/login',json={'username':'same-id','password':'beta-long-password'}).status_code==200
    assert beta.get('/facilities/'+shared_id).json()['name']=='beta'
    assert alpha.get('/auth/me',headers={'Host':'beta.test'}).status_code==421
    assert alpha.get('/auth/me',headers={'X-Tenant-ID':'beta'}).status_code==200
    for client in clients:client.close()
    for engine in engines:engine.dispose()


def test_initialization_records_human_admin_operation_once(tmp_path):
    from app.tenant import initialize_tenant
    from app.models import AuditLog
    engine, cfg = database(), config(tmp_path)
    initialize_tenant(engine, cfg, 'Alpha')
    initialize_tenant(engine, cfg, 'Alpha')
    with Session(engine) as db:
        audits = db.scalars(select(AuditLog).where(AuditLog.action == 'tenant.initialize')).all()
        assert len(audits) == 1
        assert audits[0].after_data == {'tenant_id': cfg.tenant_id, 'name': 'Alpha', 'adopt_existing': False}
        assert not audits[0].ai_used
    engine.dispose()


def test_marker_corruption_or_removal_fails_closed(tmp_path):
    from app.tenant import initialize_tenant, validate_binding, TenantBoundaryError
    engine, cfg = database(), config(tmp_path)
    initialize_tenant(engine, cfg, 'Alpha')
    marker = tmp_path / 'tenant-identity.json'
    marker.write_text('{broken', encoding='utf-8')
    with pytest.raises(TenantBoundaryError): validate_binding(engine, cfg)
    marker.unlink()
    with pytest.raises(TenantBoundaryError): validate_binding(engine, cfg)
    engine.dispose()


def test_fresh_migration_permissions_and_empty_legacy_table_allow_initialization(tmp_path):
    from sqlalchemy import text
    from app.models import Permission
    from app.tenant import initialize_tenant
    engine, cfg = database(), config(tmp_path)
    with Session(engine) as db:
        db.add(Permission(code='facility.read', description='Migration seed'))
        db.execute(text('CREATE TABLE emergency_legacy_import_metadata (id INTEGER PRIMARY KEY)'))
        db.commit()
    initialize_tenant(engine, cfg, 'Alpha')
    engine.dispose()


def test_unmapped_legacy_table_with_records_requires_adoption(tmp_path):
    from sqlalchemy import text
    from app.tenant import initialize_tenant, TenantBoundaryError
    engine, cfg = database(), config(tmp_path)
    with engine.begin() as connection:
        connection.execute(text('CREATE TABLE legacy_data (id INTEGER PRIMARY KEY)'))
        connection.execute(text('INSERT INTO legacy_data(id) VALUES (1)'))
    with pytest.raises(TenantBoundaryError): initialize_tenant(engine, cfg, 'Alpha')
    initialize_tenant(engine, cfg, 'Alpha', adopt_existing=True)
    engine.dispose()


def test_cli_sessions_refuse_wrong_department_database(tmp_path, monkeypatch):
    import app.db as database_module
    from app.tenant import initialize_tenant, TenantBoundaryError
    engine, alpha = database(), config(tmp_path / 'alpha')
    initialize_tenant(engine, alpha, 'Alpha')
    monkeypatch.setattr(database_module, 'settings', config(tmp_path / 'beta'))
    with pytest.raises(TenantBoundaryError): database_module.BoundSession(bind=engine)
    monkeypatch.setattr(database_module, 'settings', alpha)
    with database_module.BoundSession(bind=engine) as db:
        assert db.scalar(select(Employee.employee_id)) is None
    engine.dispose()


def test_complete_postgresql_migration_initialization(tmp_path):
    # Required CI service; local SQLite tests cannot prove PostgreSQL migrations.
    url = os.environ.get('FIRE_AI_TEST_POSTGRES_URL')
    if not url:
        pytest.skip('PostgreSQL service is exercised in CI')
    from app.migrations import apply_migrations
    from app.tenant import initialize_tenant, validate_binding
    from sqlalchemy import text
    migrations = Path(__file__).resolve().parents[2] / 'db' / 'migrations'
    applied = apply_migrations(url, migrations)
    assert '039_run_a_tenant_identity.sql' in applied
    assert apply_migrations(url, migrations) == []
    cfg = Settings(_env_file=None, production_mode=True, database_url=url,
                   tenant_id=str(uuid4()), trusted_hosts=['alpha.test'],
                   cookie_secure=True, storage_root=str(tmp_path))
    engine = create_engine(url)
    initialize_tenant(engine, cfg, 'Synthetic PostgreSQL alpha')
    assert validate_binding(engine, cfg)['tenant_id'] == cfg.tenant_id
    with engine.connect() as connection:
        assert connection.execute(text('SELECT COUNT(*) FROM tenant_identity')).scalar_one() == 1
        assert connection.execute(text("SELECT COUNT(*) FROM audit_logs WHERE action = 'tenant.initialize'")).scalar_one() == 1
    engine.dispose()
