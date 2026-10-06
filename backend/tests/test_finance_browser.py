"""Real shared-shell Chromium/HTTP financial Human workflow, synthetic records only."""
import os
from pathlib import Path
import socket,subprocess,sys,time,urllib.request
import pytest
pytestmark=pytest.mark.skipif(os.environ.get('FIRE_AI_TEST_BROWSER')!='1',reason='actual Chromium runs in dedicated CI job')

def test_finance_exact_budget_contract_picker_review_payment_and_balance(tmp_path):
 from playwright.sync_api import sync_playwright,expect
 root=Path(__file__).resolve().parents[2]
 env={**os.environ,'PYTHONPATH':str(root/'backend'),'FIRE_AI_DATABASE_URL':'sqlite+pysqlite:///'+str(tmp_path/'synthetic.db'),'FIRE_AI_STORAGE_ROOT':str(tmp_path/'storage'),'FIRE_AI_PRODUCTION_MODE':'false'};env.pop('FIRE_AI_TENANT_ID',None)
 seed=r'''
from pathlib import Path
from hashlib import sha256
from decimal import Decimal
from app.main import app
from app.db import Base,engine,SessionLocal
from app.models import User,UserRole,Document,ContractCase,ContractDocument,ContractCounterparty,now_utc
from app.finance_models import FinanceYear,BudgetAccount,ProcurementProfile
from app.rbac_seed import seed_rbac
from app.security import hash_password
from app.settings import settings
Base.metadata.create_all(engine)
root=Path(settings.storage_root);root.mkdir(parents=True,exist_ok=True);proof=b'Synthetic financial source evidence';(root/'proof.txt').write_bytes(proof)
with SessionLocal() as db:
 roles=seed_rbac(db);u=User(username='uifinance',password_hash=hash_password('synthetic-ui-password'));db.add(u);db.flush();db.add(UserRole(user_id=u.user_id,role_id=roles['system_admin'].role_id))
 d=Document(original_filename='Synthetic finance proof.txt',storage_path='proof.txt',sha256=sha256(proof).hexdigest(),size_bytes=len(proof));db.add(d)
 y=FinanceYear(fiscal_year=2026,currency='JPY',decimal_places=2,require_invoice_on_payment=True,status='approved',reason='Synthetic configured policy',approved_by=u.user_id,approved_at=now_utc());db.add(y);db.flush()
 parent=None
 for level in range(1,6):
  a=BudgetAccount(year_id=y.year_id,parent_id=parent.account_id if parent else None,level=level,code=f'00{level}',name='Synthetic browser leaf' if level==5 else f'Synthetic level {level}');db.add(a);db.flush();parent=a
 p=ContractCounterparty(name='Synthetic supplier');db.add(p);db.flush();c=ContractCase(title='Synthetic browser finance contract',counterparty_id=p.counterparty_id,amount=Decimal('500.01'),currency='JPY',status='approved',approved_by=u.user_id,approved_at=now_utc());db.add(c);db.flush();db.add_all([ContractDocument(contract_case_id=c.contract_case_id,document_id=d.document_id,document_role='contract_source'),ProcurementProfile(contract_case_id=c.contract_case_id,year_id=y.year_id)]);db.commit()
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
   browser=p.chromium.launch(**({'executable_path':os.environ['FIRE_AI_BROWSER_EXECUTABLE']} if os.environ.get('FIRE_AI_BROWSER_EXECUTABLE') else {}));page=browser.new_page();errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
   page.goto(base+'/ui/');page.locator('#loginUser').fill('uifinance');page.locator('#loginPass').fill('synthetic-ui-password');page.get_by_role('button',name='ログイン',exact=True).click();expect(page.locator('#financeBtn')).to_be_visible();page.locator('#financeBtn').click();expect(page.locator('#financeContent')).to_contain_text('財務処理')
   def save(fragment,status=201):
    try:
     with page.expect_response(lambda r:fragment in r.url and r.request.method=='POST') as response:page.locator('#financeSave').click()
    except Exception:
     print('Synthetic finance failure diagnostics:',page.evaluate("""() => ({message:document.getElementById('financeMessage')?.textContent,fields:Array.from(document.querySelectorAll('#financeForm input, #financeForm select, #financeForm textarea')).map(n=>({id:n.id,value:n.value,disabled:n.disabled,valid:n.validity.valid,missing:n.validity.valueMissing})),pending:!!financePendingAction})"""),errors)
     raise
    assert response.value.status==status,response.value.text();return response.value.json()
   def new_proposal(kind,amount):
    page.locator('#financeProposals').click();page.locator('#financeProposalNew').click();page.locator('#financeField_kind').select_option(kind);expect(page.locator('#financeField_account_id')).to_be_visible();page.locator('#financeField_account_id').select_option(label='005 / Synthetic browser leaf');page.locator('#financeField_amount').fill(amount);page.locator('#financeField_document_id').select_option(label='Synthetic finance proof.txt');page.locator('#financeField_reason').fill('Synthetic browser '+kind)
    if kind in ['commitment','payment']:
     page.locator('#financePick_contract_case_id_q').fill('Synthetic browser finance contract');page.locator('#financePick_contract_case_id_find').click();page.locator('#financeField_contract_case_id').select_option(label='Synthetic browser finance contract / 500.01 JPY')
    if kind=='payment':
     page.locator('#financeField_commitment_id').select_option(label='支出負担行為 / 500.01 JPY / Synthetic Human formal approval');page.locator('#financeField_invoice_id').select_option(label='請求書 / 100.01 JPY / Synthetic invoice stage approval')
     expect(page.locator('#financeField_commitment_id')).to_have_value(commitment['proposal_id']);expect(page.locator('#financeField_invoice_id')).to_have_value(invoice['event_id'])
    return save('/finance/proposals')
   def approve(proposal):
    key=proposal['proposal_id'];expect(page.locator('#financeContent')).to_contain_text(proposal['amount']);page.locator('#financeReview').click();expect(page.locator('#financeContent')).to_contain_text('根拠');page.locator('#financeField_reason').fill('Synthetic Human evidence review');save('/finance/proposals/'+key+'/review',200);page.locator('#financeApprove').click();expect(page.locator('#financeContent')).to_contain_text(proposal['amount']);page.locator('#financeField_reason').fill('Synthetic Human formal approval');r=save('/finance/proposals/'+key+'/approve',200);assert r['status']=='approved';expect(page.locator('#financeContent')).to_contain_text('approved')
   initial=new_proposal('initial','1000.01');expect(page.locator('#financeBalance')).to_have_text('0.00');approve(initial);expect(page.locator('#financeBalance')).to_have_text('1000.01')
   commitment=new_proposal('commitment','500.01');approve(commitment);expect(page.locator('#financeBalance')).to_have_text('500.00')
   # Real stage pickers select the record itself, including an inspection with a delivery FK.
   def stage(kind,amount,related=None):
    page.locator('#financeEvents').click();page.locator('#financeEventNew').click();page.locator('#financeField_kind').select_option(kind);page.locator('#financeField_contract_case_id').select_option(label='Synthetic browser finance contract / 500.01 JPY');page.locator('#financeField_description').fill('Synthetic browser '+kind);page.locator('#financeField_amount').fill(amount);page.locator('#financeField_document_id').select_option(label='Synthetic finance proof.txt')
    if related:
     label=('納品・引渡' if related['kind']=='delivery' else '検査・検収')+' / 0.00 JPY / Synthetic '+related['kind']+' stage approval'
     page.locator('#financeField_related_event_id').select_option(label=label);expect(page.locator('#financeField_related_event_id')).to_have_value(related['event_id'])
    row=save('/finance/procurement-events')
    if related:assert row['related_event_id']==related['event_id']
    page.locator('#financeEventReview').click();page.locator('#financeField_reason').fill('Synthetic '+kind+' source review');save('/finance/procurement-events/'+row['event_id']+'/review',200);page.locator('#financeEventApprove').click();page.locator('#financeField_reason').fill('Synthetic '+kind+' stage approval');return save('/finance/procurement-events/'+row['event_id']+'/approve',200)
   delivery=stage('delivery','0');inspection=stage('inspection','0',delivery);invoice=stage('invoice','100.01',inspection)
   payment=new_proposal('payment','100.01');assert payment['commitment_id']==commitment['proposal_id'] and payment['invoice_id']==invoice['event_id'];approve(payment);expect(page.locator('#financeBalance')).to_have_text('500.00');expect(page.locator('#financeContent')).to_contain_text('予約 400.00');expect(page.locator('#financeContent')).to_contain_text('執行 100.01')
   assert not errors,errors;expect(page.locator('#financeMessage')).to_be_empty()
   artifact=Path(os.environ.get('FIRE_AI_BROWSER_ARTIFACTS',str(tmp_path/'artifacts')));artifact.mkdir(parents=True,exist_ok=True);page.screenshot(path=str(artifact/'finance-human-payment.png'),full_page=True)
   # Source links must report auth loss back to this shared-PC surface.
   source=page.locator('#financeModal a[href^="/documents/"]').first;expect(source).to_be_visible()
   assert page.request.post(base+'/auth/logout').status==200
   source.click();expect(page.locator('#financeModal')).to_have_count(0)
   assert page.evaluate('financeState.permissions.length')==0
   assert not errors,errors
   browser.close()
 finally:server.terminate();server.wait(timeout=10);logs.close()


@pytest.fixture
def finance_first_use(tmp_path):
 """Real editor session with no documents, accounts or contracts pre-seeded."""
 from playwright.sync_api import sync_playwright,expect
 root=Path(__file__).resolve().parents[2]
 env={**os.environ,'PYTHONPATH':str(root/'backend'),'FIRE_AI_DATABASE_URL':'sqlite+pysqlite:///'+str(tmp_path/'first-use.db'),'FIRE_AI_STORAGE_ROOT':str(tmp_path/'storage'),'FIRE_AI_PRODUCTION_MODE':'false'}
 env.pop('FIRE_AI_TENANT_ID',None)
 seed=r'''
from app.main import app
from app.db import Base,engine,SessionLocal
from app.models import User,UserRole,now_utc
from app.finance_models import FinanceYear
from app.rbac_seed import seed_rbac
from app.security import hash_password
Base.metadata.create_all(engine)
with SessionLocal() as db:
 roles=seed_rbac(db)
 for name,role in [('editor','finance_editor'),('reviewer','finance_reviewer'),('other-editor','finance_editor'),('policy-admin','system_admin')]:
  u=User(username=name,password_hash=hash_password('synthetic-ui-password'));db.add(u);db.flush();db.add(UserRole(user_id=u.user_id,role_id=roles[role].role_id))
 # Approved fiscal policy is the separate administrator prerequisite.
 db.add(FinanceYear(fiscal_year=2026,currency='JPY',decimal_places=2,status='approved',reason='Synthetic approved administrator policy',approved_by=u.user_id,approved_at=now_utc()))
 db.commit()
'''
 subprocess.run([sys.executable,'-c',seed],cwd=root,env=env,check=True)
 with socket.socket() as allocation:
  allocation.bind(('127.0.0.1',0));port=allocation.getsockname()[1]
 base=f'http://127.0.0.1:{port}'
 with (tmp_path/'server.log').open('w') as logs:
  server=subprocess.Popen([sys.executable,'-m','uvicorn','app.main:app','--host','127.0.0.1','--port',str(port)],cwd=root,env=env,stdout=logs,stderr=logs)
  try:
   for _ in range(100):
    try:urllib.request.urlopen(base+'/health',timeout=.2).close();break
    except OSError:
     if server.poll() is not None:raise AssertionError((tmp_path/'server.log').read_text())
     time.sleep(.1)
   else:raise AssertionError('synthetic first-use server did not start')
   with sync_playwright() as p:
    browser=p.chromium.launch(**({'executable_path':os.environ['FIRE_AI_BROWSER_EXECUTABLE']} if os.environ.get('FIRE_AI_BROWSER_EXECUTABLE') else {}))
    page=browser.new_page();errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
    page.goto(base+'/ui/');page.locator('#loginUser').fill('editor');page.locator('#loginPass').fill('synthetic-ui-password');page.get_by_role('button',name='ログイン',exact=True).click()
    expect(page.locator('#financeBtn')).to_be_visible();page.locator('#financeBtn').click();expect(page.locator('#financeContent')).to_contain_text('財務処理')
    yield page,base,tmp_path
    assert not errors,errors
    browser.close()
  finally:
   server.terminate();server.wait(timeout=10)


def new_first_use_contract(page):
 from playwright.sync_api import expect
 page.locator('#financeContracts').click();page.locator('#financeContractNew').click()
 expect(page.locator('#financePick_document_id_panel')).to_be_visible()
 page.locator('#financeField_title').fill('Synthetic first-use contract')
 page.locator('#financeField_amount').fill('250.01')
 page.locator('#financeField_contract_method').fill('Synthetic entered method')
 page.locator('#financeField_year_id').select_option(index=1)


def test_finance_editor_uploads_first_original_and_saves_only_a_draft(finance_first_use):
 from hashlib import sha256
 from playwright.sync_api import expect
 page,base,tmp_path=finance_first_use
 assert page.request.get(base+'/finance/documents').json()==[]
 new_first_use_contract(page)
 upload=page.locator('#financePick_document_id_upload')
 expect(upload).to_be_visible()
 content=b'Synthetic first-use original evidence\n'
 page.locator('#financePick_document_id_file').set_input_files({'name':'Synthetic first original.txt','mimeType':'text/plain','buffer':content})
 with page.expect_response(lambda r:r.url==base+'/documents/upload' and r.request.method=='POST') as response:
  upload.click()
 assert response.value.status==201,response.value.text()
 doc=response.value.json()
 assert doc['sha256']==sha256(content).hexdigest() and doc['building_id'] is None
 expect(page.locator('#financeField_document_id')).to_have_value(doc['document_id'])
 expect(page.locator('#financePick_document_id_proof')).to_contain_text(doc['sha256'])
 expect(page.locator('#financePick_document_id_proof')).to_contain_text(doc['original_filename'])
 expect(page.locator('#financePick_document_id_proof')).to_contain_text(doc['document_id'])
 expect(page.locator('#financeField_title')).to_have_value('Synthetic first-use contract')
 expect(page.locator('#financeField_amount')).to_have_value('250.01')
 expect(page.locator('#financeField_contract_method')).to_have_value('Synthetic entered method')
 # Existing picker search keeps the uploaded original selected even off-page.
 page.locator('#financePick_document_id_q').fill('absent-search-result')
 page.locator('#financePick_document_id_find').click()
 expect(page.locator('#financePick_document_id_page')).to_have_text('1～0件')
 expect(page.locator('#financeField_document_id')).to_have_value(doc['document_id'])
 with page.expect_response(lambda r:r.url==base+'/finance/contracts' and r.request.method=='POST') as saved:
  page.locator('#financeSave').click()
 assert saved.value.status==201,saved.value.text()
 contract=saved.value.json()
 assert contract['status']=='draft' and contract['amount']=='250.01'
 detail=page.request.get(base+'/finance/contracts/'+contract['contract_case_id']).json()
 assert detail['documents'][0]['document_id']==doc['document_id']
 assert page.request.get(base+'/documents/'+doc['document_id']+'/download').body()==content
 assert page.request.get(base+'/finance/journal').json()==[]
 # A POST response is not the completion of the guarded save-and-refresh action.
 expect(page.locator('#financeForm')).to_have_count(0)
 page.wait_for_function('financePendingAction===null')
 page.locator('[data-finance-contract="'+contract['contract_case_id']+'"]').click()
 expect(page.locator('#financeContent h2')).to_have_text('Synthetic first-use contract / draft')
 expect(page.locator('#financeContent')).to_contain_text(doc['sha256'])
 page.wait_for_function('financePendingAction===null')
 artifact=Path(os.environ.get('FIRE_AI_BROWSER_ARTIFACTS',str(tmp_path/'artifacts')));artifact.mkdir(parents=True,exist_ok=True)
 page.screenshot(path=str(artifact/'finance-first-original-draft.png'),full_page=True)


def select_synthetic_original(page,name='Synthetic pending original.txt'):
 page.locator('#financePick_document_id_file').set_input_files({'name':name,'mimeType':'text/plain','buffer':b'Synthetic pending original bytes'})


def test_finance_upload_empty_selection_and_rejected_request_can_retry(finance_first_use):
 from playwright.sync_api import expect
 page,base,_=finance_first_use
 new_first_use_contract(page)
 requests=[]
 page.on('request',lambda r:requests.append(r) if r.url==base+'/documents/upload' else None)
 upload=page.locator('#financePick_document_id_upload')
 expect(upload).to_be_disabled()
 select_synthetic_original(page)
 expect(upload).to_be_enabled()
 page.locator('#financePick_document_id_file').set_input_files([])
 expect(upload).to_be_disabled()
 assert not requests
 select_synthetic_original(page)
 page.route('**/documents/upload',lambda route:route.fulfill(status=422,json={'detail':'Synthetic upload rejected'}),times=1)
 upload.click()
 expect(page.locator('#financePick_document_id_status')).to_contain_text('Synthetic upload rejected')
 expect(upload).to_be_enabled()
 expect(page.locator('#financeSave')).to_be_enabled()
 expect(page.locator('#financeField_title')).to_have_value('Synthetic first-use contract')
 assert page.request.get(base+'/finance/documents').json()==[]
 with page.expect_response(lambda r:r.url==base+'/documents/upload') as response:upload.click()
 assert response.value.status==201
 expect(page.locator('#financeField_document_id')).to_have_value(response.value.json()['document_id'])
 expect(page.locator('#financePick_document_id_status')).not_to_contain_text('rejected')
 assert len(requests)==2


def hold_upload_response(page):
 """Upload through the real API, but release its response only when the test asks."""
 held=[]
 def hold(route):
  response=route.fetch()
  held.append((route,response))
 page.route('**/documents/upload',hold,times=1)
 return held


def wait_for_held_upload(page,held):
 deadline=time.monotonic()+5
 while not held and time.monotonic()<deadline:page.wait_for_timeout(20)
 assert len(held)==1,'real upload did not reach delayed response boundary'


def test_finance_upload_pending_blocks_old_evidence_save_and_duplicate_click(finance_first_use):
 from playwright.sync_api import expect
 page,base,_=finance_first_use
 new_first_use_contract(page)
 select_synthetic_original(page,'Synthetic prior original.txt')
 with page.expect_response(lambda r:r.url==base+'/documents/upload') as previous:page.locator('#financePick_document_id_upload').click()
 old_id=previous.value.json()['document_id']
 expect(page.locator('#financeField_document_id')).to_have_value(old_id)
 select_synthetic_original(page)
 held=hold_upload_response(page)
 # Both direct repeated activation and a synthetic submit must be guarded by application state.
 page.locator('#financePick_document_id_upload').evaluate('(b)=>{b.click();b.click()}')
 expect(page.locator('#financeSave')).to_be_disabled()
 wait_for_held_upload(page,held)
 expect(page.locator('#financePick_document_id_upload')).to_be_disabled()
 page.locator('#financeForm').evaluate("f=>f.dispatchEvent(new Event('submit',{bubbles:true,cancelable:true}))")
 page.wait_for_timeout(150)
 assert page.request.get(base+'/finance/contracts').json()==[]
 assert len(held)==1
 route,response=held[0];new_id=response.json()['document_id'];route.fulfill(response=response)
 expect(page.locator('#financeField_document_id')).to_have_value(new_id)
 expect(page.locator('#financeSave')).to_be_enabled()
 assert new_id!=old_id
 assert len(page.request.get(base+'/finance/documents').json())==2


@pytest.mark.parametrize('leave',['back','nav','close'])
def test_finance_upload_locks_navigation_and_discards_late_results_after_reset(finance_first_use,leave):
 from playwright.sync_api import expect
 page,base,_=finance_first_use
 new_first_use_contract(page);select_synthetic_original(page)
 held=hold_upload_response(page)
 page.locator('#financePick_document_id_upload').click()
 expect(page.locator('#financeSave')).to_be_disabled()
 wait_for_held_upload(page,held)
 control=page.locator({'back':'#financeBack','nav':'#financeCandidates','close':'#financeClose'}[leave])
 expect(control).to_be_disabled()
 control.evaluate('(button)=>button.click()')
 expect(page.locator('#financeField_title')).to_have_value('Synthetic first-use contract')
 # Shared-session invalidation can tear down an operation even though navigation is locked.
 page.evaluate('clearFinance()')
 page.evaluate('initFinance()')
 page.locator('#financeBtn').click()
 new_first_use_contract(page)
 expect(page.locator('#financeField_document_id')).to_have_value('')
 page.locator('#financeField_title').fill('Synthetic newer untouched draft')
 assert len(held)==1
 route,response=held[0]
 with page.expect_response(lambda r:r.url==base+'/documents/upload'):route.fulfill(response=response)
 page.wait_for_timeout(150)
 expect(page.locator('#financeField_document_id')).to_have_value('')
 expect(page.locator('#financeField_title')).to_have_value('Synthetic newer untouched draft')
 expect(page.locator('#financeMessage')).to_be_empty()
 expect(page.locator('#financeSave')).to_be_enabled()
 assert len(page.request.get(base+'/finance/documents').json())==1


def save_finance_session_diagnostics(page,base,tmp_path,next_user,before,after,requests,responses,failures,finished_requests=()):
 """Synthetic failure evidence only; never record cookie/token/password headers."""
 import json
 artifact=Path(os.environ.get('FIRE_AI_BROWSER_ARTIFACTS',str(tmp_path/'artifacts')))
 artifact.mkdir(parents=True,exist_ok=True)
 prefix=artifact/('finance-session-change-'+next_user)
 evidence={'before':before,'after':after,'requests':requests,'request_failures':failures}
 output=Path(str(prefix)+'.json')
 server_log=tmp_path/'server.log'
 if server_log.exists():Path(str(prefix)+'-server.log').write_text(server_log.read_text())
 output.write_text(json.dumps(evidence,ensure_ascii=False,indent=2))
 try:
  evidence['ui']=page.evaluate("""() => ({financeIdentity:financeState.identity,financeGeneration:financeState.generation,sharedGeneration:window.FireAISession.currentGeneration(),pending:!!financePendingAction,pendingGeneration:financePendingAction?.generation,modalCount:document.querySelectorAll('#financeModal').length,modalHidden:document.getElementById('financeModal')?.classList.contains('hidden'),selectedDocument:document.getElementById('financeField_document_id')?.value,status:document.getElementById('financePick_document_id_status')?.textContent,message:document.getElementById('financeMessage')?.textContent,uploadOutcome:window.syntheticFinanceUploadOutcome})""")
  page.screenshot(path=str(prefix)+'.png',full_page=True)
 except Exception as error:evidence['capture_error']=str(error)
 output.write_text(json.dumps(evidence,ensure_ascii=False,indent=2))
 observed=[]
 for at,response in list(responses):
  finished=response.request in finished_requests
  record={'at':at,'path':response.url.removeprefix(base),'status':response.status,'finished':finished}
  if not finished:record['body_pending']=True
  elif response.url in [base+'/auth/context',base+'/auth/me']:
   try:
    data=response.json()
    record['authority']={key:data[key] for key in ['user_id','session_id','tenant_id','permissions','username'] if key in data}
   except Exception as error:record['body_error']=str(error)
  observed.append(record)
 evidence['responses']=observed
 output.write_text(json.dumps(evidence,ensure_ascii=False,indent=2))
 print('Synthetic finance session-change diagnostics:',json.dumps(evidence,ensure_ascii=False))


@pytest.mark.parametrize('next_user',['editor','other-editor'])
def test_finance_late_upload_cannot_cross_an_authenticated_session_change(finance_first_use,next_user):
 from playwright.sync_api import expect
 page,base,tmp_path=finance_first_use
 new_first_use_contract(page);select_synthetic_original(page)
 held=hold_upload_response(page)
 started=time.monotonic();requests=[];responses=[];failures=[];finished=set();before=None;after=None
 relevant=lambda url:url.startswith(base+'/auth/') or url==base+'/documents/upload'
 page.on('request',lambda r:requests.append({'at':time.monotonic()-started,'method':r.method,'path':r.url.removeprefix(base)}) if relevant(r.url) else None)
 page.on('response',lambda r:responses.append((time.monotonic()-started,r)) if relevant(r.url) else None)
 page.on('requestfinished',lambda r:finished.add(r) if relevant(r.url) else None)
 page.on('pageerror',lambda error:failures.append({'at':time.monotonic()-started,'kind':'pageerror','message':str(error)}))
 page.on('requestfailed',lambda r:failures.append({'at':time.monotonic()-started,'path':r.url.removeprefix(base),'failure':r.failure}) if relevant(r.url) else None)
 page.evaluate("""() => {const button=document.getElementById('financePick_document_id_upload'),run=button.onclick;window.syntheticFinanceUploadOutcome='not-started';button.onclick=function(...args){window.syntheticFinanceUploadOutcome='pending';return Promise.resolve(run.apply(this,args)).then(value=>{window.syntheticFinanceUploadOutcome='settled';return value},error=>{window.syntheticFinanceUploadOutcome={error:error.message,cancelled:!!error.cancelled};throw error})}}""")
 try:
  page.locator('#financePick_document_id_upload').click()
  expect(page.locator('#financeSave')).to_be_disabled()
  wait_for_held_upload(page,held)
  # Verify the intended cookie switch independently, without invoking the page's guard.
  before=page.request.get(base+'/auth/context').json()
  assert page.request.post(base+'/auth/logout').ok
  login=page.request.post(base+'/auth/login',data={'username':next_user,'password':'synthetic-ui-password'})
  assert login.ok
  after=page.request.get(base+'/auth/context').json()
  assert after['user_id']==login.json()['user_id']
  assert before['session_id']!=after['session_id']
  assert (before['user_id']==after['user_id'])==(next_user=='editor')
  assert len(held)==1
  route,response=held[0]
  with page.expect_response(lambda r:r.url==base+'/documents/upload'):route.fulfill(response=response)
  expect(page.locator('#financeModal')).to_have_count(0)
  assert page.evaluate('financeState.identity') is None
  assert page.evaluate('financeState.permissions.length')==0
  assert page.request.get(base+'/finance/contracts').json()==[]
 except Exception:
  save_finance_session_diagnostics(page,base,tmp_path,next_user,before,after,requests,responses,failures,finished)
  raise


@pytest.mark.parametrize('missing',['document.create','document.read'])
def test_finance_upload_control_requires_both_document_permissions(finance_first_use,missing):
 from playwright.sync_api import expect
 page,base,_=finance_first_use
 permissions=page.request.get(base+'/auth/permissions').json()
 permissions['permissions'].remove(missing)
 page.route('**/auth/permissions',lambda route:route.fulfill(json=permissions))
 page.locator('#financeClose').click();page.locator('#financeBtn').click()
 if missing=='document.read':
  page.locator('#financeContracts').click()
  expect(page.locator('#financeContractNew')).to_have_count(0)
 else:new_first_use_contract(page)
 expect(page.locator('#financePick_document_id_upload')).to_have_count(0)
 expect(page.locator('#financePick_document_id_file')).to_have_count(0)


def test_finance_permission_loss_before_upload_is_authoritative(finance_first_use):
 from playwright.sync_api import expect
 page,base,_=finance_first_use
 new_first_use_contract(page);select_synthetic_original(page)
 # The backend remains the authority when permissions have changed since rendering.
 assert page.request.post(base+'/auth/logout').ok
 assert page.request.post(base+'/auth/login',data={'username':'reviewer','password':'synthetic-ui-password'}).ok
 page.locator('#financePick_document_id_upload').click()
 expect(page.locator('#financeModal')).to_have_count(0)
 assert page.request.get(base+'/finance/documents').json()==[]


def test_finance_same_user_read_permission_loss_stops_upload(finance_first_use):
 from playwright.sync_api import expect
 page,base,_=finance_first_use
 new_first_use_contract(page);select_synthetic_original(page)
 permissions=page.request.get(base+'/auth/permissions').json()
 permissions['permissions'].remove('document.read')
 page.route('**/auth/permissions',lambda route:route.fulfill(json=permissions))
 page.locator('#financePick_document_id_upload').click()
 expect(page.locator('#financeModal')).to_have_count(0)
 assert page.request.get(base+'/finance/documents').json()==[]


def test_finance_postflight_error_does_not_upload_the_known_original_again(finance_first_use):
 from playwright.sync_api import expect
 page,base,_=finance_first_use
 new_first_use_contract(page);select_synthetic_original(page)
 posted=[]
 page.on('request',lambda request:posted.append(request) if request.url==base+'/documents/upload' else None)
 def permissions(route):
  if posted:route.fulfill(status=503,json={'detail':'Synthetic postflight verification failed'})
  else:route.continue_()
 page.route('**/auth/permissions',permissions)
 page.locator('#financePick_document_id_upload').click()
 expect(page.locator('#financePick_document_id_status')).to_contain_text('原本は登録済み')
 expect(page.locator('#financePick_document_id_upload')).to_be_disabled()
 expect(page.locator('#financeSave')).to_be_enabled()
 page.locator('#financePick_document_id_upload').evaluate('(button)=>button.click()')
 assert len(page.request.get(base+'/finance/documents').json())==1
 assert len(posted)==1
 expect(page.locator('#financeField_title')).to_have_value('Synthetic first-use contract')


@pytest.mark.parametrize('leave',['back','menu'])
def test_finance_failed_navigation_preserves_pending_upload_and_draft(finance_first_use,leave):
 from playwright.sync_api import expect
 page,base,_=finance_first_use
 new_first_use_contract(page);select_synthetic_original(page)
 held=hold_upload_response(page)
 page.locator('#financePick_document_id_upload').click()
 wait_for_held_upload(page,held)
 path='**/finance/contracts?*' if leave=='back' else '**/finance/candidates?*'
 page.route(path,lambda route:route.fulfill(status=503,json={'detail':'Synthetic navigation unavailable'}),times=1)
 control=page.locator('#financeBack' if leave=='back' else '#financeCandidates')
 expect(control).to_be_disabled()
 control.evaluate('(button)=>button.click()')
 route,response=held[0];route.fulfill(response=response)
 expect(page.locator('#financeField_document_id')).to_have_value(response.json()['document_id'])
 expect(page.locator('#financeSave')).to_be_enabled()
 control.click()
 expect(page.locator('#financeMessage')).to_contain_text('Synthetic navigation unavailable')
 expect(page.locator('#financeField_title')).to_have_value('Synthetic first-use contract')
 expect(page.locator('#financeField_amount')).to_have_value('250.01')


def test_finance_uploaded_original_link_uses_shared_pc_download_guard(finance_first_use):
 from playwright.sync_api import expect
 page,base,_=finance_first_use
 new_first_use_contract(page);select_synthetic_original(page)
 with page.expect_response(lambda r:r.url==base+'/documents/upload') as response:page.locator('#financePick_document_id_upload').click()
 document_id=response.value.json()['document_id']
 expect(page.locator('#financeField_document_id')).to_have_value(document_id)
 page.route('**/documents/'+document_id+'/download',lambda route:route.fulfill(status=403,json={'detail':'Synthetic original access revoked'}))
 page.locator('#financePick_document_id_proof a').click()
 expect(page.locator('#financeModal')).to_have_count(0)
 assert page.evaluate('financeState.permissions.length')==0


def test_finance_known_upload_success_survives_canonical_postflight_failure_without_retry_post(finance_first_use):
 from playwright.sync_api import expect
 page,base,_=finance_first_use
 new_first_use_contract(page);select_synthetic_original(page)
 posted=[]
 page.on('request',lambda request:posted.append(request) if request.url==base+'/documents/upload' else None)
 def identity(route):
  if posted:route.fulfill(status=503,json={'detail':'Synthetic postflight identity unavailable'})
  else:route.continue_()
 page.route('**/auth/me',identity)
 page.locator('#financePick_document_id_upload').click()
 expect(page.locator('#financePick_document_id_status')).to_contain_text('原本は登録済み')
 expect(page.locator('#financePick_document_id_upload')).to_be_disabled()
 expect(page.locator('#financeField_document_id')).to_have_value('')
 expect(page.locator('#financePick_document_id_proof')).to_be_empty()
 page.locator('#financePick_document_id_upload').evaluate('(button)=>button.click()')
 assert len(page.request.get(base+'/finance/documents').json())==1
 assert len(posted)==1


@pytest.mark.parametrize('pending_upload',[False,True])
def test_finance_failed_reopen_never_resurfaces_closed_draft(finance_first_use,pending_upload):
 from playwright.sync_api import expect
 page,base,_=finance_first_use
 new_first_use_contract(page);select_synthetic_original(page)
 held=[]
 if pending_upload:
  held=hold_upload_response(page)
  page.locator('#financePick_document_id_upload').click()
  wait_for_held_upload(page,held)
  expect(page.locator('#financeClose')).to_be_disabled()
  page.locator('#financeClose').evaluate('(button)=>button.click()')
  route,response=held[0];route.fulfill(response=response)
  expect(page.locator('#financeClose')).to_be_enabled()
 page.locator('#financeClose').click()
 page.route('**/finance/proposals?*',lambda route:route.fulfill(status=503,json={'detail':'Synthetic reopen unavailable'}),times=1)
 page.locator('#financeBtn').click()
 expect(page.locator('#financeMessage')).to_contain_text('Synthetic reopen unavailable')
 expect(page.locator('#financeForm')).to_have_count(0)
 new_first_use_contract(page)
 expect(page.locator('#financeSave')).to_be_enabled()
 expect(page.locator('#financeField_document_id')).to_have_value('')


def test_finance_upload_preflight_synchronously_locks_the_whole_draft(finance_first_use):
 from playwright.sync_api import expect
 page,base,_=finance_first_use
 new_first_use_contract(page);select_synthetic_original(page)
 expect(page.locator('#financePick_document_id_upload')).to_be_enabled()
 context=[]
 def hold_context(route):context.append((route,route.fetch()))
 page.route('**/auth/context',hold_context,times=1)
 uploaded=hold_upload_response(page)
 page.locator('#financePick_document_id_upload').click()
 wait_for_held_upload(page,context)
 for field in ['#financeField_title','#financeField_amount','#financeSave','#financeBack','#financeClose','#financePick_document_id_file']:
  expect(page.locator(field)).to_be_disabled()
 assert uploaded==[]
 route,response=context[0];route.fulfill(response=response)
 wait_for_held_upload(page,uploaded)
 expect(page.locator('#financeField_title')).to_be_disabled()
 route,response=uploaded[0];route.fulfill(response=response)
 expect(page.locator('#financeField_document_id')).to_have_value(response.json()['document_id'])
 expect(page.locator('#financeField_title')).to_be_enabled()
 expect(page.locator('#financeField_title')).to_have_value('Synthetic first-use contract')
 expect(page.locator('#financeField_amount')).to_have_value('250.01')
