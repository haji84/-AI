"""Synthetic operations/source isolation using Run A's server-selected DB guard."""
import os
from contextlib import contextmanager
from pathlib import Path
from uuid import uuid4
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine,select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from app.db import Base,get_db
from app.models import AuditLog,Document,EmergencyCase,Employee,User,UserRole
from app.operations_models import Incident,Vehicle,Dispatch
from app.rbac_seed import seed_rbac
from app.routers import auth,documents,operations,search
from app.security import hash_password
SOURCE_ID='11111111-1111-4111-8111-111111111111'
INCIDENT_ID='22222222-2222-4222-8222-222222222222'
VEHICLE_ID='33333333-3333-4333-8333-333333333333'
EMPLOYEE_ID='44444444-4444-4444-8444-444444444444'
DOCUMENT_ID='55555555-5555-4555-8555-555555555555'
DISPATCH_ID='66666666-6666-4666-8666-666666666666'

@contextmanager
def departments(tmp_path):
    from app.settings import Settings
    assert 'tenant_id' in Settings.model_fields,'canonical tenant settings are missing'
    assert (Path(__file__).resolve().parents[1]/'app/tenant.py').exists(),'canonical local guard is missing'
    from app.tenant import initialize_tenant,TenantBoundaryMiddleware
    from app.settings import Settings
    instances=[]
    try:
        for slug in ['alpha','beta']:
            cfg=Settings(_env_file=None,database_url='sqlite+pysqlite:///:memory:',tenant_id=str(uuid4()),storage_root=str(tmp_path/slug),trusted_hosts=[slug+'.test'])
            engine=create_engine(cfg.database_url,connect_args={'check_same_thread':False},poolclass=StaticPool)
            Base.metadata.create_all(engine);initialize_tenant(engine,cfg,'Synthetic '+slug)
            sessions=sessionmaker(bind=engine,expire_on_commit=False,autoflush=False)
            with sessions() as db:
                roles=seed_rbac(db)
                db.add_all([Employee(employee_id=EMPLOYEE_ID,display_name='Synthetic '+slug,employee_code='SYN'),EmergencyCase(emergency_case_id=SOURCE_ID,source_case_key='synthetic-source',incident_address=slug+'-private-source',dispatch_number=slug+'-number'),Document(document_id=DOCUMENT_ID,original_filename=slug+'-synthetic.pdf',storage_path='synthetic',sha256='c'*64,size_bytes=1)]);db.flush()
                user=User(username='same-operational-login',password_hash=hash_password(slug+'-synthetic-password'),employee_id=EMPLOYEE_ID);db.add(user);db.flush();db.add(UserRole(user_id=user.user_id,role_id=roles['system_admin'].role_id))
                db.add_all([Incident(incident_id=INCIDENT_ID,kind='emergency_support',title='Synthetic '+slug,emergency_case_id=SOURCE_ID),Vehicle(vehicle_id=VEHICLE_ID,code='SYN',name='Synthetic '+slug)]);db.flush()
                db.add(Dispatch(dispatch_id=DISPATCH_ID,incident_id=INCIDENT_ID,unit='Synthetic '+slug,vehicle_id=VEHICLE_ID,document_id=DOCUMENT_ID));db.commit()
            application=FastAPI();application.add_middleware(TenantBoundaryMiddleware,engine=engine,config=cfg)
            for router in [auth.router,documents.router,operations.router,search.router]:application.include_router(router)
            def dependency_for(factory):
                def dependency():
                    with factory() as db:yield db
                return dependency
            application.dependency_overrides[get_db]=dependency_for(sessions)
            client=TestClient(application,base_url='http://'+slug+'.test');instances.append((client,engine,cfg,sessions))
        yield instances
    finally:
        for client,engine,_,_ in instances:client.close();engine.dispose()

def login(client,slug):
    r=client.post('/auth/login',json={'username':'same-operational-login','password':slug+'-synthetic-password'});assert r.status_code==200,r.text

def test_main_registers_operations_behind_canonical_tenant_lifespan(monkeypatch):
    import app.main as main
    assert callable(getattr(main,'lifespan',None)),'canonical startup guard missing'
    assert any(m.cls.__name__=='TenantBoundaryMiddleware' for m in main.app.user_middleware)
    checks=[]
    monkeypatch.setattr(main,'validate_runtime_binding',lambda engine,settings:checks.append(engine))
    with TestClient(main.app) as client:
        assert checks==[main.engine]
        assert client.get('/operations/incidents').status_code==401

def test_operational_sources_sessions_search_and_writes_isolate_two_databases(tmp_path):
    with departments(tmp_path) as [(alpha,_,_,_), (beta,_,_,_)]:
        login(alpha,'alpha');token=alpha.cookies.get('fire_ai_session')
        assert beta.get('/operations/incidents/'+INCIDENT_ID,headers={'Cookie':'fire_ai_session='+token}).status_code==401
        assert beta.post('/auth/login',json={'username':'same-operational-login','password':'alpha-synthetic-password'}).status_code==401
        login(beta,'beta')
        for client,slug,other in [(alpha,'alpha','beta'),(beta,'beta','alpha')]:
            source=client.get('/operations/incidents/'+INCIDENT_ID).json()['source']
            assert source['source_id']==SOURCE_ID and source['address']==slug+'-private-source'
            assert client.get('/documents/'+DOCUMENT_ID).json()['original_filename']==slug+'-synthetic.pdf'
            assert client.get('/operations/employees').json()[0]['display_name']=='Synthetic '+slug
            assert client.get('/search',params={'q':other+'-private-source','modules':'operations'}).json()['hits']==[]
            assert other+'-private-source' not in client.get('/operations/export/incidents').text
        r=alpha.post('/operations/vehicles/'+VEHICLE_ID+'/fuel',json={'expected_version':1,'kind':'receipt','liters':'2.50','amount':'10.25','occurred_at':'2026-10-01T10:00:00Z','document_id':DOCUMENT_ID});assert r.status_code==201,r.text
        assert beta.get('/operations/vehicles/'+VEHICLE_ID).json()['fuel_stock']=='0.00'
        private=alpha.post('/operations/vehicles',json={'code':'ALPHA-ONLY','name':'Synthetic alpha only'}).json()
        assert beta.get('/operations/vehicles/'+private['vehicle_id']).status_code==404
        assert len(alpha.get('/operations/vehicles/'+VEHICLE_ID+'/history').json()['fuel'])==1
        assert beta.get('/operations/vehicles/'+VEHICLE_ID+'/history').json()['fuel']==[]

def test_client_tenant_selectors_cannot_choose_operational_database(tmp_path):
    with departments(tmp_path) as [(alpha,_,_,alpha_sessions),(beta,_,beta_cfg,beta_sessions)]:
        login(alpha,'alpha');login(beta,'beta')
        for field in ['tenant_id','database_url','user_id']:
            r=alpha.post('/operations/vehicles',json={'code':'SPOOF','name':'Synthetic forbidden',field:beta_cfg.tenant_id});assert r.status_code==422,r.text
        # Canonical Run A ignores selector headers/query: they cannot route databases.
        r=alpha.get('/operations/incidents/'+INCIDENT_ID,params={'tenant_id':beta_cfg.tenant_id,'database_url':'beta'},headers={'X-Tenant-ID':beta_cfg.tenant_id})
        assert r.status_code==200 and r.json()['source']['address']=='alpha-private-source'
        r=alpha.post('/operations/vehicles',params={'tenant_id':beta_cfg.tenant_id},headers={'X-Tenant-ID':beta_cfg.tenant_id},json={'code':'ALPHA-SERVER','name':'Synthetic alpha routed by server'})
        assert r.status_code==201 and beta.get('/operations/vehicles/'+r.json()['vehicle_id']).status_code==404
        assert alpha.get('/operations/incidents/'+INCIDENT_ID,headers={'Host':'beta.test'}).status_code==421
        raw=f'code,name,tenant_id\nSPOOF,Synthetic,{beta_cfg.tenant_id}\n'.encode()
        assert alpha.post('/operations/import/vehicles',files={'file':('synthetic.csv',raw,'text/csv')}).status_code==422
        with alpha_sessions() as db:assert db.scalar(select(AuditLog).where(AuditLog.action=='fleet.vehicle.create')) is not None
        with beta_sessions() as db:assert db.scalar(select(Vehicle).where(Vehicle.code=='ALPHA-SERVER')) is None

def test_wrong_binding_blocks_operational_session_and_http(tmp_path,monkeypatch):
    with departments(tmp_path) as [(alpha,alpha_engine,alpha_cfg,_),(_,beta_engine,beta_cfg,_)]:
        import app.db as db_module
        from app.tenant import TenantBoundaryError
        monkeypatch.setattr(db_module,'settings',alpha_cfg)
        with pytest.raises(TenantBoundaryError):db_module.BoundSession(bind=beta_engine)
        with db_module.BoundSession(bind=alpha_engine) as db:assert db.get(Incident,INCIDENT_ID).title=='Synthetic alpha'
        login(alpha,'alpha')
        marker=Path(alpha_cfg.storage_root)/'tenant-identity.json';marker.write_text('{"tenant_id":"'+beta_cfg.tenant_id+'"}')
        assert alpha.get('/operations/vehicles/'+VEHICLE_ID).status_code==503

def test_operations_migration_follows_canonical_tenant_identity():
    from app.migrations import split_sql
    root=Path(__file__).resolve().parents[2]
    assert (root/'db/migrations/039_run_a_tenant_identity.sql').exists()
    assert (root/'db/migrations/040_run_b_operations_fleet.sql').exists()
    assert not (root/'db/migrations/039_run_b_operations_fleet.sql').exists()
    assert len(split_sql((root/'db/migrations/040_run_b_operations_fleet.sql').read_text()))==14


def test_postgresql_review_locks_linked_source_and_approval_rejects_changed_source():
    """CI's disposable PG service; never touch Run A's initialized public schema."""
    url=os.environ.get('FIRE_AI_TEST_POSTGRES_URL')
    if not url:
        pytest.skip('actual PostgreSQL source lock is exercised in CI')
    from fastapi import HTTPException
    from sqlalchemy import text,update
    from sqlalchemy.exc import DBAPIError
    from app.operations_schemas import Action
    from app.operations_service import review_dispatch
    schema='synthetic_operations_'+uuid4().hex
    engine=create_engine(url)
    scoped=engine.execution_options(schema_translate_map={None:schema})
    try:
        with engine.begin() as connection:
            connection.execute(text(f'CREATE SCHEMA "{schema}"'))
        Base.metadata.create_all(scoped)
        sessions=sessionmaker(bind=scoped,expire_on_commit=False,autoflush=False)
        with sessions() as db:
            roles=seed_rbac(db)
            user=User(username='synthetic-pg-reviewer',password_hash=hash_password('synthetic-password'))
            source=EmergencyCase(incident_address='Synthetic original',source_case_key='synthetic-pg')
            db.add_all([user,source]);db.flush()
            db.add(UserRole(user_id=user.user_id,role_id=roles['system_admin'].role_id))
            parent=Incident(kind='emergency_support',title='Synthetic PostgreSQL review',emergency_case_id=source.emergency_case_id)
            db.add(parent);db.flush()
            dispatch=Dispatch(incident_id=parent.incident_id,unit='Synthetic unit')
            db.add(dispatch);db.commit()
            user_id,source_id,dispatch_id=user.user_id,source.emergency_case_id,dispatch.dispatch_id
        # Review acquires the real linked Case lock and leaves its transaction open.
        with sessions() as reviewer:
            reviewed=review_dispatch(reviewer,reviewer.get(User,user_id),dispatch_id,Action(expected_version=1,note='Synthetic review'))
            assert reviewed.review_snapshot['source_version']==1
            with scoped.connect() as contender:
                with pytest.raises(DBAPIError) as locked:
                    with contender.begin():
                        contender.execute(text("SET LOCAL lock_timeout = '250ms'"))
                        contender.execute(update(EmergencyCase).where(EmergencyCase.emergency_case_id==source_id).values(version=2,incident_address='Synthetic changed'))
                assert getattr(locked.value.orig,'sqlstate',None)=='55P03'
            reviewer.commit()
        # Once review commits, a source editor can write. Human approval must reject it.
        with scoped.begin() as editor:
            editor.execute(update(EmergencyCase).where(EmergencyCase.emergency_case_id==source_id).values(version=2,incident_address='Synthetic changed'))
        with sessions() as approver:
            with pytest.raises(HTTPException) as stale:
                review_dispatch(approver,approver.get(User,user_id),dispatch_id,Action(expected_version=2,note='Synthetic approval'),approve=True)
            assert stale.value.status_code==409 and 'review sources changed' in stale.value.detail
            approver.rollback()
            row=approver.get(Dispatch,dispatch_id)
            assert row.status=='reviewed' and row.version==2 and row.official_amount is None
            assert approver.scalar(select(AuditLog).where(AuditLog.action=='incident.dispatch.approve')) is None
    finally:
        # Fixed generated identifier only; cleanup cannot select another department/schema.
        with engine.begin() as connection:
            connection.execute(text(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE'))
        engine.dispose()
