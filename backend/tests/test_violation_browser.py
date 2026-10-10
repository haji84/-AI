"""Real shared-shell Chromium/HTTP violation/correction Human workflow, synthetic records only."""
import json
import os
from pathlib import Path
import socket,subprocess,sys,time,urllib.request
import pytest
pytestmark=pytest.mark.skipif(os.environ.get('FIRE_AI_TEST_BROWSER')!='1',reason='actual Chromium runs in dedicated CI job')

def test_violation_candidate_measure_response_review_and_completion(tmp_path):
 from playwright.sync_api import sync_playwright,expect
 root=Path(__file__).resolve().parents[2]
 env={**os.environ,'PYTHONPATH':str(root/'backend'),'FIRE_AI_DATABASE_URL':'sqlite+pysqlite:///'+str(tmp_path/'synthetic.db'),'FIRE_AI_STORAGE_ROOT':str(tmp_path/'storage'),'FIRE_AI_PRODUCTION_MODE':'false'};env.pop('FIRE_AI_TENANT_ID',None)
 seed="from datetime import date\nfrom hashlib import sha256\nfrom pathlib import Path\nfrom fastapi.testclient import TestClient\nfrom sqlalchemy import select\nfrom app.main import app\nfrom app.db import Base,engine,SessionLocal\nfrom app.models import (User,Employee,Role,Permission,RolePermission,UserRole,Facility,Inspection,InspectionFinding,Document,LegalRule,LegalRuleVersion,LegalJurisdiction,LegalSource,LegalSourceDocument,LegalSourceDocumentVersion,LegalProvision,LegalRuleCitation,UserSession,now_utc)\nfrom app.rbac_seed import PERMISSIONS\nfrom app.settings import settings\nfrom app.security import hash_password\nfrom app.legal_structure import ProvisionRecord\n\nfrom app.rbac_seed import seed_rbac\nBase.metadata.create_all(engine)\nwith SessionLocal() as db:\n    roles=seed_rbac(db);employee=Employee(display_name='Synthetic Human');db.add(employee);db.flush();user=User(username='violation',employee_id=employee.employee_id,password_hash=hash_password('synthetic-password'));db.add(user);db.flush();db.add(UserRole(user_id=user.user_id,role_id=roles['system_admin'].role_id));db.commit()\ndef sources(client):\n    def upload(name,content):\n        r=client.post('/documents/upload',files={'file':(name,content,'text/plain')});assert r.status_code==201,r.text;return r.json()['document_id']\n    proof=upload('synthetic-proof.txt',b'Synthetic observation evidence');procedure=upload('synthetic-procedure.txt',b'Synthetic Human formal procedure');raw=upload('synthetic-rule.txt',b'Synthetic Rule article')\n    with SessionLocal() as db:\n        user=db.scalar(select(User).where(User.username=='violation'))\n        facility=Facility(name='Synthetic facility');db.add(facility);db.flush()\n        inspection=Inspection(building_id=facility.building_id,inspected_at=date(2026,10,1));db.add(inspection);db.flush()\n        finding=InspectionFinding(inspection_id=inspection.inspection_id,finding_text='Synthetic observation, not a formal violation');db.add(finding)\n        jurisdiction=LegalJurisdiction(code='SYN',name='Synthetic',jurisdiction_type='fire_union');db.add(jurisdiction);db.flush()\n        source=LegalSource(jurisdiction_id=jurisdiction.jurisdiction_id,source_code='SYN',name='Synthetic source',source_type='regulation',adapter_type='manual',base_url='https://synthetic.invalid/',trust_level='official');db.add(source);db.flush()\n        doc=LegalSourceDocument(legal_source_id=source.legal_source_id,external_id='SYN',document_type='regulation',title='Synthetic fixture only');db.add(doc);db.flush()\n        version=LegalSourceDocumentVersion(legal_source_document_id=doc.legal_source_document_id,raw_document_id=raw,normalized_text='Synthetic Rule article',sha256=sha256(b'Synthetic Rule article').hexdigest(),source_url='https://synthetic.invalid/rule',structure_status='parsed');db.add(version);db.flush()\n        provision=LegalProvision(legal_source_document_version_id=version.legal_source_document_version_id,provision_type='article',provision_key='SYN-1',sequence_no=1,body_text='Synthetic Rule article',content_sha256=ProvisionRecord(provision_key='SYN-1',parent_key=None,provision_type='article',sequence_no=1,body_text='Synthetic Rule article').content_sha256);rule=LegalRule(rule_code='SYN-1',name='Synthetic fixture rule',domain='equipment_requirement');db.add_all([provision,rule]);db.flush()\n        rv=LegalRuleVersion(rule_id=rule.rule_id,version_no=1,effective_from=date(2026,1,1),conditions={'all':[{'field':'status','op':'eq','value':'active'}]},outcome={'synthetic':True},source_legal_document_version_id=version.legal_source_document_version_id,status='approved',approved_by=user.user_id,approved_at=now_utc());db.add(rv);db.flush();db.add(LegalRuleCitation(legal_rule_version_id=rv.legal_rule_version_id,legal_provision_id=provision.legal_provision_id,cited_text_snapshot='Synthetic Rule article'));db.commit()\n        return dict(building_id=facility.building_id,finding_id=finding.finding_id,rule_id=rv.legal_rule_version_id,provision_id=provision.legal_provision_id,legal_source_version_id=version.legal_source_document_version_id,proof=proof,procedure=procedure)\n\nwith TestClient(app) as c:\n    assert c.post('/auth/login',json={'username':'violation','password':'synthetic-password'}).status_code==200\n    sources(c)\n"
 subprocess.run([sys.executable,'-c',seed],cwd=root,env=env,check=True)
 with socket.socket() as allocation:allocation.bind(('127.0.0.1',0));port=allocation.getsockname()[1]
 artifact=Path(os.environ.get('FIRE_AI_BROWSER_ARTIFACTS',str(tmp_path/'artifacts')));artifact.mkdir(parents=True,exist_ok=True)
 diagnostics={'synthetic_only':True, 'selected_fields':[], 'network':[], 'artifact_errors':[]}
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
   diagnostics['page_errors']=errors
   def capture_response(response):
    try:
     if response.request.method not in ('POST','PATCH') or not response.url.startswith(base+'/violations'):
      return
     record={'path':response.url[len(base):], 'method':response.request.method, 'status':response.status}
     if record['path']=='/violations' and record['method']=='POST':
      keys=('building_id','finding_id','rule_version_ids','evidence_document_ids','procedure_document_ids')
      try:
       sent=response.request.post_data_json or {};received=response.json()
       record['request']={key:sent.get(key) for key in keys}
       record['response']={key:received.get(key) for key in ('case_id','status',*keys)}
      except Exception as error:record['capture_error']=type(error).__name__
     diagnostics['network'].append(record)
    except Exception as error:diagnostics['artifact_errors'].append({'artifact':'response_callback','error':type(error).__name__})
   page.on('response',capture_response)
   try:
    page.goto(base+'/ui/');page.locator('#loginUser').fill('violation');page.locator('#loginPass').fill('synthetic-password');page.get_by_role('button',name='ログイン',exact=True).click();expect(page.locator('#violationBtn')).to_be_visible();page.locator('#violationBtn').click();page.locator('#violationNew').click()
    def pick(field,label,delay_authority=False):
     box=page.locator('#violationField_'+field).locator('..').locator('div').first
     expect(box.locator('select option').filter(has_text=label)).to_have_count(1)
     selected=box.locator('select').select_option(label=label)
     if delay_authority:
      held=[]
      def hold(route):held.append(route)
      page.route('**/auth/context',hold)
      try:
       with page.expect_request(lambda r:r.url.endswith('/auth/context')):
        box.get_by_role('button',name='選択',exact=True).click()
       expect(page.locator('#violationForm button[type=submit]')).to_be_disabled()
       assert page.locator('#violationField_'+field).input_value()==''
       page.evaluate("""() => {
        window.syntheticSubmitReplayed=0;
        document.getElementById('violationForm').addEventListener('submit',()=>window.syntheticSubmitReplayed++);
       }""")
       with page.expect_request(lambda r:r.url.endswith('/auth/context')):
        page.locator('#violationForm').evaluate("form=>form.dispatchEvent(new Event('submit',{bubbles:true,cancelable:true}))")
       assert len(held)>=2
       # Pass through the real server authority response for submit first.
       held.pop().continue_()
       page.wait_for_function('window.syntheticSubmitReplayed===1')
       assert not any(r['path']=='/violations' and r['method']=='POST' for r in diagnostics['network'])
      finally:
       page.unroute('**/auth/context',hold)
       for route in held:route.continue_()
     else:box.get_by_role('button',name='選択',exact=True).click()
     actual=page.locator('#violationField_'+field).input_value()
     diagnostics['selected_fields'].append({'field':field,'chosen_ids':selected,'actual':actual})
     expect(page.locator('#violationField_'+field),f'{field}: selected ID must remain in the readonly field').to_have_value(selected[0])
    def save(path,status=200):
     with page.expect_response(lambda r:r.url.endswith(path) and r.request.method in ('POST','PATCH')) as response:
      page.locator('#violationForm button[type=submit]').click()
     assert response.value.status==status,response.value.text()
     return response.value.json()
    def human(button,path):
     page.locator('#'+button).click();page.locator('#violationField_reason').fill('Synthetic Human originals and procedure checked');page.locator('#violationField_human_acknowledged').select_option('true');return save(path)
    pick('building_id','Synthetic facility');pick('finding_id','Synthetic observation, not a formal violation');page.locator('#violationField_possible_issue').fill('Synthetic browser possible issue');pick('rule_version_ids','SYN-1 / Synthetic fixture rule / v1');pick('evidence_document_ids','synthetic-proof.txt');pick('procedure_document_ids','synthetic-procedure.txt',delay_authority=True);case=save('/violations',201);case_path='/violations/'+case['case_id'];assert case['status']=='candidate'
    for field in ('rule_version_ids','evidence_document_ids','procedure_document_ids'):
     assert case.get(field),f'created candidate missing {field}: {diagnostics["network"]}'
    human('violationReview',case_path+'/review');case=human('violationConfirm',case_path+'/confirm');assert case['status']=='confirmed'
    page.locator('#violationMeasureNew').click();page.locator('#violationField_kind').select_option('order');page.locator('#violationField_instruction').fill('Synthetic browser Human order');pick('document_ids','synthetic-proof.txt');pick('procedure_document_ids','synthetic-procedure.txt');m=save(case_path+'/measures',201)
    page.locator('[data-violation-measure]').click();human('violationMeasureReview',case_path+'/measures/'+m['measure_id']+'/review');page.locator('[data-violation-measure]').click();human('violationMeasureConfirm',case_path+'/measures/'+m['measure_id']+'/confirm')
    page.locator('#violationCorrectionNew').click();page.locator('#violationField_description').fill('Synthetic browser correction');page.locator('#violationField_due_on').fill('2026-10-10');task=save(case_path+'/corrections',201);task_path=case_path+'/corrections/'+task['action_id']
    def evidence(button,verb):
     page.locator('[data-violation-correction]').click();page.locator('#'+button).click();page.locator('#violationField_reason').fill('Synthetic Human proof checked');page.locator('#violationField_human_acknowledged').select_option('true');pick('evidence_document_ids','synthetic-proof.txt')
     if verb=='respond':page.locator('#violationField_response_text').fill('Synthetic response with evidence')
     return save(task_path+'/'+verb)
    evidence('violationRespond','respond');evidence('violationVerifyNo','verify');expect(page.locator('#violationContent')).to_contain_text('回答あり');evidence('violationVerifyYes','verify');task=evidence('violationTaskComplete','complete');assert task['status']=='completed'
    case=human('violationComplete',case_path+'/complete');assert case['status']=='completed';expect(page.locator('#violationContent')).to_contain_text('正式違反・改善完了');page.locator('[data-violation-measure]').click();page.locator('#violationMeasureWithdraw').click();page.locator('#violationField_reason').fill('Synthetic completed-case order resolution');page.locator('#violationField_human_acknowledged').select_option('true');pick('proof_document_ids','synthetic-procedure.txt');withdrawn=save(case_path+'/measures/'+m['measure_id']+'/withdraw');assert withdrawn['status']=='withdrawn';page.locator('[data-violation-correction]').click();expect(page.locator('#violationContent')).to_contain_text('response');expect(page.locator('#violationContent')).to_contain_text('completion')
    page.screenshot(path=str(artifact/'violation-human-completion.png'),full_page=True)
    assert page.request.post(base+'/auth/logout').status==200
    page.evaluate('violationAction(()=>violationCases())');expect(page.locator('#violationModal')).to_have_count(0);assert page.evaluate('violationState.permissions.length')==0;assert not errors,errors
   finally:
    try:
     if not page.is_closed() and page.locator('#violationModal').count():
      page.screenshot(path=str(artifact/'violation-diagnostic-final.png'),full_page=True)
    except Exception as error:diagnostics['artifact_errors'].append({'artifact':'screenshot','error':type(error).__name__})
    try:browser.close()
    except Exception as error:diagnostics['artifact_errors'].append({'artifact':'browser_close','error':type(error).__name__})
 finally:
  def diagnostic_error(name,error):
   kind=type(error).__name__
   diagnostics['artifact_errors'].append({'artifact':name,'error':kind})
   print(f'violation diagnostic {name}: {kind}',file=sys.stderr)
  try:
   server.terminate();server.wait(timeout=10)
  except Exception as error:
   diagnostic_error('server_cleanup',error)
   try:server.kill();server.wait(timeout=5)
   except Exception as error:diagnostic_error('server_kill',error)
  try:logs.close()
  except Exception as error:diagnostic_error('log_close',error)
  try:(artifact/'violation-diagnostic-server.log').write_text((tmp_path/'server.log').read_text())
  except Exception as error:diagnostic_error('server_log_write',error)
  try:(artifact/'violation-diagnostic.json').write_text(json.dumps(diagnostics,ensure_ascii=False,indent=2))
  except Exception as error:diagnostic_error('json_write',error)
