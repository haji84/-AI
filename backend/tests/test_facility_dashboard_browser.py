"""Real Chromium facility-source visibility and changed-session rights; synthetic only."""
import os
from pathlib import Path
import socket
import subprocess
import sys
import time
import urllib.request

import pytest

pytestmark = pytest.mark.skipif(
    os.environ.get('FIRE_AI_TEST_BROWSER') != '1',
    reason='real Chromium facility dashboard permissions execute in CI',
)


def test_facility_only_reader_and_revoked_source_rights(tmp_path):
    from playwright.sync_api import sync_playwright, expect

    root = Path(__file__).resolve().parents[2]
    env = {**os.environ, 'PYTHONPATH': str(root / 'backend'),
           'FIRE_AI_DATABASE_URL': 'sqlite+pysqlite:///' + str(tmp_path / 'synthetic.db'),
           'FIRE_AI_STORAGE_ROOT': str(tmp_path / 'storage'), 'FIRE_AI_PRODUCTION_MODE': 'false'}
    env.pop('FIRE_AI_TENANT_ID', None)
    subprocess.run([sys.executable, '-m', 'app.bootstrap', '--username', 'dashboard-admin',
                    '--display-name', 'Synthetic dashboard operator', '--password', 'synthetic-dashboard-password'],
                   cwd=root, env=env, check=True, capture_output=True)
    seed = """
from datetime import date
from sqlalchemy import select
from app.db import SessionLocal
from app.models import Employee,User,Role,Permission,RolePermission,UserRole,Facility,Inspection,InspectionFinding,Submission,SubmissionType
from app.security import hash_password
from app.submission_seed import seed_submission_types
with SessionLocal() as db:
 seed_submission_types(db)
 employee=Employee(display_name='Synthetic facility reader');role=Role(code='synthetic_facility_reader',name='Synthetic facility reader')
 db.add_all([employee,role]);db.flush()
 user=User(employee_id=employee.employee_id,username='dashboard-reader',password_hash=hash_password('synthetic-dashboard-password'))
 db.add(user);db.flush()
 permission=db.scalar(select(Permission).where(Permission.code=='facility.read'))
 db.add_all([UserRole(user_id=user.user_id,role_id=role.role_id),RolePermission(role_id=role.role_id,permission_id=permission.permission_id)])
 facility=Facility(name='Synthetic permission facility',status='active');db.add(facility);db.flush()
 inspection=Inspection(building_id=facility.building_id,inspected_at=date(2026,10,2));db.add(inspection);db.flush()
 db.add(InspectionFinding(inspection_id=inspection.inspection_id,finding_text='PRIVATE synthetic inspection finding'))
 kind=db.scalar(select(SubmissionType).where(SubmissionType.code=='fire_plan'))
 db.add(Submission(building_id=facility.building_id,submission_type_id=kind.submission_type_id,status='reviewed',official_number='87654321'))
 db.commit()
"""
    subprocess.run([sys.executable, '-c', seed], cwd=root, env=env, check=True, capture_output=True)
    with socket.socket() as allocation:
        allocation.bind(('127.0.0.1', 0)); port = allocation.getsockname()[1]
    base = f'http://127.0.0.1:{port}'
    logs = (tmp_path / 'server.log').open('w')
    server = subprocess.Popen([sys.executable, '-m', 'uvicorn', 'app.main:app', '--host', '127.0.0.1', '--port', str(port)],
                              cwd=root, env=env, stdout=logs, stderr=logs)
    try:
        for _ in range(100):
            try:
                urllib.request.urlopen(base + '/health', timeout=.2).close(); break
            except OSError:
                if server.poll() is not None:
                    raise AssertionError((tmp_path / 'server.log').read_text())
                time.sleep(.1)
        else:
            raise AssertionError('synthetic dashboard server did not start')
        with sync_playwright() as browser_api:
            browser = browser_api.chromium.launch()
            page = browser.new_page(); errors = []; requests = []
            page.on('pageerror', lambda error: errors.append(str(error)))
            page.on('request', lambda request: requests.append(request.url))
            page.on('dialog', lambda dialog: dialog.dismiss())

            def login(username):
                page.goto(base + '/ui/')
                page.locator('#loginUser').fill(username)
                page.locator('#loginPass').fill('synthetic-dashboard-password')
                page.get_by_role('button', name='ログイン', exact=True).click()
                expect(page.locator('#facilityList')).to_contain_text('Synthetic permission facility')

            def assert_limited_detail():
                requests.clear()
                page.locator('.facilityItem').click()
                detail = page.locator('#detailView')
                expect(detail).to_be_visible()
                for label in ['査察情報は閲覧権限がありません', '届出情報は閲覧権限がありません',
                              '設置設備情報は閲覧権限がありません', '図面解析情報は閲覧権限がありません']:
                    expect(detail).to_contain_text(label)
                for hidden in ['PRIVATE synthetic', '87654321', '査察 0件', '未完了指摘 0件',
                               '登録確認なし・要否未判定', '査察履歴なし', '届出記録なし']:
                    expect(detail).not_to_contain_text(hidden)
                assert not any('/inspections?' in url or '/submissions?' in url or
                               url.endswith('/equipment') or url.endswith('/drawing-analyses') for url in requests), requests
                assert page.evaluate('state.inspections === null && state.submissions === null && state.equipment === null && state.drawings === null')

            login('dashboard-reader'); assert_limited_detail()
            facility_id = page.evaluate('state.selected.building_id')
            assert page.request.get(base + '/inspections?building_id=' + facility_id).status == 403
            assert page.request.get(base + '/submissions?building_id=' + facility_id).status == 403
            login('dashboard-admin')
            page.locator('.facilityItem').click()
            expect(page.locator('#detailView')).to_contain_text('PRIVATE synthetic inspection finding')
            expect(page.locator('#detailView')).to_contain_text('87654321')
            revoke = """
from sqlalchemy import delete,select
from app.db import SessionLocal
from app.models import Role,Permission,RolePermission
with SessionLocal() as db:
 role=db.scalar(select(Role).where(Role.code=='system_admin'))
 keep=db.scalar(select(Permission).where(Permission.code=='facility.read'))
 db.execute(delete(RolePermission).where(RolePermission.role_id==role.role_id,RolePermission.permission_id!=keep.permission_id));db.commit()
"""
            subprocess.run([sys.executable, '-c', revoke], cwd=root, env=env, check=True, capture_output=True)
            page.locator('.facilityItem').click()
            expect(page.locator('#loginView')).to_be_visible()
            expect(page.locator('#detailView')).not_to_contain_text('PRIVATE synthetic inspection finding')
            assert page.evaluate('state.detail') is None
            login('dashboard-admin'); assert_limited_detail()
            assert not errors, errors
            artifact = Path(os.environ.get('FIRE_AI_BROWSER_ARTIFACTS', str(tmp_path / 'artifacts')))
            artifact.mkdir(parents=True, exist_ok=True)
            page.screenshot(path=str(artifact / 'facility-dashboard-restricted-sources.png'), full_page=True)
            browser.close()
    finally:
        server.terminate(); server.wait(timeout=10); logs.close()
        if sys.exc_info()[0]:
            print((tmp_path / 'server.log').read_text())
