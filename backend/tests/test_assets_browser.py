"""Real same-shell HTTP/Chromium stock and Human service flow; synthetic, opt-in CI."""
import os
from pathlib import Path
import socket
import subprocess
import sys
import time
import urllib.request
import pytest

pytestmark = pytest.mark.skipif(os.environ.get('FIRE_AI_TEST_BROWSER') != '1',
                               reason='real browser job explicitly required')


def test_assets_stock_borrower_and_human_service_browser_flow(tmp_path):
    from playwright.sync_api import sync_playwright, expect
    root = Path(__file__).resolve().parents[2]
    env = {**os.environ, 'PYTHONPATH': str(root/'backend'),
           'FIRE_AI_DATABASE_URL': 'sqlite+pysqlite:///'+str(tmp_path/'synthetic.db'),
           'FIRE_AI_STORAGE_ROOT': str(tmp_path/'storage'), 'FIRE_AI_PRODUCTION_MODE': 'false'}
    env.pop('FIRE_AI_TENANT_ID', None)
    seed = r"""
from pathlib import Path
from hashlib import sha256
from app.main import app
from app.db import Base,engine,SessionLocal
from app.models import Employee,User,UserRole,Document
from app.rbac_seed import seed_rbac
from app.security import hash_password
from app.settings import settings
Base.metadata.create_all(engine)
proof=b'Synthetic Human service evidence only.\n'
root=Path(settings.storage_root);root.mkdir(parents=True,exist_ok=True);(root/'proof.txt').write_bytes(proof)
with SessionLocal() as db:
 roles=seed_rbac(db);e=Employee(display_name='Synthetic browser operator',active=True);db.add(e);db.flush()
 u=User(employee_id=e.employee_id,username='uiassets',password_hash=hash_password('synthetic-ui-password'));db.add(u);db.flush()
 db.add(UserRole(user_id=u.user_id,role_id=roles['system_admin'].role_id))
 db.add_all([Employee(display_name=f'AA Synthetic {i:03}',employee_code=f'PAGE-{i:03}',active=True) for i in range(205)])
 db.add(Employee(employee_id='11111111-1111-4111-8111-111111111111',display_name='ZZ Later borrower',employee_code='LAST',active=True))
 db.add(Document(document_id='22222222-2222-4222-8222-222222222222',original_filename='Synthetic-proof.txt',storage_path='proof.txt',mime_type='text/plain',sha256=sha256(proof).hexdigest(),size_bytes=len(proof)))
 db.commit()
"""
    subprocess.run([sys.executable, '-c', seed], cwd=root, env=env, check=True)
    with socket.socket() as allocation:
        allocation.bind(('127.0.0.1', 0)); port = allocation.getsockname()[1]
    base = f'http://127.0.0.1:{port}'
    logs = (tmp_path/'server.log').open('w')
    server = subprocess.Popen([sys.executable, '-m', 'uvicorn', 'app.main:app', '--host', '127.0.0.1', '--port', str(port)],
                              cwd=root, env=env, stdout=logs, stderr=logs)
    try:
        for _ in range(100):
            try:
                urllib.request.urlopen(base+'/health', timeout=.2).close(); break
            except OSError:
                if server.poll() is not None: raise AssertionError((tmp_path/'server.log').read_text())
                time.sleep(.1)
        else: raise AssertionError('synthetic server did not start')
        with sync_playwright() as p:
            browser = p.chromium.launch(); page = browser.new_page(); errors = []
            page.on('pageerror', lambda error: errors.append(str(error)))
            page.on('console', lambda message: errors.append(message.text) if message.type == 'error' else None)
            page.goto(base+'/ui/')
            page.locator('#loginUser').fill('uiassets'); page.locator('#loginPass').fill('synthetic-ui-password')
            page.get_by_role('button', name='ログイン', exact=True).click()
            expect(page.locator('#assetsBtn')).to_be_visible(); page.locator('#assetsBtn').click()
            expect(page.locator('#assetsNew')).to_be_visible()

            def fill(key, value): page.locator('#assetsField_'+key).fill(value)
            def save(path, status=201):
                with page.expect_response(lambda r: r.url.endswith(path) and r.request.method == 'POST') as saved:
                    page.locator('#assetsForm button[type=submit]').click()
                assert saved.value.status == status, saved.value.text()
                return saved.value.json()

            page.locator('#assetsNew').click(); fill('code','BROWSER'); fill('name','Synthetic browser stock'); fill('unit','piece')
            asset = save('/assets/registry'); aid = asset['asset_id']
            expect(page.locator('#assetsLotNew')).to_be_visible()
            page.locator('#assetsLocations').click(); page.locator('#assetsLocationNew').click()
            fill('code','BROWSER-STORE'); fill('name','Synthetic browser store'); location = save('/assets/locations')
            expect(page.locator('#assetsContent')).to_contain_text('Synthetic browser store')
            page.locator('#assetsRegistry').click(); page.locator(f'[data-asset-open="{aid}"]').click()
            page.locator('#assetsLotNew').click(); fill('batch_code','BROWSER-BATCH'); fill('provenance','Synthetic source batch')
            lot = save(f'/assets/registry/{aid}/lots')
            expect(page.locator('#assetsContent')).to_contain_text('BROWSER-BATCH')
            page.locator('#assetsMovementNew').click()
            page.locator('#assetsField_lot_id').select_option(lot['lot_id'])
            page.locator('#assetsField_location_id').select_option(location['location_id'])
            fill('quantity','3.125'); fill('reason','Synthetic browser receipt'); save('/assets/movements')
            expect(page.locator('#assetsContent')).to_contain_text('3.125')
            page.locator('#assetsMovementNew').click(); page.locator('#assetsField_kind').select_option('loan')
            expect(page.locator('#assetsBorrowerNext')).to_be_enabled()
            assert page.locator('#assetsField_borrower_employee_id option[value="11111111-1111-4111-8111-111111111111"]').count() == 0
            page.locator('#assetsBorrowerNext').click()
            expect(page.locator('#assetsField_borrower_employee_id option[value="11111111-1111-4111-8111-111111111111"]')).to_be_attached()
            page.locator('#assetsBorrowerQuery').fill('ZZ Later borrower'); page.locator('#assetsBorrowerSearch').click()
            expect(page.locator('#assetsBorrowerPage')).to_have_text('1～1件')
            page.locator('#assetsField_borrower_employee_id').select_option('11111111-1111-4111-8111-111111111111')
            page.locator('#assetsField_lot_id').select_option(lot['lot_id'])
            page.locator('#assetsField_location_id').select_option(location['location_id'])
            fill('quantity','1.125'); fill('reason','Synthetic browser loan'); loan = save('/assets/movements')
            assert loan['loan_id']
            expect(page.locator('#assetsContent')).to_contain_text('2.000')
            response = page.request.get(base+'/assets/loans/'+loan['loan_id']); assert response.ok
            assert response.json()['borrower_employee_id'] == '11111111-1111-4111-8111-111111111111'
            page.locator('#assetsServiceNew').click()
            expect(page.locator('#assetsField_description')).to_be_visible()
            old_description = page.locator('#assetsField_description').element_handle()
            page.locator('#assetsField_kind').select_option('pressure_test')
            page.wait_for_function('(node) => !node.isConnected', arg=old_description)
            fill('description','Synthetic Human pressure test'); fill('cost','0')
            fill('next_pressure_test_on','2099-10-06'); fill('next_use_on','2099-10-07')
            fill('next_calibration_on','2099-10-08'); fill('next_service_on','2099-10-09')
            fill('document_id','22222222-2222-4222-8222-222222222222')
            service = save(f'/assets/registry/{aid}/services'); sid = service['service_id']
            expect(page.locator('#assetsReview')).to_be_visible()
            for date in ['2099-10-06','2099-10-07','2099-10-08','2099-10-09']:
                expect(page.locator('#assetsContent')).to_contain_text(date)
            proof_link = page.locator('#assetsContent a[href="/documents/22222222-2222-4222-8222-222222222222/download"]')
            expect(proof_link).to_be_visible()
            assert page.request.get(base+proof_link.get_attribute('href')).text() == 'Synthetic Human service evidence only.\n'
            assert page.request.get(base+'/assets/registry/'+aid).json()['next_pressure_test_on'] is None
            page.locator('#assetsReview').click(); fill('reason','Synthetic Human checked original and proposed values')
            save(f'/assets/services/{sid}/review',200); expect(page.locator('#assetsApprove')).to_be_visible()
            page.locator('#assetsApprove').click(); fill('reason','Synthetic Human approval')
            approved = save(f'/assets/services/{sid}/approve',200); assert approved['status'] == 'approved'
            expect(page.locator('#assetsContent h2')).to_contain_text('approved')
            assert page.request.get(base+'/assets/registry/'+aid).json()['next_pressure_test_on'] == '2099-10-06'
            artifact = Path(os.environ.get('FIRE_AI_BROWSER_ARTIFACTS',str(tmp_path/'artifacts'))); artifact.mkdir(parents=True,exist_ok=True)
            page.screenshot(path=str(artifact/'operational-assets.png'),full_page=True)
            assert not errors, errors
            expect(page.locator('#assetsMessage')).to_be_empty()
            browser.close()
    finally:
        server.terminate(); server.wait(timeout=10); logs.close()
