"""Synthetic RED audit: available crew must require current personnel authority."""
from test_run_b_workforce import client, create_roster, approve_roster, remove
from datetime import date
import pytest
from sqlalchemy import select
from app.db import SessionLocal
from app.models import Document,User,UserSession,FeatureFlag,now_utc,Employee
from app.workforce_models import WorkforceRosterEntry,WorkforceEmployeeQualification,WorkforceShiftType,WorkforceLeaveEntry
from app.personnel import EmployeeAssignment,OrganizationUnit
from sqlalchemy.orm import Session
from app import workforce_crew
from test_observed_statistics_postgres import statistics_pg

URL='/workforce/available-crew?on_date=2026-10-10'


def original_fixture(client,source='roster',kind='personnel_notice'):
    roster=approve_roster(client,create_roster(client))
    with SessionLocal() as db:
        actor=db.scalar(select(User).where(User.username=='workforce'))
        original=Document(storage_path='synthetic-unused-no-file',original_filename='Synthetic typed evidence',sha256='1'*64,document_type=kind)
        db.add(original);db.flush();qualification=None
        if source=='roster':db.get(WorkforceRosterEntry,roster['roster_entry_id']).document_id=original.document_id
        else:
            qualification=WorkforceEmployeeQualification(employee_id=roster['employee_id'],code='EMT',label='Synthetic qualification',valid_from=date(2026,1,1),document_id=original.document_id,created_by=actor.user_id)
            db.add(qualification);db.flush()
        db.commit()
        return roster,original.document_id,qualification.qualification_id if qualification else None


def assert_private_denial(response,status,roster=None):
    assert response.status_code==status,response.text
    assert response.headers.get('cache-control')=='no-store'
    for private in ('=Synthetic FormulaUser','EMT',*( [roster['employee_id'],roster['roster_entry_id']] if roster else [])):
        assert private not in response.text


@pytest.mark.parametrize('source',['roster','qualification'])
def test_available_crew_requires_typed_original_authority(client,source):
    roster,_,_=original_fixture(client,source,'hazardous_evidence')
    response=client.get('/workforce/available-crew?on_date=2026-10-10')
    assert response.status_code==403
    assert response.headers.get('cache-control')=='no-store'
    for private in ('=Synthetic FormulaUser','EMT',roster['employee_id'],roster['roster_entry_id']):assert private not in response.text


def test_available_crew_denies_personnel_permission_loss(client):
    roster = approve_roster(client, create_roster(client))
    path = '/workforce/available-crew?on_date=2026-10-10'
    allowed = client.get(path)
    assert allowed.status_code == 200, allowed.text
    rows = allowed.json()
    assert len(rows) == 1, rows
    assert rows[0]['roster_entry_id'] == roster['roster_entry_id']
    assert rows[0]['employee_id'] == roster['employee_id']
    assert rows[0]['display_name'] == '=Synthetic FormulaUser'
    remove('personnel.read')
    denied = client.get(path)
    assert denied.status_code == 403, (
        'Current personnel.read loss must reject individual crew data; '
        f'actual status={denied.status_code}, synthetic response={denied.text}'
    )
    assert denied.headers.get('cache-control') == 'no-store'
    for private_value in ('=Synthetic FormulaUser', roster['roster_entry_id'], roster['employee_id']):
        assert private_value not in denied.text


@pytest.mark.parametrize('source',['roster','qualification'])
def test_typed_original_current_authority_allows_existing_projection(client,source):
    roster,_,_=original_fixture(client,source)
    response=client.get(URL)
    assert response.status_code==200,response.text
    assert response.headers['cache-control']=='no-store'
    assert response.json()[0]['employee_id']==roster['employee_id']
    assert response.json()[0]['qualifications']==(['EMT'] if source=='qualification' else [])
    assert 'fingerprint' not in response.text and 'sha256' not in response.text


@pytest.mark.parametrize('source',['roster','qualification'])
def test_missing_original_is_not_verified(client,source):
    roster,key,_=original_fixture(client,source)
    with SessionLocal() as db:
        db.delete(db.get(Document,key));db.commit()
    assert_private_denial(client.get(URL),403,roster)


@pytest.mark.parametrize('path',[URL,'/workforce/available-crew?on_date=not-a-date','/workforce/available-crew'])
def test_no_store_validation_and_unauthenticated(client,path):
    if path!=URL:assert_private_denial(client.get(path),422)
    client.cookies.clear()
    assert_private_denial(client.get(path),401)


@pytest.mark.parametrize('change,status',[
    ('personnel',403),('workforce',403),('document',403),('session',401),
    ('account',403),('actor_employee',403),('password',403),('module',503),
    ('name',409),('assignment',409),('organization',409),('work_rule',409),
    ('qualification',409),('original_sha',409),('original_type',403),
    ('roster',409),('leave_insert',409),('qualification_insert',409),('roster_insert',409),
])
def test_fresh_postflight_blocks_change_without_stale_projection(client,monkeypatch,change,status):
    roster,doc_key,qualification=original_fixture(client,'qualification')
    original_capture=workforce_crew.capture
    changed=False

    def capture_and_change(*args,**kwargs):
        nonlocal changed
        result=original_capture(*args,**kwargs)
        if not changed:
            changed=True
            if change in ('personnel','workforce','document'):remove(change+'.read')
            else:
                with SessionLocal() as writer:
                    actor=writer.scalar(select(User).where(User.username=='workforce'))
                    row=writer.get(WorkforceRosterEntry,roster['roster_entry_id'])
                    if change=='session':writer.query(UserSession).filter_by(user_id=actor.user_id).update({'revoked_at':now_utc()})
                    elif change=='account':actor.active=False
                    elif change=='actor_employee':writer.get(Employee,actor.employee_id).active=False
                    elif change=='password':
                        from datetime import datetime,timezone,timedelta
                        actor.password_expires_at=datetime.now(timezone.utc)-timedelta(days=1)
                    elif change=='module':writer.add(FeatureFlag(key='module.workforce.enabled',module_code='workforce',enabled=False))
                    elif change=='name':writer.get(Employee,row.employee_id).display_name='Synthetic changed name'
                    elif change=='assignment':writer.get(EmployeeAssignment,row.assignment_id).title='Synthetic changed title'
                    elif change=='organization':writer.get(OrganizationUnit,row.organization_id).name='Synthetic changed station'
                    elif change=='work_rule':writer.get(WorkforceShiftType,row.shift_type_id).name='Synthetic changed shift'
                    elif change=='qualification':writer.get(WorkforceEmployeeQualification,qualification).label='Synthetic changed evidence'
                    elif change=='original_sha':writer.get(Document,doc_key).sha256='2'*64
                    elif change=='original_type':writer.get(Document,doc_key).document_type='hazardous_evidence'
                    elif change=='roster':row.note='Synthetic changed note'
                    elif change=='leave_insert':writer.add(WorkforceLeaveEntry(employee_id=row.employee_id,leave_type='special',kind='use',quantity_minutes=1,effective_on=row.work_date,leave_start_at=row.starts_at,leave_end_at=row.ends_at,status='approved',created_by=actor.user_id))
                    elif change=='qualification_insert':writer.add(WorkforceEmployeeQualification(employee_id=row.employee_id,code='NEW',label='Synthetic new qualification',valid_from=date(2026,1,1),created_by=actor.user_id))
                    elif change=='roster_insert':
                        values={c.name:getattr(row,c.name) for c in row.__table__.columns if c.name not in ('roster_entry_id','created_at','updated_at')}
                        writer.add(WorkforceRosterEntry(**values))
                    writer.commit()
        return result

    monkeypatch.setattr(workforce_crew,'capture',capture_and_change)
    assert_private_denial(client.get(URL),status,roster)
    assert changed


def test_stale_and_leave_eligibility_are_preserved(client):
    from app import workforce_service
    from app.db import engine
    roster=approve_roster(client,create_roster(client))
    with Session(engine) as db:
        before=workforce_service.available_crew(db,date(2026,10,10))
    assert client.get(URL).json()==before
    with SessionLocal() as db:
        db.get(EmployeeAssignment,roster['assignment_id']).version+=1;db.commit()
    assert client.get(URL).json()==[]


@pytest.mark.parametrize('change',['none','template_sha','template_type','ownership'])
def test_derived_original_template_and_live_closure_dependencies(client,monkeypatch,change):
    from app.models import FormTemplate,Permission,RolePermission,Role
    from app.inquiries_models import Inquiry,InquiryRenderedForm
    roster,original_key,_=original_fixture(client)
    with SessionLocal() as db:
        actor=db.scalar(select(User).where(User.username=='workforce'))
        role=db.scalar(select(Role).where(Role.code=='workforce-test'))
        # Fixture-only inquiry access, in the disposable synthetic DB.
        permission=Permission(code='inquiry.read');db.add(permission);db.flush()
        db.add(RolePermission(role_id=role.role_id,permission_id=permission.permission_id))
        inquiry=Inquiry(year=2026,question='Synthetic derivation',created_by=actor.user_id)
        template_document=Document(storage_path='synthetic-unused-template',original_filename='Synthetic template',sha256='3'*64,document_type='personnel_notice')
        db.add_all([inquiry,template_document]);db.flush()
        template=FormTemplate(template_code='SYN-CREW',name='Synthetic template',module_code='workforce',document_id=template_document.document_id,version_label='1')
        db.add(template);db.flush()
        db.get(Document,original_key).document_type='inquiry_rendered_original'
        db.add(InquiryRenderedForm(inquiry_id=inquiry.inquiry_id,form_template_id=template.form_template_id,document_id=original_key,manifest={'template_document_id':template_document.document_id},created_by=actor.user_id));db.commit()
        template_key=template_document.document_id
        template_id=template.form_template_id
    if change!='none':
        original_capture=workforce_crew.capture
        changed=False
        def interrupted(*args,**kwargs):
            nonlocal changed
            result=original_capture(*args,**kwargs)
            if not changed:
                changed=True
                with SessionLocal() as writer:
                    if change=='template_sha':writer.get(Document,template_key).sha256='4'*64
                    elif change=='template_type':writer.get(Document,template_key).document_type='hazardous_evidence'
                    else:writer.get(FormTemplate,template_id).name='Synthetic changed template'
                    writer.commit()
            return result
        monkeypatch.setattr(workforce_crew,'capture',interrupted)
    response=client.get(URL)
    if change=='none':assert response.status_code==200,response.text
    else:assert_private_denial(response,403 if change=='template_type' else 409,roster)


@pytest.mark.parametrize('change',['assignment','work_rule','leave','inactive','qualification_dates'])
def test_existing_eligibility_and_filters_remain_exact(client,change):
    from datetime import timedelta
    from app import workforce_service
    from app.db import engine
    roster,_,qualification=original_fixture(client,'qualification')
    with SessionLocal() as db:
        row=db.get(WorkforceRosterEntry,roster['roster_entry_id'])
        if change=='assignment':db.get(EmployeeAssignment,row.assignment_id).version+=1
        elif change=='work_rule':db.get(WorkforceShiftType,row.shift_type_id).version+=1
        elif change=='inactive':db.get(Employee,row.employee_id).active=False
        elif change=='qualification_dates':db.get(WorkforceEmployeeQualification,qualification).valid_to=date(2026,10,9)
        else:
            db.add(WorkforceLeaveEntry(employee_id=row.employee_id,leave_type='special',kind='use',quantity_minutes=1,effective_on=row.work_date,leave_start_at=row.starts_at+timedelta(minutes=1),leave_end_at=row.starts_at+timedelta(minutes=2),status='approved',created_by=row.created_by))
        db.commit()
    with Session(engine) as db:
        expected=workforce_service.available_crew(db,date(2026,10,10))
    response=client.get(URL)
    assert response.status_code==200,response.text
    assert response.json()==expected
    assert response.headers['cache-control']=='no-store'
    assert client.get(URL+'&organization_id=00000000-0000-4000-8000-000000000001').json()==[]
    assert client.get(URL+'&shift_type_id=00000000-0000-4000-8000-000000000001').json()==[]


def test_shared_original_fingerprint_is_independent_of_candidate_query_order(client):
    from app.db import engine
    from app.statistics_service import RequestIdentity,bound_transaction
    from app.security import token_digest
    roster,_,_=original_fixture(client)
    with SessionLocal() as db:
        row=db.get(WorkforceRosterEntry,roster['roster_entry_id'])
        values={column.name:getattr(row,column.name) for column in row.__table__.columns if column.name not in ('roster_entry_id','created_at','updated_at')}
        db.add(WorkforceRosterEntry(**values));db.commit()
        actor=db.scalar(select(User).where(User.username=='workforce'))
        identity=RequestIdentity(engine,actor.user_id,token_digest(client.cookies.get('fire_ai_session')))
    with bound_transaction(identity,capture=True) as db:
        first=workforce_crew.capture(db,identity,date(2026,10,10),project=False)
    with bound_transaction(identity,capture=True) as db:
        execute=db.execute
        class ReverseCandidates:
            def __init__(self,result):self.result=result
            def all(self):return list(reversed(self.result.all()))
        def reversed_query(statement,*args,**kwargs):
            result=execute(statement,*args,**kwargs)
            descriptions=getattr(statement,'column_descriptions',[])
            if len(descriptions)==2 and descriptions[0].get('entity') is WorkforceRosterEntry and descriptions[1].get('entity') is Employee:
                return ReverseCandidates(result)
            return result
        db.execute=reversed_query
        second=workforce_crew.capture(db,identity,date(2026,10,10),project=False)
    assert first['fingerprint']==second['fingerprint']


@pytest.fixture
def crew_pg(statistics_pg):
    """Pipeline-backed disposable migrated PG; local absence is SKIP, not PASS."""
    from datetime import datetime,time,timezone
    from app.models import Permission,RolePermission
    from app.routers.workforce import router
    from test_run_b_workforce import CODES
    c,engine,refs=statistics_pg
    c.app.include_router(router)
    with Session(engine) as db:
        # Synthetic test role only; no production grants or authorization change.
        for code in CODES:
            permission=db.scalar(select(Permission).where(Permission.code==code))
            if permission is None:
                permission=Permission(code=code);db.add(permission);db.flush()
            if db.get(RolePermission,(refs['role_id'],permission.permission_id)) is None:
                db.add(RolePermission(role_id=refs['role_id'],permission_id=permission.permission_id))
        organization=OrganizationUnit(code='CREW-SYN',name='Synthetic station')
        employee=Employee(employee_code='CREW-SYN',display_name='=Synthetic FormulaUser')
        shift=WorkforceShiftType(code='CREW-SYN',name='Synthetic shift',start_time=time(8),end_time=time(17),payable_minutes=480)
        db.add_all([organization,employee,shift]);db.flush()
        assignment=EmployeeAssignment(employee_id=employee.employee_id,organization_id=organization.organization_id,title='Synthetic member',kind='primary',valid_from=date(2026,1,1))
        document=Document(storage_path='synthetic-unused-no-file',original_filename='Synthetic personnel original',sha256='1'*64,document_type='personnel_notice')
        db.add_all([assignment,document]);db.flush()
        roster=WorkforceRosterEntry(employee_id=employee.employee_id,organization_id=organization.organization_id,assignment_id=assignment.assignment_id,assignment_version=1,shift_type_id=shift.shift_type_id,work_date=date(2026,10,10),starts_at=datetime(2026,10,10,8,tzinfo=timezone.utc),ends_at=datetime(2026,10,10,17,tzinfo=timezone.utc),payable_minutes=480,status='approved',work_rule_snapshot={'shift_version':1,'approved_by':refs['user_id']},document_id=document.document_id,created_by=refs['user_id'])
        db.add(roster);db.flush()
        qualification=WorkforceEmployeeQualification(employee_id=employee.employee_id,code='EMT',label='Synthetic qualification',valid_from=date(2026,1,1),document_id=document.document_id,created_by=refs['user_id'])
        db.add(qualification);db.flush();db.commit()
        refs={**refs,'roster_id':roster.roster_entry_id,'employee_id':employee.employee_id,'document_id':document.document_id,'assignment_id':assignment.assignment_id,'qualification_id':qualification.qualification_id}
    yield c,engine,refs


@pytest.mark.parametrize('change,status',[('session',401),('personnel',403),('original_type',403),('original_sha',409),('qualification',409),('assignment',409),('leave',409)])
def test_postgresql_fresh_read_committed_release_rejects_separate_writer(crew_pg,monkeypatch,change,status):
    from sqlalchemy import text
    from app.models import Permission,RolePermission
    c,engine,refs=crew_pg
    assert c.get(URL).status_code==200
    original=workforce_crew.capture
    modes=[]

    def concurrent(db,identity,*args,**kwargs):
        modes.append((db.scalar(text('SHOW transaction_isolation')),db.scalar(text('SHOW transaction_read_only'))))
        result=original(db,identity,*args,**kwargs)
        if len(modes)==1:
            with Session(engine) as writer:
                roster=writer.get(WorkforceRosterEntry,refs['roster_id'])
                if change=='session':writer.query(UserSession).filter_by(user_id=refs['user_id']).update({'revoked_at':now_utc()})
                elif change=='personnel':
                    permission=writer.scalar(select(Permission).where(Permission.code=='personnel.read'))
                    writer.query(RolePermission).filter_by(role_id=refs['role_id'],permission_id=permission.permission_id).delete()
                elif change=='original_type':writer.get(Document,refs['document_id']).document_type='hazardous_evidence'
                elif change=='original_sha':writer.get(Document,refs['document_id']).sha256='2'*64
                elif change=='qualification':writer.get(WorkforceEmployeeQualification,refs['qualification_id']).label='Synthetic changed qualification'
                elif change=='assignment':writer.get(EmployeeAssignment,refs['assignment_id']).title='Synthetic changed title'
                elif change=='leave':writer.add(WorkforceLeaveEntry(employee_id=refs['employee_id'],leave_type='special',kind='use',quantity_minutes=1,effective_on=roster.work_date,leave_start_at=roster.starts_at,leave_end_at=roster.ends_at,status='approved',created_by=refs['user_id']))
                writer.commit()
        return result

    monkeypatch.setattr(workforce_crew,'capture',concurrent)
    assert_private_denial(c.get(URL),status)
    assert modes[0]==('repeatable read','on')
    if status==409 or change=='original_type':assert modes[1]==('read committed','off')
    with engine.connect() as connection:
        assert connection.exec_driver_sql('SHOW transaction_read_only').scalar_one()=='off'
        assert connection.exec_driver_sql('SHOW transaction_isolation').scalar_one()=='read committed'
