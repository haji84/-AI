"""Synthetic workforce integrity, Human gates and shared personnel integration."""
import os
os.environ['FIRE_AI_DATABASE_URL']='sqlite+pysqlite:///:memory:'

from datetime import date,datetime,timezone
from io import BytesIO
from pathlib import Path
import csv
import subprocess

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.db import Base,engine,SessionLocal
from app.main import app
from app.models import Employee,User,Role,Permission,RolePermission,UserRole,AuditLog
from app.personnel import OrganizationUnit,EmployeeAssignment
from app.security import hash_password
from app.workforce_models import WorkforceRosterEntry,WorkforceLeaveEntry

CODES=[
    'workforce.read','workforce.create','workforce.update','workforce.review','workforce.approve',
    'workforce.admin','workforce.import','workforce.export','workforce.aggregate',
    'search.use','document.read','personnel.read',
]

@pytest.fixture
def client():
    Base.metadata.drop_all(engine);Base.metadata.create_all(engine)
    with SessionLocal() as db:
        org=OrganizationUnit(code='MAIN',name='Synthetic Main');support=OrganizationUnit(code='SUP',name='Synthetic Support')
        operator=Employee(display_name='Synthetic Operator',employee_code='OP')
        target=Employee(display_name='=Synthetic FormulaUser',employee_code='E001')
        db.add_all([org,support,operator,target]);db.flush()
        for emp in [operator,target]:
            db.add(EmployeeAssignment(employee_id=emp.employee_id,organization_id=org.organization_id,title='Member',kind='primary',valid_from=date(2026,1,1)))
        user=User(username='workforce',employee_id=operator.employee_id,password_hash=hash_password('synthetic-password'))
        role=Role(code='workforce-test',name='Synthetic Workforce')
        db.add_all([user,role]);db.flush();db.add(UserRole(user_id=user.user_id,role_id=role.role_id))
        for code in CODES:
            p=Permission(code=code);db.add(p);db.flush();db.add(RolePermission(role_id=role.role_id,permission_id=p.permission_id))
        db.commit()
    with TestClient(app) as c:
        r=c.post('/auth/login',json={'username':'workforce','password':'synthetic-password'});assert r.status_code==200,r.text
        yield c

def remove(code):
    with SessionLocal() as db:
        p=db.scalar(select(Permission).where(Permission.code==code))
        for link in db.scalars(select(RolePermission).where(RolePermission.permission_id==p.permission_id)).all():db.delete(link)
        db.commit()

def refs():
    with SessionLocal() as db:
        emp=db.scalar(select(Employee).where(Employee.employee_code=='E001'))
        main=db.scalar(select(OrganizationUnit).where(OrganizationUnit.code=='MAIN'))
        support=db.scalar(select(OrganizationUnit).where(OrganizationUnit.code=='SUP'))
        assignment=db.scalar(select(EmployeeAssignment).where(EmployeeAssignment.employee_id==emp.employee_id))
        return emp.employee_id,main.organization_id,support.organization_id,assignment.assignment_id

def shift(client,code='DAY',start='08:30:00',end='17:15:00',cross=False,payable=465):
    r=client.post('/workforce/shift-types',json={'code':code,'name':code,'start_time':start,'end_time':end,'timezone_name':'Asia/Tokyo','cross_midnight':cross,'payable_minutes':payable})
    assert r.status_code==201,r.text;return r.json()

def action(client,path,row,action='review',status=200):
    r=client.post('/workforce/'+path+'/'+action,json={'expected_version':row['version'],'note':'Synthetic Human decision'})
    assert r.status_code==status,r.text
    return r.json() if r.content else None

def approve_roster(client,row):
    row=action(client,'rosters/'+row['roster_entry_id'],row,'review')
    return action(client,'rosters/'+row['roster_entry_id'],row,'approve')

def create_roster(client,day='2026-10-10',org=None,shift_id=None,support=False):
    emp,main,support_org,_=refs()
    org=org or main
    if shift_id is None:shift_id=shift(client)['shift_type_id']
    r=client.post('/workforce/rosters',json={'employee_id':emp,'organization_id':org,'shift_type_id':shift_id,'work_date':day,'support_placement':support})
    assert r.status_code==201,r.text;return r.json()

def test_shift_explicit_cross_midnight_and_stale_update(client):
    bad=client.post('/workforce/shift-types',json={'code':'NIGHTBAD','name':'Night','start_time':'16:00:00','end_time':'08:00:00','timezone_name':'Asia/Tokyo','cross_midnight':False,'payable_minutes':945})
    assert bad.status_code==422
    night=shift(client,'NIGHT','16:00:00','08:00:00',True,945)
    assert night['payable_minutes']==945
    r=client.patch('/workforce/shift-types/'+night['shift_type_id'],json={'expected_version':1,'name':'Night updated'})
    assert r.status_code==200 and r.json()['version']==2
    assert client.patch('/workforce/shift-types/'+night['shift_type_id'],json={'expected_version':1,'name':'Stale'}).status_code==409

def test_roster_uses_effective_assignment_support_and_blocks_overlap_and_stale_source(client):
    s=shift(client);emp,main,support,assignment_id=refs()
    normal=create_roster(client,'2026-10-10',main,s['shift_type_id'])
    assert normal['assignment_id']==assignment_id and normal['assignment_version']==1 and normal['status']=='draft'
    assert client.post('/workforce/rosters',json={'employee_id':emp,'organization_id':main,'shift_type_id':s['shift_type_id'],'work_date':'2026-10-10','support_placement':False}).status_code==409
    wrong=client.post('/workforce/rosters',json={'employee_id':emp,'organization_id':support,'shift_type_id':s['shift_type_id'],'work_date':'2026-10-11','support_placement':False})
    assert wrong.status_code==409
    support_row=create_roster(client,'2026-10-11',support,s['shift_type_id'],True)
    assert support_row['support_placement'] is True
    stale=create_roster(client,'2026-10-12',main,s['shift_type_id'])
    with SessionLocal() as db:
        a=db.get(EmployeeAssignment,assignment_id);a.version+=1;db.commit()
    assert client.post('/workforce/rosters/'+stale['roster_entry_id']+'/review',json={'expected_version':1,'note':'Review stale'}).status_code==409
    approved=approve_roster(client,normal)
    assert approved['status']=='approved' and approved['approved_by']

def test_staffing_rule_qualification_and_partial_leave_overlap(client):
    s=shift(client);emp,main,_,_=refs()
    q=client.post('/workforce/qualifications',json={'employee_id':emp,'code':'EMT','label':'Synthetic qualification','valid_from':'2026-01-01'})
    assert q.status_code==201,q.text
    rule=client.post('/workforce/staffing-rules',json={'organization_id':main,'shift_type_id':s['shift_type_id'],'min_staff':1,'qualification_code':'EMT','effective_from':'2026-01-01'}).json()
    rule=action(client,'staffing-rules/'+rule['staffing_rule_id'],rule,'review');rule=action(client,'staffing-rules/'+rule['staffing_rule_id'],rule,'approve')
    roster=approve_roster(client,create_roster(client,'2026-10-10',main,s['shift_type_id']))
    warning=client.get('/workforce/warnings?on_date=2026-10-10').json()[0];assert warning['available']==1 and warning['shortage']==0
    grant=client.post('/workforce/leave',json={'employee_id':emp,'leave_type':'annual','kind':'grant','quantity_minutes':480,'effective_on':'2026-10-01','private_reason':'PrivateLeaveSecret'}).json()
    grant=action(client,'leave/'+grant['leave_entry_id'],grant,'review');grant=action(client,'leave/'+grant['leave_entry_id'],grant,'approve')
    use=client.post('/workforce/leave',json={'employee_id':emp,'leave_type':'annual','kind':'use','quantity_minutes':60,'effective_on':'2026-10-10','leave_start_at':'2026-10-10T09:00:00+09:00','leave_end_at':'2026-10-10T10:00:00+09:00','private_reason':'PrivateUseSecret'}).json()
    use=action(client,'leave/'+use['leave_entry_id'],use,'review');use=action(client,'leave/'+use['leave_entry_id'],use,'approve')
    balance=client.get('/workforce/leave-balance/'+emp+'?as_of=2026-10-10').json();assert balance['annual']==420
    warning=client.get('/workforce/warnings?on_date=2026-10-10').json()[0];assert warning['available']==0 and warning['shortage']==1
    later=client.post('/workforce/leave',json={'employee_id':emp,'leave_type':'annual','kind':'use','quantity_minutes':500,'effective_on':'2026-10-11','leave_start_at':'2026-10-11T08:30:00+09:00','leave_end_at':'2026-10-11T17:15:00+09:00'}).json()
    later=action(client,'leave/'+later['leave_entry_id'],later,'review')
    assert client.post('/workforce/leave/'+later['leave_entry_id']+'/approve',json={'expected_version':later['version'],'note':'Would go negative'}).status_code==409
    remove('personnel.read')
    assert 'PrivateLeaveSecret' not in str(client.get('/workforce/leave').json())

def test_attendance_time_ledgers_timezone_human_gate_and_comp_balance(client):
    s=shift(client,payable=480);emp,main,_,_=refs()
    roster=approve_roster(client,create_roster(client,'2026-10-15',main,s['shift_type_id']))
    naive=client.post('/workforce/attendance',json={'employee_id':emp,'roster_entry_id':roster['roster_entry_id'],'work_date':'2026-10-15','check_in_at':'2026-10-15T08:00:00','check_out_at':'2026-10-15T17:00:00'})
    assert naive.status_code==422
    r=client.post('/workforce/attendance',json={'employee_id':emp,'roster_entry_id':roster['roster_entry_id'],'work_date':'2026-10-15','check_in_at':'2026-10-15T08:00:00+09:00','check_out_at':'2026-10-15T17:00:00+09:00'})
    assert r.status_code==201,r.text;attendance=r.json()
    assert attendance['worked_minutes']==540 and attendance['calculation']['overtime_candidate_minutes']==60
    attendance=action(client,'attendance/'+attendance['attendance_id'],attendance,'review');attendance=action(client,'attendance/'+attendance['attendance_id'],attendance,'approve')
    overtime=client.post('/workforce/time-entries',json={'employee_id':emp,'attendance_id':attendance['attendance_id'],'kind':'overtime','minutes':60,'occurred_on':'2026-10-15','note':'Synthetic overtime'}).json()
    overtime=action(client,'time-entries/'+overtime['time_entry_id'],overtime,'review');action(client,'time-entries/'+overtime['time_entry_id'],overtime,'approve')
    grant=client.post('/workforce/time-entries',json={'employee_id':emp,'kind':'comp_grant','minutes':120,'occurred_on':'2026-10-16'}).json()
    grant=action(client,'time-entries/'+grant['time_entry_id'],grant,'review');action(client,'time-entries/'+grant['time_entry_id'],grant,'approve')
    use=client.post('/workforce/time-entries',json={'employee_id':emp,'kind':'comp_use','minutes':60,'occurred_on':'2026-10-17'}).json()
    use=action(client,'time-entries/'+use['time_entry_id'],use,'review');action(client,'time-entries/'+use['time_entry_id'],use,'approve')
    assert client.get('/workforce/comp-balance/'+emp+'?as_of=2026-10-17').json()['minutes']==60
    too_much=client.post('/workforce/time-entries',json={'employee_id':emp,'kind':'comp_use','minutes':120,'occurred_on':'2026-10-18'}).json()
    too_much=action(client,'time-entries/'+too_much['time_entry_id'],too_much,'review')
    assert client.post('/workforce/time-entries/'+too_much['time_entry_id']+'/approve',json={'expected_version':too_much['version'],'note':'Too much'}).status_code==409
    stats=client.get('/workforce/statistics?year=2026&month=10').json();assert stats['worked_minutes']==540 and stats['overtime_minutes']==60

def test_import_export_search_privacy_and_fresh_registration(client):
    s=shift(client);emp,main,_,_=refs()
    raw=b'schema_version,employee_code,organization_code,shift_code,work_date,support_placement,note\nworkforce-v1,E001,MAIN,DAY,2026-10-20,false,NeedleRosterSearch\n'
    p=client.post('/workforce/import/rosters',files={'file':('synthetic.csv',raw,'text/csv')});assert p.status_code==200,p.text;preview=p.json()
    assert client.get('/workforce/rosters?from_date=2026-10-20&to_date=2026-10-20').json()==[]
    r=client.post('/workforce/import-previews/'+preview['preview_id']+'/confirm',json={'expected_version':1,'file_sha256':preview['file_sha256']});assert r.status_code==200,r.text
    assert r.json()['inserted']==1
    out=client.get('/workforce/export/rosters?format=csv');assert out.status_code==200 and "'=Synthetic FormulaUser" in out.text
    rows=list(csv.DictReader(out.content.decode('utf-8-sig').splitlines()));assert rows[0]['assignment_id']
    xlsx=client.get('/workforce/export/rosters?format=xlsx');assert xlsx.status_code==200 and xlsx.content[:2]==b'PK'
    search=client.get('/search?q=NeedleRosterSearch&modules=workforce');assert search.status_code==200 and search.json()['hits'][0]['source_type']=='workforce_roster'
    leave=client.post('/workforce/leave',json={'employee_id':emp,'leave_type':'special','kind':'grant','quantity_minutes':60,'effective_on':'2026-10-20','private_reason':'PrivateSearchMustNotLeak'})
    assert leave.status_code==201
    assert client.get('/search?q=PrivateSearchMustNotLeak&modules=workforce').json()['hits']==[]
    assert 'workforce_roster_entries' in Base.metadata.tables and 'workforce_leave_entries' in Base.metadata.tables

def test_review_and_approval_permissions_are_separate(client):
    s=shift(client);emp,main,_,_=refs();row=create_roster(client,'2026-10-22',main,s['shift_type_id'])
    remove('workforce.approve')
    reviewed=action(client,'rosters/'+row['roster_entry_id'],row,'review')
    assert client.post('/workforce/rosters/'+row['roster_entry_id']+'/approve',json={'expected_version':reviewed['version'],'note':'Denied'}).status_code==403

def test_workforce_ui_and_bootstrap_registration():
    root=Path(__file__).resolve().parents[2]
    html=(root/'frontend/index.html').read_text()
    js=(root/'frontend/workforce.js').read_text()
    assert 'id="workforceBtn"' in html and '/ui/workforce.js' in html and 'await initWorkforce()' in html
    assert '最低人員' in js and '休暇Ledger' in js and '時間外/代休Ledger' in js
    r=subprocess.run(['python','-c',"import os;os.environ['FIRE_AI_DATABASE_URL']='sqlite+pysqlite:///:memory:';import app.bootstrap;from app.db import Base;assert 'workforce_roster_entries' in Base.metadata.tables"],cwd=root/'backend',capture_output=True,text=True)
    assert r.returncode==0,r.stderr

def test_workforce_audit_is_written(client):
    shift(client)
    with SessionLocal() as db:
        assert db.scalar(select(AuditLog).where(AuditLog.action=='workforce.shift.create'))
