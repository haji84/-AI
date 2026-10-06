"""Human-only department roles, exact rules, timed/acting grants and revocation."""
from datetime import date,timedelta
import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session
from test_password_expiry import expiry_environment,learning_environment,target_account


def create_role(client,name='Synthetic intake correction'):
    result=client.post('/administration/permission-roles',json={'name':name,'permission_codes':['learning.read','learning.record','document.read','intake.read'],'reason':'Human least-privilege approval'})
    assert result.status_code==201,result.text
    return result.json()


def test_custom_role_preserves_source_authority_and_cas(expiry_environment):
    client,engine=expiry_environment;role=create_role(client)
    identity=target_account(engine)
    granted=client.patch('/administration/accounts/'+identity,json={'expected_version':1,'role_ids':[role['role_id']],'reason':'Human appointment'})
    assert granted.status_code==200,granted.text
    from fastapi.testclient import TestClient
    with TestClient(client.app) as reader:
        assert reader.post('/auth/login',json={'username':'expiry-target','password':'synthetic-target-password'}).status_code==200
        context=reader.get('/learning/context');assert context.status_code==200
        assert 'ocr' in context.json()['tasks'] and 'audio_correction' not in context.json()['tasks']
        assert reader.get('/learning/corrections?task=audio_correction').status_code==403
        changed=client.patch('/administration/permission-roles/'+role['role_id'],json={'expected_version':role['version'],'permission_codes':['document.read','intake.read'],'reason':'Human revoke learning'})
        assert changed.status_code==200,changed.text
        assert reader.get('/auth/me').status_code==401
    assert client.patch('/administration/permission-roles/'+role['role_id'],json={'expected_version':1,'active':False,'reason':'stale'}).status_code==409


def test_temporary_and_acting_grants_use_jst_dates_and_immutable_revoke(expiry_environment,monkeypatch):
    from app import personnel
    from app.authz import permission_codes
    client,engine=expiry_environment;role=create_role(client);identity=target_account(engine)
    today=date(2026,10,7);monkeypatch.setattr(personnel,'business_date',lambda:today)
    payload={'user_id':identity,'role_id':role['role_id'],'valid_from':str(today+timedelta(days=1)),'valid_to':str(today+timedelta(days=2)),'reason':'Human temporary coverage'}
    response=client.post('/administration/role-grants',json=payload)
    assert response.status_code==201,response.text
    grant=response.json()
    with Session(engine) as db:assert 'learning.read' not in permission_codes(db,identity)
    monkeypatch.setattr(personnel,'business_date',lambda:today+timedelta(days=1))
    with Session(engine) as db:assert 'learning.read' in permission_codes(db,identity)
    revoked=client.post('/administration/role-grants/'+grant['grant_id']+'/revoke',json={'expected_version':1,'reason':'Human coverage ended'})
    assert revoked.status_code==200,revoked.text
    with Session(engine) as db:assert 'learning.read' not in permission_codes(db,identity)
    assert client.post('/administration/role-grants/'+grant['grant_id']+'/revoke',json={'expected_version':1,'reason':'stale'}).status_code==409
    history=client.get('/administration/role-grants?user_id='+identity)
    assert history.status_code==200 and history.json()[0]['revoked_at'] is not None


def test_exact_human_role_rule_follows_active_assignment_not_ai_title_guess(expiry_environment,monkeypatch):
    from app import personnel
    from app.models import User,Employee
    from app.personnel import EmployeeAssignment,OrganizationUnit
    from app.authz import permission_codes
    client,engine=expiry_environment;role=create_role(client);identity=target_account(engine)
    day=date(2026,10,7);monkeypatch.setattr(personnel,'business_date',lambda:day)
    with Session(engine) as db:
        unit=OrganizationUnit(code='SYNTH',name='Synthetic organization');db.add(unit);db.flush()
        employee=db.get(User,identity).employee_id
        db.add(EmployeeAssignment(employee_id=employee,organization_id=unit.organization_id,title='予防担当',kind='primary',valid_from=day));db.commit();organization=unit.organization_id
    created=client.post('/administration/role-rules',json={'name':'Synthetic exact assignment rule','role_id':role['role_id'],'organization_id':organization,'title':'予防担当','kind':'primary','valid_from':str(day),'reason':'Human role policy'})
    assert created.status_code==201,created.text
    with Session(engine) as db:assert 'learning.read' in permission_codes(db,identity)
    with Session(engine) as db:
        assignment=db.scalar(select(EmployeeAssignment).where(EmployeeAssignment.employee_id==employee));assignment.title='予防担当候補';db.commit()
    with Session(engine) as db:assert 'learning.read' not in permission_codes(db,identity)


def test_permissions_require_human_sensitive_ack_and_seeded_roles_are_readonly(expiry_environment):
    from app.models import Role
    client,engine=expiry_environment
    unknown=client.post('/administration/permission-roles',json={'name':'Synthetic unknown','permission_codes':['invented.clinical.read'],'reason':'Human invalid code'})
    assert unknown.status_code==422
    body={'name':'Synthetic clinical viewer','permission_codes':['emergency.patient.read'],'reason':'Human sensitive authorization'}
    assert client.post('/administration/permission-roles',json=body).status_code==422
    body['sensitive_acknowledged']=True;role=client.post('/administration/permission-roles',json=body)
    assert role.status_code==201,role.text
    with Session(engine) as db:root=db.scalar(select(Role).where(Role.code=='system_admin'));identity=root.role_id
    assert client.patch('/administration/permission-roles/'+identity,json={'expected_version':1,'active':False,'reason':'Human forbidden system mutation'}).status_code==422
    target=target_account(engine)
    root_grant=client.post('/administration/role-grants',json={'user_id':target,'role_id':identity,'valid_from':'2026-10-07','valid_to':'2026-10-08','sensitive_acknowledged':True,'reason':'Human invalid root proxy'})
    assert root_grant.status_code==422


def test_timed_acting_grant_expires_and_checks_principal_and_source(expiry_environment,monkeypatch):
    from app.models import Employee,Document
    from app.authz import permission_codes
    from app import personnel
    client,engine=expiry_environment;role=create_role(client);identity=target_account(engine);today=date(2026,10,7)
    with Session(engine) as db:
        principal=Employee(display_name='Synthetic acting principal');source=Document(original_filename='synthetic-role-policy.txt',storage_path='synthetic/policy.txt',sha256='c'*64)
        db.add_all([principal,source]);db.commit();principal_id=principal.employee_id;source_id=source.document_id
    monkeypatch.setattr(personnel,'business_date',lambda:today)
    created=client.post('/administration/role-grants',json={'user_id':identity,'role_id':role['role_id'],'acting_for_employee_id':principal_id,'source_document_id':source_id,'expected_source_sha256':'c'*64,'valid_from':str(today),'valid_to':str(today),'reason':'Human one-day proxy'})
    assert created.status_code==201,created.text
    with Session(engine) as db:assert 'learning.read' in permission_codes(db,identity)
    monkeypatch.setattr(personnel,'business_date',lambda:today+timedelta(days=1))
    with Session(engine) as db:assert 'learning.read' not in permission_codes(db,identity)
    monkeypatch.setattr(personnel,'business_date',lambda:today)
    with Session(engine) as db:db.get(Employee,principal_id).active=False;db.commit()
    with Session(engine) as db:assert 'learning.read' not in permission_codes(db,identity)
    with Session(engine) as db:db.get(Employee,principal_id).active=True;db.get(Document,source_id).sha256='d'*64;db.commit()
    with Session(engine) as db:assert 'learning.read' not in permission_codes(db,identity)


def test_seed_refresh_preserves_custom_role_and_audit_never_contains_credentials(expiry_environment):
    from app.models import Role,AuditLog
    from app.rbac_seed import seed_rbac
    from app.authz import permission_codes
    client,engine=expiry_environment;role=create_role(client)
    with Session(engine) as db:
        seed_rbac(db);db.commit()
        stored=db.get(Role,role['role_id']);assert not stored.system_role and stored.name==role['name']
        events=db.scalars(select(AuditLog).where(AuditLog.action=='permission.role.create')).all()
        assert len(events)==1 and 'password_hash' not in str(events[0].after_data)
        assert 'synthetic-target-password' not in str(events[0].after_data)


def test_inactive_organization_and_stale_rule_reference_stop_permissions(expiry_environment,monkeypatch):
    from app.models import User,Document
    from app.personnel import EmployeeAssignment,OrganizationUnit
    from app.authz import permission_codes
    from app import personnel
    client,engine=expiry_environment;role=create_role(client);identity=target_account(engine);day=date(2026,10,7)
    monkeypatch.setattr(personnel,'business_date',lambda:day)
    with Session(engine) as db:
        unit=OrganizationUnit(code='SOURCE',name='Synthetic source unit');source=Document(original_filename='synthetic-rule.txt',storage_path='synthetic/rule.txt',sha256='e'*64);db.add_all([unit,source]);db.flush()
        db.add(EmployeeAssignment(employee_id=db.get(User,identity).employee_id,organization_id=unit.organization_id,title='Synthetic title',kind='primary',valid_from=day));db.commit();unit_id=unit.organization_id;source_id=source.document_id
    result=client.post('/administration/role-rules',json={'name':'Synthetic source rule','role_id':role['role_id'],'organization_id':unit_id,'source_document_id':source_id,'expected_source_sha256':'e'*64,'valid_from':str(day),'reason':'Human source review'})
    assert result.status_code==201,result.text
    rule=result.json()
    with Session(engine) as db:assert 'learning.read' in permission_codes(db,identity)
    with Session(engine) as db:db.get(OrganizationUnit,unit_id).active=False;db.commit()
    with Session(engine) as db:assert 'learning.read' not in permission_codes(db,identity)
    with Session(engine) as db:db.get(OrganizationUnit,unit_id).active=True;db.get(Document,source_id).sha256='f'*64;db.commit()
    with Session(engine) as db:assert 'learning.read' not in permission_codes(db,identity)
    path='/administration/role-rules/'+rule['rule_id']
    assert client.patch(path,json={'expected_version':1,'active':False,'reason':'Human suspend'}).status_code==200
    resumed=client.patch(path,json={'expected_version':2,'active':True,'reason':'Human stale resume'})
    assert resumed.status_code==409,resumed.text


def test_own_permission_explanation_contains_no_other_employee_or_private_reason(expiry_environment):
    from app.models import Employee
    from fastapi.testclient import TestClient
    client,engine=expiry_environment;role=create_role(client);identity=target_account(engine)
    from app.personnel import business_date
    with Session(engine) as db:
        person=Employee(display_name='PRIVATE other employee');db.add(person);db.commit();person_id=person.employee_id
    day=business_date()
    grant=client.post('/administration/role-grants',json={'user_id':identity,'role_id':role['role_id'],'acting_for_employee_id':person_id,'valid_from':str(day),'valid_to':str(day),'reason':'PRIVATE absence reason'})
    assert grant.status_code==201,grant.text
    with TestClient(client.app) as reader:
        reader.post('/auth/login',json={'username':'expiry-target','password':'synthetic-target-password'})
        explained=reader.get('/administration/own-role-explanation')
        assert explained.status_code==200,explained.text
        assert 'acting' in explained.text and role['name'] in explained.text
        assert 'PRIVATE' not in explained.text and person_id not in explained.text
        assert reader.get('/administration/permission-roles').status_code==403


def test_human_source_preview_hash_is_required_and_stale_preview_rejected(expiry_environment):
    from app.models import Document
    from app.personnel import business_date
    client,engine=expiry_environment;role=create_role(client);identity=target_account(engine)
    with Session(engine) as db:
        source=Document(original_filename='synthetic-reviewed-policy.txt',storage_path='synthetic/preview.txt',sha256='a'*64);db.add(source);db.commit();source_id=source.document_id
    day=str(business_date())
    body={'user_id':identity,'role_id':role['role_id'],'valid_from':day,'valid_to':day,'source_document_id':source_id,'reason':'Human reviewed preview'}
    assert client.post('/administration/role-grants',json=body).status_code==422
    body['expected_source_sha256']='b'*64
    assert client.post('/administration/role-grants',json=body).status_code==409
    body['expected_source_sha256']='a'*64
    assert client.post('/administration/role-grants',json=body).status_code==201


def test_inactive_role_cannot_be_newly_assigned_to_account(expiry_environment):
    client,engine=expiry_environment;role=create_role(client);identity=target_account(engine)
    suspended=client.patch('/administration/permission-roles/'+role['role_id'],json={'expected_version':1,'active':False,'reason':'Human suspend'})
    assert suspended.status_code==200,suspended.text
    denied=client.patch('/administration/accounts/'+identity,json={'expected_version':1,'role_ids':[role['role_id']],'reason':'Human inactive grant'})
    assert denied.status_code==409,denied.text


def test_postgresql_competing_role_changes_have_one_audited_cas_winner(expiry_environment):
    import threading
    from fastapi.testclient import TestClient
    from app.models import AuditLog,Role
    client,engine=expiry_environment
    if engine.dialect.name!='postgresql':pytest.skip('actual PostgreSQL locking required')
    role=create_role(client);barrier=threading.Barrier(2);responses=[];failures=[]
    def change(index):
        try:
            with TestClient(client.app) as second:
                second.cookies.update(client.cookies);barrier.wait(timeout=10)
                responses.append(second.patch('/administration/permission-roles/'+role['role_id'],json={'expected_version':1,'name':'Synthetic winner '+str(index),'reason':'Human concurrent edit'}).status_code)
        except BaseException as error:failures.append(error)
    threads=[threading.Thread(target=change,args=(index,)) for index in range(2)]
    for thread in threads:thread.start()
    for thread in threads:thread.join(timeout=20)
    assert not failures and all(not thread.is_alive() for thread in threads),failures
    assert sorted(responses)==[200,409],responses
    with Session(engine) as db:
        assert db.get(Role,role['role_id']).version==2
        assert len(db.scalars(select(AuditLog).where(AuditLog.action=='permission.role.update',AuditLog.entity_id==role['role_id'])).all())==1


@pytest.mark.parametrize('future',[False,True])
def test_personnel_only_cannot_self_grant_through_human_rule(expiry_environment,future):
    from app.models import User,RolePermission,Permission,UserRole
    from app.personnel import OrganizationUnit,business_date
    from fastapi.testclient import TestClient
    client,engine=expiry_environment;identity=target_account(engine)
    managerial=client.post('/administration/permission-roles',json={'name':'Synthetic account delegate','permission_codes':['account.manage'],'sensitive_acknowledged':True,'reason':'Human privileged role'}).json()
    personnel=client.post('/administration/permission-roles',json={'name':'Synthetic personnel only','permission_codes':['personnel.manage'],'sensitive_acknowledged':True,'reason':'Human restricted staff operator'}).json()
    with Session(engine) as db:
        unit=OrganizationUnit(code='ESCALATION',name='Synthetic guarded organization');db.add(unit);db.flush();db.add(UserRole(user_id=identity,role_id=personnel['role_id']));employee=db.get(User,identity).employee_id;db.commit();organization=unit.organization_id
    start=business_date()+timedelta(days=1 if future else 0)
    made=client.post('/administration/role-rules',json={'name':'Synthetic delegate rule','role_id':managerial['role_id'],'organization_id':organization,'valid_from':str(start),'sensitive_acknowledged':True,'reason':'Human guarded policy'})
    assert made.status_code==201,made.text
    with TestClient(client.app) as limited:
        limited.post('/auth/login',json={'username':'expiry-target','password':'synthetic-target-password'})
        assert limited.get('/administration/accounts').status_code==403
        changed=limited.post('/administration/staff/'+employee+'/assignments',json={'expected_version':1,'organization_id':organization,'title':'Synthetic privileged title','valid_from':str(start),'role_ids':[],'reason':'Human unauthorized implicit grant'})
        assert changed.status_code==403,changed.text
        assert limited.get('/administration/accounts').status_code==403


def test_role_mutation_rechecks_originating_session_revoked_while_waiting(expiry_environment,monkeypatch):
    from app.routers import administration
    from app.models import UserSession,now_utc,Role
    client,engine=expiry_environment;original=administration.account_change_lock
    def revoked_lock(db):
        original(db)
        for row in db.scalars(select(UserSession)):row.revoked_at=now_utc()
        db.flush()
    monkeypatch.setattr(administration,'account_change_lock',revoked_lock)
    response=client.post('/administration/permission-roles',json={'name':'Synthetic revoked requester','permission_codes':['facility.read'],'reason':'Human queued revoked session'})
    assert response.status_code==401,response.text
    with Session(engine) as db:assert not db.scalar(select(Role).where(Role.name=='Synthetic revoked requester'))


def test_sensitive_role_reactivation_requires_acknowledgement_of_retained_permissions(expiry_environment):
    client,_=expiry_environment
    role=client.post('/administration/permission-roles',json={'name':'Synthetic dormant clinical role','permission_codes':['emergency.patient.read'],'sensitive_acknowledged':True,'reason':'Human clinical authority'}).json()
    path='/administration/permission-roles/'+role['role_id']
    assert client.patch(path,json={'expected_version':1,'active':False,'reason':'Human suspend'}).status_code==200
    assert client.patch(path,json={'expected_version':2,'active':True,'reason':'Human unacknowledged resume'}).status_code==422
    acknowledged=client.patch(path,json={'expected_version':2,'active':True,'sensitive_acknowledged':True,'reason':'Human reviewed resume'})
    assert acknowledged.status_code==200,acknowledged.text


def test_human_can_create_inactive_role_without_ignoring_selected_state(expiry_environment):
    client,_=expiry_environment
    result=client.post('/administration/permission-roles',json={'name':'Synthetic inactive draft role','permission_codes':['facility.read'],'active':False,'reason':'Human inactive initial definition'})
    assert result.status_code==201,result.text
    assert result.json()['active'] is False
