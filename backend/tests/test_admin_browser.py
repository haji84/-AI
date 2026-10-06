"""Real Chromium + HTTP integration, synthetic records only, opt-in CI job."""
import os
from pathlib import Path
import subprocess
import sys
import time
import urllib.request
import pytest

pytestmark=pytest.mark.skipif(os.environ.get('FIRE_AI_TEST_BROWSER')!='1',reason='real browser job explicitly required')


def test_human_administration_browser_flow(tmp_path):
    from playwright.sync_api import sync_playwright, expect
    root=Path(__file__).resolve().parents[2]
    env={**os.environ,'PYTHONPATH':str(root/'backend'),
         'FIRE_AI_DATABASE_URL':'sqlite+pysqlite:///'+str(tmp_path/'synthetic.db'),
         'FIRE_AI_STORAGE_ROOT':str(tmp_path/'storage'),'FIRE_AI_PRODUCTION_MODE':'false'}
    env.pop('FIRE_AI_TENANT_ID',None)
    seed="""
from app.main import app
from app.db import Base,engine,SessionLocal
from app.models import Employee,User,UserRole
from app.rbac_seed import seed_rbac
from app.security import hash_password
Base.metadata.create_all(engine)
with SessionLocal() as db:
 roles=seed_rbac(db);e=Employee(display_name='Synthetic browser administrator');db.add(e);db.flush()
 u=User(employee_id=e.employee_id,username='uiadmin',password_hash=hash_password('synthetic-ui-password'));db.add(u);db.flush()
 db.add(UserRole(user_id=u.user_id,role_id=roles['system_admin'].role_id));db.commit()
"""
    subprocess.run([sys.executable,'-c',seed],cwd=root,env=env,check=True)
    logs=(tmp_path/'server.log').open('w')
    server=subprocess.Popen([sys.executable,'-m','uvicorn','app.main:app','--host','127.0.0.1','--port','9087'],cwd=root,env=env,stdout=logs,stderr=logs)
    try:
        for _ in range(100):
            try:
                urllib.request.urlopen('http://127.0.0.1:9087/health',timeout=.2).close();break
            except OSError:
                if server.poll() is not None:raise AssertionError((tmp_path/'server.log').read_text())
                time.sleep(.1)
        else:raise AssertionError('synthetic server did not start')
        with sync_playwright() as p:
            browser=p.chromium.launch();page=browser.new_page();errors=[]
            page.on('pageerror',lambda error:errors.append(str(error)))
            page.on('dialog',lambda dialog:dialog.accept())
            page.goto('http://127.0.0.1:9087/ui/admin.html')
            page.locator('#loginForm input[name=username]').fill('uiadmin')
            page.locator('#loginForm input[name=password]').fill('synthetic-ui-password')
            page.locator('#loginForm button').click();expect(page.locator('#workspace')).to_be_visible()
            page.locator('#orgForm input[name=code]').fill('SYN')
            page.locator('#orgForm input[name=name]').fill('Synthetic unit')
            page.locator('#orgForm button').click();expect(page.locator('#organizations')).to_contain_text('Synthetic unit')
            page.locator('#staffForm input[name=employee_code]').fill('SYN01')
            page.locator('#staffForm input[name=display_name]').fill('Synthetic crew')
            page.locator('#staffForm button').click();expect(page.locator('#staff')).to_contain_text('Synthetic crew')
            page.locator('#assignmentForm select[name=employee_id]').select_option(label='SYN01 Synthetic crew')
            page.locator('#assignmentForm input[name=title]').fill('Synthetic duty')
            page.locator('#assignmentForm input[name=reason]').fill('Synthetic Human appointment')
            with page.expect_response(lambda response:'/assignments' in response.url and response.request.method=='POST') as appointment:
                page.locator('#assignmentForm button').click()
            assert appointment.value.status==201
            expect(page.locator('#message')).to_have_text('保存しました。')
            page.locator('#historyForm select[name=employee_id]').select_option(label='SYN01 Synthetic crew')
            page.locator('#historyForm button').click();expect(page.locator('#history')).to_contain_text('Synthetic duty')
            page.locator('#accountForm select[name=employee_id]').select_option(label='SYN01 Synthetic crew')
            page.locator('#accountForm input[name=username]').fill('syntheticcrew')
            page.locator('#accountForm input[name=password]').fill('synthetic-crew-password')
            page.locator('#accountForm input[name=reason]').fill('Synthetic Human approval')
            page.locator('#accountForm button').click();expect(page.locator('#accounts')).to_contain_text('syntheticcrew')
            page.locator('#auditButton').click();expect(page.locator('#audit')).to_contain_text('personnel.assignment')
            artifact=Path(os.environ.get('FIRE_AI_BROWSER_ARTIFACTS',str(tmp_path/'artifacts')));artifact.mkdir(parents=True,exist_ok=True)
            page.screenshot(path=str(artifact/'personnel-administration.png'),full_page=True)
            assert not errors,errors
            page.locator('#logoutButton').click();expect(page.locator('#loginSection')).to_be_visible()
            browser.close()
    finally:
        server.terminate();server.wait(timeout=10);logs.close()
