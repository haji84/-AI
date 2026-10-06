"""Synthetic reproductions of workforce Human/concurrency/time correctness review."""
from datetime import date,datetime,timezone
import pytest
from sqlalchemy import select
from app.models import UserSession,User,now_utc,Permission,RolePermission,Employee,AuditLog
from app.personnel import EmployeeAssignment
from app.workforce_models import WorkforceAttendance,WorkforceTimeEntry
from test_run_b_workforce import client,shift,refs,create_roster,approve_roster,action,SessionLocal


@pytest.mark.parametrize('change',['session','permission','employee','password'])
def test_mutation_rechecks_authority_after_wait(client,monkeypatch,change):
    from app import authz
    original=getattr(authz,'account_change_lock',lambda db:None)
    def invalidated(db):
        original(db)
        user=db.scalar(select(User).where(User.username=='workforce'))
        if change=='session':
            for row in db.scalars(select(UserSession)):row.revoked_at=now_utc()
        elif change=='permission':
            p=db.scalar(select(Permission).where(Permission.code=='workforce.admin'))
            for row in db.scalars(select(RolePermission).where(RolePermission.permission_id==p.permission_id)):db.delete(row)
        elif change=='employee':db.get(Employee,user.employee_id).active=False
        else:user.password_expires_at=now_utc()
        db.flush()
    monkeypatch.setattr(authz,'account_change_lock',invalidated,raising=False)
    r=client.post('/workforce/shift-types',json={'code':'REVOKED','name':'Synthetic','start_time':'08:00','end_time':'17:00','payable_minutes':480})
    assert r.status_code in (401,403),r.text
    with SessionLocal() as db:assert not db.scalar(select(AuditLog).where(AuditLog.action=='workforce.shift.create'))


@pytest.mark.parametrize('ledger',['leave','time-entries'])
def test_backdated_deduction_cannot_overdraw_future_balance(client,ledger):
    emp,*_=refs()
    def entry(kind,day):
        data={'employee_id':emp,'kind':kind,'quantity_minutes':100,'effective_on':day,'leave_type':'annual'} if ledger=='leave' else {'employee_id':emp,'kind':kind,'minutes':100,'occurred_on':day}
        if ledger=='leave' and kind=='use':data.update(leave_start_at=day+'T09:00:00+09:00',leave_end_at=day+'T10:40:00+09:00')
        r=client.post('/workforce/'+ledger,json=data);assert r.status_code==201,r.text
        row=r.json();key='leave_entry_id' if ledger=='leave' else 'time_entry_id'
        return action(client,ledger+'/'+row[key],row,'review'),key
    grant='grant' if ledger=='leave' else 'comp_grant';use='use' if ledger=='leave' else 'comp_use'
    row,key=entry(grant,'2026-10-01');action(client,ledger+'/'+row[key],row,'approve')
    row,key=entry(use,'2026-10-10');action(client,ledger+'/'+row[key],row,'approve')
    row,key=entry(use,'2026-10-05')
    assert client.post('/workforce/'+ledger+'/'+row[key]+'/approve',json={'expected_version':row['version'],'note':'Synthetic backdated deduction'}).status_code==409


def test_attendance_instant_survives_reload_and_checkout_only_patch(client):
    emp,*_=refs()
    r=client.post('/workforce/attendance',json={'employee_id':emp,'work_date':'2026-10-10','check_in_at':'2026-10-10T08:00:00+09:00','check_out_at':'2026-10-10T17:00:00Z'})
    assert r.status_code==201,r.text
    row=r.json();reloaded=next(x for x in client.get('/workforce/attendance').json() if x['attendance_id']==row['attendance_id'])
    assert datetime.fromisoformat(reloaded['check_in_at'].replace('Z','+00:00'))==datetime(2026,10,9,23,tzinfo=timezone.utc)
    r=client.post('/workforce/attendance',json={'employee_id':emp,'work_date':'2026-10-11','check_in_at':'2026-10-11T08:00:00+09:00'});row=r.json()
    patched=client.patch('/workforce/attendance/'+row['attendance_id'],json={'expected_version':1,'check_out_at':'2026-10-11T17:00:00+09:00'})
    assert patched.status_code==200,patched.text
    assert patched.json()['calculation']['elapsed_minutes']==540
    bad=client.patch('/workforce/attendance/'+row['attendance_id'],json={'expected_version':2,'check_in_at':'2026-10-11T18:00:00+09:00'})
    assert bad.status_code==422,bad.text


def test_morning_leave_uses_business_date_for_utc_input(client):
    emp,*_=refs()
    r=client.post('/workforce/leave',json={'employee_id':emp,'leave_type':'annual','kind':'use','quantity_minutes':60,'effective_on':'2026-10-16','leave_start_at':'2026-10-15T23:00:00Z','leave_end_at':'2026-10-16T00:00:00Z'})
    assert r.status_code==201,r.text


def test_shift_patch_validates_merged_midnight_configuration(client):
    row=shift(client)
    r=client.patch('/workforce/shift-types/'+row['shift_type_id'],json={'expected_version':row['version'],'end_time':'07:00:00'})
    assert r.status_code==422,r.text


def test_stale_approved_roster_is_excluded_from_crew_and_staffing(client):
    s=shift(client);emp,org,_,assignment=refs()
    rule=client.post('/workforce/staffing-rules',json={'organization_id':org,'shift_type_id':s['shift_type_id'],'min_staff':1,'effective_from':'2026-01-01'}).json()
    rule=action(client,'staffing-rules/'+rule['staffing_rule_id'],rule,'review');action(client,'staffing-rules/'+rule['staffing_rule_id'],rule,'approve')
    approve_roster(client,create_roster(client,'2026-10-10',org,s['shift_type_id']))
    with SessionLocal() as db:db.get(EmployeeAssignment,assignment).version+=1;db.commit()
    assert client.get('/workforce/available-crew?on_date=2026-10-10').json()==[]
    warning=client.get('/workforce/warnings?on_date=2026-10-10').json()[0]
    assert warning['available']==0 and warning['shortage']==1 and warning['stale_roster_entry_ids']


def test_human_roster_reason_is_persisted_in_audit(client):
    row=create_roster(client);identity=row['roster_entry_id'];note='Synthetic reason preserved across Human audit'
    r=client.post('/workforce/rosters/'+identity+'/review',json={'expected_version':1,'note':note});assert r.status_code==200,r.text
    with SessionLocal() as db:
        audit=db.scalar(select(AuditLog).where(AuditLog.entity_id==identity,AuditLog.action.like('%review')))
        assert note in str(audit.after_data)


def test_employee_after_first_two_hundred_is_reachable(client):
    with SessionLocal() as db:
        db.add_all([Employee(display_name=f'Synthetic A{i:04}',employee_code=f'MANY{i:04}') for i in range(205)])
        target=Employee(display_name='Synthetic Z last',employee_code='LAST');db.add(target);db.commit();identity=target.employee_id
    rows=client.get('/workforce/employees?offset=200&limit=100').json()
    assert any(x['employee_id']==identity for x in rows)


def test_ledger_page_after_first_thousand_is_reachable(client):
    emp,*_=refs()
    with SessionLocal() as db:
        user=db.scalar(select(User).where(User.username=='workforce'))
        db.add_all([WorkforceTimeEntry(employee_id=emp,kind='comp_grant',minutes=1,occurred_on=date(2026,10,1),created_by=user.user_id) for _ in range(1002)]);db.commit()
    first=client.get('/workforce/time-entries?offset=0&limit=1000').json()
    remaining=client.get('/workforce/time-entries?offset=1000&limit=1000').json()
    assert len(first)==1000 and len(remaining)==2
    assert not {x['time_entry_id'] for x in first}&{x['time_entry_id'] for x in remaining}


def test_twenty_four_hour_rule_requires_explicit_human_segments(client):
    r=client.post('/workforce/shift-types',json={'code':'24H','name':'Synthetic24h','start_time':'08:30','end_time':'08:30','cross_midnight':True,'payable_minutes':945,'work_segments':[[0,480],[720,1185]]})
    assert r.status_code==201,r.text
    row=r.json();approved=client.post('/workforce/shift-types/'+row['shift_type_id']+'/approve-work-rule',json={'expected_version':row['version'],'note':'Human synthetic work/break schedule'})
    assert approved.status_code==200,approved.text
    emp,org,*_=refs();roster=approve_roster(client,create_roster(client,'2026-10-10',org,row['shift_type_id']))
    attendance=client.post('/workforce/attendance',json={'employee_id':emp,'roster_entry_id':roster['roster_entry_id'],'work_date':'2026-10-10','check_in_at':'2026-10-10T08:30:00+09:00','check_out_at':'2026-10-11T08:30:00+09:00'}).json()
    attendance=action(client,'attendance/'+attendance['attendance_id'],attendance,'review');attendance=action(client,'attendance/'+attendance['attendance_id'],attendance,'approve')
    assert attendance['worked_minutes']==945 and attendance['calculation']['elapsed_minutes']==1440
    assert attendance['calculation']['overtime_candidate_minutes'] is None
