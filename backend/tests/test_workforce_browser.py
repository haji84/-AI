"""Actual Chromium Human controls, rule warnings and shared-PC clearing; synthetic."""
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import time
import urllib.request
import pytest

pytestmark=pytest.mark.skipif(os.environ.get('FIRE_AI_TEST_BROWSER')!='1',reason='real Chromium CI explicitly required')


def test_workforce_human_controls_stale_warning_and_session_clear(tmp_path):
    from playwright.sync_api import sync_playwright,expect
    root=Path(__file__).resolve().parents[2]
    env={**os.environ,'PYTHONPATH':str(root/'backend'),'FIRE_AI_DATABASE_URL':'sqlite+pysqlite:///'+str(tmp_path/'synthetic.db'),'FIRE_AI_STORAGE_ROOT':str(tmp_path/'storage'),'FIRE_AI_PRODUCTION_MODE':'false'}
    env.pop('FIRE_AI_TENANT_ID',None)
    seed=r'''
import json
from datetime import date
from fastapi.testclient import TestClient
from app.main import app
from app.db import Base,engine,SessionLocal
from app.models import Employee,User,UserRole
from app.personnel import OrganizationUnit,EmployeeAssignment
from app.rbac_seed import seed_rbac
from app.security import hash_password
Base.metadata.create_all(engine)
with SessionLocal() as db:
 roles=seed_rbac(db);org=OrganizationUnit(code='SYNTHETIC',name='Synthetic organization');db.add(org);db.flush()
 employee=Employee(display_name='ZZ Synthetic target',employee_code='LAST');db.add(employee);db.flush()
 db.add(EmployeeAssignment(employee_id=employee.employee_id,organization_id=org.organization_id,kind='primary',valid_from=date(2026,1,1)))
 user=User(employee_id=employee.employee_id,username='uiworkforce',password_hash=hash_password('synthetic-ui-password'));db.add(user);db.flush();db.add(UserRole(user_id=user.user_id,role_id=roles['system_admin'].role_id))
 db.add_all([Employee(display_name=f'AA Synthetic {i:03}',employee_code=f'PAGE-{i:03}') for i in range(205)])
 db.commit();emp=employee.employee_id;organization=org.organization_id
with TestClient(app) as client:
 assert client.post('/auth/login',json={'username':'uiworkforce','password':'synthetic-ui-password'}).status_code==200
 def post(path,data,status=201):
  r=client.post(path,json=data);assert r.status_code==status,r.text;return r.json()
 def approved(base,row,key):
  row=post(base+'/'+row[key]+'/review',{'expected_version':row['version'],'note':'Human synthetic review'},200)
  return post(base+'/'+row[key]+'/approve',{'expected_version':row['version'],'note':'Human synthetic approval'},200)
 shift=post('/workforce/shift-types',{'code':'SYNTHETIC','name':'Synthetic day','start_time':'08:00','end_time':'17:00','payable_minutes':480,'work_segments':[[0,480]]})
 shift=post('/workforce/shift-types/'+shift['shift_type_id']+'/approve-work-rule',{'expected_version':1,'note':'Human synthetic work intervals'},200)
 rule=post('/workforce/staffing-rules',{'organization_id':organization,'shift_type_id':shift['shift_type_id'],'min_staff':1,'effective_from':'2026-01-01'})
 approved('/workforce/staffing-rules',rule,'staffing_rule_id')
 roster=post('/workforce/rosters',{'employee_id':emp,'organization_id':organization,'shift_type_id':shift['shift_type_id'],'work_date':'2026-10-10'})
 roster=approved('/workforce/rosters',roster,'roster_entry_id')
 attendance=post('/workforce/attendance',{'employee_id':emp,'roster_entry_id':roster['roster_entry_id'],'work_date':'2026-10-10','check_in_at':'2026-10-10T08:00:00+09:00','check_out_at':'2026-10-10T17:00:00+09:00'})
 ledger=post('/workforce/time-entries',{'employee_id':emp,'kind':'comp_grant','minutes':60,'occurred_on':'2026-10-10'})
 print(json.dumps({'attendance':attendance['attendance_id'],'time':ledger['time_entry_id'],'shift':shift['shift_type_id'],'shift_version':shift['version'],'employee':emp}))
'''
    seeded=subprocess.run([sys.executable,'-c',seed],cwd=root,env=env,capture_output=True,text=True)
    assert seeded.returncode==0,seeded.stderr
    ids=json.loads(seeded.stdout.strip().splitlines()[-1])
    with socket.socket() as allocation:allocation.bind(('127.0.0.1',0));port=allocation.getsockname()[1]
    base=f'http://127.0.0.1:{port}';logs=(tmp_path/'server.log').open('w')
    server=subprocess.Popen([sys.executable,'-m','uvicorn','app.main:app','--host','127.0.0.1','--port',str(port)],cwd=root,env=env,stdout=logs,stderr=logs)
    try:
        for _ in range(100):
            try:urllib.request.urlopen(base+'/health',timeout=.2).close();break
            except OSError:
                if server.poll() is not None:raise AssertionError((tmp_path/'server.log').read_text())
                time.sleep(.1)
        else:raise AssertionError('synthetic server did not start')
        with sync_playwright() as playwright:
            browser=playwright.chromium.launch();page=browser.new_page(timezone_id='America/New_York');errors=[]
            page.on('pageerror',lambda error:errors.append(str(error)));page.on('dialog',lambda dialog:dialog.accept('Human synthetic browser rationale'))
            page.goto(base+'/ui/');page.locator('#loginUser').fill('uiworkforce');page.locator('#loginPass').fill('synthetic-ui-password');page.get_by_role('button',name='ログイン',exact=True).click()
            expect(page.locator('#workforceBtn')).to_be_visible();page.locator('#workforceBtn').click();page.locator('#workforceAttendance').click()
            for kind,key,endpoint in [('attendance','attendance','attendance'),('time','time','time-entries')]:
                for action in ('review','approve'):
                    with page.expect_response(lambda r,endpoint=endpoint,key=key,action=action:r.url.endswith('/workforce/'+endpoint+'/'+ids[key]+'/'+action) and r.request.method=='POST') as saved:
                        page.locator(f'[data-workforce-human="{kind}:{action}:{ids[key]}"]').click()
                    assert saved.value.status==200,saved.value.text()
            page.locator('#workforceLeave').click();page.locator('#workforceLeaveNew').click()
            expect(page.locator('#workforceField_employee_id option[value="'+ids['employee']+'"]')).to_have_count(1)
            page.locator('#workforceField_kind').select_option('use');page.locator('#workforceField_quantity_minutes').fill('60');page.locator('#workforceField_effective_on').fill('2026-10-16');page.locator('#workforceField_leave_start_at').fill('2026-10-16T08:00');page.locator('#workforceField_leave_end_at').fill('2026-10-16T09:00')
            with page.expect_response(lambda r:r.url.endswith('/workforce/leave') and r.request.method=='POST') as saved:page.locator('#workforceSaveLeave').click()
            assert saved.value.status==201,saved.value.text()
            changed=page.request.patch(base+'/workforce/shift-types/'+ids['shift'],data={'expected_version':ids['shift_version'],'name':'Synthetic changed configuration'});assert changed.status==200,changed.text()
            page.locator('#workforceWarnings').click();page.locator('#workforceWarningDate').fill('2026-10-10');page.locator('#workforceWarningLoad').click();expect(page.locator('#workforceContent')).to_contain_text('判定不可')
            assert page.request.post(base+'/auth/logout').status==200
            page.locator('#workforceAttendance').click();expect(page.locator('#workforceModal')).to_have_count(0)
            assert page.evaluate('workforceState.employees.length+workforceState.permissions.length')==0
            assert not errors,errors
            browser.close()
    except BaseException:
        logs.flush();print((tmp_path/'server.log').read_text());raise
    finally:
        server.terminate()
        try:server.wait(timeout=10)
        except subprocess.TimeoutExpired:server.kill();server.wait(timeout=5)
        logs.close()
