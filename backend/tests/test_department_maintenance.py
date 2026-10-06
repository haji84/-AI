import os
from pathlib import Path
from uuid import uuid4
import pytest
from sqlalchemy import create_engine,text
from sqlalchemy.engine import make_url


def test_runtime_refuses_transaction_during_maintenance():
    from app.department_maintenance import acquire_runtime_lock,MaintenanceUnavailable
    class Result:
        def scalar_one(self):return False
    class Connection:
        def execute(self,statement,parameters):return Result()
        def invalidate(self):pass
    with pytest.raises(MaintenanceUnavailable):acquire_runtime_lock(Connection(),str(uuid4()))


def test_postgresql_runtime_and_maintenance_exclude_each_other(tmp_path,monkeypatch):
    url=os.environ.get('FIRE_AI_TEST_POSTGRES_URL')
    if not url:pytest.skip('real PostgreSQL maintenance locking executes in CI')
    from app.department_maintenance import exclusive_maintenance,MaintenanceUnavailable
    from app.migrations import apply_migrations
    from app.tenant import initialize_tenant
    from app.settings import Settings,settings
    from app.db import BoundSession
    name='fi_maintenance_'+uuid4().hex[:16];tenant_id=str(uuid4())
    cluster=create_engine(make_url(url).set(database='postgres'),isolation_level='AUTOCOMMIT');target=None
    try:
        with cluster.connect() as db:db.exec_driver_sql('CREATE DATABASE '+name)
        target_url=make_url(url).set(database=name).render_as_string(hide_password=False)
        apply_migrations(target_url,Path(__file__).resolve().parents[2]/'db/migrations')
        target=create_engine(target_url)
        config=Settings(database_url=target_url,storage_root=str(tmp_path/'storage'),tenant_id=tenant_id,trusted_hosts=['synthetic.test'])
        initialize_tenant(target,config,'Synthetic maintenance department')
        for field in ['database_url','storage_root','tenant_id','trusted_hosts']:
            monkeypatch.setattr(settings,field,getattr(config,field))
        with exclusive_maintenance(target_url,tenant_id):
            with BoundSession(bind=target) as db:
                with pytest.raises(MaintenanceUnavailable):db.execute(text('SELECT 1'))
                from sqlalchemy.exc import PendingRollbackError
                with pytest.raises(PendingRollbackError):db.execute(text('SELECT 1'))
                db.rollback()
                with pytest.raises(MaintenanceUnavailable):db.execute(text('SELECT 1'))
        with BoundSession(bind=target) as db:
            assert db.execute(text('SELECT 1')).scalar_one()==1
            with pytest.raises(MaintenanceUnavailable):
                with exclusive_maintenance(target_url,tenant_id):pass
        with pytest.raises(RuntimeError,match='synthetic maintenance failure'):
            with exclusive_maintenance(target_url,tenant_id):raise RuntimeError('synthetic maintenance failure')
        with exclusive_maintenance(target_url,tenant_id):pass
        with target.connect() as migration_owner:
            migration_owner.execute(text("SELECT pg_advisory_lock(hashtext('fire-ai-schema-migration'))"))
            migration_owner.commit()
            try:
                with pytest.raises(ValueError,match='another migration'):
                    apply_migrations(target_url,Path(__file__).resolve().parents[2]/'db/migrations')
            finally:
                migration_owner.execute(text("SELECT pg_advisory_unlock(hashtext('fire-ai-schema-migration'))"))
                migration_owner.commit()
        with exclusive_maintenance(target_url,tenant_id):pass
        with pytest.raises(ValueError):
            with exclusive_maintenance(target_url,str(uuid4())):pass
        with exclusive_maintenance(target_url,tenant_id):
            with pytest.raises(MaintenanceUnavailable):
                with exclusive_maintenance(target_url,tenant_id):pass
    finally:
        if target:target.dispose()
        with cluster.connect() as db:db.exec_driver_sql('DROP DATABASE IF EXISTS '+name+' WITH (FORCE)')
        cluster.dispose()


def test_reusing_rejected_session_cannot_bypass_maintenance(monkeypatch):
    from app.db import BoundSession
    from app.settings import settings
    from app.department_maintenance import MaintenanceUnavailable
    from sqlalchemy.exc import PendingRollbackError
    engine=create_engine('sqlite:///:memory:')
    with engine.connect() as connection:
        raw=connection.connection.driver_connection
        raw.create_function('hashtext',1,lambda value:1)
        raw.create_function('pg_try_advisory_xact_lock_shared',1,lambda value:0)
    db=BoundSession(bind=engine)
    monkeypatch.setattr(settings,'tenant_id',str(uuid4()))
    monkeypatch.setattr(engine.dialect,'name','postgresql')
    try:
        with pytest.raises(MaintenanceUnavailable):db.execute(text('SELECT 1'))
        with pytest.raises((MaintenanceUnavailable,PendingRollbackError)):db.execute(text('SELECT 1'))
    finally:
        db.close();engine.dispose()
