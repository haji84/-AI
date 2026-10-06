"""Fast execution of the finance picker; actual HTTP/Chromium flows live next door."""
from pathlib import Path
import subprocess


def test_finance_document_picker_offers_common_original_upload(tmp_path):
 root=Path(__file__).resolve().parents[2]
 script=tmp_path/'finance-upload.cjs'
 script.write_text(r'''
const fs=require('fs'),vm=require('vm'),assert=require('assert');
const nodes=new Map(),panels=[];
const get=id=>{if(!nodes.has(id))nodes.set(id,{value:'',innerHTML:'',textContent:'',remove(){},closest(){return {append(panel){panels.push(panel)}}}});return nodes.get(id)};
const ctx={URLSearchParams,$:get,esc:String,document:{contains:()=>true,createElement(){return {}}},api:async()=>[]};
vm.createContext(ctx);vm.runInContext(fs.readFileSync(process.argv[2],'utf8'),ctx);
vm.runInContext("financeState.permissions=['document.create','document.read']",ctx);
(async()=>{
 await ctx.financePicker('document_id','/finance/documents','Original');
 assert(panels[0].innerHTML.includes('type="file"'),'Document picker must expose original file selection');
 assert(panels[0].innerHTML.includes('financePick_document_id_upload'),'Document picker must expose upload action');
 vm.runInContext("financeState.permissions=['document.read']",ctx);
 await ctx.financePicker('document_id','/finance/documents','Original');
 assert(!panels[1].innerHTML.includes('type="file"'),'Read-only user must not receive upload control');
})().catch(e=>{console.error(e);process.exit(1)});
''')
 result=subprocess.run(['node',str(script),str(root/'frontend/finance.js')],capture_output=True,text=True)
 assert result.returncode==0,result.stderr


import pytest


@pytest.mark.parametrize('case',['permissions','success','pending','retry','cancel','new-form','back','close','session','preflight-session','preflight-navigation','late-error','two-pickers','permission-revoked','navigation','nav-background','postflight-retry','failed-menu','failed-menu-pending','failed-back','failed-back-pending','same-user-read-loss','close-reopen','clear-session','session-expired','failed-reopen','failed-reopen-pending','postflight-identity-retry','guarded-upload-result','proof-download-denied','proof-download-session','control-ownership','shared-preflight','shared-preflight-session','shared-upload-session','shared-upload-other-user','shared-upload-rights','shared-body-session','shared-postflight-outage','shared-canonical-postflight'])
def test_finance_upload_async_form_behavior(case):
 root=Path(__file__).resolve().parents[2]
 result=subprocess.run(['node',str(Path(__file__).with_name('finance_upload_dom.js')),str(root/'frontend/finance.js'),case],capture_output=True,text=True)
 assert result.returncode==0,result.stderr
 assert 'PASS '+case in result.stdout


def test_finance_upload_acknowledges_success_without_exposing_unguarded_result(tmp_path):
 from test_finance_browser_state import run
 run(tmp_path,r'''
let accepted=0,posted=false,returned=false;const original=context.api;
context.ack=(...args)=>{if(args.length)throw Error('raw response exposed before identity guard');accepted++};
context.api=async(path,opt)=>{if(path==='/documents/upload'){posted=true;return {document_id:'PRIVATE ORIGINAL',sha256:'PRIVATE HASH'}}if(path==='/auth/me'&&posted)throw Object.assign(new Error('postflight unavailable'),{status:503});return original(path,opt)};
try{await vm.runInContext("financeAPI('/documents/upload',{method:'POST'},ack)",context);returned=true}catch(e){if(e.status!==503)throw e}
if(accepted!==1||returned)throw Error('known POST success must be acknowledged without returning unverified source data');
''')


def test_finance_upload_acknowledgment_does_not_bypass_identity_cleanup(tmp_path):
 from test_finance_browser_state import run
 run(tmp_path,r'''
let accepted=0,posted=false;const original=context.api;
node('financeContent').innerHTML='PRIVATE';context.ack=()=>accepted++;
context.api=async(path,opt)=>{if(path==='/documents/upload'){posted=true;return {document_id:'PRIVATE'}}if(path==='/auth/me')return {user_id:posted?'OTHER USER':'SYNTHETIC'};return original(path,opt)};
let refused=false;try{await vm.runInContext("financeAPI('/documents/upload',{method:'POST'},ack)",context)}catch(e){refused=e.cancelled}
if(!refused||accepted!==1||node('financeContent').innerHTML||vm.runInContext('financeState.identity',context))throw Error('upload acknowledgment bypassed canonical identity cleanup');
''')


def test_finance_failure_diagnostics_never_wait_for_an_unfinished_body(tmp_path,monkeypatch):
 import json
 from test_finance_browser import save_finance_session_diagnostics
 monkeypatch.setenv('FIRE_AI_BROWSER_ARTIFACTS',str(tmp_path/'artifacts'))
 (tmp_path/'server.log').write_text('Synthetic server request log')
 class PendingResponse:
  url='http://synthetic.local/auth/context'
  status=200
  request=object()
  reads=0
  def json(self):
   self.reads+=1
   raise RuntimeError('Synthetic body is still pending')
 class Page:
  def evaluate(self,_):return {'pending':True,'modalCount':1}
  def screenshot(self,**_):pass
 response=PendingResponse()
 save_finance_session_diagnostics(Page(),'http://synthetic.local',tmp_path,'other-editor',None,None,[],[(0,response)],[])
 evidence=json.loads((tmp_path/'artifacts/finance-session-change-other-editor.json').read_text())
 assert response.reads==0
 assert evidence['responses'][0]['body_pending'] is True
 assert evidence['ui']['pending'] is True
 assert (tmp_path/'artifacts/finance-session-change-other-editor-server.log').read_text()=='Synthetic server request log'


def test_finance_failure_diagnostics_persist_before_decoding_finished_bodies(tmp_path,monkeypatch):
 import json
 from test_finance_browser import save_finance_session_diagnostics
 artifact=tmp_path/'artifacts'
 monkeypatch.setenv('FIRE_AI_BROWSER_ARTIFACTS',str(artifact))
 (tmp_path/'server.log').write_text('Synthetic server request log')
 class FinishedResponse:
  url='http://synthetic.local/auth/context'
  status=200
  request=object()
  def json(self):
   assert (artifact/'finance-session-change-other-editor.json').exists()
   assert (artifact/'finance-session-change-other-editor-server.log').exists()
   return {'user_id':'Synthetic user','session_id':'Synthetic nonsecret session','password':'DO NOT RECORD'}
 class Page:
  def evaluate(self,_):return {'pending':True}
  def screenshot(self,**_):pass
 response=FinishedResponse()
 save_finance_session_diagnostics(Page(),'http://synthetic.local',tmp_path,'other-editor',None,None,[],[(0,response)],[],{response.request})
 text=(artifact/'finance-session-change-other-editor.json').read_text()
 assert 'DO NOT RECORD' not in text
 evidence=json.loads(text)
 assert evidence['responses'][0]['authority']['session_id']=='Synthetic nonsecret session'


def test_finance_action_observer_preserves_promise_locks_and_transient_privacy_checks(tmp_path):
 import json
 from test_finance_browser import FINANCE_BROWSER_OBSERVER
 root=Path(__file__).resolve().parents[2]
 script=r'''
const fs=require('fs'),vm=require('vm'),assert=require('node:assert/strict');
const observers=[],controls=[{disabled:false}],nodes={financeMessage:{textContent:''},financeModal:{querySelectorAll:()=>controls,classList:{contains:()=>false}},financeBtn:{disabled:false}};
const context={console,performance,document:{body:{},querySelectorAll:()=>[],querySelector:()=>null,getElementById:id=>nodes[id]},$:id=>nodes[id],FireAISession:{currentGeneration:()=>1},addEventListener(){},MutationObserver:class {constructor(callback){this.callback=callback;observers.push(this)}observe(){}disconnect(){this.disconnected=true}}};
context.window=context;vm.createContext(context);vm.runInContext(fs.readFileSync(process.argv[2],'utf8'),context);
let sourcePromise,rejectAction=false;const original=context.financeAction;context.financeAction=function(...args){sourcePromise=rejectAction?Promise.reject(Error('synthetic unexpected action rejection')):original.apply(this,args);return sourcePromise};
vm.runInContext('('+OBSERVER+')()',context);
(async()=>{let release,ran=0;const watched=context.financeAction(()=>new Promise(resolve=>release=resolve)),operation=sourcePromise;
assert.equal(watched,operation,'observer must preserve original promise identity');assert(controls[0].disabled,'synchronous operation lock must remain');assert.equal(context.syntheticFinanceTrace.actions[0].settled,false);
await context.financeAction(()=>ran++);assert.equal(ran,0);assert.equal(context.syntheticFinanceTrace.actions.length,1);
release();await operation;assert.equal(context.syntheticFinanceTrace.actions[0].settled,true);assert.equal(controls[0].disabled,false);
rejectAction=true;const rejected=context.financeAction(()=>{});assert.equal(rejected,sourcePromise);await assert.rejects(rejected,/synthetic unexpected action rejection/);await new Promise(resolve=>setImmediate(resolve));assert.equal(context.syntheticFinanceTrace.actions.at(-1).error,'synthetic unexpected action rejection');
const token=context.syntheticFinanceStartWatch('#financeForm');const transient={nodeType:1,matches:selector=>selector==='#financeForm',querySelector:()=>null};observers.at(-1).callback([{addedNodes:[transient]}]);
const result=context.syntheticFinanceFinishWatch(token);assert.equal(result.violations.length,1,'even removed-before-callback private nodes must be recorded');assert(observers.at(-1).disconnected);
console.log('observer verified');})().catch(error=>{console.error(error);process.exitCode=1});
'''.replace('OBSERVER',json.dumps(FINANCE_BROWSER_OBSERVER))
 file=tmp_path/'observer.js';file.write_text(script)
 result=subprocess.run(['node',str(file),str(root/'frontend/finance.js')],capture_output=True,text=True,timeout=10)
 assert result.returncode==0,result.stderr
 assert 'observer verified' in result.stdout


def test_finance_fixture_trace_captures_proposal_transport_finish_and_native_timing(tmp_path,monkeypatch):
 import json
 from test_finance_browser import FinanceBrowserTrace
 monkeypatch.setenv('FIRE_AI_BROWSER_ARTIFACTS',str(tmp_path/'artifacts'))
 (tmp_path/'server.log').write_text('Synthetic server trace')
 class Page:
  def __init__(self):self.handlers={}
  def on(self,name,handler):self.handlers[name]=handler
  def evaluate(self,_):return {'pending':True,'actionTrace':{'actions':[{'id':1,'settled':False}]}}
  def screenshot(self,**_):pass
 class Request:
  url='http://synthetic.local/finance/proposals?limit=100'
  method='GET'
  timing={'startTime':1000,'requestStart':0,'responseStart':5010,'responseEnd':5012}
 class Response:
  url=Request.url
  status=503
  def __init__(self,request):self.request=request
 page=Page();trace=FinanceBrowserTrace(page,'http://synthetic.local');request=Request();response=Response(request)
 page.handlers['request'](request);page.handlers['response'](response);page.handlers['requestfinished'](request)
 trace.save(tmp_path,'Synthetic_case')
 evidence=json.loads((tmp_path/'artifacts/finance-case-Synthetic_case.json').read_text())
 record=evidence['requests'][0]
 assert record['path']=='/finance/proposals?limit=100' and record['status']==503
 assert record['at']<=record['response_at']<=record['finished_at']
 assert record['timing']['responseEnd']==5012
 assert evidence['ui']['actionTrace']['actions'][0]['settled'] is False


def test_finance_action_settlement_rejects_observed_unexpected_errors():
 from test_finance_browser import await_finance_action
 class Page:
  def wait_for_function(self,*args,**kwargs):pass
  def evaluate(self,*args):return {'actions':[{'id':1,'settled':True,'error':'Synthetic unexpected rejection'}],'violations':[]}
 with pytest.raises(AssertionError,match='Synthetic unexpected rejection'):
  await_finance_action(Page(),0)
