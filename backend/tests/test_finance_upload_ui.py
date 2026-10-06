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
