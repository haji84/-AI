"""Real authenticated Chromium journey using synthetic originals and source fixtures only."""
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import time
import urllib.request

import pytest

pytestmark = pytest.mark.skipif(os.environ.get('FIRE_AI_TEST_BROWSER') != '1', reason='actual Chromium runs in dedicated CI job')

SEED = r'''
import json
from datetime import date
from hashlib import sha256
from fastapi.testclient import TestClient
from sqlalchemy import select
from app.main import app
from app.db import SessionLocal
from app.models import User, Facility, Inspection, InspectionFinding, LegalJurisdiction, LegalSource, LegalSourceDocument, LegalSourceDocumentVersion
from app.violation_models import ViolationCase
with TestClient(app) as client:
    assert client.post('/auth/login',json={'username':'hazardous-browser','password':'synthetic-hazardous-password'}).status_code == 200
    raw=client.post('/documents/upload',files={'file':('synthetic-legal-original.txt',b'Synthetic source only; no legal authority.','text/plain')})
    assert raw.status_code == 201, raw.text
    raw_id=raw.json()['document_id']
with SessionLocal() as db:
    user=db.scalar(select(User).where(User.username=='hazardous-browser'))
    facility=Facility(name='Synthetic hazardous facility',status='active');other=Facility(name='Synthetic other facility',status='active')
    db.add_all([facility,other]);db.flush()
    inspection=Inspection(building_id=facility.building_id,inspected_at=date(2026,10,1),inspection_type='Synthetic inspection')
    db.add(inspection);db.flush();db.add(InspectionFinding(inspection_id=inspection.inspection_id,finding_text='Synthetic inspection finding',corrective_status='open'))
    case=ViolationCase(building_id=facility.building_id,observed_on=date(2026,10,1),possible_issue='Synthetic linked candidate',created_by=user.user_id)
    db.add(case)
    jurisdiction=LegalJurisdiction(code='HAZ-SYN',name='Synthetic hazardous source',jurisdiction_type='fire_union');db.add(jurisdiction);db.flush()
    source=LegalSource(jurisdiction_id=jurisdiction.jurisdiction_id,source_code='HAZ-SYN',name='Synthetic source',source_type='regulation',adapter_type='manual',base_url='https://synthetic.invalid/',trust_level='official');db.add(source);db.flush()
    doc=LegalSourceDocument(legal_source_id=source.legal_source_id,external_id='HAZ-SYN',document_type='regulation',title='Synthetic hazardous legal source');db.add(doc);db.flush()
    version=LegalSourceDocumentVersion(legal_source_document_id=doc.legal_source_document_id,raw_document_id=raw_id,normalized_text='Synthetic source only; no legal authority.',sha256=sha256(b'Synthetic source only; no legal authority.').hexdigest(),source_url='https://synthetic.invalid/hazardous-source',structure_status='parsed')
    db.add(version);db.commit()
    print(json.dumps({'building_id':facility.building_id,'inspection_id':inspection.inspection_id,'case_id':case.case_id,'raw_document_id':raw_id,'legal_source_version_id':version.legal_source_document_version_id}))
'''


def test_hazardous_sources_upload_human_confirmation_revision_deadline_and_history(tmp_path):
    from playwright.sync_api import expect, sync_playwright

    root = Path(__file__).resolve().parents[2]
    env = {**os.environ, 'PYTHONPATH': str(root / 'backend'), 'FIRE_AI_DATABASE_URL': 'sqlite+pysqlite:///' + str(tmp_path / 'synthetic.db'), 'FIRE_AI_STORAGE_ROOT': str(tmp_path / 'storage'), 'FIRE_AI_PRODUCTION_MODE': 'false'}
    env.pop('FIRE_AI_TENANT_ID', None)
    subprocess.run([sys.executable, '-m', 'app.bootstrap', '--username', 'hazardous-browser', '--display-name', 'Synthetic hazardous reviewer', '--password', 'synthetic-hazardous-password'], cwd=root, env=env, check=True, capture_output=True)
    seeded = subprocess.run([sys.executable, '-c', SEED], cwd=root, env=env, check=True, capture_output=True, text=True)
    identifiers = json.loads(seeded.stdout.strip().splitlines()[-1])
    with socket.socket() as allocation:
        allocation.bind(('127.0.0.1', 0))
        port = allocation.getsockname()[1]
    base = f'http://127.0.0.1:{port}'
    logs = (tmp_path / 'server.log').open('w')
    server = subprocess.Popen([sys.executable, '-m', 'uvicorn', 'app.main:app', '--host', '127.0.0.1', '--port', str(port)], cwd=root, env=env, stdout=logs, stderr=logs)
    try:
        for _ in range(100):
            try:
                urllib.request.urlopen(base + '/health', timeout=.2).close()
                break
            except OSError:
                if server.poll() is not None:
                    raise AssertionError((tmp_path / 'server.log').read_text())
                time.sleep(.1)
        else:
            raise AssertionError('synthetic server did not start')
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch()
            page = browser.new_page()
            page_errors = []
            page.on('pageerror', lambda error: page_errors.append(str(error)))
            artifacts = Path(os.environ.get('FIRE_AI_BROWSER_ARTIFACTS', str(tmp_path / 'artifacts')))
            artifacts.mkdir(parents=True, exist_ok=True)

            def pick(kind, label):
                box = page.locator('#hazardousPicker_' + kind)
                option = box.locator('option').filter(has_text=label)
                expect(option).to_have_count(1)
                box.locator('select').select_option(value=option.get_attribute('value'))
                box.get_by_role('button', name='選択', exact=True).click()
                expect(page.locator('#hazardousPicker_' + kind + '_selected')).to_contain_text(label)

            def save(path, status=200):
                with page.expect_response(lambda response: response.url.endswith(path) and response.request.method in ('POST', 'PATCH')) as pending:
                    page.locator('#hazardousSave').click()
                response = pending.value
                assert response.status == status, response.text()
                return response.json()

            def decision(button, path, status=200):
                page.locator('#' + button).click()
                page.locator('#hazardousField_reason').fill('Synthetic Human checked current facts and actual originals')
                ack = page.locator('#hazardousField_human_acknowledged')
                if ack.count():
                    ack.check()
                return save(path, status)

            page.goto(base + '/ui/')
            page.locator('#loginUser').fill('hazardous-browser')
            page.locator('#loginPass').fill('synthetic-hazardous-password')
            page.get_by_role('button', name='ログイン', exact=True).click()
            expect(page.locator('#hazardousBtn')).to_be_visible()
            page.locator('#hazardousBtn').click()
            page.locator('#hazardousNew').click()
            pick('facilities', 'Synthetic hazardous facility')
            page.locator('#hazardousField_name').fill('Synthetic hazardous installation')
            page.locator('#hazardousField_category_label').fill('Synthetic Human-entered category')
            page.locator('#hazardousField_location_detail').fill('Synthetic storage location')
            page.locator('#hazardousMaterialAdd').click()
            material = page.locator('[data-hazardous-material]')
            for key, value in {'name':'Synthetic substance','category_label':'Original material category','quantity':'999999999999999999.123456','quantity_unit':'L','capacity':'1.000001','capacity_unit':'m³'}.items():
                material.locator('[data-material-field=' + key + ']').fill(value)
            material.locator('[data-material-field=capacity]').fill('01.000001')
            page.locator('#hazardousSave').click()
            expect(page.locator('#hazardousMessage')).to_contain_text('先頭の0')
            assert page.request.get(base + '/hazardous/installations').json() == []
            material.locator('[data-material-field=capacity]').fill('1.000001')
            installation = save('/hazardous/installations', 201)
            assert installation['materials'][0]['quantity'] == '999999999999999999.123456'
            assert installation['materials'][0]['capacity'] == '1.000001'
            assert installation['materials'][0]['capacity_unit'] == 'm³'
            path = '/hazardous/installations/' + installation['installation_id']
            page.locator('#hazardousRecordNew').click()
            page.locator('#hazardousField_title').fill('Synthetic original permit record')
            page.locator('#hazardousField_reference_no').fill('SYNTHETIC-001')
            page.locator('#hazardousField_recorded_on').fill('2026-10-01')
            page.locator('#hazardousField_due_on').fill('2026-10-10')
            pick('legal', 'Synthetic hazardous legal source')
            pick('inspections', 'Synthetic inspection')
            pick('violations', 'Synthetic linked candidate')
            page.locator('#hazardousUploadFile').set_input_files({'name':'synthetic-permit-original.txt','mimeType':'text/plain','buffer':b'Synthetic permit evidence only.'})
            held_upload = []
            def hold_upload(route):
                held_upload.append(route)
            page.route('**/documents/upload', hold_upload)
            page.locator('#hazardousUpload').click()
            expect(page.locator('#hazardousFormStatus')).to_contain_text('登録中')
            expect(page.locator('#hazardousSave')).to_be_disabled()
            for _ in range(100):
                if held_upload:
                    break
                page.wait_for_timeout(10)
            assert held_upload, 'the synthetic original upload must reach the HTTP boundary'
            # Native implicit submission cannot save a draft before upload finishes.
            page.locator('#hazardousField_title').press('Enter')
            assert page.request.get(base + path).json()['evidence_records'] == []
            with page.expect_response(lambda response: response.url.endswith('/documents/upload') and response.request.method == 'POST') as upload:
                held_upload[0].continue_()
            page.unroute('**/documents/upload', hold_upload)
            assert upload.value.status == 201, upload.value.text()
            document = upload.value.json()
            expect(page.locator('#hazardousPicker_documents_selected')).to_contain_text('synthetic-permit-original.txt')
            record = save(path + '/records', 201)
            record_path = path + '/records/' + record['record_id']
            assert record['status'] == 'draft'
            expect(page.locator('#hazardousContent')).to_contain_text('法令原本を保存')
            with page.expect_download() as download:
                page.locator('[data-hazardous-document="' + document['document_id'] + '"]').click()
            downloaded = tmp_path / 'downloaded-synthetic-original.txt'
            download.value.save_as(downloaded)
            assert downloaded.read_bytes() == b'Synthetic permit evidence only.'
            # Simulate changed bytes and matching metadata only in this isolated,
            # synthetic fixture. The saved draft still binds the previous hash.
            change_source = '''
from hashlib import sha256
from pathlib import Path
import os
from app.db import SessionLocal
from app.models import Document
from app.settings import settings
with SessionLocal() as db:
    document=db.get(Document,os.environ['HAZARDOUS_SYNTHETIC_DOCUMENT_ID'])
    content=b'Synthetic revised permit evidence.'
    (Path(settings.storage_root)/document.storage_path).write_bytes(content)
    document.sha256=sha256(content).hexdigest();document.size_bytes=len(content);db.commit()
'''
            subprocess.run([sys.executable, '-c', change_source], cwd=root, env={**env, 'HAZARDOUS_SYNTHETIC_DOCUMENT_ID':document['document_id']}, check=True, capture_output=True)
            decision('hazardousConfirm', record_path + '/confirm', 409)
            expect(page.locator('#hazardousMessage')).to_contain_text('訂正保存後')
            expect(page.locator('#hazardousField_reason')).to_have_value('Synthetic Human checked current facts and actual originals')
            page.locator('#hazardousBack').click()
            page.locator('#hazardousRecordEdit').click()
            page.locator('#hazardousField_reason').fill('Synthetic Human rechecked the changed source and rebound the draft')
            record = save(record_path)
            expect(page.locator('#hazardousConfirm')).to_be_visible()
            failed_reads = []
            def fail_first_detail(route):
                if route.request.method == 'GET' and not failed_reads:
                    failed_reads.append(True)
                    route.fulfill(status=503, content_type='application/json', body='{"detail":"Synthetic detail temporarily unavailable"}')
                else:
                    route.continue_()
            page.route(base + path, fail_first_detail)
            record = decision('hazardousConfirm', record_path + '/confirm')
            assert record['status'] == 'confirmed' and record['confirmation_current'] is True
            expect(page.locator('#hazardousSavedReload')).to_be_visible()
            expect(page.locator('#hazardousContent')).to_contain_text('登録・更新は完了しました')
            expect(page.locator('#hazardousForm')).to_have_count(0)
            page.locator('#hazardousSavedReload').click()
            expect(page.locator('#hazardousContent')).to_contain_text('現行の事実・原本をHuman確認済')
            page.unroute(base + path, fail_first_detail)
            page.screenshot(path=str(artifacts / 'hazardous-human-confirmed.png'), full_page=True)
            page.locator('[data-hazardous-inspection]').click()
            expect(page.locator('#hazardousContent')).to_contain_text('Synthetic inspection finding')
            page.locator('#hazardousInspectionBack').click()
            page.locator('[data-hazardous-violation]').click()
            expect(page.locator('#violationContent')).to_contain_text('Synthetic linked candidate')
            expect(page.locator('#hazardousModal')).to_have_count(0)
            page.locator('#violationClose').click()
            page.locator('#hazardousBtn').click()
            page.locator('#hazardousDeadlinesNav').click()
            page.locator('#hazardousDueBefore').fill('2026-10-11')
            previous_deadline_button = page.locator('[data-hazardous-installation]').element_handle()
            page.locator('#hazardousDueSearch').click()
            # SharedSession validates and redispatches the click asynchronously.
            # Wait for the actual old render to be removed, even when row text is unchanged.
            page.wait_for_function('(previous) => !previous.isConnected', arg=previous_deadline_button)
            expect(page.locator('#hazardousContent')).to_contain_text('Synthetic original permit record')
            page.locator('[data-hazardous-installation]').click()
            page.locator('#hazardousEdit').click()
            # Another Human changes the same record while this form retains its original version.
            changed = page.request.patch(base + path, data={'expected_version': installation['version'], 'reason':'Synthetic concurrent correction', 'notes':'Concurrent synthetic fact'})
            assert changed.status == 200, changed.text()
            page.locator('#hazardousField_reason').fill('Synthetic stale correction')
            save(path, 409)
            expect(page.locator('#hazardousMessage')).to_contain_text('再読込')
            expect(page.locator('#hazardousField_reason')).to_have_value('Synthetic stale correction')
            page.locator('#hazardousBack').click()
            page.locator('#hazardousEdit').click()
            page.locator('[data-material-field=quantity]').fill('0.000001')
            page.locator('#hazardousField_reason').fill('Synthetic corrected quantity from original')
            installation = save(path)
            assert installation['materials'][0]['quantity'] == '0.000001'
            expect(page.locator('#hazardousContent')).to_contain_text('過去の確認')
            page.locator('[data-hazardous-record]').click()
            revised = decision('hazardousRevision', record_path + '/revisions', 201)
            assert revised['status'] == 'draft' and revised['supersedes_record_id'] == record['record_id']
            revised_path = path + '/records/' + revised['record_id']
            page.locator('#hazardousRecordEdit').click()
            page.locator('#hazardousField_kind').select_option('change')
            page.locator('#hazardousField_title').fill('Synthetic revised change evidence')
            page.locator('#hazardousField_reason').fill('Synthetic clarification of evidence')
            revised = save(revised_path)
            revised = decision('hazardousConfirm', revised_path + '/confirm')
            assert revised['confirmation_current'] is True
            detail = page.request.get(base + path).json()
            previous = next(item for item in detail['evidence_records'] if item['record_id'] == record['record_id'])
            assert previous['status'] == 'superseded'
            assert previous['source_snapshot'] == record['source_snapshot']
            cancelled = decision('hazardousCancel', revised_path + '/cancel')
            assert cancelled['status'] == 'cancelled' and cancelled['source_snapshot']
            page.locator('#hazardousRecordBack').click()
            retired = decision('hazardousRetire', path + '/retire')
            assert retired['status'] == 'retired'
            expect(page.locator('#hazardousContent')).to_contain_text('変更履歴')
            expect(page.locator('#hazardousEdit')).to_have_count(0)
            page.screenshot(path=str(artifacts / 'hazardous-retired-history.png'), full_page=True)
            detail = page.request.get(base + path).json()
            assert detail['history'] and len(detail['evidence_records']) == 2
            # Removing only a source permission invalidates the shared-PC view,
            # even though hazardous.read and the login session remain unchanged.
            revoke_source = '''
from sqlalchemy import select
from app.db import SessionLocal
from app.models import Permission, Role, RolePermission
with SessionLocal() as db:
    role=db.scalar(select(Role).where(Role.code=='system_admin'))
    permission=db.scalar(select(Permission).where(Permission.code=='document.read'))
    grant=db.scalar(select(RolePermission).where(RolePermission.role_id==role.role_id,RolePermission.permission_id==permission.permission_id))
    db.delete(grant);db.commit()
'''
            subprocess.run([sys.executable, '-c', revoke_source], cwd=root, env=env, check=True, capture_output=True)
            page.locator('#hazardousListNav').click()
            expect(page.locator('#hazardousModal')).to_have_count(0)
            expect(page.locator('#loginView')).to_be_visible()
            assert page.evaluate('hazardousState.permissions.length') == 0
            restore_source = '''
from app.db import SessionLocal
from app.rbac_seed import seed_rbac
with SessionLocal() as db:
    seed_rbac(db);db.commit()
'''
            subprocess.run([sys.executable, '-c', restore_source], cwd=root, env=env, check=True, capture_output=True)
            page.locator('#loginUser').fill('hazardous-browser')
            page.locator('#loginPass').fill('synthetic-hazardous-password')
            page.get_by_role('button', name='ログイン', exact=True).click()
            expect(page.locator('#hazardousBtn')).to_be_visible()
            page.locator('#hazardousBtn').click()
            page.locator('[data-hazardous-installation]').click()
            expect(page.locator('#hazardousContent')).to_contain_text('Synthetic hazardous installation')
            # Same account, new session: the current private view and cached actions must disappear.
            before = page.request.get(base + '/auth/context').json()
            assert page.request.post(base + '/auth/login', data={'username':'hazardous-browser','password':'synthetic-hazardous-password'}).status == 200
            after = page.request.get(base + '/auth/context').json()
            assert before['session_id'] != after['session_id']
            page.evaluate('hazardousAction(()=>hazardousList())')
            expect(page.locator('#hazardousModal')).to_have_count(0)
            expect(page.locator('#loginView')).to_be_visible()
            assert page.evaluate('hazardousState.permissions.length') == 0
            assert not page_errors, page_errors
            browser.close()
    finally:
        server.terminate()
        server.wait(timeout=10)
        logs.close()
