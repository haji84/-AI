"""Private report workflow UI contracts; all fixtures are synthetic."""
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import time
import urllib.request

import pytest


BROWSER = pytest.mark.skipif(
    os.environ.get('FIRE_AI_TEST_BROWSER') != '1',
    reason='actual Chromium runs in the dedicated browser CI job',
)
ROOT = Path(__file__).resolve().parents[2]


def run_audit_js(body, before_start=''):
    """Run the real UI and shared-session implementation at the network boundary."""
    module = ROOT / 'frontend/emergency-audit.js'
    html = ROOT / 'frontend/emergency-audit.html'
    assert module.exists() and html.exists(), 'private report workflow is not implemented'
    harness = r"""
const fs=require('fs'),vm=require('vm'),assert=require('node:assert/strict');
const nodes={},allNodes=[],handlers={},windowHandlers={};
function node(tag='div',id='',attrs=''){
 const listeners={},classes=new Set();let ownText='',identity='';
 const e={tagName:tag.toUpperCase(),children:[],dataset:{},style:{},isConnected:true,parentElement:null,
  hidden:/\bhidden\b/.test(attrs),disabled:/\bdisabled\b/.test(attrs),value:attrs.match(/\bvalue="([^"]*)"/)?.[1]??'',files:[],checked:false,multiple:/\bmultiple\b/.test(attrs),src:'',href:'',type:'',selected:false,
  get id(){return identity},set id(v){identity=v;if(v)nodes[v]=this},
  classList:{add(...xs){xs.forEach(x=>classes.add(x))},remove(...xs){xs.forEach(x=>classes.delete(x))},contains(x){return classes.has(x)},toggle(x,on){if(on??!classes.has(x))classes.add(x);else classes.delete(x)}},
  set textContent(v){ownText=String(v??'');this.children=[]},get textContent(){return ownText+this.children.map(c=>typeof c==='string'?c:c.textContent).join('')},
  set innerHTML(v){throw new Error('Unsafe HTML rendering in private UI')},
  append(...items){for(const c of items){this.children.push(c);if(c&&typeof c==='object')c.parentElement=this;}if(this.tagName==='SELECT'&&this.children.length&&!this.value)this.value=this.children[0].value},
  appendChild(item){this.append(item);return item},replaceChildren(...items){ownText='';this.children=[];this.append(...items)},
  setAttribute(k,v){this[k]=String(v)},getAttribute(k){return this[k]},removeAttribute(k){this[k]=''},
  addEventListener(k,f){(listeners[k]??=[]).push(f)},removeEventListener(){},
  get selectedOptions(){return this.children.filter(c=>c.selected||(this.multiple?false:c.value===this.value))},
  querySelectorAll(selector){const found=[];const visit=x=>{for(const c of x.children){if(typeof c!=='object')continue;if(selector==='button'&&c.tagName==='BUTTON')found.push(c);visit(c)}};visit(this);return found},
  closest(){return this},focus(){},scrollIntoView(){},remove(){this.isConnected=false},setPointerCapture(){},releasePointerCapture(){},decode(){return Promise.resolve()},
  getBoundingClientRect(){return {left:0,top:0,width:500,height:700}},
  async fire(k,extra={}){const event={target:this,currentTarget:this,preventDefault(){},stopImmediatePropagation(){},...extra};for(const f of listeners[k]||[])await f(event);return this['on'+k]?.(event)},
  click(){return this.fire('click')},dispatchEvent(event){return this.fire(event.type,event)}
 };e.id=id;allNodes.push(e);return e;
}
const markup=fs.readFileSync(process.argv[2],'utf8');
for(const m of markup.matchAll(/<([a-z][a-z0-9]*)\b([^>]*\bid="([^"]+)"[^>]*)>/g))node(m[1],m[3],m[2]);
for(const m of markup.matchAll(/<select\b[^>]*id="([^"]+)"[^>]*>([\s\S]*?)<\/select>/g)){
 const parent=nodes[m[1]];for(const o of m[2].matchAll(/<option\b([^>]*)>([\s\S]*?)<\/option>/g)){const option=node('option');option.value=o[1].match(/value="([^"]*)"/)?.[1]??o[2];option.textContent=o[2];parent.append(option)}
 if(parent.children.length)parent.value=parent.children[0].value;
}
const document={getElementById:id=>nodes[id],createElement:t=>node(t),createTextNode:t=>String(t),addEventListener(k,f){handlers[k]=f},visibilityState:'visible',querySelectorAll(){return allNodes},body:node('body')};
let authority={user_id:'00000000-0000-4000-8000-000000000010',session_id:'a',tenant_id:null,permissions:['emergency.case.read','emergency.patient.read','emergency.report.read','emergency.report.create','emergency.report.review','emergency.audit.configure','emergency.audit.approve','emergency.audit.read_all']};
const RID='00000000-0000-4000-8000-000000000001',REV='00000000-0000-4000-8000-000000000002',PID='00000000-0000-4000-8000-000000000003',RUN='00000000-0000-4000-8000-000000000004';
const profile={config_id:PID,kind:'profile',label:'合成帳票',form_key:'synthetic-form',status:'draft',version:1,source_id:null,created_by:authority.user_id,created_employee_id:null,approved_by:null,approval_version:null,impact:null,definition:{label:'合成帳票',form_key:'synthetic-form',valid_from:'2026-01-01',valid_to:null,fields:[{field_id:'temperature',label:'合成の数値欄',value_type:'number',page:1,bbox:[.1,.1,.5,.2],extraction:'region',unit:null,phase:null,code_map:{},options:[]}]}};
const finding={rule_id:'synthetic-required',status:'REVIEW_REQUIRED',message:'原本を確認してください。',fields:['temperature'],source_reference:{document_title:'合成資料',version:'1',page:1,section:'1'},rule_approval:'PROVISIONAL_NOT_APPROVED'};
const run={run_id:RUN,revision_id:REV,report_version:1,created_at:'2026-11-21T00:00:00Z',mode:'candidate',approval:'PROVISIONAL_NOT_APPROVED',rule_set_id:null,findings:[finding],counts:{REVIEW_REQUIRED:1,NO_ISSUE_DETECTED:0,NOT_TESTED:0,NOT_APPLICABLE:0},stale:false,changes:{resolved:[],persistent:[],new:['synthetic-required'],untested:[]},decisions:[]};
let detail={report_id:RID,version:1,current_revision_id:REV,revision_number:1,dataset_kind:'synthetic',created_at:'2026-11-21T00:00:00Z',status:'active',job_status:'done',owner:true,reviewer_id:null,submitted_at:null,revisions:[{revision_id:REV,number:1,created_at:'2026-11-21T00:00:00Z'}],revision:{revision_id:REV,number:1,media_type:'application/pdf',page_count:1,profile_id:PID,processing_status:'ready',error_code:null,reading:{pages:[]},fields:{temperature:{label:'合成の数値欄',value_type:'number',state:'unconfirmed',value:null,candidate:36.5,evidence:[{page:1,bbox:[.1,.1,.5,.2],text:'36.5',method:'pdf_text',confidence:null}],issues:[]}},ai_result:null},last_run:null,initial_run:null,events:[],measurement:null};
let reportRows=[detail],requests=[],endpoint,createdUrls=[],revokedUrls=[],createdBlobs=[],timers=[],sources=[],ruleRows=[];
const realURL=URL;class TestURL extends realURL{};TestURL.createObjectURL=blob=>{assert(blob instanceof Blob);const value='blob:synthetic-'+(createdUrls.length+1);createdUrls.push(value);createdBlobs.push(blob);return value};TestURL.revokeObjectURL=url=>revokedUrls.push(url);
const capabilities={enabled:true,storage_ready:true,internal_enabled:false,ocr:{available:true},ai:{configured:false},worker:{status:'running'},limits:{max_file_bytes:26214400,max_pages:50},permissions:authority.permissions};
endpoint=async(path,options={})=>{
 const clean=path.split('?')[0];
 if(clean.endsWith('/capabilities'))return capabilities;
 if(clean.endsWith('/profiles'))return [profile];
 if(clean.endsWith('/rule-sets'))return ruleRows;
 if(clean.endsWith('/reviewers'))return [{user_id:'00000000-0000-4000-8000-000000000011',display_name:'合成確認担当'}];
 if(clean.endsWith('/sources'))return sources;
 if(clean.endsWith('/rule-candidates'))return {total:433,items:[]};
 if(clean.endsWith('/reports')&&!options.method)return reportRows;
 if(clean.endsWith('/reports')&&options.method==='GET')return reportRows;
 if(clean.endsWith('/reports/'+RID)||clean.endsWith('/revisions/'+REV))return detail;
 if(clean.endsWith('.png'))return new Response(new Uint8Array([137,80,78,71]),{headers:{'Content-Type':'image/png'}});
 throw new Error('Unexpected API request '+path+' '+(options.method??'GET'));
};
const window={location:{origin:'http://synthetic.local',pathname:'/ui/emergency-audit.html',replace(){}},addEventListener(k,f){windowHandlers[k]=f},fetch:async(path,options={})=>{
 if(path==='/auth/context')return new Response(JSON.stringify(authority));
 requests.push({path,method:options.method??'GET',body:typeof options.body==='string'?JSON.parse(options.body):options.body});
 const result=await endpoint(path,options);return result instanceof Response?result:new Response(JSON.stringify(result));}};
const context={window,document,fetch:(...args)=>window.fetch(...args),URL:TestURL,URLSearchParams,Response,Blob,FormData,AbortController,WeakSet,Event,MouseEvent:Event,structuredClone,crypto:require('node:crypto').webcrypto,console,performance,setTimeout:(f,t)=>{timers.push({callback:f,delay:t});const timer=setTimeout(f,t);timer.unref();return timer},clearTimeout,setInterval:(f,t)=>{const timer=setInterval(f,t);timer.unref();return timer},clearInterval};
vm.createContext(context);vm.runInContext(fs.readFileSync(process.argv[3],'utf8'),context);vm.runInContext(fs.readFileSync(process.argv[1],'utf8'),context);
const flush=()=>new Promise(r=>setImmediate(r));async function settled(){for(let i=0;i<16;i++)await flush()}
async function invoke(id,event='click',extra={}){assert(nodes[id],id+' exists');await nodes[id].fire(event,extra);await settled()}
async function selectReport(){await settled();assert.equal(nodes.reportList.children.length,1);await nodes.reportList.children[0].fire('click');await settled()}
async function main(){await settled();
"""
    harness = harness.replace('vm.createContext(context);', before_start + '\nvm.createContext(context);')
    script = harness + body + '\n}\nmain().catch(e=>{console.error(e);process.exitCode=1});'
    completed = subprocess.run(
        ['node', '-e', script, str(module), str(html), str(ROOT / 'frontend/shared-session.js')],
        capture_output=True, text=True, timeout=25,
    )
    assert completed.returncode == 0, completed.stderr


def test_audit_confirmed_blank_never_reuses_ocr_candidate():
    run_audit_js(r"""
await selectReport();assert.equal(nodes.reportWorkspace.hidden,false);assert.equal(nodes.sourceImage.hidden,false);
assert.equal(nodes.saveFields.disabled,true);
nodes['field-state-temperature'].value='confirmed';await invoke('field-state-temperature','change');
nodes['field-blank-temperature'].checked=true;await invoke('field-blank-temperature','change');
nodes.confirmOriginal.checked=true;await invoke('confirmOriginal','change');
let payload;const regular=endpoint;
endpoint=(path,options)=>{if(path.endsWith('/fields')){payload=JSON.parse(options.body);detail=structuredClone(detail);detail.version=2;detail.revision.fields.temperature.state='confirmed';detail.revision.fields.temperature.value=null;return detail}return regular(path,options)};
await invoke('saveFields');
assert.equal(payload.confirmed_from_original,true);assert.equal(payload.expected_version,1);
assert.deepEqual(payload.fields,[{field_id:'temperature',state:'confirmed',value:null}]);
assert.equal(nodes.confirmOriginal.checked,false);assert.equal(nodes.saveFields.disabled,true);
assert(!requests.some(r=>r.path.endsWith('/checks')));assert(!requests.some(r=>r.body?.kind==='submitted'));
""")


def test_audit_session_reset_removes_private_content_and_revokes_images():
    run_audit_js(r"""
await selectReport();assert(createdUrls.length>0);const old=[...createdUrls];
nodes.revisionFile.value='private-file.pdf';nodes.profileName.value='DO_NOT_KEEP_PRIVATE_VALUE';
window.FireAISession.invalidate();await settled();
assert.equal(nodes.reportWorkspace.hidden,true);assert.equal(nodes.sourceImage.src,'');assert.equal(nodes.mappingImage.src,'');
assert.equal(nodes.fieldList.children.length,0);assert.equal(nodes.reportList.children.length,0);
assert.equal(nodes.revisionFile.value,'');assert.equal(nodes.profileName.value,'');assert.equal(nodes.startUpload.disabled,true);
assert(old.every(url=>revokedUrls.includes(url)));
""")


def test_audit_forbidden_response_is_not_reflected_or_kept_on_screen():
    run_audit_js(r"""
await selectReport();const regular=endpoint;endpoint=(path,options)=>path.endsWith('/reports/'+RID)?new Response('{"detail":"DO_NOT_ECHO_PRIVATE_VALUE"}',{status:403}):regular(path,options);
await invoke('refreshReport');
assert.equal(nodes.reportWorkspace.hidden,true);assert.equal(nodes.startUpload.disabled,true);assert.equal(nodes.sourceImage.src,'');
assert(!allNodes.some(n=>n.textContent.includes('DO_NOT_ECHO_PRIVATE_VALUE')));
""")


def test_audit_uploads_one_at_a_time_and_network_retry_keeps_identity():
    run_audit_js(r"""
const first=Object.assign(new Blob(['%PDF-synthetic-one'],{type:'application/pdf'}),{name:'synthetic-one.pdf'});
const second=Object.assign(new Blob(['%PDF-synthetic-two'],{type:'application/pdf'}),{name:'synthetic-two.pdf'});
nodes.uploadFiles.files=[first,second];await invoke('uploadFiles','change');
let active=0,maxActive=0,uploads=[];const regular=endpoint;
endpoint=async(path,options)=>{if(path==='/emergency/audit/reports'&&options.method==='POST'){
 active++;maxActive=Math.max(maxActive,active);const requestId=options.body.get('request_id');uploads.push(requestId);await flush();active--;
 if(uploads.length===1)throw new Error('connection lost');return detail;
}return regular(path,options)};
await invoke('startUpload');assert.equal(maxActive,1);assert.equal(uploads.length,2);
await invoke('retry-upload-0');assert.equal(uploads.length,3);assert.equal(uploads[0],uploads[2]);assert.notEqual(uploads[0],uploads[1]);
assert.equal(requests.filter(r=>r.method==='POST'&&r.path.endsWith('/reports')).every(r=>r.body.get('dataset_kind')==='synthetic'),true);
nodes.uploadFiles.files=[{name:'too-large.pdf',size:26214401,type:'application/pdf'}];await invoke('uploadFiles','change');await invoke('startUpload');
assert.equal(uploads.length,3);assert.equal(nodes.uploadFiles.value,'');assert.equal(nodes.startUpload.disabled,true);
""")


def test_audit_late_source_preview_does_not_restore_cleared_selection():
    run_audit_js(r"""
let release;const regular=endpoint;endpoint=(path,options)=>path.endsWith('.png')?new Promise(resolve=>release=resolve):regular(path,options);
const pending=nodes.reportList.children[0].fire('click');await settled();assert.equal(typeof release,'function');
window.FireAISession.invalidate();release(new Response(new Uint8Array([137,80,78,71]),{headers:{'Content-Type':'image/png'}}));
await pending;await settled();assert.equal(nodes.reportWorkspace.hidden,true);assert.equal(nodes.sourceImage.src,'');assert.equal(createdUrls.length,0);
""")


def test_audit_rule_builder_uses_numeric_expressions_and_draft_save_only():
    run_audit_js(r"""
assert.equal(nodes.profileList.children.length,1);await nodes.profileList.children[0].fire('click');await settled();
nodes.ruleSetLabel.value='合成ルール';nodes.ruleCode.value='synthetic-range';nodes.ruleTitle.value='合成の範囲確認';nodes.ruleField.value='temperature';nodes.ruleOperator.value='range';await invoke('ruleOperator','change');
nodes.ruleMinimum.value='35';nodes.ruleMaximum.value='40';nodes.ruleSourceTitle.value='合成資料';nodes.ruleSourceVersion.value='1';nodes.ruleSourcePage.value='2';nodes.ruleEvidence.value='例示';
let saved;const regular=endpoint;endpoint=(path,options)=>{if(path.endsWith('/rule-sets')&&options.method==='POST'){saved=JSON.parse(options.body);return {config_id:'00000000-0000-4000-8000-000000000099',kind:'rules',label:saved.definition.label,form_key:'synthetic-form',status:'draft',version:1,definition:saved.definition,source_id:null,created_by:authority.user_id}}return regular(path,options)};
await invoke('saveRule');assert(saved);assert.deepEqual(saved.definition.rules[0].assertion,{kind:'all',expressions:[{kind:'field',field:'temperature',operator:'ge',value:35},{kind:'field',field:'temperature',operator:'le',value:40}]});
assert.equal(saved.definition.rules[0].source.page,'2');assert(!requests.some(r=>r.path.endsWith('/approve')));
nodes.reviewConfiguration.value=PID;await invoke('reviewConfiguration','change');assert(nodes.configurationDefinition);assert.deepEqual(JSON.parse(nodes.configurationDefinition.textContent),profile.definition);
""")


def test_audit_switching_form_does_not_carry_previous_rule_set():
    run_audit_js(r"""
await nodes.profileList.children[0].fire('click');await settled();
const other={...profile,config_id:'00000000-0000-4000-8000-000000000099',form_key:'other-form',definition:{...profile.definition,form_key:'other-form'}};
let saved=[];const regular=endpoint;
endpoint=(path,options)=>{
 if(path.endsWith('/profiles'))return [profile,other];
 if(path.endsWith('/rule-sets')&&options.method==='POST'){
  const body=JSON.parse(options.body);saved.push(body);
  return {config_id:'00000000-0000-4000-8000-000000000077',kind:'rules',status:'draft',label:body.definition.label,form_key:body.definition.form_key,definition:body.definition};
 }return regular(path,options);
};
nodes.ruleSetLabel.value='First set';nodes.ruleCode.value='first-rule';nodes.ruleTitle.value='First rule';nodes.ruleField.value='temperature';
nodes.ruleSourceTitle.value='Synthetic reference';nodes.ruleSourceVersion.value='1';nodes.ruleSourcePage.value='1';
await invoke('saveRule');assert.equal(saved.length,1);
await nodes.profileList.children[1].fire('click');await settled();
nodes.ruleSetLabel.value='Second set';nodes.ruleCode.value='second-rule';nodes.ruleTitle.value='Second rule';nodes.ruleField.value='temperature';
await invoke('saveRule');assert.equal(saved.length,2);
assert.equal(saved[1].definition.form_key,'other-form');assert.equal(saved[1].supersedes_id,null);
assert.deepEqual(saved[1].definition.rules.map(rule=>rule.rule_id),['second-rule']);
""")


def test_audit_old_poll_cannot_replace_a_newer_saved_report():
    run_audit_js(r"""
detail=structuredClone(detail);detail.job_status='queued';detail.revision.processing_status='processing';
await selectReport();const previous=structuredClone(detail);let release;const regular=endpoint;
endpoint=(path,options)=>{
 if(path.endsWith('/reports/'+RID))return new Promise(resolve=>release=resolve);
 if(path.endsWith('/events')){detail=structuredClone(detail);detail.version=2;detail.job_status='done';detail.revision.processing_status='ready';detail.revision.fields.temperature.state='confirmed';detail.revision.fields.temperature.value=36.5;return detail}
 return regular(path,options);
};
const poll=timers.find(timer=>timer.delay===1500);assert(poll);const pending=poll.callback();await settled();assert.equal(typeof release,'function');
await invoke('recordStudy');assert.equal(nodes.jobPanel.hidden,true);assert.equal(nodes['field-state-temperature'].value,'confirmed');
release(previous);await pending;await settled();
assert.equal(nodes.jobPanel.hidden,true);assert.equal(nodes['field-state-temperature'].value,'confirmed');
""")


@pytest.mark.parametrize('preview_status', [200, 422])
def test_audit_polled_revision_requires_its_own_original_before_confirmation(preview_status):
    run_audit_js(r"""
detail=structuredClone(detail);detail.job_status='queued';detail.revision.processing_status='processing';detail.revision.page_count=2;
await selectReport();await invoke('nextPage');const oldImage=nodes.sourceImage.src;assert(oldImage);
const newRev='00000000-0000-4000-8000-000000000099';let release,saved;const regular=endpoint;
endpoint=(path,options)=>{
 if(path.includes('/revisions/'+newRev+'/pages/'))return new Promise(resolve=>release=resolve);
 if(path.endsWith('/fields')){saved={path,body:JSON.parse(options.body)};return detail}
 return regular(path,options);
};
detail=structuredClone(detail);detail.version=3;detail.current_revision_id=newRev;detail.revision_number=2;detail.revision.revision_id=newRev;detail.revision.number=2;detail.revision.page_count=1;detail.job_status='done';detail.revision.processing_status='ready';detail.revision.fields.temperature.candidate=99;
const poll=timers.find(timer=>timer.delay===1500);assert(poll);const pending=poll.callback();await settled();
assert(nodes.reportHeading.textContent.includes('2'));assert.equal(nodes['field-value-temperature'].value,'99');
assert.equal(nodes.sourceImage.src,'');assert.equal(nodes.sourceImage.hidden,true);assert(revokedUrls.includes(oldImage));
assert.equal(typeof release,'function');assert.equal(nodes.previousPage.disabled,true);assert.equal(nodes.nextPage.disabled,true);assert.match(nodes.pageLabel.textContent,/1 \/ 1/);
assert.equal(nodes['field-state-temperature'].disabled,true);assert.equal(nodes.confirmOriginal.disabled,true);
nodes['field-state-temperature'].value='confirmed';nodes['field-value-temperature'].value='36.5';await invoke('field-state-temperature','change');nodes.confirmOriginal.checked=true;await invoke('confirmOriginal','change');await invoke('saveFields');assert.equal(saved,undefined);
release(previewStatus===200?new Response(new Uint8Array([137,80,78,71]),{headers:{'Content-Type':'image/png'}}):new Response('{}',{status:422}));
await pending;await settled();
if(previewStatus===200){
 assert.equal(nodes.sourceImage.hidden,false);assert.notEqual(nodes.sourceImage.src,oldImage);assert.equal(nodes['field-state-temperature'].disabled,false);
 nodes['field-value-temperature'].value='99';await invoke('field-value-temperature','input');nodes.confirmOriginal.checked=true;await invoke('confirmOriginal','change');await invoke('saveFields');
 assert(saved.path.includes(newRev));assert.equal(saved.body.fields[0].value,99);assert.equal(saved.body.confirmed_from_original,true);
}else{
 assert.equal(nodes.sourceImage.hidden,true);assert.equal(nodes['field-state-temperature'].disabled,true);assert.equal(nodes.confirmOriginal.disabled,true);
 await invoke('saveFields');assert.equal(saved,undefined);
}
""", before_start=f'const previewStatus={preview_status};')


def test_audit_old_page_response_cannot_return_after_polled_revision_switch():
    run_audit_js(r"""
detail=structuredClone(detail);detail.job_status='queued';detail.revision.processing_status='processing';detail.revision.page_count=2;await selectReport();
const next='00000000-0000-4000-8000-000000000099';let oldRelease,newRelease;const regular=endpoint;
endpoint=(path,options)=>{
 if(path.endsWith('/revisions/'+REV+'/pages/2.png'))return new Promise(resolve=>oldRelease=resolve);
 if(path.endsWith('/revisions/'+next+'/pages/1.png'))return new Promise(resolve=>newRelease=resolve);
 return regular(path,options);
};
const oldPending=nodes.nextPage.fire('click');await settled();assert.equal(typeof oldRelease,'function');
detail=structuredClone(detail);detail.version=3;detail.current_revision_id=next;detail.revision_number=2;detail.revision.revision_id=next;detail.revision.number=2;detail.revision.page_count=1;detail.job_status='done';detail.revision.processing_status='ready';
const pending=timers.find(timer=>timer.delay===1500).callback();await settled();assert.equal(typeof newRelease,'function');
newRelease(new Response(new Uint8Array([137,80,78,71,2]),{headers:{'Content-Type':'image/png'}}));await pending;await settled();const latest=nodes.sourceImage.src;assert(latest);const created=createdUrls.length;
oldRelease(new Response(new Uint8Array([137,80,78,71,1]),{headers:{'Content-Type':'image/png'}}));await oldPending;await settled();
assert.equal(nodes.sourceImage.src,latest);assert.equal(createdUrls.length,created);assert.match(nodes.pageLabel.textContent,/1 \/ 1/);
""")


def test_audit_mapping_edit_loads_its_source_page_before_region_can_be_saved():
    run_audit_js(r"""
await nodes.profileList.children[0].fire('click');await settled();const first=nodes.mappingImage.src;assert(first);
let release;const regular=endpoint;endpoint=(path,options)=>path.endsWith('/sources/'+profile.source_id+'/pages/2.png')?new Promise(resolve=>release=resolve):regular(path,options);
const pending=nodes.mappedFieldList.children[0].children[1].children[0].fire('click');await settled();
assert.equal(nodes.mappedFieldPage.value,'2');assert.equal(nodes.mappingImage.src,'');assert.equal(nodes.mappingImage.hidden,true);assert.equal(typeof release,'function');assert.equal(nodes.saveMappedField.disabled,true);
nodes.mappedFieldLabel.value='Must not save while page is pending';await invoke('saveMappedField');assert(!nodes.mappedFieldList.textContent.includes('Must not save'));
release(new Response(new Uint8Array([137,80,78,71]),{headers:{'Content-Type':'image/png'}}));await pending;await settled();
assert.equal(nodes.mappingImage.hidden,false);assert.notEqual(nodes.mappingImage.src,first);assert.equal(nodes.saveMappedField.disabled,false);
nodes.mappedFieldLabel.value='Synthetic field after page check';await invoke('saveMappedField');assert(nodes.mappedFieldList.textContent.includes('Synthetic field after page check'));
assert.equal(nodes.mappedFieldPage.value,'2');await invoke('addMappedField');assert.equal(nodes.mappedFieldPage.value,'2');
""", before_start=r"""
profile.source_id='00000000-0000-4000-8000-000000000066';profile.definition.fields[0].page=2;
sources=[{source_id:profile.source_id,sha256:'b'.repeat(64),media_type:'application/pdf',page_count:2,created_at:'2026-01-01T00:00:00Z'}];
""")


def test_audit_mapping_manual_page_change_discards_late_preview_and_blocks_failed_page():
    run_audit_js(r"""
await nodes.profileList.children[0].fire('click');await settled();const first=nodes.mappingImage.src;assert(first);
nodes.mappedFieldId.value='new-field';nodes.mappedFieldLabel.value='Synthetic field';
for(const [id,value] of [['regionX0','0'],['regionY0','0'],['regionX1','1'],['regionY1','1']])nodes[id].value=value;
let pageTwo,pageThree;const regular=endpoint;endpoint=(path,options)=>path.endsWith('/pages/2.png')?new Promise(resolve=>pageTwo=resolve):path.endsWith('/pages/3.png')?new Promise(resolve=>pageThree=resolve):regular(path,options);
nodes.mappedFieldPage.value='2';const second=nodes.mappedFieldPage.fire('change');await settled();assert.equal(nodes.mappingImage.src,'');assert.equal(nodes.saveMappedField.disabled,true);
nodes.mappedFieldPage.value='3';const third=nodes.mappedFieldPage.fire('change');await settled();
pageTwo(new Response(new Uint8Array([137,80,78,71]),{headers:{'Content-Type':'image/png'}}));await second;await settled();assert.equal(nodes.mappingImage.src,'');
pageThree(new Response('{}',{status:422}));await third;await settled();assert.equal(nodes.mappingImage.hidden,true);assert.equal(nodes.saveMappedField.disabled,true);
await invoke('saveMappedField');assert.equal(nodes.mappedFieldList.children.length,1);
await invoke('mappingImage','pointerdown',{clientX:10,clientY:10,pointerId:1});await invoke('mappingImage','pointerup',{clientX:100,clientY:100,pointerId:1});assert.equal(nodes.regionX0.value,'0');
""", before_start=r"""
profile.source_id='00000000-0000-4000-8000-000000000066';sources=[{source_id:profile.source_id,sha256:'b'.repeat(64),media_type:'application/pdf',page_count:3,created_at:'2026-01-01T00:00:00Z'}];
""")


def test_audit_changed_upload_options_apply_before_first_attempt_and_freeze_on_retry():
    run_audit_js(r"""
const file=Object.assign(new Blob(['%PDF-synthetic'],{type:'application/pdf'}),{name:'synthetic.pdf'});
nodes.uploadFiles.files=[file];await invoke('uploadFiles','change');
nodes.profileSelect.value=PID;await invoke('profileSelect','change');
let uploads=[];const regular=endpoint;endpoint=(path,options)=>{
 if(path.endsWith('/reports')&&options.method==='POST'){uploads.push({id:options.body.get('request_id'),profile:options.body.get('profile_id')});if(uploads.length===1)throw new Error('lost response');return detail}
 return regular(path,options);
};
await invoke('startUpload');assert.equal(uploads[0].profile,PID);
nodes.profileSelect.value='';await invoke('profileSelect','change');await invoke('retry-upload-0');
assert.deepEqual(uploads[1],uploads[0]);
""")


def test_audit_existing_manual_is_reused_with_its_saved_hash():
    run_audit_js(r"""
const sourceId='00000000-0000-4000-8000-000000000066',hash='b'.repeat(64);
sources=[{source_id:sourceId,sha256:hash,media_type:'application/pdf',page_count:3,created_at:'2026-01-01T00:00:00Z'}];
profile.source_id=sourceId;await nodes.profileList.children[0].fire('click');await settled();
let ruleBody;const regular=endpoint;endpoint=(path,options)=>{
 if(path.endsWith('/profiles')&&options.method==='POST')return profile;
 if(path.endsWith('/rule-sets')&&options.method==='POST'){ruleBody=JSON.parse(options.body);return {config_id:'00000000-0000-4000-8000-000000000077',kind:'rules',status:'draft',label:ruleBody.definition.label,form_key:ruleBody.definition.form_key,definition:ruleBody.definition}}
 return regular(path,options);
};
nodes.profileName.value='Retained source';await invoke('profileName','input');await invoke('saveProfile');
assert(nodes.sourceSelect);assert.equal(nodes.sourceSelect.value,sourceId);
nodes.ruleSetLabel.value='Retained source rule';nodes.ruleCode.value='retained-rule';nodes.ruleTitle.value='Synthetic required';nodes.ruleField.value='temperature';
nodes.ruleSourceTitle.value='Synthetic saved reference';nodes.ruleSourceVersion.value='1';nodes.ruleSourcePage.value='1';
await invoke('saveRule');assert.equal(ruleBody.source_id,sourceId);assert.equal(ruleBody.definition.rules[0].source.sha256,hash);
assert(!requests.some(request=>request.path.endsWith('/sources')&&request.method==='POST'));
""")


def test_audit_datetime_confirmation_preserves_an_explicit_timezone():
    run_audit_js(r"""
detail=structuredClone(detail);detail.revision.fields.temperature={...detail.revision.fields.temperature,value_type:'datetime',candidate:'2026-01-01T09:15:00+09:00'};
await selectReport();assert.equal(nodes['field-value-temperature'].type,'text');assert.equal(nodes['field-value-temperature'].value,'2026-01-01T09:15:00+09:00');
let payload;const regular=endpoint;endpoint=(path,options)=>path.endsWith('/fields')?(payload=JSON.parse(options.body),{...detail,version:2}):regular(path,options);
nodes['field-state-temperature'].value='confirmed';await invoke('field-state-temperature','change');nodes.confirmOriginal.checked=true;await invoke('confirmOriginal','change');await invoke('saveFields');
assert.equal(payload.fields[0].value,'2026-01-01T09:15:00+09:00');
""")


def test_audit_partial_mapping_coordinates_are_not_assumed_to_be_zero():
    run_audit_js(r"""
await invoke('newProfile');nodes.mappedFieldId.value='mapped';nodes.mappedFieldLabel.value='Synthetic field';
nodes.regionX0.value='';nodes.regionY0.value='0';nodes.regionX1.value='1';nodes.regionY1.value='1';await invoke('saveMappedField');
assert.equal(nodes.mappedFieldList.children.length,0);assert(nodes.mappingMessage.textContent.length>0);
""")


def test_audit_disposition_reason_is_explicit_and_does_not_overwrite_other_rows():
    run_audit_js(r"""
detail=structuredClone(detail);detail.last_run={...run,decisions:{'unrelated':'false_alarm'},decision_reasons:{'unrelated':'reading_error'}};await selectReport();
assert(nodes['decision-reason-synthetic-required']);assert.equal(nodes['decision-reason-synthetic-required'].value,'unknown');
nodes['decision-choice-synthetic-required'].value='correction_needed';nodes['decision-reason-synthetic-required'].value='missing';
let recorded;const regular=endpoint;endpoint=(path,options)=>path.endsWith('/decisions')?(recorded=JSON.parse(options.body),{...detail,version:2}):regular(path,options);
await invoke('decision-save-synthetic-required');
assert.deepEqual(recorded.decisions,[{rule_id:'synthetic-required',decision:'correction_needed',reason_code:'missing'}]);
""")


def test_audit_pattern_summary_is_scoped_read_only_and_keeps_independent_truth_separate():
    run_audit_js(r"""
await selectReport();let payload;const regular=endpoint;
endpoint=(path,options)=>path.endsWith('/correction-patterns')?(payload=JSON.parse(options.body),{
 report_count:1,run_count:3,unreviewed_run_count:2,automatic_rule_updates:false,model_training_performed:false,
 items:[{rule_id:'synthetic-required',rule_set_id:null,label:'<img src=x onerror=alert(1)>',warning_count:2,report_count:1,decision_counts:{correction_needed:1,false_alarm:1},reason_counts:{missing:1,reading_error:1},verified_error_count:1,unresolved_truth_count:1}]
}):regular(path,options);
assert(nodes.patternScope);nodes.patternScope.value='selected';await invoke('loadPatterns');
assert.deepEqual(payload.report_ids,[RID]);assert.match(nodes.patternSummary.textContent,/未確認.*2/);
assert.match(nodes.patternTable.textContent,/別担当者が確認した誤り/);assert.match(nodes.patternTable.textContent,/担当者の判断/);
assert.match(nodes.patternTable.textContent,/誤警告だった/);assert.match(nodes.patternTable.textContent,/記載漏れ/);
assert.equal(requests.filter(request=>request.method==='POST').length,1);
window.FireAISession.invalidate();await settled();assert.equal(nodes.patternTable.children.length,0);assert.equal(nodes.patternSummary.textContent,'');
""")


def test_audit_assigned_review_only_user_can_record_review_time_and_dispositions():
    run_audit_js(r"""
await selectReport();assert.equal(nodes.revisionFile.disabled,true);assert.equal(nodes['field-state-temperature'].disabled,true);
assert.equal(nodes.recordStudy.disabled,true);assert.equal(nodes.recordSubmission.disabled,true);assert.equal(nodes.startWork.disabled,false);assert.equal(nodes.recordWork.disabled,false);
assert.equal(nodes['decision-choice-synthetic-required'].disabled,false);
let posts=[];const regular=endpoint;endpoint=(path,options)=>{
 if(path.endsWith('/events')||path.endsWith('/decisions')){posts.push(JSON.parse(options.body));detail={...detail,version:detail.version+1};return detail}
 return regular(path,options);
};
nodes.workStartedAt.value='2026-01-01T10:00';nodes.workEndedAt.value='2026-01-01T10:10';nodes.workStage.value='second_review';await invoke('recordWork');
nodes['decision-choice-synthetic-required'].value='false_alarm';nodes['decision-reason-synthetic-required'].value='reading_error';await invoke('decision-save-synthetic-required');
assert.equal(posts.length,2);assert.equal(posts[0].kind,'work_interval');assert.equal(posts[0].payload.stage,'second_review');assert.equal(posts[1].decisions[0].decision,'false_alarm');
assert.equal(nodes.uploadFiles.disabled,true);assert.equal(nodes.runCheck.disabled,true);
""", before_start=r"""
authority.permissions=authority.permissions.filter(code=>!['emergency.report.create','emergency.audit.configure','emergency.audit.approve','emergency.audit.read_all'].includes(code));
detail.owner=false;detail.reviewer_id=authority.user_id;detail.last_run=run;
""")


def test_audit_review_only_profile_view_does_not_request_restricted_manual():
    run_audit_js(r"""
await selectReport();const regular=endpoint;endpoint=(path,options)=>path.includes('/sources/')?new Response('{}',{status:403}):regular(path,options);
await nodes.profileList.children[0].fire('click');await settled();
assert(!requests.some(request=>request.path.includes('/sources/')));assert.equal(nodes.reportWorkspace.hidden,false);
assert.equal(nodes.startWork.disabled,false);assert.equal(nodes.sourceSelect.disabled,true);
""", before_start=r"""
authority.permissions=authority.permissions.filter(code=>!['emergency.report.create','emergency.audit.configure','emergency.audit.approve','emergency.audit.read_all'].includes(code));
detail.owner=false;detail.reviewer_id=authority.user_id;profile.source_id='00000000-0000-4000-8000-000000000066';
""")


def test_audit_approval_renders_conditions_exceptions_sources_and_period_in_japanese():
    run_audit_js(r"""
nodes.reviewConfiguration.value=ruleRows[0].config_id;await invoke('reviewConfiguration','change');
assert(nodes.configurationHuman);const text=nodes.configurationHuman.textContent;
for(const expected of ['すべて','いずれか','該当しない','空欄','記入あり','適用条件','例外条件','確認する条件','合成の数値欄','35','以上','40','以下','Synthetic source','2026-01-01','2026-12-31'])assert(text.includes(expected),expected);
assert.deepEqual(JSON.parse(nodes.configurationDefinition.textContent),ruleRows[0].definition);
assert(!requests.some(request=>request.path.endsWith('/approve')));
window.FireAISession.invalidate();await settled();assert.equal(nodes.configurationHuman.children.length,0);assert.equal(nodes.configurationDefinition.textContent,'');
""", before_start=r"""
ruleRows=[{config_id:'00000000-0000-4000-8000-000000000077',kind:'rules',status:'draft',label:'Synthetic range',form_key:'synthetic-form',definition:{
 label:'Synthetic range',form_key:'synthetic-form',valid_from:'2026-01-01',valid_to:'2026-12-31',rules:[{rule_id:'synthetic-range',label:'数値欄の確認',message:'Synthetic test',severity:'review',source:{document_title:'Synthetic source',version:'1',page:'3',section:'Example'},
 applies_when:{kind:'any',expressions:[{kind:'field',field:'temperature',operator:'not_blank'},{kind:'field',field:'temperature',operator:'eq',value:36}]},
 exceptions:[{kind:'not',expression:{kind:'field',field:'temperature',operator:'blank'}}],
 assertion:{kind:'all',expressions:[{kind:'field',field:'temperature',operator:'ge',value:35},{kind:'field',field:'temperature',operator:'le',value:40}]}
 }]}}];
""")


def test_audit_work_events_require_explicit_interval_and_submission_action():
    run_audit_js(r"""
await selectReport();let events=[];const regular=endpoint;
endpoint=(path,options)=>{if(path.endsWith('/events')){const body=JSON.parse(options.body);events.push(body);detail=structuredClone(detail);detail.version++;if(body.kind==='submitted')detail.submitted_at=body.payload.occurred_at;return detail}return regular(path,options)};
assert(!requests.some(r=>r.body?.kind==='submitted'));
nodes.workStartedAt.value='2026-01-01T09:00';nodes.workEndedAt.value='2026-01-01T09:12';nodes.workStage.value='correction';await invoke('recordWork');
assert.equal(events.length,1);assert.equal(events[0].kind,'work_interval');assert.equal(events[0].payload.stage,'correction');
assert.equal(new Date(events[0].payload.ended_at)-new Date(events[0].payload.started_at),720000);
nodes.submittedAt.value='2026-01-01T09:20';await invoke('recordSubmission');assert.equal(events.length,1);
nodes.submissionConfirmed.checked=true;await invoke('submissionConfirmed','change');await invoke('recordSubmission');
assert.equal(events.length,2);assert.equal(events[1].kind,'submitted');assert.equal(typeof events[1].payload.occurred_at,'string');
""")


def test_audit_independent_truth_requires_whole_report_and_keeps_initial_run():
    run_audit_js(r"""
detail=structuredClone(detail);detail.owner=false;detail.reviewer_id=authority.user_id;detail.initial_run={...run,rule_read_states:{'synthetic-required':'unconfirmed'}};
detail.last_run={...run,run_id:'00000000-0000-4000-8000-000000000044'};await selectReport();await invoke('loadTruthReview');
let recorded;const regular=endpoint;endpoint=(path,options)=>{if(path.endsWith('/events')){recorded=JSON.parse(options.body);return {...detail,version:2}}return regular(path,options)};
nodes['truth-synthetic-required'].value='error';nodes['truth-read-synthetic-required'].value='confirmed';nodes.truthReviewComplete.checked=true;
await invoke('saveTruthReview');assert.equal(recorded,undefined);
nodes.wholeReportChecked.checked=true;await invoke('saveTruthReview');
assert.equal(recorded.kind,'truth_review');assert.equal(recorded.payload.run_id,RUN);assert.equal(recorded.payload.complete,true);assert.equal(recorded.payload.whole_report_checked,true);
assert.equal(recorded.payload.items[0].truth,'error');assert.match(recorded.payload.items[0].error_id,/^[0-9a-f-]{36}$/);
assert.deepEqual(recorded.payload.items[0].detected_in_run_ids,[]);assert.deepEqual(recorded.payload.missed_errors,[]);
""")


def test_audit_measurement_export_preserves_unknowns_and_has_no_source_values():
    run_audit_js(r"""
const expected={dataset_kind:'synthetic',comparison_confirmed:false,held_out_confirmed:false,followup_days:null,targets:{},reports:[]};
const regular=endpoint;endpoint=(path,options)=>path.endsWith('/measurement-export')?expected:regular(path,options);
nodes.measurementExportReports.children[0].selected=true;await invoke('exportMeasurements');
assert.equal(createdBlobs.length,1);assert.deepEqual(JSON.parse(await createdBlobs[0].text()),expected);
assert.equal(requests.filter(r=>r.path.endsWith('/measurement-export'))[0].body.report_ids[0],RID);
assert(!requests.some(r=>r.body?.kind==='followup'||r.body?.kind==='submitted'||r.body?.kind==='truth_review'));
""")


def test_audit_large_batch_selection_is_bounded_without_parallel_upload():
    run_audit_js(r"""
const file=Object.assign(new Blob(['%PDF-synthetic'],{type:'application/pdf'}),{name:'synthetic.pdf'});
nodes.uploadFiles.files=Array.from({length:900},()=>file);await invoke('uploadFiles','change');
assert.equal(nodes.startUpload.disabled,false);assert.match(nodes.uploadSummary.textContent,/900/);assert(nodes.uploadQueue.children.length<=60);
assert(!requests.some(r=>r.method==='POST'));
nodes.uploadFiles.files=Array.from({length:1001},()=>file);await invoke('uploadFiles','change');
assert.equal(nodes.startUpload.disabled,true);assert.equal(nodes.uploadQueue.children.length,0);
""")


def test_audit_later_run_truth_reuses_only_explicitly_selected_error():
    run_audit_js(r"""
const later='00000000-0000-4000-8000-000000000044',error='00000000-0000-4000-8000-000000000088';
detail=structuredClone(detail);detail.owner=false;detail.reviewer_id=authority.user_id;detail.initial_run=run;detail.last_run={...run,run_id:later};
detail.runs=[{run_id:RUN,revision_id:REV,created_at:run.created_at,mode:'candidate'},{run_id:later,revision_id:REV,created_at:run.created_at,mode:'candidate'}];
detail.events=[{kind:'truth_review',payload:{run_id:RUN,items:[{rule_id:'synthetic-required',truth:'error',error_id:error,verified_read_state:'confirmed'}],missed_errors:[]},created_at:run.created_at}];
let recorded;const regular=endpoint;endpoint=(path,options)=>path.endsWith('/runs/'+later)?detail.last_run:path.endsWith('/events')?(recorded=JSON.parse(options.body),{...detail,version:2}):regular(path,options);
await selectReport();nodes.truthRunSelect.value=later;await invoke('loadTruthReview');
assert.equal(nodes['truth-synthetic-required'].value,'unknown');
nodes['truth-synthetic-required'].value='error';nodes['truth-read-synthetic-required'].value='confirmed';nodes['truth-error-synthetic-required'].value=error;
nodes.wholeReportChecked.checked=true;nodes.truthReviewComplete.checked=true;await invoke('saveTruthReview');
assert.equal(recorded.payload.run_id,later);assert.equal(recorded.payload.items[0].error_id,error);
""")


def test_audit_vision_candidates_keep_unconfirmed_state_and_source_regions():
    run_audit_js(r"""
detail=structuredClone(detail);detail.revision.ai_result={mode:'vision',status:'REVIEW_REQUIRED',candidates:[{page:1,bbox:[.2,.3,.4,.5],text:'SYNTHETIC HANDWRITING',kind:'handwritten',state:'unconfirmed'}]};
await selectReport();assert.match(nodes.aiCandidates.textContent,/未確認/);assert.match(nodes.aiCandidates.textContent,/SYNTHETIC HANDWRITING/);
assert.equal(nodes['field-state-temperature'].value,'unconfirmed');assert.equal(nodes.saveFields.disabled,true);
assert(nodes.sourceRegions.children.some(item=>item.className.includes('ai-region')));
""")


def test_audit_work_correction_references_retained_event():
    run_audit_js(r"""
const eventId='00000000-0000-4000-8000-000000000077';
detail=structuredClone(detail);detail.events=[{event_id:eventId,kind:'work_interval',created_at:'2026-01-01T09:12:00Z',can_correct:true,supersedes_event_id:null,payload:{stage:'correction',started_at:'2026-01-01T09:00:00Z',ended_at:'2026-01-01T09:12:00Z'}}];
await selectReport();await invoke('edit-event-'+eventId);nodes.workEndedAt.value='2026-01-01T09:15';
let saved;const regular=endpoint;endpoint=(path,options)=>path.endsWith('/events')?(saved=JSON.parse(options.body),{...detail,version:2}):regular(path,options);
await invoke('recordWork');assert.equal(saved.supersedes_event_id,eventId);assert.equal(saved.kind,'work_interval');
assert.equal(new Date(saved.payload.ended_at)-new Date(saved.payload.started_at),900000);assert.notEqual(saved.event_id,eventId);
""")


def test_audit_whole_report_review_requires_the_matching_original():
    run_audit_js(r"""
const oldRevision='00000000-0000-4000-8000-000000000055';
detail=structuredClone(detail);detail.owner=false;detail.reviewer_id=authority.user_id;detail.initial_run={...run,revision_id:oldRevision};
await selectReport();await invoke('loadTruthReview');assert.equal(nodes.wholeReportChecked.disabled,true);
const regular=endpoint;endpoint=(path,options)=>path.endsWith('/revisions/'+oldRevision)?{...detail,revision:{...detail.revision,revision_id:oldRevision}}:regular(path,options);
await invoke('openTruthSource');assert.equal(nodes.wholeReportChecked.disabled,false);assert.equal(nodes.runCheck.disabled,true);
""")


SEED_BROWSER_DATABASE = r"""
from sqlalchemy import select
from app.main import app
from app.db import Base, SessionLocal, engine
from app.models import Employee, Permission, Role, RolePermission, User, UserRole
from app.security import hash_password
Base.metadata.create_all(engine)
details={'emergency.case.read','emergency.patient.read','emergency.report.read'}
roles={
 'owner':details|{'emergency.report.create','emergency.audit.configure'},
 'reviewer':details|{'emergency.report.create','emergency.report.review','emergency.audit.configure','emergency.audit.approve','emergency.audit.read_all'},
 'denied':{'document.read'},
}
with SessionLocal() as db:
 permissions={code:Permission(code=code) for code in set().union(*roles.values())}
 db.add_all(permissions.values());db.flush()
 for name,codes in roles.items():
  role=Role(code='synthetic-audit-'+name,name='Synthetic '+name)
  employee=Employee(display_name='Synthetic '+name)
  db.add_all([role,employee]);db.flush()
  user=User(username='audit-browser-'+name,employee_id=employee.employee_id,password_hash=hash_password('synthetic-audit-browser-password'))
  db.add(user);db.flush();db.add(UserRole(user_id=user.user_id,role_id=role.role_id))
  db.add_all([RolePermission(role_id=role.role_id,permission_id=permissions[code].permission_id) for code in codes])
 db.commit()
"""


@pytest.fixture
def audit_server(tmp_path):
    """A real API process and durable worker, with an isolated synthetic database."""
    key = tmp_path / 'synthetic-key'
    key.write_bytes(os.urandom(32))
    key.chmod(0o600)
    env = {name: value for name, value in os.environ.items() if not name.startswith('FIRE_AI_')}
    env.update(
        PYTHONPATH=str(ROOT / 'backend'),
        FIRE_AI_DATABASE_URL='sqlite+pysqlite:///' + str(tmp_path / 'synthetic.db'),
        FIRE_AI_STORAGE_ROOT=str(tmp_path / 'storage'), FIRE_AI_PRODUCTION_MODE='false',
        FIRE_AI_EMERGENCY_AUDIT_ENABLED='true', FIRE_AI_EMERGENCY_AUDIT_KEY_FILE=str(key),
        FIRE_AI_EMERGENCY_AUDIT_OCR_LANGUAGE='eng', FIRE_AI_EMERGENCY_AUDIT_WORKER_TIMEOUT='60',
    )
    subprocess.run([sys.executable, '-c', SEED_BROWSER_DATABASE], cwd=ROOT, env=env,
                   capture_output=True, check=True, timeout=30)
    with socket.socket() as allocation:
        allocation.bind(('127.0.0.1', 0))
        port = allocation.getsockname()[1]
    base = f'http://127.0.0.1:{port}'
    with (tmp_path / 'server.log').open('w') as logs:
        server = subprocess.Popen(
            [sys.executable, '-m', 'uvicorn', 'app.main:app', '--host', '127.0.0.1', '--port', str(port)],
            cwd=ROOT, env=env, stdout=logs, stderr=logs,
        )
        worker = None
        try:
            for _ in range(100):
                try:
                    urllib.request.urlopen(base + '/health', timeout=.2).close()
                    break
                except OSError:
                    if server.poll() is not None:
                        raise AssertionError('synthetic audit API stopped')
                    time.sleep(.1)
            else:
                raise AssertionError('synthetic audit API did not start')
            worker = subprocess.Popen(
                [sys.executable, '-c', 'import time\nfrom app.emergency_audit_worker import process_one\nwhile True:\n process_one()\n time.sleep(.2)'],
                cwd=ROOT, env=env, stdout=logs, stderr=logs,
            )
            yield base
        finally:
            for process in (worker, server):
                if process is None:
                    continue
                process.terminate()
                try:
                    process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=5)


def browser_login(context, base, role='owner'):
    response = context.request.post(base + '/auth/login', data={
        'username': 'audit-browser-' + role, 'password': 'synthetic-audit-browser-password',
    })
    assert response.status == 200


def synthetic_pdf(value='80'):
    import pymupdf
    document = pymupdf.open()
    page = document.new_page()
    page.insert_text((40, 60), value)
    page.insert_text((40, 160), 'SYNTHETIC REPORT / NO PERSONAL DATA')
    data = document.tobytes()
    document.close()
    return data


def browser_configuration(context, base, *, label='Synthetic form'):
    from uuid import uuid4
    profile = context.request.post(base + '/emergency/audit/profiles', data={
        'request_id': str(uuid4()), 'definition': {
            'label': label, 'form_key': 'synthetic-form', 'valid_from': '2026-01-01',
            'fields': [{'field_id': 'temperature', 'label': '合成の数値欄', 'value_type': 'number',
                        'page': 1, 'bbox': [0, 0, 1, .12], 'extraction': 'region'}],
        },
    })
    assert profile.status == 201, profile.text()
    rules = context.request.post(base + '/emergency/audit/rule-sets', data={
        'request_id': str(uuid4()), 'definition': {
            'label': 'Synthetic range only', 'form_key': 'synthetic-form', 'valid_from': '2026-01-01',
            'rules': [{'rule_id': 'synthetic-range', 'label': '合成の範囲確認', 'message': '合成の値を原本で確認してください。',
                       'severity': 'review', 'source': {'document_title': 'Synthetic reference', 'version': '1', 'page': '1'},
                       'assertion': {'kind': 'all', 'expressions': [
                           {'kind': 'field', 'field': 'temperature', 'operator': 'ge', 'value': 35},
                           {'kind': 'field', 'field': 'temperature', 'operator': 'le', 'value': 40},
                       ]}}],
        },
    })
    assert rules.status == 201, rules.text()
    return profile.json(), rules.json()


def browser_upload(context, base, profile_id):
    from uuid import uuid4
    response = context.request.post(base + '/emergency/audit/reports', multipart={
        'request_id': str(uuid4()), 'dataset_kind': 'synthetic', 'profile_id': profile_id,
        'file': {'name': 'synthetic-report.pdf', 'mimeType': 'application/pdf', 'buffer': synthetic_pdf()},
    })
    assert response.status == 201, response.text()
    return response.json()


@BROWSER
def test_browser_private_source_confirmation_check_revision_and_responsive(audit_server, tmp_path):
    from playwright.sync_api import expect, sync_playwright
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(executable_path=os.environ.get('FIRE_AI_TEST_CHROMIUM'))
        context = browser.new_context(viewport={'width': 1440, 'height': 1000})
        browser_login(context, audit_server)
        profile, rules = browser_configuration(context, audit_server)
        page = context.new_page()
        page.set_default_timeout(30000)
        errors = []
        page.on('pageerror', lambda error: errors.append(str(error)))
        page.goto(audit_server + '/ui/emergency-audit.html')
        expect(page.locator('#uploadFiles')).to_be_enabled()
        page.locator('#profileSelect').select_option(profile['config_id'])
        page.locator('#uploadFiles').set_input_files({'name': 'synthetic-report.pdf', 'mimeType': 'application/pdf', 'buffer': synthetic_pdf()})
        page.locator('#startUpload').click()
        expect(page.locator('#reportWorkspace')).to_be_visible()
        expect(page.locator('#sourceImage')).to_be_visible()
        expect(page.locator('#field-state-temperature')).to_be_enabled()
        expect(page.locator('#field-state-temperature')).to_have_value('unconfirmed')
        expect(page.locator('#saveFields')).to_be_disabled()
        expect(page.locator('#field-value-temperature')).to_have_value('80')
        page.locator('#field-state-temperature').select_option('confirmed')
        page.locator('#confirmOriginal').check()
        page.locator('#saveFields').click()
        expect(page.locator('#fieldMessage')).to_contain_text('保存しました')
        page.locator('#checkRules').select_option(rules['config_id'])
        page.locator('#runCheck').click()
        expect(page.locator('.finding-card').first).to_contain_text('確認が必要')
        expect(page.locator('#checkMeta')).to_contain_text('検査した範囲')
        expect(page.locator('#reportBanner')).to_contain_text('実測ではありません')
        page.locator('.decision-controls .decision-choice').select_option('correction_needed')
        page.locator('.decision-controls button').click()
        expect(page.locator('#findingMessage')).to_contain_text('確認結果を記録')
        page.locator('#revisionFile').set_input_files({'name': 'synthetic-corrected.pdf', 'mimeType': 'application/pdf', 'buffer': synthetic_pdf('36.5')})
        page.locator('#uploadRevision').click()
        expect(page.locator('#reportHeading')).to_contain_text('版 2')
        expect(page.locator('#field-value-temperature')).to_have_value('36.5')
        expect(page.locator('#field-state-temperature')).to_be_enabled()
        page.locator('#field-state-temperature').select_option('confirmed')
        page.locator('#confirmOriginal').check()
        page.locator('#saveFields').click()
        expect(page.locator('#fieldMessage')).to_contain_text('保存しました')
        page.locator('#runCheck').click()
        expect(page.locator('#findingList')).to_contain_text('この検査では指摘なし')
        expect(page.locator('#revisionDifference')).to_contain_text('指摘がなくなった')
        artifacts = Path(os.environ.get('FIRE_AI_BROWSER_ARTIFACTS', str(tmp_path / 'artifacts')))
        artifacts.mkdir(parents=True, exist_ok=True)
        page.screenshot(path=str(artifacts / 'emergency-audit-corrected.png'), full_page=True)
        page.set_viewport_size({'width': 390, 'height': 844})
        assert page.evaluate('document.documentElement.scrollWidth <= window.innerWidth')
        page.screenshot(path=str(artifacts / 'emergency-audit-mobile.png'), full_page=True)
        assert page.evaluate('Object.keys(localStorage).length + Object.keys(sessionStorage).length') == 0
        page.locator('.history-details summary').click()
        page.get_by_role('button', name='版 1', exact=True).click()
        expect(page.locator('#reportBanner')).to_contain_text('過去の原本')
        expect(page.locator('#runCheck')).to_be_disabled()
        expect(page.locator('#saveFields')).to_be_disabled()
        assert errors == []
        browser.close()


@BROWSER
def test_browser_private_state_403_xss_and_late_source_cleanup(audit_server):
    from playwright.sync_api import expect, sync_playwright
    from io import BytesIO
    from PIL import Image
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(executable_path=os.environ.get('FIRE_AI_TEST_CHROMIUM'))
        context = browser.new_context()
        browser_login(context, audit_server)
        profile, _ = browser_configuration(context, audit_server, label='<img src=x onerror="window.auditInjected=1">')
        report = browser_upload(context, audit_server, profile['config_id'])
        page = context.new_page()
        page.goto(audit_server + '/ui/emergency-audit.html')
        expect(page.locator('[data-report-id]')).to_have_count(1)
        assert page.evaluate('window.auditInjected === undefined')
        assert page.locator('#profileList img').count() == 0
        pending = []
        preview = audit_server + '/emergency/audit/revisions/' + report['current_revision_id'] + '/pages/1.png'
        page.route(preview, lambda route: pending.append(route))
        page.locator('[data-report-id]').click()
        for _ in range(100):
            if pending:
                break
            page.wait_for_timeout(20)
        assert len(pending) == 1
        page.evaluate('window.FireAISession.invalidate()')
        output = BytesIO()
        Image.new('RGB', (50, 50), 'white').save(output, format='PNG')
        pending.pop().fulfill(status=200, content_type='image/png', body=output.getvalue())
        expect(page.locator('#reportWorkspace')).to_be_hidden()
        expect(page.locator('#sourceImage')).not_to_have_attribute('src')
        expect(page.locator('#reportList')).to_be_empty()
        expect(page.locator('#uploadFiles')).to_have_value('')
        page.unroute(preview)
        page.route('**/emergency/audit/capabilities', lambda route: route.fulfill(
            status=403, content_type='application/json', body='{"detail":"DO_NOT_ECHO_PRIVATE_VALUE"}'))
        page.reload()
        expect(page.locator('#auditMessage')).to_contain_text('権限')
        expect(page.locator('#uploadFiles')).to_be_disabled()
        expect(page.locator('body')).not_to_contain_text('DO_NOT_ECHO_PRIVATE_VALUE')
        browser.close()


@BROWSER
def test_browser_visual_field_mapping_and_rule_builder_save_drafts(audit_server):
    from playwright.sync_api import expect, sync_playwright
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(executable_path=os.environ.get('FIRE_AI_TEST_CHROMIUM'))
        context = browser.new_context()
        browser_login(context, audit_server)
        page = context.new_page()
        page.goto(audit_server + '/ui/emergency-audit.html')
        expect(page.locator('#configurationTab')).to_be_enabled()
        page.locator('#configurationTab').click()
        page.locator('#newProfile').click()
        page.locator('#profileName').fill('Synthetic visual form')
        page.locator('#profileCode').fill('synthetic-visual')
        page.locator('#profileValidFrom').fill('2026-01-01')
        page.locator('#configSourceFile').set_input_files({
            'name': 'synthetic-template.pdf', 'mimeType': 'application/pdf', 'buffer': synthetic_pdf(),
        })
        page.locator('#uploadConfigSource').click()
        expect(page.locator('#configSourceMessage')).to_contain_text('根拠を保存しました')
        expect(page.locator('#mappingImage')).to_be_visible()
        page.locator('#mappedFieldId').fill('value')
        page.locator('#mappedFieldLabel').fill('合成の数値欄')
        page.locator('#mappedFieldType').select_option('number')
        for identity, value in [('regionX0', '0'), ('regionY0', '0'), ('regionX1', '1'), ('regionY1', '0.12')]:
            page.locator('#' + identity).fill(value)
        page.locator('#saveMappedField').click()
        expect(page.locator('#mappedFieldList')).to_contain_text('合成の数値欄')
        page.locator('#saveProfile').click()
        expect(page.locator('#profileMessage')).to_contain_text('下書きとして保存')
        page.locator('#ruleSetLabel').fill('Synthetic required rule')
        page.locator('#ruleCode').fill('required-value')
        page.locator('#ruleTitle').fill('合成の入力欄を確認')
        page.locator('#ruleField').select_option('value')
        page.locator('#ruleSourceTitle').fill('Synthetic reference')
        page.locator('#ruleSourceVersion').fill('1')
        page.locator('#ruleSourcePage').fill('1')
        page.locator('#saveRule').click()
        expect(page.locator('#ruleMessage')).to_contain_text('下書きとして保存')
        expect(page.locator('#approveConfiguration')).to_be_disabled()
        records = context.request.get(audit_server + '/emergency/audit/rule-sets').json()
        assert len(records) == 1
        assert records[0]['status'] == 'draft'
        assert records[0]['definition']['rules'][0]['assertion'] == {
            'kind': 'field', 'field': 'value', 'operator': 'not_blank',
        }
        browser.close()
