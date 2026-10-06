"""Actual shell cached-edit and delayed response privacy, synthetic data only."""
import os
from pathlib import Path
import socket,subprocess,sys,time,urllib.request
import pytest
pytestmark=pytest.mark.skipif(os.environ.get('FIRE_AI_TEST_BROWSER')!='1',reason='actual Chromium shared-session privacy executes in CI')


def test_shared_shell_cached_edit_right_loss_and_same_user_relogin_discard(tmp_path):
 from playwright.sync_api import sync_playwright,expect
 root=Path(__file__).resolve().parents[2]
 env={**os.environ,'PYTHONPATH':str(root/'backend'),'FIRE_AI_DATABASE_URL':'sqlite+pysqlite:///'+str(tmp_path/'synthetic.db'),'FIRE_AI_STORAGE_ROOT':str(tmp_path/'storage'),'FIRE_AI_PRODUCTION_MODE':'false'};env.pop('FIRE_AI_TENANT_ID',None)
 subprocess.run([sys.executable,'-m','app.bootstrap','--username','shared-ui','--display-name','Synthetic shared operator','--password','synthetic-shared-password'],cwd=root,env=env,check=True,capture_output=True)
 seed="""
from app.db import SessionLocal
from app.models import Facility
with SessionLocal() as db:
 db.add(Facility(name='Synthetic cached private facility',status='active'));db.commit()
"""
 subprocess.run([sys.executable,'-c',seed],cwd=root,env=env,check=True,capture_output=True)
 with socket.socket() as allocation:allocation.bind(('127.0.0.1',0));port=allocation.getsockname()[1]
 base=f'http://127.0.0.1:{port}';logs=(tmp_path/'server.log').open('w');server=subprocess.Popen([sys.executable,'-m','uvicorn','app.main:app','--host','127.0.0.1','--port',str(port)],cwd=root,env=env,stdout=logs,stderr=logs)
 try:
  for _ in range(100):
   try:urllib.request.urlopen(base+'/health',timeout=.2).close();break
   except OSError:
    if server.poll() is not None:raise AssertionError((tmp_path/'server.log').read_text())
    time.sleep(.1)
  else:raise AssertionError('synthetic server did not start')
  with sync_playwright() as p:
   browser=p.chromium.launch();page=browser.new_page();errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
   def login():
    page.goto(base+'/ui/');page.locator('#loginUser').fill('shared-ui');page.locator('#loginPass').fill('synthetic-shared-password');page.get_by_role('button',name='ログイン',exact=True).click();expect(page.locator('#facilityList')).to_contain_text('Synthetic cached private facility')
   def delay():
    pending=[]
    def hold(route):pending.append(route)
    page.route('**/facilities?*',hold)
    page.evaluate("window.delayedOutcome=null;void fetch('/facilities?offset=0&limit=50').then(r=>r.json()).then(x=>window.delayedOutcome={data:x}).catch(e=>window.delayedOutcome={cancelled:!!e.cancelled})")
    for _ in range(100):
     if pending:break
     page.wait_for_timeout(10)
    assert pending,'actual private request did not reach native route'
    return pending,hold
   login();page.locator('.facilityItem').click();expect(page.locator('#detailView')).to_contain_text('Synthetic cached private facility')
   pending,hold=delay()
   # Remove a right without revoking this session: the common context must detect it.
   revoke="""
from sqlalchemy import select
from app.db import SessionLocal
from app.models import Permission,Role,RolePermission
with SessionLocal() as db:
 r=db.scalar(select(Role).where(Role.code=='system_admin'));p=db.scalar(select(Permission).where(Permission.code=='facility.read'))
 row=db.scalar(select(RolePermission).where(RolePermission.role_id==r.role_id,RolePermission.permission_id==p.permission_id));db.delete(row);db.commit()
"""
   subprocess.run([sys.executable,'-c',revoke],cwd=root,env=env,check=True,capture_output=True)
   page.locator('#detailView').get_by_role('button',name='編集',exact=True).click();expect(page.locator('#loginView')).to_be_visible();expect(page.locator('#editModal')).to_be_hidden();expect(page.locator('#loginPass')).to_have_value('');expect(page.locator('#detailView')).not_to_contain_text('Synthetic cached private facility')
   pending[0].fulfill(status=200,content_type='application/json',body='{"private":"synthetic old response"}')
   page.wait_for_function('window.delayedOutcome?.cancelled===true');assert page.evaluate('state.detail') is None
   page.unroute('**/facilities?*',hold)
   # Restore only the synthetic policy; bootstrap correctly rejects existing accounts.
   restore="""
from app.db import SessionLocal
from app.rbac_seed import seed_rbac
with SessionLocal() as db:
 seed_rbac(db);db.commit()
"""
   subprocess.run([sys.executable,'-c',restore],cwd=root,env=env,check=True,capture_output=True)
   login();pending,hold=delay();before=page.request.get(base+'/auth/context').json()
   assert page.request.post(base+'/auth/login',data={'username':'shared-ui','password':'synthetic-shared-password'}).status==200
   after=page.request.get(base+'/auth/context').json();assert before['user_id']==after['user_id'] and before['session_id']!=after['session_id']
   pending[0].fulfill(status=200,content_type='application/json',body='{"private":"synthetic old session"}')
   page.wait_for_function('window.delayedOutcome?.cancelled===true');expect(page.locator('#loginView')).to_be_visible();assert page.evaluate('state.detail') is None
   assert not errors,errors
   artifact=Path(os.environ.get('FIRE_AI_BROWSER_ARTIFACTS',str(tmp_path/'artifacts')));artifact.mkdir(parents=True,exist_ok=True);page.screenshot(path=str(artifact/'shared-session-authority-cleared.png'),full_page=True);browser.close()
 finally:server.terminate();server.wait(timeout=10);logs.close()
