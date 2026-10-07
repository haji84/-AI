"""Real PostgreSQL acceptance, never replaced by SQLite concurrency claims."""
from contextlib import contextmanager
from datetime import date, datetime, timezone
from pathlib import Path
import os
import threading
from uuid import uuid4
import pytest
from sqlalchemy import create_engine, event, select, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session
from app.db import Base
from app.models import EmergencyCase, EmergencyPatient, User, UserRole, UserSession, RolePermission, Permission
from app.security import hash_password, token_digest
from app.rbac_seed import seed_rbac
from app.migrations import apply_migrations, split_sql
from test_observed_statistics_api import QUERY, AGGREGATE, save, revoke


def test_additive_statistics_migration_exists_and_parses_without_vehicle_assignment_dependency():
    migration=Path(__file__).resolve().parents[2]/'db/migrations/054_observed_statistics.sql'
    assert migration.exists(), 'The observed statistics persistence migration must be supplied'
    sql=migration.read_text()
    statements=split_sql(sql)
    assert len(statements)>=9
    assert 'statistics_reports' in sql and 'statistics_evidence' in sql and 'statistics_history' in sql
    assert 'vehicle_assignments' not in sql


@contextmanager
def postgres_database():
    base=os.environ.get('FIRE_AI_TEST_POSTGRES_URL')
    if not base:pytest.skip('real PostgreSQL statistics acceptance runs in CI')
    name='fi_statistics_'+uuid4().hex[:16]
    cluster=create_engine(make_url(base).set(database='postgres'),isolation_level='AUTOCOMMIT')
    with cluster.connect() as connection:connection.exec_driver_sql('CREATE DATABASE '+name)
    target=make_url(base).set(database=name).render_as_string(hide_password=False)
    engine=None
    try:
        apply_migrations(target,Path(__file__).resolve().parents[2]/'db/migrations')
        engine=create_engine(target,pool_size=5,max_overflow=5)
        yield engine
    finally:
        if engine:engine.dispose()
        with cluster.connect() as connection:connection.exec_driver_sql('DROP DATABASE '+name+' WITH (FORCE)')
        cluster.dispose()


@pytest.fixture
def statistics_pg():
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from app.routers import auth,statistics
    from app.db import get_db
    from app.models import Role
    with postgres_database() as engine:
        with Session(engine) as db:
            seed_rbac(db)
            role=Role(code='synthetic-statistics-pg',name='Synthetic statistics aggregate');db.add(role);db.flush()
            for code in AGGREGATE:
                permission=db.scalar(select(Permission).where(Permission.code==code))
                if permission is None:permission=Permission(code=code);db.add(permission);db.flush()
                db.add(RolePermission(role_id=role.role_id,permission_id=permission.permission_id))
            user=User(username='synthetic-statistics',password_hash=hash_password('synthetic-statistics-password'));db.add(user);db.flush()
            db.add(UserRole(user_id=user.user_id,role_id=role.role_id))
            case=EmergencyCase(source_case_key='synthetic',call_date=date(2026,1,2));db.add(case);db.flush()
            db.add(EmergencyPatient(emergency_case_id=case.emergency_case_id,patient_number=1));db.commit()
            refs={'user_id':user.user_id,'role_id':role.role_id,'case_id':case.emergency_case_id}
        application=FastAPI();application.include_router(auth.router);application.include_router(statistics.router)
        def dependency():
            with Session(engine,expire_on_commit=False) as db:yield db
        application.dependency_overrides[get_db]=dependency
        with TestClient(application) as client:
            assert client.post('/auth/login',json={'username':'synthetic-statistics','password':'synthetic-statistics-password'}).status_code==200
            yield client,engine,refs


def identity_for(client,engine,refs):
    from app.statistics_service import RequestIdentity
    return RequestIdentity(engine,refs['user_id'],token_digest(client.cookies.get('fire_ai_session')))


def test_postgresql_capture_is_repeatable_read_readonly_and_pool_is_clean(statistics_pg,monkeypatch):
    from app import statistics_service as service
    client,engine,refs=statistics_pg
    original=service.capture_sources
    observed=[]
    def inspected(db,period,keys):
        observed.append((db.scalar(text('SHOW transaction_isolation')),db.scalar(text('SHOW transaction_read_only'))))
        return original(db,period,keys)
    monkeypatch.setattr(service,'capture_sources',inspected)
    row=save(client)
    assert row['snapshot']['metrics'][0]['value']=='1'
    assert observed==[('repeatable read','on')]
    with engine.connect() as connection:
        assert connection.exec_driver_sql('SHOW transaction_read_only').scalar_one()=='off'
        assert connection.exec_driver_sql('SHOW transaction_isolation').scalar_one()=='read committed'
    with service.final_session(identity_for(client,engine,refs),AGGREGATE) as db:
        assert db.scalar(text('SHOW transaction_read_only'))=='off'
        assert db.scalar(text('SHOW transaction_isolation'))=='read committed'


def test_source_change_between_queries_does_not_mix_snapshot(statistics_pg,monkeypatch):
    from app import statistics_service as service
    client,engine,refs=statistics_pg
    original=service.capture_sources
    fired=False
    def change_between(connection,cursor,statement,parameters,context,executemany):
        nonlocal fired
        if not fired and 'FROM emergency_patients' in statement and connection.get_execution_options().get('postgresql_readonly'):
            fired=True
            with Session(engine) as writer:
                case=EmergencyCase(source_case_key='concurrent',call_date=date(2026,1,3));writer.add(case);writer.flush()
                writer.add(EmergencyPatient(emergency_case_id=case.emergency_case_id,patient_number=1))
                # Also alter an already captured parent's children: a READ COMMITTED
                # capture would otherwise just misclassify a new parent's child as unknown.
                writer.add(EmergencyPatient(emergency_case_id=refs['case_id'],patient_number=2));writer.commit()
    event.listen(engine,'before_cursor_execute',change_between)
    try:
        row=save(client)
    finally:event.remove(engine,'before_cursor_execute',change_between)
    assert fired
    assert [m['value'] for m in row['snapshot']['metrics']]==['1','1']
    assert [m['value'] for m in client.post('/statistics/query',json=QUERY).json()['metrics']]==['2','3']


def test_bound_maintenance_guard_starts_configured_snapshot_and_rejects_maintenance(statistics_pg,tmp_path,monkeypatch):
    from app import statistics_service as service
    from app.settings import Settings,settings
    from app.tenant import initialize_tenant
    from app.department_maintenance import exclusive_maintenance,MaintenanceUnavailable
    from app.statistics_sources import pin_period
    from app.statistics_schemas import StatisticsQuery
    client,engine,refs=statistics_pg
    config=Settings(_env_file=None,tenant_id=str(uuid4()),trusted_hosts=['testserver'],storage_root=str(tmp_path/'department'))
    initialize_tenant(engine,config,'Synthetic statistics PG',adopt_existing=True)
    for key in ['tenant_id','trusted_hosts','storage_root']:monkeypatch.setattr(settings,key,getattr(config,key))
    queries=[]
    def record(connection,cursor,statement,parameters,context,executemany):
        if 'pg_try_advisory_xact_lock_shared' in statement:
            options=connection.get_execution_options()
            queries.append((options.get('isolation_level'),options.get('postgresql_readonly'),
                            connection.exec_driver_sql('SHOW transaction_isolation').scalar_one(),
                            connection.exec_driver_sql('SHOW transaction_read_only').scalar_one()))
    event.listen(engine,'after_cursor_execute',record)
    identity=identity_for(client,engine,refs)
    period=pin_period(StatisticsQuery(**QUERY),'Asia/Tokyo')
    try:service.capture_in_snapshot(identity,period,QUERY['metric_keys'])
    finally:event.remove(engine,'after_cursor_execute',record)
    assert queries==[('REPEATABLE READ',True,'repeatable read','on')]
    with exclusive_maintenance(engine.url.render_as_string(hide_password=False),config.tenant_id):
        with pytest.raises(MaintenanceUnavailable):service.capture_in_snapshot(identity,period,QUERY['metric_keys'])
    assert service.capture_in_snapshot(identity,period,QUERY['metric_keys']).public['metrics'][0]['value']=='1'


def compete(client,path,payload):
    from fastapi.testclient import TestClient
    barrier=threading.Barrier(2);statuses=[];errors=[]
    def run():
        try:
            with TestClient(client.app) as other:
                other.cookies.update(client.cookies);barrier.wait(timeout=10)
                statuses.append(other.post(path,json=payload).status_code)
        except BaseException as exc:errors.append(exc)
    threads=[threading.Thread(target=run) for _ in range(2)]
    for thread in threads:thread.start()
    for thread in threads:thread.join(timeout=25)
    assert not errors and all(not thread.is_alive() for thread in threads),errors
    return sorted(statuses)


@pytest.mark.parametrize('action',['confirm','replacements'])
def test_concurrent_confirm_and_replacement_have_exactly_one_winner(statistics_pg,action):
    client,engine,refs=statistics_pg;row=save(client)
    payload={'expected_version':1,'acknowledged':True,'review_note':'Synthetic'} if action=='confirm' else {'expected_version':1,'reason':'Synthetic'}
    assert compete(client,'/statistics/reports/'+row['report_id']+'/'+action,payload)==[200 if action=='confirm' else 201,409]
    history=client.get('/statistics/reports/'+row['report_id']+'/history').json()['items']
    assert len(history)==2


def test_postgresql_sql_snapshot_history_evidence_immutability(statistics_pg):
    from sqlalchemy.exc import DBAPIError
    client,engine,refs=statistics_pg;row=save(client)
    for statement in ["UPDATE statistics_reports SET snapshot='{}'", "DELETE FROM statistics_reports", "UPDATE statistics_evidence SET fingerprint='tampered'", "DELETE FROM statistics_evidence", "UPDATE statistics_history SET note='tampered'", "DELETE FROM statistics_history"]:
        with pytest.raises(DBAPIError):
            with engine.begin() as connection:connection.exec_driver_sql(statement)
    assert client.get('/statistics/reports/'+row['report_id']).json()['snapshot']==row['snapshot']


def test_post_capture_permission_loss_blocks_pg_release(statistics_pg,monkeypatch):
    from app import statistics_service as service
    client,engine,refs=statistics_pg
    original=service.capture_in_snapshot
    def capture_then_revoke(*args,**kwargs):
        result=original(*args,**kwargs);revoke(engine,refs,'emergency.report.read');return result
    monkeypatch.setattr(service,'capture_in_snapshot',capture_then_revoke)
    assert client.post('/statistics/query',json=QUERY).status_code==403


def test_queued_account_change_wins_before_mutation_guard(statistics_pg,tmp_path,monkeypatch):
    import time
    from app import statistics_service as service
    from app.personnel import account_change_lock
    from app.settings import Settings, settings
    from app.tenant import initialize_tenant
    client,engine,refs=statistics_pg
    config=Settings(_env_file=None,tenant_id=str(uuid4()),trusted_hosts=['testserver'],storage_root=str(tmp_path/'queued-department'))
    initialize_tenant(engine,config,'Synthetic queued authority',adopt_existing=True)
    for key in ['tenant_id','trusted_hosts','storage_root']:monkeypatch.setattr(settings,key,getattr(config,key))
    original=service.capture_in_snapshot
    capture_ready=threading.Event();admin_holds=threading.Event();pid_ready=threading.Event();errors=[];waiter={}
    def administration():
        try:
            assert capture_ready.wait(10)
            with Session(engine) as db:
                account_change_lock(db)
                user=db.get(User,refs['user_id']);user.active=False;db.flush();admin_holds.set()
                assert pid_ready.wait(10)
                deadline=time.monotonic()+10
                with engine.connect() as observer:
                    while time.monotonic()<deadline:
                        blocked=observer.execute(text("SELECT EXISTS (SELECT 1 FROM pg_locks WHERE pid=:pid AND locktype='advisory' AND NOT granted)"),{'pid':waiter['pid']}).scalar_one()
                        if blocked:
                            waiter['observed_blocked']=True
                            break
                        time.sleep(0.02)
                    else:raise AssertionError('Final authorization never waited for the actual account-change lock')
                db.commit()
        except BaseException as exc:errors.append(exc);admin_holds.set()
    worker=threading.Thread(target=administration);worker.start()
    def gated_capture(*args,**kwargs):
        result=original(*args,**kwargs);capture_ready.set();assert admin_holds.wait(10);return result
    def queued_guard(db):
        # BoundSession has already run its maintenance SELECT before this PID query.
        waiter['pid']=db.scalar(text('SELECT pg_backend_pid()'));pid_ready.set()
        account_change_lock(db)
    monkeypatch.setattr(service,'capture_in_snapshot',gated_capture)
    monkeypatch.setattr(service,'account_change_lock',queued_guard)
    response=client.post('/statistics/reports',json=QUERY);worker.join(timeout=15)
    assert not errors and not worker.is_alive(),errors
    assert waiter.get('observed_blocked') is True
    assert response.status_code==403,response.text
    with Session(engine) as db:
        from app.statistics_models import StatisticsReport
        assert db.scalar(select(StatisticsReport)) is None


def test_two_department_engines_cannot_select_each_others_values_or_reports(statistics_pg,tmp_path,monkeypatch):
    from app import statistics_service as service
    from app.statistics_sources import pin_period
    from app.statistics_schemas import StatisticsQuery
    from app.statistics_models import StatisticsReport
    from app.settings import Settings, settings
    from app.tenant import initialize_tenant, TenantBoundaryError
    client,first,refs=statistics_pg
    row=save(client)
    with postgres_database() as second:
        with Session(second) as db:
            db.add(EmergencyCase(source_case_key='second-only',call_date=date(2026,1,4)))
            db.add(EmergencyCase(source_case_key='second-more',call_date=date(2026,1,5)));db.commit()
        first_config=Settings(_env_file=None,tenant_id=str(uuid4()),trusted_hosts=['alpha.test'],storage_root=str(tmp_path/'alpha'))
        second_config=Settings(_env_file=None,tenant_id=str(uuid4()),trusted_hosts=['beta.test'],storage_root=str(tmp_path/'beta'))
        initialize_tenant(first,first_config,'Synthetic alpha',adopt_existing=True)
        initialize_tenant(second,second_config,'Synthetic beta',adopt_existing=True)
        period=pin_period(StatisticsQuery(**QUERY),'Asia/Tokyo')
        first_identity=identity_for(client,first,refs)
        second_identity=service.RequestIdentity(second,first_identity.user_id,first_identity.session_digest)
        def select_binding(config):
            for key in ['tenant_id','trusted_hosts','storage_root']:
                monkeypatch.setattr(settings,key,getattr(config,key))
        select_binding(first_config)
        first_capture=service.capture_in_snapshot(first_identity,period,['emergency.cases'])
        with service.final_session(first_identity,{'statistics.read'}) as db:
            assert db.get(StatisticsReport,row['report_id']) is not None
        with pytest.raises(TenantBoundaryError):
            service.capture_in_snapshot(second_identity,period,['emergency.cases'])
        with pytest.raises(TenantBoundaryError):
            with service.final_session(second_identity,{'statistics.read'}):pass
        select_binding(second_config)
        second_capture=service.capture_in_snapshot(second_identity,period,['emergency.cases'])
        assert first_capture.public['metrics'][0]['value']=='1'
        assert second_capture.public['metrics'][0]['value']=='2'
        with Session(second) as db:assert db.get(StatisticsReport,row['report_id']) is None
        with pytest.raises(TenantBoundaryError):
            service.capture_in_snapshot(first_identity,period,['emergency.cases'])
        with pytest.raises(TenantBoundaryError):
            with service.final_session(first_identity,{'statistics.read'}):pass
        # A correctly bound second department still rejects a foreign originating session.
        with pytest.raises(Exception) as exc:
            with service.final_session(second_identity,{'statistics.read'}):pass
        assert getattr(exc.value,'status_code',None)==401


def test_postgresql_recorded_instants_use_business_boundaries_for_fire_and_operations(statistics_pg):
    from app.models import FireInvestigationCase
    from app.operations_models import Incident
    client,engine,refs=statistics_pg
    with Session(engine) as db:
        for value in ['2026-01-01T00:00:00+09:00','2025-12-31T15:00:00Z','2026-01-31T23:59:59+09:00','2026-02-01T00:00:00+09:00']:
            db.add(Incident(kind='rescue',title='Synthetic aware',occurred_at=datetime.fromisoformat(value)))
        fire=FireInvestigationCase(title='Synthetic fire',occurred_at=datetime.fromisoformat('2025-12-31T15:00:00Z'));db.add(fire);db.flush()
        db.add(Incident(kind='fire',title='Synthetic linked fire',fire_investigation_case_id=fire.fire_investigation_case_id));db.commit()
    response=client.post('/statistics/query',json={**QUERY,'metric_keys':['operations.incidents']})
    assert response.status_code==200,response.text
    assert response.json()['metrics'][0]['value']=='4'
    assert response.json()['metrics'][0]['exclusions']==[]
