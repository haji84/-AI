"""Actual shared-shell Chromium inquiry source selection, rejection and Human confirmation."""
import os
from pathlib import Path
import socket,subprocess,sys,time,urllib.request
from urllib.parse import parse_qs,urlsplit
import pytest
pytestmark=pytest.mark.skipif(os.environ.get('FIRE_AI_TEST_BROWSER')!='1',reason='actual Chromium inquiry workflow executes in dedicated CI job')
def test_inquiry_authorized_source_unsupported_number_human_answer_and_navigation(tmp_path):
 from playwright.sync_api import sync_playwright,expect
 root=Path(__file__).resolve().parents[2]
 env={**os.environ,'PYTHONPATH':str(root/'backend'),'FIRE_AI_DATABASE_URL':'sqlite+pysqlite:///'+str(tmp_path/'synthetic.db'),'FIRE_AI_STORAGE_ROOT':str(tmp_path/'storage'),'FIRE_AI_PRODUCTION_MODE':'false'};env.pop('FIRE_AI_TENANT_ID',None)
 seed=r'''
from pathlib import Path
from hashlib import sha256
from app.main import app
from app.db import Base,engine,SessionLocal
from app.models import User,UserRole,Document
from app.rbac_seed import seed_rbac
from app.security import hash_password
from app.settings import settings
Base.metadata.create_all(engine)
root=Path(settings.storage_root);root.mkdir(parents=True,exist_ok=True);raw=b'Synthetic count 12 people.';(root/'proof.txt').write_bytes(raw)
with SessionLocal() as db:
 roles=seed_rbac(db);u=User(username='uiinquiry',password_hash=hash_password('synthetic-ui-password'));db.add(u);db.flush();db.add(UserRole(user_id=u.user_id,role_id=roles['system_admin'].role_id));db.add(Document(original_filename='Synthetic council evidence.txt',storage_path='proof.txt',sha256=sha256(raw).hexdigest(),size_bytes=len(raw),mime_type='text/plain'));db.commit()
'''
 subprocess.run([sys.executable,'-c',seed],cwd=root,env=env,check=True)
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
   page.goto(base+'/ui/');page.locator('#loginUser').fill('uiinquiry');page.locator('#loginPass').fill('synthetic-ui-password');page.get_by_role('button',name='ログイン',exact=True).click();expect(page.locator('#inquiriesBtn')).to_be_visible();page.locator('#inquiriesBtn').click();expect(page.locator('#inquiryContent')).to_contain_text('過去の質問')
   page.locator('#inquiryNew').click();page.locator('#inquiryNewYear').fill('2026');page.locator('#inquiryQuestion').fill('Synthetic browser council count')
   with page.expect_response(lambda r:r.url.endswith('/inquiries') and r.request.method=='POST') as response:page.locator('#inquiryCreate').click()
   assert response.value.status==201,response.value.text();row=response.value.json();key=row['inquiry_id']
   page.locator('#inquiryEvidence').click();expect(page.locator('#inquirySourceSelect')).to_contain_text('Synthetic count 12 people.')
   expect(page.locator('#inquirySourceType')).to_have_value('document')
   expect(page.locator('#inquirySourceFind')).to_be_enabled()
   page.locator('#inquirySourceQuery').fill('Synthetic count')
   # The initial preview has identical text. It cannot prove this search has
   # finished; wait for its actual response and the pending-operation release.
   with page.expect_response(lambda r:r.request.method=='GET' and r.url.startswith(base+'/inquiries/sources?') and parse_qs(urlsplit(r.url).query).get('source_type')==['document'] and parse_qs(urlsplit(r.url).query).get('q')==['Synthetic count']) as searched:
    page.locator('#inquirySourceFind').click()
   assert searched.value.status==200,searched.value.text()
   expect(page.locator('#inquirySourceFind')).to_be_enabled()
   expect(page.locator('#inquiryEvidenceSave')).to_be_enabled()
   expect(page.locator('#inquirySourceText')).to_contain_text('Synthetic count 12 people.')
   page.locator('#inquiryExcerpt').fill('Synthetic count 12 people.')
   with page.expect_response(lambda r:r.url.endswith('/evidence') and r.request.method=='POST') as response:page.locator('#inquiryEvidenceSave').click()
   assert response.value.status==201,response.value.text();evidence=response.value.json();expect(page.locator('#inquiryContent')).to_contain_text(evidence['snapshot']['documents'][0]['sha256'])
   page.locator('#inquiryEdit').click();page.locator('#inquiryDraft').fill('Unsupported count 13 people.')
   with page.expect_response(lambda r:r.url.endswith('/inquiries/'+key) and r.request.method=='PATCH') as response:page.locator('#inquiryDraftSave').click()
   assert response.value.status==422,response.value.text();expect(page.locator('#inquiryMessage')).to_contain_text('unsupported numerical claim')
   # Return through the actual list/year surface to the unchanged draft.
   page.locator('#inquiryList').click();page.locator('#inquiryYear').fill('2026');page.locator('#inquiryQuery').fill('Synthetic browser')
   # Find first waits for shared-session authority. An old row can still be
   # visible then, but its queued click is discarded once search locks it.
   with page.expect_response(lambda r:r.request.method=='GET' and r.url.startswith(base+'/inquiries?') and parse_qs(urlsplit(r.url).query).get('year')==['2026'] and parse_qs(urlsplit(r.url).query).get('q')==['Synthetic browser']) as searched:
    page.locator('#inquiryFind').click()
   assert searched.value.status==200,searched.value.text()
   assert any(item['inquiry_id']==key for item in searched.value.json())
   expect(page.locator('#inquiryFind')).to_be_enabled()
   result=page.locator('[data-inquiry="'+key+'"]');expect(result).to_be_enabled();result.click()
   page.locator('#inquiryAI').click();expect(page.locator('#inquiryCandidateContent')).to_contain_text('deterministic-evidence-extract')
   with page.expect_response(lambda r:r.url.endswith('/inquiries/'+key+'/adopt-candidate') and r.request.method=='POST') as adopted:page.locator('#inquiryAdopt').click()
   assert adopted.value.status==200,adopted.value.text();adopted_row=adopted.value.json()
   expect(page.locator('#inquiryContent')).to_contain_text('Version '+str(adopted_row['version']));expect(page.locator('#inquiryContent')).to_contain_text(adopted_row['draft']);expect(page.locator('#inquiryEdit')).to_be_enabled()
   page.locator('#inquiryEdit').click();page.locator('#inquiryDraft').fill('Human checked count 12 people.')
   with page.expect_response(lambda r:r.url.endswith('/inquiries/'+key) and r.request.method=='PATCH') as response:page.locator('#inquiryDraftSave').click()
   assert response.value.status==200,response.value.text();assert response.value.json()['status']=='draft'
   for action,button in [('review','inquiryReview'),('approve','inquiryApprove')]:
    page.locator('#'+button).click();page.locator('#inquiryHumanChecked').check();page.locator('#inquiryReason').fill('Synthetic Human checked original and exact count')
    with page.expect_response(lambda r:r.url.endswith('/'+action) and r.request.method=='POST') as response:page.locator('#inquiryHumanSave').click()
    assert response.value.status==200,response.value.text();row=response.value.json();assert row['status']==('reviewed' if action=='review' else 'approved')
   expect(page.locator('#inquiryContent')).to_contain_text('Human承認済み回答');expect(page.locator('#inquiryEdit')).to_have_count(0)
   expect(page.locator('[data-inquiry-source="'+evidence['evidence_id']+'"]')).to_be_enabled()
   with page.expect_download() as downloaded:page.locator('[data-inquiry-source="'+evidence['evidence_id']+'"]').click()
   download=downloaded.value;assert Path(download.path()).read_bytes()==b'Synthetic count 12 people.'
   assert not errors,errors;expect(page.locator('#inquiryMessage')).to_be_empty()
   artifact=Path(os.environ.get('FIRE_AI_BROWSER_ARTIFACTS',str(tmp_path/'artifacts')));artifact.mkdir(parents=True,exist_ok=True);page.screenshot(path=str(artifact/'inquiry-human-evidence-answer.png'),full_page=True);browser.close()
 finally:server.terminate();server.wait(timeout=10);logs.close()
