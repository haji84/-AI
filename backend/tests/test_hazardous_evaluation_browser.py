"""Actual browser candidate/evidence/Human flow; synthetic Rule only."""
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
from fastapi.testclient import TestClient
from sqlalchemy import select
from app.main import app
from app.db import engine, SessionLocal
from app.models import Facility, LegalProfile, LegalProfileJurisdiction, LegalJurisdiction
from app.settings import settings
from pathlib import Path
from test_hazardous_rule_authoring import structured_rule
Path(settings.storage_root).mkdir(parents=True, exist_ok=True)
identity = structured_rule(engine)
with TestClient(app) as client:
 assert client.post('/auth/login', json={'username':'evaluation-browser','password':'synthetic-evaluation-password'}).status_code == 200
 approved = client.post('/legal-rules/versions/' + identity + '/approve', json={'expected_version':1})
 assert approved.status_code == 200, approved.text
 with SessionLocal() as db:
  facility = Facility(name='Synthetic evaluation facility', status='active')
  profile = LegalProfile(code='SYN-EVAL-BROWSER', name='Synthetic explicit evaluation profile')
  db.add_all([facility, profile]); db.flush()
  db.add(LegalProfileJurisdiction(legal_profile_id=profile.legal_profile_id, jurisdiction_id=db.scalar(select(LegalJurisdiction)).jurisdiction_id))
  db.commit(); building_id=facility.building_id; profile_id=profile.legal_profile_id
 installation=client.post('/hazardous/installations', json={'building_id':building_id,'name':'Synthetic evaluated installation','category_label':'Recorded explicit category','materials':[
  {'name':'Synthetic exact material','quantity':'100.000000','quantity_unit':'L'},
  {'name':'Synthetic unresolved material','quantity':'100','quantity_unit':'kg'}]})
 assert installation.status_code == 201, installation.text
 print(json.dumps({'profile_id':profile_id,'installation_id':installation.json()['installation_id']}))
'''


def test_approved_rule_candidate_trace_separate_human_review_and_current_rights(tmp_path):
    from playwright.sync_api import expect, sync_playwright
    root = Path(__file__).resolve().parents[2]
    env = {key: value for key, value in os.environ.items() if not key.startswith('FIRE_AI_')}
    env.update(PYTHONPATH=os.pathsep.join([str(root / 'backend'), str(root / 'backend/tests')]),
        FIRE_AI_DATABASE_URL='sqlite+pysqlite:///' + str(tmp_path / 'synthetic.db'),
        FIRE_AI_STORAGE_ROOT=str(tmp_path / 'storage'), FIRE_AI_PRODUCTION_MODE='false')
    subprocess.run([sys.executable, '-m', 'app.bootstrap', '--username', 'evaluation-browser',
        '--display-name', 'Synthetic evaluation reviewer', '--password', 'synthetic-evaluation-password'], cwd=root, env=env, check=True, capture_output=True)
    seeded = subprocess.run([sys.executable, '-c', SEED], cwd=root, env=env, check=True, capture_output=True, text=True)
    identifiers = json.loads(seeded.stdout.strip().splitlines()[-1])
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
                if server.poll() is not None: raise AssertionError((tmp_path / 'server.log').read_text())
                time.sleep(.1)
        else: raise AssertionError('synthetic evaluation server did not start')
        with sync_playwright() as p:
            browser = p.chromium.launch(); page = browser.new_page(); errors = []
            page.on('pageerror', lambda error: errors.append(str(error)))
            page.goto(base + '/ui/')
            page.locator('#loginUser').fill('evaluation-browser')
            page.locator('#loginPass').fill('synthetic-evaluation-password')
            page.get_by_role('button', name='ログイン', exact=True).click()
            page.locator('#hazardousBtn').click()
            page.locator('[data-hazardous-installation]').click()
            page.locator('#hazardousEvaluationList').click()
            page.locator('#hazardousEvaluationNew').click()
            page.locator('#hazardousField_profile').select_option(identifiers['profile_id'])
            page.locator('#hazardousField_evaluation_date').fill('2026-10-09')
            with page.expect_response(lambda r: r.url.endswith('/evaluations') and r.request.method == 'POST') as created:
                page.locator('#hazardousSave').click()
            assert created.value.status == 201, created.value.text()
            candidate = created.value.json()
            assert candidate['formal_decision'] is False and candidate['coverage_complete'] is False
            assert [item['state'] for item in candidate['results']] == ['matched', 'unresolved']
            expect(page.locator('#hazardousContent')).to_contain_text('未解決・Human確認が必要')
            expect(page.locator('#hazardousContent')).to_contain_text('正式な適合・違反・許可の判定ではありません')
            page.locator('#hazardousClose').click()
            page.locator('#workQueueBtn').click()
            expect(page.locator('#workQueuePanel')).to_contain_text('危険物評価候補のHuman確認')
            expect(page.locator('#workQueuePanel')).not_to_contain_text('Synthetic exact material')
            page.locator('[data-work-queue-open]').click()
            expect(page.locator('#hazardousContent')).to_contain_text('未解決・Human確認が必要')
            page.locator('#hazardousContent details').click()
            expect(page.locator('#hazardousContent pre')).to_contain_text('Synthetic Article 1')
            artifacts = Path(os.environ.get('FIRE_AI_BROWSER_ARTIFACTS', str(tmp_path / 'artifacts')))
            artifacts.mkdir(parents=True, exist_ok=True)
            page.screenshot(path=str(artifacts / 'hazardous-evaluation-candidate.png'), full_page=True)
            page.locator('#hazardousEvaluationReview').click()
            page.locator('#hazardousField_evaluation_reason').fill('Synthetic independent Human evidence review')
            page.locator('#hazardousField_evaluation_ack').check()
            with page.expect_response(lambda r: r.url.endswith('/review') and r.request.method == 'POST') as reviewed:
                page.locator('#hazardousSave').click()
            assert reviewed.value.status == 200, reviewed.value.text()
            assert reviewed.value.json()['status'] == 'reviewed'
            expect(page.locator('#hazardousContent')).to_contain_text('Human確認済')
            expect(page.locator('#hazardousEvaluationReview')).to_have_count(0)
            page.screenshot(path=str(artifacts / 'hazardous-evaluation-human-reviewed.png'), full_page=True)
            page.locator('#hazardousClose').click()
            page.locator('#workQueueBtn').click()
            expect(page.locator('[data-work-queue-open]')).to_have_count(0)
            page.screenshot(path=str(artifacts / 'hazardous-queue-reviewed-removal.png'), full_page=True)
            record_path = '/hazardous/installations/' + identifiers['installation_id'] + '/records'
            evidence = candidate['rules_snapshot'][0]['source']
            created_record = page.request.post(base + record_path, data={
                'expected_installation_version': 1, 'kind': 'notification',
                'title': 'Synthetic notification original evidence', 'recorded_on': '2026-10-01',
                'due_on': '2026-10-10', 'document_ids': [evidence['original']['document_id']],
                'legal_source_version_ids': [evidence['legal_source_version_id']]})
            assert created_record.status == 201, created_record.text()
            record_id = created_record.json()['record_id']
            page.locator('#workQueueRefresh').click()
            pending_record = page.locator('#workQueuePanel article').filter(has_text='危険物記録の原本・根拠確認')
            expect(pending_record).to_have_count(1)
            expect(page.locator('#workQueuePanel')).not_to_contain_text('Synthetic notification original evidence')
            pending_record.get_by_role('button', name='元記録を開く', exact=True).click()
            expect(page.locator('#hazardousContent')).to_contain_text('Synthetic notification original evidence')
            page.locator('#hazardousConfirm').click()
            page.locator('#hazardousField_reason').fill('Synthetic independent original confirmation')
            page.locator('#hazardousField_human_acknowledged').check()
            with page.expect_response(lambda r: r.url.endswith('/records/' + record_id + '/confirm') and r.request.method == 'POST') as confirmed_record:
                page.locator('#hazardousSave').click()
            assert confirmed_record.value.status == 200, confirmed_record.value.text()
            expect(page.locator('#hazardousContent')).to_contain_text('現行の事実・原本をHuman確認済')
            page.locator('#hazardousClose').click()
            page.locator('#workQueueBtn').click()
            expect(page.locator('#workQueuePanel')).not_to_contain_text('危険物記録の原本・根拠確認')
            expect(page.locator('#workQueuePanel')).to_contain_text('危険物記録の期限確認')
            page.screenshot(path=str(artifacts / 'hazardous-queue-record-confirmed-deadline.png'), full_page=True)
            page.locator('#hazardousBtn').click()
            page.locator('[data-hazardous-installation]').click()
            page.locator('#hazardousEvaluationList').click()
            page.locator('[data-hazardous-evaluation]').click()
            expect(page.locator('#hazardousContent')).to_contain_text('Human確認済')
            revoke = "from app.db import engine; from test_hazardous_rule_authoring import revoke_original_access; revoke_original_access(engine)"
            subprocess.run([sys.executable, '-c', revoke], cwd=root, env=env, check=True, capture_output=True)
            page.locator('#hazardousEvaluationReload').click()
            expect(page.locator('#hazardousModal')).to_have_count(0)
            assert not errors, errors
            browser.close()
    finally:
        server.terminate(); server.wait(timeout=10); logs.close()
