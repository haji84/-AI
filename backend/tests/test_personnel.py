import os
os.environ.setdefault('FIRE_AI_DATABASE_URL', 'sqlite+pysqlite:///:memory:')
from datetime import date, timedelta
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool
from app.db import Base, get_db
from app.models import Employee, User, UserRole, AuditLog
from app.rbac_seed import seed_rbac
from app.security import hash_password


@pytest.fixture
def environment():
    from app.personnel import OrganizationUnit, EmployeeAssignment
    from app.routers import administration, auth
    engine = create_engine('sqlite+pysqlite:///:memory:', connect_args={'check_same_thread':False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        roles=seed_rbac(db)
        staff=Employee(display_name='Synthetic administrator');db.add(staff);db.flush()
        user=User(employee_id=staff.employee_id,username='admin',password_hash=hash_password('synthetic-admin-password'))
        db.add(user);db.flush();db.add(UserRole(user_id=user.user_id,role_id=roles['system_admin'].role_id));db.commit()
        role_ids={code:role.role_id for code,role in roles.items()}
    app=FastAPI();app.include_router(auth.router);app.include_router(administration.router)
    def dependency():
        with Session(engine,expire_on_commit=False) as db:yield db
    app.dependency_overrides[get_db]=dependency
    client=TestClient(app)
    assert client.post('/auth/login',json={'username':'admin','password':'synthetic-admin-password'}).status_code==200
    yield client,engine,role_ids,app
    client.close();engine.dispose()


def org(client,code='A'):
    response=client.post('/administration/organizations',json={'code':code,'name':'Synthetic '+code})
    assert response.status_code==201,response.text
    return response.json()


def staff(client):
    response=client.post('/administration/staff',json={'employee_code':'S001','display_name':'Synthetic staff'})
    assert response.status_code==201,response.text
    return response.json()


def test_human_assignment_history_controls_effective_roles(environment,monkeypatch):
    from app import personnel
    from app.authz import permission_codes
    client,engine,roles,_=environment
    a,b=org(client),org(client,'B');person=staff(client)
    account=client.post('/administration/accounts',json={'employee_id':person['employee_id'],'username':'staff',
        'password':'synthetic-staff-password','reason':'Human採用承認'}).json()
    day=date(2026,10,1)
    first=client.post('/administration/staff/'+person['employee_id']+'/assignments',json={
        'expected_version':1,'organization_id':a['organization_id'],'title':'予防係',
        'valid_from':day.isoformat(),'role_ids':[roles['prevention_editor']],'reason':'Human辞令確認'})
    assert first.status_code==201,first.text
    monkeypatch.setattr(personnel,'business_date',lambda:day)
    with Session(engine) as db:assert 'facility.update' in permission_codes(db,account['user_id'])
    moved=client.post('/administration/staff/'+person['employee_id']+'/transfer',json={
        'expected_version':2,'organization_id':b['organization_id'],'title':'救急係',
        'valid_from':(day+timedelta(days=1)).isoformat(),'role_ids':[roles['emergency_reporter']],'reason':'Human異動承認'})
    assert moved.status_code==201,moved.text
    with Session(engine) as db:assert 'facility.update' in permission_codes(db,account['user_id'])
    monkeypatch.setattr(personnel,'business_date',lambda:day+timedelta(days=1))
    with Session(engine) as db:
        codes=permission_codes(db,account['user_id'])
        assert 'facility.update' not in codes and 'emergency.report.read' in codes
        assert db.scalar(select(AuditLog).where(AuditLog.action=='personnel.transfer')) is not None
    history=client.get('/administration/staff/'+person['employee_id']+'/assignments').json()
    assert len(history)==2
    assert next(x for x in history if x['organization_id']==a['organization_id'])['valid_to']==day.isoformat()


def test_stale_staff_change_and_overlapping_assignments_do_not_overwrite(environment):
    client,_,roles,_=environment;unit=org(client);person=staff(client)
    payload={'expected_version':1,'organization_id':unit['organization_id'],'title':'予防',
        'valid_from':'2026-01-01','role_ids':[roles['prevention_editor']],'reason':'Human確認'}
    url='/administration/staff/'+person['employee_id']+'/assignments'
    assert client.post(url,json=payload).status_code==201
    assert client.post(url,json=payload).status_code==409
    payload['expected_version']=2
    assert client.post(url,json=payload).status_code==409
    assert len(client.get(url).json())==1


def test_staff_inactivation_revokes_login_and_existing_session(environment):
    client,engine,_,app=environment;person=staff(client)
    response=client.post('/administration/accounts',json={'employee_id':person['employee_id'],'username':'staff',
        'password':'synthetic-staff-password','reason':'Human採用承認'})
    assert response.status_code==201,response.text
    second=TestClient(app)
    assert second.post('/auth/login',json={'username':'staff','password':'synthetic-staff-password'}).status_code==200
    response=client.patch('/administration/staff/'+person['employee_id'],json={'expected_version':1,'active':False,'reason':'Human退職確認'})
    assert response.status_code==200,response.text
    assert second.get('/auth/me').status_code in {401,403}
    assert second.post('/auth/login',json={'username':'staff','password':'synthetic-staff-password'}).status_code==401
    second.close()


def test_regular_account_cannot_administer_staff_and_org_cycle_is_rejected(environment):
    client,_,_,app=environment;root=org(client);person=staff(client)
    account=client.post('/administration/accounts',json={'employee_id':person['employee_id'],'username':'staff',
        'password':'synthetic-staff-password','reason':'Human採用承認'})
    assert account.status_code==201
    second=TestClient(app);second.post('/auth/login',json={'username':'staff','password':'synthetic-staff-password'})
    assert second.get('/administration/staff').status_code==403
    child=client.post('/administration/organizations',json={'code':'child','name':'Synthetic child','parent_id':root['organization_id']}).json()
    cycle=client.patch('/administration/organizations/'+root['organization_id'],json={'expected_version':1,
        'parent_id':child['organization_id'],'reason':'Human組織改編'})
    assert cycle.status_code==409
    second.close()


def test_human_account_role_changes_preserve_last_administrator_and_versions(environment):
    client,engine,roles,_=environment
    admin_id=client.get('/auth/me').json()['user_id']
    url='/administration/accounts/'+admin_id
    denied=client.patch(url,json={'expected_version':1,'role_ids':[],'reason':'Human権限変更'})
    assert denied.status_code==409,denied.text
    assert client.get('/auth/me').status_code==200
    person=staff(client)
    account=client.post('/administration/accounts',json={'employee_id':person['employee_id'],'username':'second',
        'password':'synthetic-second-password','reason':'Human採用承認'}).json()
    changed=client.patch('/administration/accounts/'+account['user_id'],json={'expected_version':1,
        'role_ids':[roles['system_admin']],'reason':'Human管理者委任'})
    assert changed.status_code==200,changed.text
    assert client.patch('/administration/accounts/'+account['user_id'],json={'expected_version':1,'active':False,'reason':'Human無効化'}).status_code==409
    with Session(engine) as db:
        record=db.scalar(select(AuditLog).where(AuditLog.action=='account.update'))
        assert record and 'password_hash' not in str(record.after_data)
        assert '$argon2' not in str(record.after_data) and 'synthetic-second-password' not in str(record.after_data)


def test_self_password_change_revokes_sessions_and_prevents_reuse(environment):
    client,_,_,_=environment
    response=client.post('/administration/password',json={'current_password':'synthetic-admin-password','new_password':'changed-synthetic-password'})
    assert response.status_code==200,response.text
    assert client.get('/auth/me').status_code==401
    assert client.post('/auth/login',json={'username':'admin','password':'synthetic-admin-password'}).status_code==401
    assert client.post('/auth/login',json={'username':'admin','password':'changed-synthetic-password'}).status_code==200
    reuse=client.post('/administration/password',json={'current_password':'changed-synthetic-password','new_password':'synthetic-admin-password'})
    assert reuse.status_code==422,reuse.text


def test_personnel_manager_cannot_grant_operational_roles_without_account_authority(environment):
    from app.models import Role, Permission, RolePermission
    client,engine,roles,app=environment;unit=org(client);person=staff(client)
    account=client.post('/administration/accounts',json={'employee_id':person['employee_id'],'username':'hr',
        'password':'synthetic-hr-password','reason':'Human採用承認'}).json()
    with Session(engine) as db:
        hr=Role(code='hr',name='Synthetic personnel manager');db.add(hr);db.flush()
        for code in ['personnel.manage','personnel.read']:
            permission=db.scalar(select(Permission).where(Permission.code==code))
            db.add(RolePermission(role_id=hr.role_id,permission_id=permission.permission_id))
        db.add(UserRole(user_id=account['user_id'],role_id=hr.role_id));db.commit()
    second=TestClient(app);second.post('/auth/login',json={'username':'hr','password':'synthetic-hr-password'})
    response=second.post('/administration/staff/'+person['employee_id']+'/assignments',json={
        'expected_version':1,'organization_id':unit['organization_id'],'title':'予防係',
        'valid_from':'2026-01-01','role_ids':[roles['legal_rule_approver']],'reason':'Human辞令'})
    assert response.status_code==403,response.text
    second.close()


def test_primary_history_and_secondary_duty_can_be_closed_with_versions(environment,monkeypatch):
    from app import personnel
    from app.authz import permission_codes
    client,engine,roles,_=environment;unit=org(client);person=staff(client)
    account=client.post('/administration/accounts',json={'employee_id':person['employee_id'],'username':'staff',
        'password':'synthetic-staff-password','reason':'Human採用承認'}).json()
    response=client.post('/administration/staff/'+person['employee_id']+'/assignments',json={
        'expected_version':1,'organization_id':unit['organization_id'],'title':'兼務', 'kind':'secondary',
        'valid_from':'2026-01-01','role_ids':[roles['prevention_editor']],'reason':'Human兼務承認'})
    assert response.status_code==201,response.text
    assignment=response.json()
    closed=client.patch('/administration/assignments/'+assignment['assignment_id'],json={
        'expected_version':1,'expected_employee_version':2,'valid_to':'2026-10-05','reason':'Human兼務終了'})
    assert closed.status_code==200,closed.text
    monkeypatch.setattr(personnel,'business_date',lambda:date(2026,10,5))
    with Session(engine) as db:assert 'facility.update' in permission_codes(db,account['user_id'])
    monkeypatch.setattr(personnel,'business_date',lambda:date(2026,10,6))
    with Session(engine) as db:assert 'facility.update' not in permission_codes(db,account['user_id'])


def test_retiring_last_administrator_is_rejected_and_audit_has_assignment_roles(environment):
    client,engine,roles,_=environment
    admin_user_id=client.get('/auth/me').json()['user_id']
    with Session(engine) as db:admin_employee_id=db.get(User,admin_user_id).employee_id
    assert client.patch('/administration/staff/'+admin_employee_id,json={
        'expected_version':1,'active':False,'reason':'Human退職'}).status_code==409
    assert client.get('/auth/me').status_code==200
    unit=org(client);person=staff(client)
    response=client.post('/administration/staff/'+person['employee_id']+'/assignments',json={
        'expected_version':1,'organization_id':unit['organization_id'],'title':'予防係',
        'valid_from':'2026-01-01','role_ids':[roles['prevention_editor']],'reason':'Human辞令'})
    assert response.status_code==201
    with Session(engine) as db:
        record=db.scalar(select(AuditLog).where(AuditLog.action=='personnel.assignment.create'))
        assert record.after_data['role_ids']==[roles['prevention_editor']]


def test_postgresql_primary_assignment_overlap_is_enforced_by_database(tmp_path):
    url=os.environ.get('FIRE_AI_TEST_POSTGRES_URL')
    if not url:pytest.skip('PostgreSQL personnel history constraint is exercised in CI')
    from pathlib import Path
    from sqlalchemy.engine import make_url
    from sqlalchemy import text
    from sqlalchemy.exc import DBAPIError
    from uuid import uuid4
    from app.migrations import apply_migrations
    from app.personnel import OrganizationUnit, EmployeeAssignment
    name='fi_personnel_'+uuid4().hex[:16]
    admin=create_engine(make_url(url).set(database='postgres'),isolation_level='AUTOCOMMIT')
    target=None
    try:
        with admin.connect() as connection:connection.exec_driver_sql('CREATE DATABASE '+name)
        target_url=make_url(url).set(database=name).render_as_string(hide_password=False)
        applied=apply_migrations(target_url,Path(__file__).resolve().parents[2]/'db'/'migrations')
        assert '041_run_a_personnel_administration.sql' in applied
        assert apply_migrations(target_url,Path(__file__).resolve().parents[2]/'db'/'migrations')==[]
        target=create_engine(target_url)
        with Session(target) as db:
            unit=OrganizationUnit(code='TEST',name='Synthetic unit');employee=Employee(display_name='Synthetic employee')
            db.add_all([unit,employee]);db.flush();eid,oid=employee.employee_id,unit.organization_id
            db.add(EmployeeAssignment(employee_id=eid,organization_id=oid,title='本務',valid_from=date(2026,1,1)))
            db.commit()
        with pytest.raises(DBAPIError):
            with Session(target) as db:
                db.add(EmployeeAssignment(employee_id=eid,organization_id=oid,title='重複',valid_from=date(2026,10,1)))
                db.commit()
        with Session(target) as db:
            db.add(EmployeeAssignment(employee_id=eid,organization_id=oid,title='兼務',kind='secondary',valid_from=date(2026,10,1)))
            db.commit()
        # A reset holds the same PostgreSQL transaction lock as login. The old
        # password must be re-read only after reset commit, never yield a session.
        from concurrent.futures import ThreadPoolExecutor, TimeoutError
        from threading import Event
        from app.personnel import account_change_lock
        from app.routers import auth, administration
        with Session(target) as db:
            user=User(username='race',password_hash=hash_password('synthetic-old-password'))
            db.add(user);db.commit();uid=user.user_id
        http_app=FastAPI();http_app.include_router(auth.router)
        def sessions():
            with Session(target,expire_on_commit=False) as db:yield db
        http_app.dependency_overrides[get_db]=sessions
        entered=Event()
        def old_login():
            with TestClient(http_app) as client:
                entered.set()
                return client.post('/auth/login',json={'username':'race','password':'synthetic-old-password'}).status_code
        with Session(target) as reset:
            account_change_lock(reset)
            administration.replace_password(reset,reset.get(User,uid),'synthetic-new-password',1)
            with ThreadPoolExecutor(max_workers=1) as pool:
                future=pool.submit(old_login);assert entered.wait(5)
                try:
                    with pytest.raises(TimeoutError):future.result(timeout=.25)
                finally:
                    reset.commit()
                assert future.result(timeout=10)==401
    finally:
        if target:target.dispose()
        with admin.connect() as connection:connection.exec_driver_sql('DROP DATABASE IF EXISTS '+name+' WITH (FORCE)')
        admin.dispose()


def test_personnel_manager_cannot_reopen_role_bearing_assignment(environment):
    from app.models import Role, Permission, RolePermission
    client,engine,roles,app=environment;unit=org(client);person=staff(client)
    account=client.post('/administration/accounts',json={'employee_id':person['employee_id'],'username':'hr',
        'password':'synthetic-hr-password','reason':'Human採用承認'}).json()
    assignment=client.post('/administration/staff/'+person['employee_id']+'/assignments',json={
        'expected_version':1,'organization_id':unit['organization_id'],'title':'旧所属',
        'valid_from':'2025-01-01','valid_to':'2025-12-31','role_ids':[roles['legal_rule_approver']],
        'reason':'Human過去辞令'}).json()
    with Session(engine) as db:
        hr=Role(code='hr',name='Synthetic HR');db.add(hr);db.flush()
        for code in ['personnel.manage','personnel.read']:
            permission=db.scalar(select(Permission).where(Permission.code==code))
            db.add(RolePermission(role_id=hr.role_id,permission_id=permission.permission_id))
        db.add(UserRole(user_id=account['user_id'],role_id=hr.role_id));db.commit()
    with TestClient(app) as second:
        assert second.post('/auth/login',json={'username':'hr','password':'synthetic-hr-password'}).status_code==200
        response=second.patch('/administration/assignments/'+assignment['assignment_id'],json={
            'expected_version':1,'expected_employee_version':2,'valid_to':None,'reason':'Human期間変更'})
        assert response.status_code==403,response.text
        assert second.patch('/administration/assignments/'+assignment['assignment_id'],json={
            'expected_version':1,'expected_employee_version':2,'title':'旧所属訂正','reason':'Human表記訂正'}).status_code==200


def test_login_rechecks_password_after_account_change_serialization(environment,monkeypatch):
    from app.routers import auth
    client,engine,roles,app=environment
    called=[]
    def completed_reset(db):
        called.append(True)
        user=db.scalar(select(User).where(User.username=='admin'))
        user.password_hash=hash_password('concurrent-reset-password');db.commit();db.expire_all()
    monkeypatch.setattr(auth,'account_change_lock',completed_reset,raising=False)
    with TestClient(app) as second:
        assert second.post('/auth/login',json={'username':'admin','password':'synthetic-admin-password'}).status_code==401
    assert called


@pytest.mark.parametrize('resource',['organizations','staff'])
def test_hr_cannot_restore_active_state_without_account_authority(environment,resource):
    from app.models import Role, Permission, RolePermission
    client,engine,roles,app=environment;unit=org(client);person=staff(client)
    account=client.post('/administration/accounts',json={'employee_id':person['employee_id'],'username':'hr',
        'password':'synthetic-hr-password','reason':'Human採用承認'}).json()
    target=unit if resource=='organizations' else client.post('/administration/staff',json={'employee_code':'TARGET','display_name':'Synthetic target'}).json()
    key='organization_id' if resource=='organizations' else 'employee_id';url='/administration/'+resource+'/'+target[key]
    assert client.patch(url,json={'expected_version':1,'active':False,'reason':'Human無効化'}).status_code==200
    with Session(engine) as db:
        hr=Role(code='hr',name='Synthetic HR');db.add(hr);db.flush()
        for code in ['personnel.manage','personnel.read']:
            permission=db.scalar(select(Permission).where(Permission.code==code));db.add(RolePermission(role_id=hr.role_id,permission_id=permission.permission_id))
        db.add(UserRole(user_id=account['user_id'],role_id=hr.role_id));db.commit()
    with TestClient(app) as second:
        second.post('/auth/login',json={'username':'hr','password':'synthetic-hr-password'})
        assert second.patch(url,json={'expected_version':2,'active':True,'reason':'Human復帰'}).status_code==403


def test_password_rejects_fifth_previous_generation(environment):
    client,engine,roles,_=environment
    user_id=client.get('/auth/me').json()['user_id']
    unit=org(client);person=staff(client)
    target=client.post('/administration/accounts',json={'employee_id':person['employee_id'],'username':'history',
        'password':'history-generation-0','reason':'Human登録'}).json()
    for generation in range(1,6):
        response=client.post('/administration/accounts/'+target['user_id']+'/password-reset',json={
            'expected_version':generation,'new_password':'history-generation-'+str(generation),'reason':'Human更新'})
        assert response.status_code==200,response.text
    assert client.post('/administration/accounts/'+target['user_id']+'/password-reset',json={
        'expected_version':6,'new_password':'history-generation-0','reason':'Human再利用'}).status_code==422


def test_account_manager_has_narrow_staff_picker_without_personnel_read(environment):
    from app.models import Role, Permission, RolePermission
    client,engine,roles,app=environment;person=staff(client)
    account=client.post('/administration/accounts',json={'employee_id':person['employee_id'],'username':'accounts',
        'password':'synthetic-account-password','reason':'Human採用承認'}).json()
    with Session(engine) as db:
        role=Role(code='accounts',name='Synthetic account manager');db.add(role);db.flush()
        permission=db.scalar(select(Permission).where(Permission.code=='account.manage'))
        db.add(RolePermission(role_id=role.role_id,permission_id=permission.permission_id));db.add(UserRole(user_id=account['user_id'],role_id=role.role_id));db.commit()
    with TestClient(app) as second:
        second.post('/auth/login',json={'username':'accounts','password':'synthetic-account-password'})
        assert second.get('/administration/staff').status_code==403
        response=second.get('/administration/account-staff')
        assert response.status_code==200,response.text
        assert set(response.json()[0])=={'employee_id','employee_code','display_name','active'}


def test_audit_keyset_pages_do_not_drop_older_history(environment):
    client,engine,_,_=environment
    with Session(engine) as db:
        for i in range(5):db.add(AuditLog(action='synthetic.paging',entity_type='synthetic',entity_id=str(i)))
        db.commit()
    first=client.get('/administration/audit?limit=2&action=synthetic.paging').json()
    second=client.get('/administration/audit',params={'limit':2,'action':'synthetic.paging','before_id':first[-1]['audit_id']}).json()
    assert len(first)==len(second)==2
    assert set(row['audit_id'] for row in first).isdisjoint(row['audit_id'] for row in second)
    assert all(row['action']=='synthetic.paging' for row in first+second)
