"""Real PostgreSQL interleavings; never substitute SQLite concurrency evidence."""
from datetime import date
import threading
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
from sqlalchemy import select
from test_learning import learning_environment


@pytest.fixture
def workforce_pg(learning_environment):
    client,engine=learning_environment
    if engine.dialect.name!='postgresql':pytest.skip('real PostgreSQL transaction interleaving required')
    from app.routers import workforce
    from app.models import Employee
    from app.personnel import OrganizationUnit,EmployeeAssignment
    client.app.include_router(workforce.router)
    with Session(engine) as db:
        org=OrganizationUnit(code='SYNTHETIC',name='Synthetic PG organization');emp=Employee(display_name='Synthetic PG employee')
        db.add_all([org,emp]);db.flush();db.add(EmployeeAssignment(employee_id=emp.employee_id,organization_id=org.organization_id,title='Synthetic duty member',kind='primary',valid_from=date(2026,1,1)));db.commit()
        refs={'employee_id':emp.employee_id,'organization_id':org.organization_id}
    row=client.post('/workforce/shift-types',json={'code':'SYNTHETIC','name':'Synthetic','start_time':'08:00','end_time':'17:00','payable_minutes':480,'work_segments':[[0,480]]}).json()
    r=client.post('/workforce/shift-types/'+row['shift_type_id']+'/approve-work-rule',json={'expected_version':1,'note':'Human synthetic intervals'});assert r.status_code==200,r.text
    yield client,engine,{**refs,'shift_type_id':row['shift_type_id'],'work_date':'2026-10-10'}


def compete(client,requests):
    barrier=threading.Barrier(2);responses=[];errors=[]
    def send(path,payload):
        try:
            with TestClient(client.app) as other:
                other.cookies.update(client.cookies);barrier.wait(timeout=10)
                responses.append(other.post(path,json=payload).status_code)
        except BaseException as exc:errors.append(exc)
    threads=[threading.Thread(target=send,args=request) for request in requests]
    for thread in threads:thread.start()
    for thread in threads:thread.join(timeout=20)
    assert not errors and all(not thread.is_alive() for thread in threads),errors
    return responses


@pytest.mark.parametrize('sources',['manual-manual','import-manual','import-import'])
def test_competing_roster_creation_or_confirm_has_one_winner(workforce_pg,sources):
    client,engine,payload=workforce_pg
    requests=[('/workforce/rosters',payload)]*2
    if sources!='manual-manual':
        from app.models import Employee
        with Session(engine) as db:
            employee=db.get(Employee,payload['employee_id']);employee.employee_code='SYNTHETIC';db.commit()
        raw=b'schema_version,employee_code,organization_code,shift_code,work_date,support_placement,note\nworkforce-v1,SYNTHETIC,SYNTHETIC,SYNTHETIC,2026-10-10,false,Synthetic\n'
        r=client.post('/workforce/import/rosters',files={'file':('synthetic.csv',raw,'text/csv')});assert r.status_code==200,r.text
        preview=r.json();request=('/workforce/import-previews/'+preview['preview_id']+'/confirm',{'expected_version':1,'file_sha256':preview['file_sha256']})
        requests=[request,request if sources=='import-import' else requests[0]]
    results=compete(client,requests)
    assert 409 in results and any(status in (200,201) for status in results),results
    assert len(client.get('/workforce/rosters').json())==1


@pytest.mark.parametrize('ledger',['leave','time-entries'])
def test_competing_deductions_cannot_spend_same_balance(workforce_pg,ledger):
    client,engine,refs=workforce_pg
    def create(kind,day):
        payload={'employee_id':refs['employee_id'],'kind':kind}
        if ledger=='leave':
            payload.update(leave_type='annual',quantity_minutes=100,effective_on=day)
            if kind=='use':payload.update(leave_start_at=day+'T09:00:00+09:00',leave_end_at=day+'T10:40:00+09:00')
        else:payload.update(minutes=100,occurred_on=day)
        r=client.post('/workforce/'+ledger,json=payload);assert r.status_code==201,r.text
        row=r.json();key='leave_entry_id' if ledger=='leave' else 'time_entry_id';path='/workforce/'+ledger+'/'+row[key]
        r=client.post(path+'/review',json={'expected_version':1,'note':'Human synthetic review'});assert r.status_code==200,r.text
        return path,{'expected_version':2,'note':'Human synthetic approval'}
    path,body=create('grant' if ledger=='leave' else 'comp_grant','2026-10-01');assert client.post(path+'/approve',json=body).status_code==200
    first=create('use' if ledger=='leave' else 'comp_use','2026-10-10');second=create('use' if ledger=='leave' else 'comp_use','2026-10-11')
    assert sorted(compete(client,[(path+'/approve',body) for path,body in (first,second)]))==[200,409]
