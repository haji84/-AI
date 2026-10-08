"""Synthetic original -> correction -> Human review -> future assignment."""
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import urllib.request

import pytest

pytestmark = pytest.mark.skipif(os.environ.get('FIRE_AI_TEST_BROWSER') != '1', reason='real Chromium CI required')


def test_personnel_notice_human_browser_flow(tmp_path):
    from playwright.sync_api import sync_playwright, expect
    root = Path(__file__).resolve().parents[2]
    env = {**os.environ, 'PYTHONPATH': str(root / 'backend'),
        'FIRE_AI_DATABASE_URL': 'sqlite+pysqlite:///' + str(tmp_path / 'synthetic.db'),
        'FIRE_AI_STORAGE_ROOT': str(tmp_path / 'storage'), 'FIRE_AI_PRODUCTION_MODE': 'false'}
    env.pop('FIRE_AI_TENANT_ID', None)
    seed = """
from datetime import date
from app.main import app
from app.db import Base,engine,SessionLocal
from app.models import Employee,User,UserRole
from app.personnel import OrganizationUnit,EmployeeAssignment
from app.rbac_seed import seed_rbac
from app.security import hash_password
Base.metadata.create_all(engine)
with SessionLocal() as db:
 roles=seed_rbac(db)
 admin=Employee(display_name='Synthetic notice administrator')
 crew=Employee(employee_code='SYN01',display_name='Synthetic notice crew',title='Captain')
 old=OrganizationUnit(code='OLD',name='Synthetic old station')
 new=OrganizationUnit(code='NEW',name='Synthetic new station')
 db.add_all([admin,crew,old,new]);db.flush()
 user=User(employee_id=admin.employee_id,username='noticeadmin',password_hash=hash_password('synthetic-notice-password'))
 db.add(user);db.flush();db.add(UserRole(user_id=user.user_id,role_id=roles['system_admin'].role_id))
 db.add(EmployeeAssignment(employee_id=crew.employee_id,organization_id=old.organization_id,title='Captain',kind='primary',valid_from=date(2026,1,1)))
 db.commit()
"""
    subprocess.run([sys.executable, '-c', seed], cwd=root, env=env, check=True)
    original = tmp_path / 'synthetic-notice.txt'
    original.write_text(json.dumps({'employee_code': 'UNKNOWN', 'organization_code': 'NEW',
        'title': 'Captain', 'kind': 'primary', 'valid_from': '2026-11-01', 'valid_to': None, 'mode': 'transfer'}))
    raw = original.read_bytes()
    logs = (tmp_path / 'server.log').open('w')
    server = subprocess.Popen([sys.executable, '-m', 'uvicorn', 'app.main:app', '--host', '127.0.0.1', '--port', '9136'],
        cwd=root, env=env, stdout=logs, stderr=logs)
    try:
        for _ in range(100):
            try:
                urllib.request.urlopen('http://127.0.0.1:9136/health', timeout=.2).close(); break
            except OSError:
                if server.poll() is not None: raise AssertionError((tmp_path / 'server.log').read_text())
                time.sleep(.1)
        else: raise AssertionError('synthetic notice server did not start')
        with sync_playwright() as p:
            browser = p.chromium.launch(); page = browser.new_page(); errors = []
            page.on('pageerror', lambda error: errors.append(str(error)))
            page.on('dialog', lambda dialog: dialog.accept())
            page.goto('http://127.0.0.1:9136/ui/admin.html')
            page.locator('#loginForm input[name=username]').fill('noticeadmin')
            page.locator('#loginForm input[name=password]').fill('synthetic-notice-password')
            page.locator('#loginForm button').click()
            expect(page.locator('#personnelIntake')).to_be_visible()
            page.locator('#noticeUpload input[name=file]').set_input_files(original)
            with page.expect_response(lambda r: r.url.endswith('/personnel-intake/proposals') and r.request.method == 'POST') as created:
                page.locator('#noticeUpload button').click()
            assert created.value.status == 201
            expect(page.locator('#noticeErrors')).to_contain_text('職員コードが未登録')
            expect(page.locator('#noticeReview')).to_be_disabled()
            expect(page.locator('#noticeApply')).to_be_disabled()
            page.locator('#noticeEdit input[name=employee_code]').fill('SYN01')
            page.locator('#noticeEdit input[name=reason]').fill('Synthetic Human source correction')
            with page.expect_response(lambda r: '/personnel-intake/proposals/' in r.url and r.request.method == 'PATCH') as revised:
                page.locator('#noticeEdit button').click()
            assert revised.value.status == 200
            expect(page.locator('#noticeErrors')).to_have_text('')
            expect(page.locator('#noticeAfter')).to_contain_text('2026-11-01')
            expect(page.locator('#noticeReview')).to_be_enabled()
            expect(page.locator('#noticeApply')).to_be_disabled()
            page.locator('#noticeDecision input[name=reason]').fill('Synthetic Human original verification')
            page.locator('#noticeDecision input[name=acknowledged]').check()
            with page.expect_response(lambda r: r.url.endswith('/review') and r.request.method == 'POST') as reviewed:
                page.locator('#noticeReview').click()
            assert reviewed.value.status == 200
            expect(page.locator('#noticeIdentity')).to_contain_text('Human確認済')
            # Separate apply remains necessary after review; no assignment yet.
            subprocess.run([sys.executable, '-c', "from app.db import SessionLocal; from app.personnel import EmployeeAssignment; from sqlalchemy import select,func\nwith SessionLocal() as db: assert db.scalar(select(func.count()).select_from(EmployeeAssignment))==1"], cwd=root, env=env, check=True)
            page.locator('#noticeDecision input[name=reason]').fill('Synthetic Human future appointment approval')
            page.locator('#noticeDecision input[name=acknowledged]').check()
            with page.expect_response(lambda r: r.url.endswith('/apply') and r.request.method == 'POST') as applied:
                page.locator('#noticeApply').click()
            assert applied.value.status == 200
            expect(page.locator('#noticeIdentity')).to_contain_text('適用済')
            expect(page.locator('#noticeApply')).to_be_disabled()
            page.locator('#historyForm select[name=employee_id]').select_option(label='SYN01 Synthetic notice crew')
            page.locator('#historyForm button').click()
            expect(page.locator('#history')).to_contain_text('Synthetic new station')
            expect(page.locator('#history')).to_contain_text('2026-10-31')
            expect(page.locator('#history')).to_contain_text('2026-11-01')
            verification = """
from pathlib import Path
from hashlib import sha256
from sqlalchemy import select,func
from app.db import SessionLocal
from app.models import Document,RolePermission,Permission
from app.personnel import EmployeeAssignment,AssignmentRole
from app.settings import settings
with SessionLocal() as db:
 assert db.scalar(select(func.count()).select_from(EmployeeAssignment))==2
 assert db.scalar(select(func.count()).select_from(AssignmentRole))==0
 doc=db.scalar(select(Document).where(Document.document_type=='personnel_notice'))
 assert sha256((Path(settings.storage_root)/doc.storage_path).read_bytes()).hexdigest()==doc.sha256
 denied=db.scalar(select(Permission).where(Permission.code=='personnel.read'))
 db.query(RolePermission).filter(RolePermission.permission_id==denied.permission_id).delete();db.commit()
"""
            artifact = Path(os.environ.get('FIRE_AI_BROWSER_ARTIFACTS', str(tmp_path / 'artifacts'))); artifact.mkdir(parents=True, exist_ok=True)
            page.screenshot(path=str(artifact / 'personnel-notice-human-apply.png'), full_page=True)
            subprocess.run([sys.executable, '-c', verification], cwd=root, env=env, check=True)
            page.evaluate("window.dispatchEvent(new Event('focus'))")
            expect(page.locator('#personnelIntake')).to_be_hidden()
            expect(page.locator('#noticeSource')).to_have_text('')
            expect(page.locator('#noticeAfter')).to_have_text('')
            assert original.read_bytes() == raw
            assert not errors, errors
            browser.close()
    finally:
        server.terminate(); server.wait(timeout=10); logs.close()
