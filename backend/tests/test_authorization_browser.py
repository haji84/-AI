"""Actual Chromium Human role/rule/proxy administration; synthetic evidence only."""
import os
from pathlib import Path
import subprocess
import sys
import time
import urllib.request
import pytest
pytestmark=pytest.mark.skipif(os.environ.get('FIRE_AI_TEST_BROWSER')!='1',reason='real browser CI explicitly required')


def test_human_permission_browser_create_rule_proxy_revoke_and_shared_pc_clear(tmp_path):
    from playwright.sync_api import sync_playwright,expect
    root=Path(__file__).resolve().parents[2]
    env={**os.environ,'PYTHONPATH':str(root/'backend'),'FIRE_AI_DATABASE_URL':'sqlite+pysqlite:///'+str(tmp_path/'synthetic-roles.db'),'FIRE_AI_STORAGE_ROOT':str(tmp_path/'storage'),'FIRE_AI_PRODUCTION_MODE':'false'}
    env.pop('FIRE_AI_TENANT_ID',None)
    subprocess.run([sys.executable,'-m','app.bootstrap','--username','roleui','--display-name','Synthetic role operator','--password','synthetic-role-ui-password'],cwd=root,env=env,check=True,capture_output=True)
    seed="""
from sqlalchemy.orm import Session
from app.db import engine
from app.models import Employee,User
from app.security import hash_password
with Session(engine) as db:
    person=Employee(display_name='Synthetic grantee');db.add(person);db.flush()
    db.add(User(employee_id=person.employee_id,username='role-reader',password_hash=hash_password('synthetic-role-reader-password')));db.commit()
"""
    subprocess.run([sys.executable,'-c',seed],cwd=root,env=env,check=True,capture_output=True)
    logs=(tmp_path/'server.log').open('w');server=subprocess.Popen([sys.executable,'-m','uvicorn','app.main:app','--host','127.0.0.1','--port','9093'],cwd=root,env=env,stdout=logs,stderr=logs)
    try:
        for _ in range(100):
            try:urllib.request.urlopen('http://127.0.0.1:9093/health',timeout=.2).close();break
            except OSError:
                if server.poll() is not None:raise AssertionError((tmp_path/'server.log').read_text())
                time.sleep(.1)
        else:raise AssertionError('synthetic role server not ready')
        with sync_playwright() as browser_api:
            browser=browser_api.chromium.launch();page=browser.new_page();errors=[]
            page.on('pageerror',lambda error:errors.append(str(error)))
            page.on('dialog',lambda dialog:dialog.accept('Synthetic Human cancellation') if dialog.type=='prompt' else dialog.accept())
            page.goto('http://127.0.0.1:9093/ui/permissions.html')
            page.locator('#loginForm input[name=username]').fill('roleui');page.locator('#loginForm input[name=password]').fill('synthetic-role-ui-password');page.locator('#loginForm button').click()
            expect(page.locator('#manager')).to_be_visible()
            page.locator('#roleForm input[name=name]').fill('Synthetic department viewer');page.locator('#permissionChoices input[value="facility.read"]').check();page.locator('#roleForm input[name=reason]').fill('Synthetic Human minimum access');page.locator('#roleForm button').click()
            expect(page.locator('#roleList')).to_contain_text('Synthetic department viewer')
            roles=page.request.get('http://127.0.0.1:9093/administration/permission-roles').json();role=next(x for x in roles if x['name']=='Synthetic department viewer')
            context=page.request.get('http://127.0.0.1:9093/administration/context').json();day=context['business_date']
            source=page.request.post('http://127.0.0.1:9093/documents/upload',multipart={'file':{'name':'synthetic-role-source.txt','mimeType':'text/plain','buffer':b'Synthetic Human role source'}})
            assert source.status==201,source.text()
            doc=source.json()
            page.locator('#ruleForm input[name=source_link]').fill('/documents/'+doc['document_id']+'/download');page.locator('#ruleForm .sourcePreview').click();expect(page.locator('#ruleForm .sourceEvidence')).to_contain_text(doc['sha256'])
            page.locator('#ruleForm input[name=name]').fill('Synthetic exact title policy');page.locator('#ruleForm select[name=role_id]').select_option(role['role_id']);page.locator('#ruleForm input[name=title]').fill('Synthetic fire duty');page.locator('#ruleForm input[name=valid_from]').fill(day);page.locator('#ruleForm input[name=reason]').fill('Synthetic exact role approval');page.locator('#ruleForm button[type=submit],#ruleForm button:not([type])').click()
            expect(page.locator('#ruleList')).to_contain_text('Synthetic exact title policy')
            page.locator('#grantForm select[name=user_id]').select_option(label='role-reader');page.locator('#grantForm select[name=role_id]').select_option(role['role_id']);page.locator('#grantForm select[name=acting_for_employee_id]').select_option(label='Synthetic role operator');page.locator('#grantForm input[name=valid_from]').fill(day);page.locator('#grantForm input[name=valid_to]').fill(day);page.locator('#grantForm input[name=reason]').fill('PRIVATE synthetic absence');page.locator('#grantForm button[type=submit],#grantForm button:not([type])').click()
            expect(page.locator('#grantList')).to_contain_text('role-reader');expect(page.locator('#grantList')).to_contain_text('Synthetic role operator')
            reader=browser.new_context();other=reader.new_page();other.goto('http://127.0.0.1:9093/ui/permissions.html');other.locator('#loginForm input[name=username]').fill('role-reader');other.locator('#loginForm input[name=password]').fill('synthetic-role-reader-password');other.locator('#loginForm button').click()
            expect(other.locator('#ownRoles')).to_contain_text('Synthetic department viewer');expect(other.locator('#ownRoles')).to_contain_text('代理');expect(other.locator('#manager')).to_be_hidden();expect(other.locator('body')).not_to_contain_text('PRIVATE synthetic absence');assert other.request.get('http://127.0.0.1:9093/administration/permissions').status==403
            page.locator('#grantList button').filter(has_text='取消').click();expect(page.locator('#grantList')).to_contain_text('取消済み')
            assert other.request.get('http://127.0.0.1:9093/auth/me').status==401
            page.locator('#roleForm input[name=name]').fill('PRIVATE role draft');page.locator('#ruleForm input[name=title]').fill('PRIVATE title draft');page.locator('#logoutButton').click();expect(page.locator('#loginSection')).to_be_visible()
            page.locator('#loginForm input[name=username]').fill('role-reader');page.locator('#loginForm input[name=password]').fill('synthetic-role-reader-password');page.locator('#loginForm button').click()
            expect(page.locator('#workspace')).to_be_visible();expect(page.locator('#manager')).to_be_hidden();expect(page.locator('#ownRoles')).to_contain_text('有効Roleなし');expect(page.locator('body')).not_to_contain_text('PRIVATE')
            expect(page.locator('#roleForm input[name=name]')).to_have_value('');expect(page.locator('#ruleForm input[name=title]')).to_have_value('');expect(page.locator('#roleList')).to_be_empty()
            artifact=Path(os.environ.get('FIRE_AI_BROWSER_ARTIFACTS',str(tmp_path/'artifacts')));artifact.mkdir(parents=True,exist_ok=True);page.screenshot(path=str(artifact/'human-role-management.png'),full_page=True)
            assert not errors,errors
            reader.close();browser.close()
    finally:server.terminate();server.wait(timeout=15);logs.close()
