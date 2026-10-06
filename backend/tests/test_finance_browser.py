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
   browser=p.chromium.launch();page=browser.new_page();errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
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
