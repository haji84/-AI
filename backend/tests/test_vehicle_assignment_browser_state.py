"""Real operations + SharedSession/API source; synthetic DOM/HTTP transport only.

These regressions fail if the production UI loses view ownership, permits a
second mutation, hides source/version meaning, or exposes a protected draft.
Real API persistence is covered separately by the Chromium journey.
"""
import json
from pathlib import Path
import subprocess

import pytest

ROOT = Path(__file__).resolve().parents[2]


def run_ui(body):
    harness = r'''
const assert=require('node:assert/strict'),vm=require('node:vm');
const nodes={},handlers={},windowHandlers={};
function element(id='',tagName='DIV',attrs=''){
 const classes=new Set((attrs.match(/class="([^"]*)"/)?.[1]??'').split(' '));
 const n={id,tagName,children:[],isConnected:true,disabled:/\bdisabled\b/.test(attrs),checked:false,value:attrs.match(/value="([^"]*)"/)?.[1]??'',textContent:'',dataset:{},style:{},
 classList:{add:x=>classes.add(x),remove:x=>classes.delete(x),contains:x=>classes.has(x),toggle(x,b){if(b)classes.add(x);else classes.delete(x)}},
 setAttribute(k,v){this[k]=String(v)},
 remove(){for(const child of [...this.children])child.remove();this.isConnected=false;if(nodes[this.id]===this)delete nodes[this.id]},
 append(child){child.parent=this;this.children.push(child);if(child.id)nodes[child.id]=child},
 closest(selector){if(selector.startsWith('#'))return this.id===selector.slice(1)?this:this.parent?.closest(selector)??null;return this},
 querySelectorAll(selector){const all=this.children.flatMap(x=>[x,...x.querySelectorAll('*')]);if(selector==='*')return all;if(selector==='button, input, select, textarea')return all.filter(x=>['BUTTON','INPUT','SELECT','TEXTAREA'].includes(x.tagName));return all.filter(x=>selector.startsWith('[data-')?x.dataset[selector.slice(6,-1).replace(/-([a-z])/g,(_,c)=>c.toUpperCase())]!==undefined:selector.split(',').map(x=>x.trim().toUpperCase()).includes(x.tagName))},
 _html:'',get innerHTML(){return this._html},set innerHTML(html){
 for(const child of [...this.children])child.remove();this.children=[];this._html=html;
 const stack=[this];for(const m of html.matchAll(/<\/?([a-z][\w-]*)\b([^>]*)>/gi)){
  if(m[0].startsWith('</')){if(stack.length>1)stack.pop();continue}
  const key=m[2].match(/\bid="([^"]+)"/)?.[1]??'',child=element(key,m[1].toUpperCase(),m[2]);
  for(const a of m[2].matchAll(/data-([\w-]+)="([^"]*)"/g))child.dataset[a[1].replace(/-([a-z])/g,(_,c)=>c.toUpperCase())]=a[2];
  stack.at(-1).append(child);if(!['INPUT','HR','BR','IMG'].includes(child.tagName))stack.push(child);
 }
 }};return n;
}
const document={visibilityState:'visible',body:element('body'),createElement:()=>element(),getElementById:id=>nodes[id],querySelectorAll:selector=>document.body.querySelectorAll(selector),addEventListener(k,f){(handlers[k]??=[]).push(f)}};
for(const id of ['operationsBtn'])document.body.append(element(id));
let authority={user_id:'human-user',session_id:'session-a',tenant_id:null,permissions:['fleet.read','fleet.update']};
let requests=[],resets=0;
const orgA={organization_id:'org-a',code:'STA-A',name:'Synthetic Alpha Station',version:2,active:true};
const orgB={organization_id:'org-b',code:'STA-B',name:'Synthetic Beta Station',version:3,active:true};
let vehicle={vehicle_id:'vehicle-a',version:4,code:'VEH-A',name:'Synthetic pump vehicle',active:true,odometer:'100',fuel_stock:'0'};
let assignment={vehicle_id:'vehicle-a',vehicle_version:4,current:null,items:[],total:0,limit:50,offset:0};
function record(org=orgA){return {assignment_change_id:'change-a',action:org?'assign':'unassign',state:org?'assigned':'unassigned',organization:org,recorded_organization:org,before_organization:null,after_organization:org,vehicle_version_before:4,vehicle_version_after:5,changed_by:'human-user',changed_at:'2026-10-07T08:00:00Z',reason:'Synthetic assignment reason',source_evidence:'Synthetic order ref A-7',human_confirmation:{acknowledged:true,user_id:'human-user',at:'2026-10-07T08:00:00Z'}}}
let endpoint=async(path,options)=>{
 if(path==='/auth/permissions')return {permissions:authority.permissions};
 if(path.includes('/fleet-organizations?'))return {items:[orgA,orgB],total:2,limit:100,offset:0};
 if(path.includes('/assignments?'))return assignment;
 if(path.endsWith('/assignments')&&options?.method==='POST'){const change=record();assignment={...assignment,vehicle_version:5,current:change,items:[change],total:1};return {vehicle_version:5,current:change,change}}
 if(path.endsWith('/history'))return {trips:[],fuel:[],services:[]};
 if(path.startsWith('/operations/vehicles?'))return [vehicle];
 if(path==='/operations/vehicles/vehicle-a')return vehicle;
 throw Error('Unexpected request '+path);
};
let authorityEndpoint=async()=>new Response(JSON.stringify(authority));
const window={location:{origin:'http://synthetic.local'},addEventListener(k,f){(windowHandlers[k]??=[]).push(f)},removeEventListener(k,f){windowHandlers[k]=(windowHandlers[k]??[]).filter(x=>x!==f)},fetch:async(path,options)=>{if(path==='/auth/context')return authorityEndpoint();requests.push({path:String(path),options});const data=await endpoint(String(path),options);return data instanceof Response?data:new Response(JSON.stringify(data));}};
const context={window,document,console,URL,URLSearchParams,Response,Event,WeakSet,$:id=>nodes[id],esc:v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#039;'}[c])),fetch:(...args)=>window.fetch(...args)};
vm.createContext(context);const run=s=>vm.runInContext(s,context);const flush=()=>new Promise(resolve=>setImmediate(resolve));
async function event(node,type='click'){
 const tasks=[];
 async function dispatch(){const e={target:node,type,preventDefault(){},stopImmediatePropagation(){this.stopped=true}};
 for(const h of windowHandlers[type]??[]){await h(e);if(e.stopped)return}
 for(const h of handlers[type]??[]){await h(e);if(e.stopped)return}
 if(node.isConnected&&!node.disabled)return node['on'+type]?.(e);
 }
 node.click=()=>{const p=dispatch();tasks.push(p);return p};node.dispatchEvent=()=>node.click();
 await node.click();while(tasks.length)await Promise.all(tasks.splice(0));
}
const submits=()=>requests.filter(x=>x.options?.method==='POST');
async function open(){await run('openOperations()');await run("operationsVehicleDetail('vehicle-a')")}
function fill(){nodes.operationsAssignmentReason.value='Synthetic assignment reason';nodes.operationsAssignmentSource.value='Synthetic order ref A-7';nodes.operationsAssignmentAcknowledged.checked=true;}
async function edit(){await nodes.operationsAssignmentEdit.onclick();await flush();}
'''
    api = next(line for line in (ROOT / 'frontend/index.html').read_text().splitlines()
               if line.startswith('async function api('))
    script = harness + '\n'.join(
        f'vm.runInContext({json.dumps(source)},context);'
        for source in [(ROOT/'frontend/shared-session.js').read_text(), api,
                       (ROOT/'frontend/operations.js').read_text()]
    ) + "\nwindow.FireAISession.install({reset(){resets++;run('clearOperations()')}});\n"
    script += 'async function main(){\n' + body + r'''
}let complete=false;main().then(()=>complete=true).catch(e=>{complete=true;console.error(e);process.exitCode=1});
process.on('beforeExit',()=>{if(!complete){console.error('Scenario did not finish');process.exitCode=1}});
'''
    result = subprocess.run(['node', '-e', script], capture_output=True, text=True, timeout=20)
    assert result.returncode == 0, result.stderr


def test_current_unknown_explicit_unassigned_and_frozen_history_are_distinct():
    run_ui(r'''
await open();assert.match(nodes.operationsContent.innerHTML,/未記録.*不明/);
const changed=record();changed.organization={...orgA,name:'Renamed Alpha',active:false};
assignment={...assignment,current:changed,items:[changed],total:1,vehicle_version:5};await nodes.operationsReload.onclick();
let html=nodes.operationsContent.innerHTML;assert.match(html,/Synthetic Alpha Station/);assert.match(html,/Renamed Alpha/);assert.match(html,/無効/);assert.match(html,/Human記録の参照情報/);assert.match(html,/Synthetic order ref A-7/);assert.match(html,/human-user/);
assignment={...assignment,current:record(null),items:[record(null),changed],total:2};await nodes.operationsReload.onclick();
assert.match(nodes.operationsContent.innerHTML,/未配属（Human確認済み）/);assert.equal(nodes.operationsAssignmentEdit.disabled,false);
''')


def test_assign_requires_reference_reason_ack_and_named_target_with_current_versions():
    run_ui(r'''
assignment.vehicle_version=9;await open();await edit();
fill();nodes.operationsAssignmentOrganization.value='org-b';await nodes.operationsAssignmentOrganization.onchange();nodes.operationsAssignmentAcknowledged.checked=true;
nodes.operationsAssignmentSource.value=' ';await nodes.operationsAssignmentForm.onsubmit({preventDefault(){}});assert.equal(submits().length,0);assert.match(nodes.operationsAssignmentMessage.textContent,/参照情報/);
nodes.operationsAssignmentSource.value='Synthetic order ref A-7';nodes.operationsAssignmentAcknowledged.checked=false;await nodes.operationsAssignmentForm.onsubmit({preventDefault(){}});assert.equal(submits().length,0);
nodes.operationsAssignmentAcknowledged.checked=true;await nodes.operationsAssignmentForm.onsubmit({preventDefault(){}});
assert.equal(submits().length,1);assert.deepEqual(JSON.parse(submits()[0].options.body),{expected_version:9,action:'assign',organization_id:'org-b',expected_organization_version:3,reason:'Synthetic assignment reason',source_evidence:'Synthetic order ref A-7',human_acknowledged:true});
assert(!nodes.operationsAssignmentForm);assert.match(nodes.operationsContent.innerHTML,/Synthetic Alpha Station/);
''')


def test_unassign_omits_target_and_does_not_depend_on_vehicle_active():
    run_ui(r'''
vehicle.active=false;assignment.current=record();await open();await edit();fill();nodes.operationsAssignmentAction.value='unassign';await nodes.operationsAssignmentAction.onchange();nodes.operationsAssignmentAcknowledged.checked=true;
assert.match(nodes.operationsAssignmentAfter.textContent,/未配属/);await nodes.operationsAssignmentForm.onsubmit({preventDefault(){}});
const data=JSON.parse(submits()[0].options.body);assert.equal(data.action,'unassign');assert(!Object.hasOwn(data,'organization_id'));assert(!Object.hasOwn(data,'expected_organization_version'));
''')


@pytest.mark.parametrize('status', [409, 422])
def test_recoverable_error_preserves_draft_and_reload_rechecks_vehicle(status):
    run_ui(r'''
await open();await edit();fill();nodes.operationsAssignmentOrganization.value='org-a';await nodes.operationsAssignmentOrganization.onchange();nodes.operationsAssignmentAcknowledged.checked=true;
const original=endpoint;endpoint=async(path,options)=>options?.method==='POST'?new Response('{"detail":"Synthetic no-op or stale request"}',{status:STATUS}):original(path,options);
await nodes.operationsAssignmentForm.onsubmit({preventDefault(){}});assert.equal(nodes.operationsAssignmentReason.value,'Synthetic assignment reason');assert.equal(nodes.operationsAssignmentSource.value,'Synthetic order ref A-7');assert.equal(nodes.operationsAssignmentSave.disabled,false);assert(nodes.operationsAssignmentReload);
assignment.vehicle_version=12;await nodes.operationsAssignmentReload.onclick();assert.equal(nodes.operationsAssignmentReason.value,'Synthetic assignment reason');assert.equal(nodes.operationsAssignmentAcknowledged.checked,false);
endpoint=original;nodes.operationsAssignmentAcknowledged.checked=true;await nodes.operationsAssignmentForm.onsubmit({preventDefault(){}});assert.equal(JSON.parse(submits().at(-1).options.body).expected_version,12);
'''.replace('STATUS', str(status)))


def test_busy_queued_and_detached_submits_cannot_duplicate_and_refresh_retry_is_read_only():
    run_ui(r'''
await open();await edit();fill();nodes.operationsAssignmentOrganization.value='org-a';await nodes.operationsAssignmentOrganization.onchange();nodes.operationsAssignmentAcknowledged.checked=true;
let release;const original=endpoint;endpoint=async(path,options)=>options?.method==='POST'?new Promise(resolve=>release=()=>resolve(original(path,options))):original(path,options);
const form=nodes.operationsAssignmentForm,first=form.onsubmit({preventDefault(){}});assert.equal(nodes.operationsAssignmentSave.disabled,true);await form.onsubmit({preventDefault(){}});await flush();assert.equal(submits().length,1);
let failRefresh=true;const postEndpoint=endpoint;endpoint=async(path,options)=>path.includes('/assignments?')&&failRefresh?new Response('{"detail":"Synthetic refresh failure"}',{status:503}):postEndpoint(path,options);
release();await first;assert(!nodes.operationsAssignmentForm);assert.match(nodes.operationsContent.innerHTML,/保存済み/);assert(nodes.operationsAssignmentRetry);await form.onsubmit({preventDefault(){}});assert.equal(submits().length,1);
failRefresh=false;await nodes.operationsAssignmentRetry.onclick();assert.equal(submits().length,1);assert.match(nodes.operationsContent.innerHTML,/Synthetic Alpha Station/);
''')


@pytest.mark.parametrize('dismiss', ["await nodes.operationsAssignmentBack.onclick()", "await nodes.operationsClose.onclick()", "await nodes.operationsVehicles.onclick()"])
def test_delayed_lookup_cannot_restore_cancelled_or_newer_view(dismiss):
    run_ui(r'''
await open();let release;const original=endpoint;endpoint=async(path,options)=>path.includes('/fleet-organizations?')?new Promise(resolve=>release=()=>resolve({items:[orgA],total:1,limit:100,offset:0})):original(path,options);
const editing=nodes.operationsAssignmentEdit.onclick();await flush();assert(release);const saved=nodes.operationsAssignmentForm;
DISMISS;
const html=nodes.operationsContent.innerHTML;release();await editing;assert.equal(nodes.operationsContent.innerHTML,html);assert.equal(saved.isConnected,false);
'''.replace('DISMISS', dismiss))


def test_newer_detail_and_close_preflight_invalidate_pending_reads_before_redispatch():
    run_ui(r'''
await open();let release;const original=endpoint;endpoint=async(path,options)=>path.includes('/assignments?')?new Promise(resolve=>release=()=>resolve(assignment)):original(path,options);
const old=nodes.operationsReload.onclick();await flush();assert(!nodes.operationsAssignmentEdit,'stale controls survive new read');
let authorityRelease;authorityEndpoint=()=>{authorityEndpoint=async()=>new Response(JSON.stringify(authority));return new Promise(resolve=>authorityRelease=()=>resolve(new Response(JSON.stringify(authority))));};
const close=event(nodes.operationsClose);await flush();release();await flush();assert(!nodes.operationsAssignmentEdit,'late detail restored controls while Close was awaiting authority');
authorityEndpoint=async()=>new Response(JSON.stringify(authority));authorityRelease();await close;await old;assert.equal(nodes.operationsModal.classList.contains('hidden'),true);
''')


@pytest.mark.parametrize('change', ["authority={...authority,session_id:'session-b'}", "authority={...authority,permissions:['fleet.read']}"])
def test_real_session_change_erases_protected_form_and_history(change):
    run_ui(r'''
assignment.current=record();await open();await edit();fill();let release;const original=endpoint;
endpoint=async(path,options)=>path.includes('/fleet-organizations?')?new Promise(resolve=>release=()=>resolve({items:[orgB],total:1,limit:100,offset:0})):original(path,options);
const lookup=nodes.operationsAssignmentSearch.onclick();await flush();CHANGE;release();await lookup;
assert.equal(resets,1);assert(!nodes.operationsModal);assert.equal(run('operationsState.vehicle'),null);assert.equal(run('operationsState.assignment'),null);
'''.replace('CHANGE', change))


def test_read_only_rights_hide_editor_and_denied_update_erases_private_content():
    run_ui(r'''
authority.permissions=['fleet.read'];await open();assert(!nodes.operationsAssignmentEdit);assert.match(nodes.operationsContent.innerHTML,/配属履歴/);
authority={...authority,session_id:'session-b',permissions:['fleet.read','fleet.update']};window.FireAISession.invalidate();await open();await edit();fill();nodes.operationsAssignmentOrganization.value='org-a';await nodes.operationsAssignmentOrganization.onchange();nodes.operationsAssignmentAcknowledged.checked=true;
const original=endpoint;endpoint=async(path,options)=>options?.method==='POST'?new Response('{"detail":"Forbidden"}',{status:403}):original(path,options);
await nodes.operationsAssignmentForm.onsubmit({preventDefault(){}});assert(!nodes.operationsModal);assert.equal(run('operationsState.assignment'),null);
''')


def test_failed_navigation_authority_preflight_clears_instead_of_stranding_draft():
    run_ui(r'''
await open();await edit();fill();nodes.operationsAssignmentOrganization.value='org-a';await nodes.operationsAssignmentOrganization.onchange();nodes.operationsAssignmentAcknowledged.checked=true;
let release;authorityEndpoint=()=>new Promise(resolve=>release=()=>resolve(new Response('{"detail":"authority unavailable"}',{status:503})));
const leaving=event(nodes.operationsAssignmentBack);await flush();assert.equal(nodes.operationsAssignmentSave.disabled,true);assert.match(nodes.operationsAssignmentMessage.textContent,/切り替え/);release();await leaving;
assert.equal(resets,1);assert(!nodes.operationsModal);assert.equal(run('operationsState.assignment'),null);assert.equal(submits().length,0);
''')


def test_newer_vehicle_detail_supersedes_old_vehicle_list_without_stale_controls():
    run_ui(r'''
await open();let release;const original=endpoint;
endpoint=async(path,options)=>path.startsWith('/operations/vehicles?')?new Promise(resolve=>release=()=>resolve([vehicle])):original(path,options);
const old=nodes.operationsVehicles.onclick();await flush();assert(!nodes.operationsAssignmentEdit,'old detail remained actionable during list read');
await run("operationsVehicleDetail('vehicle-a')");const html=nodes.operationsContent.innerHTML;release();await old;assert.equal(nodes.operationsContent.innerHTML,html);
''')


def test_org_pagination_newer_lookup_and_escaping_keep_selected_name_and_version():
    run_ui(r'''
await open();const original=endpoint;let release;
endpoint=async(path,options)=>path.includes('/fleet-organizations?')?new URL(path,window.location.origin).searchParams.get('q')==='old'?new Promise(resolve=>release=()=>resolve({items:[orgA],total:1,offset:0,limit:100})):{items:[{...orgB,name:'<img src=x onerror=bad>'}],total:101,offset:0,limit:100}:original(path,options);
await edit();assert(nodes.operationsAssignmentOrganization.innerHTML.includes('&lt;img'));assert(!nodes.operationsAssignmentOrganization.innerHTML.includes('<img'));assert.equal(nodes.operationsAssignmentOrgNext.disabled,false);
nodes.operationsAssignmentQuery.value='old';const old=nodes.operationsAssignmentSearch.onclick();await flush();nodes.operationsAssignmentQuery.value='fresh';await nodes.operationsAssignmentSearch.onclick();const html=nodes.operationsAssignmentOrganization.innerHTML;release();await old;assert.equal(nodes.operationsAssignmentOrganization.innerHTML,html);
await nodes.operationsAssignmentOrgNext.onclick();assert.equal(new URL(requests.at(-1).path,window.location.origin).searchParams.get('offset'),'100');
''')


def test_delayed_save_after_cancel_does_not_resurrect_detail_and_old_form_cannot_submit():
    run_ui(r'''
await open();await edit();fill();nodes.operationsAssignmentOrganization.value='org-a';await nodes.operationsAssignmentOrganization.onchange();nodes.operationsAssignmentAcknowledged.checked=true;
let release;const original=endpoint;endpoint=async(path,options)=>options?.method==='POST'?new Promise(resolve=>release=()=>resolve(original(path,options))):original(path,options);
const form=nodes.operationsAssignmentForm,save=form.onsubmit({preventDefault(){}});await flush();await nodes.operationsVehicles.onclick();const html=nodes.operationsContent.innerHTML;
release();await save;await form.onsubmit({preventDefault(){}});assert.equal(nodes.operationsContent.innerHTML,html);assert.equal(submits().length,1);
''')


def test_history_pagination_uses_server_total_and_current_vehicle_version():
    run_ui(r'''
assignment={...assignment,items:Array.from({length:50},()=>record()),total:51,vehicle_version:19};await open();assert.equal(nodes.operationsAssignmentNext.disabled,false);
const original=endpoint;endpoint=async(path,options)=>path.includes('/assignments?')?{...assignment,items:[record()],offset:50}:original(path,options);
await nodes.operationsAssignmentNext.onclick();assert(requests.some(x=>x.path.endsWith('assignments?limit=50&offset=50')));assert.equal(nodes.operationsAssignmentPrev.disabled,false);assert.equal(nodes.operationsAssignmentNext.disabled,true);assert.match(nodes.operationsContent.innerHTML,/車両 Version 19/);
''')


def test_rejected_save_restores_truthful_pagination_controls():
    run_ui(r'''
await open();await edit();fill();nodes.operationsAssignmentOrganization.value='org-a';await nodes.operationsAssignmentOrganization.onchange();nodes.operationsAssignmentAcknowledged.checked=true;
const original=endpoint;endpoint=async(path,options)=>options?.method==='POST'?new Response('{"detail":"Synthetic rejected update"}',{status:422}):original(path,options);
assert.equal(nodes.operationsAssignmentOrgNext.disabled,true);await nodes.operationsAssignmentForm.onsubmit({preventDefault(){}});assert.equal(nodes.operationsAssignmentOrgNext.disabled,true);assert.equal(nodes.operationsAssignmentOrgPrev.disabled,true);
''')


def test_source_lookup_loading_cannot_commit_hidden_stale_selection():
    run_ui(r'''
await open();await edit();fill();nodes.operationsAssignmentOrganization.value='org-a';await nodes.operationsAssignmentOrganization.onchange();nodes.operationsAssignmentAcknowledged.checked=true;
let release;const original=endpoint;endpoint=async(path,options)=>path.includes('/fleet-organizations?')?new Promise(resolve=>release=()=>resolve({items:[orgB],total:1,limit:100,offset:0})):original(path,options);
const lookup=nodes.operationsAssignmentSearch.onclick();await flush();assert.equal(nodes.operationsAssignmentSave.disabled,true);await nodes.operationsAssignmentForm.onsubmit({preventDefault(){}});assert.equal(submits().length,0);release();await lookup;assert.equal(nodes.operationsAssignmentSave.disabled,false);
''')


def test_reload_changed_organization_requires_reselection_but_keeps_written_draft():
    run_ui(r'''
await open();await edit();fill();nodes.operationsAssignmentOrganization.value='org-a';await nodes.operationsAssignmentOrganization.onchange();nodes.operationsAssignmentAcknowledged.checked=true;
const original=endpoint;endpoint=async(path,options)=>path.includes('/fleet-organizations?')?{items:[{...orgA,version:8,name:'Changed Alpha'}],total:1,limit:100,offset:0}:original(path,options);
await nodes.operationsAssignmentReload.onclick();assert.equal(nodes.operationsAssignmentReason.value,'Synthetic assignment reason');assert.equal(nodes.operationsAssignmentSource.value,'Synthetic order ref A-7');assert.equal(nodes.operationsAssignmentOrganization.value,'');assert.match(nodes.operationsAssignmentMessage.textContent,/選び直/);
nodes.operationsAssignmentOrganization.value='org-a';await nodes.operationsAssignmentOrganization.onchange();nodes.operationsAssignmentAcknowledged.checked=true;await nodes.operationsAssignmentForm.onsubmit({preventDefault(){}});assert.equal(JSON.parse(submits()[0].options.body).expected_organization_version,8);
''')


def test_reload_is_unavailable_during_pending_lookup_and_recovers_after_failure():
    run_ui(r'''
await open();await edit();let release;const original=endpoint;
endpoint=async(path,options)=>path.includes('/fleet-organizations?')?new Promise(resolve=>release=()=>resolve(new Response('{"detail":"temporary read error"}',{status:503}))):original(path,options);
const lookup=nodes.operationsAssignmentSearch.onclick();await flush();assert.equal(nodes.operationsAssignmentReload.disabled,true);await nodes.operationsAssignmentReload.onclick();release();await lookup;assert.equal(nodes.operationsAssignmentReload.disabled,false);assert.equal(nodes.operationsAssignmentSave.disabled,false);
''')


@pytest.mark.parametrize('navigation', ['operationsClose', 'operationsSummary'])
def test_delayed_vehicle_list_yields_to_navigation_during_authority_preflight(navigation):
    run_ui(r'''
await open();let release;const original=endpoint;
endpoint=async(path,options)=>path.startsWith('/operations/vehicles?')?new Promise(resolve=>release=()=>resolve([vehicle])):original(path,options);
const old=nodes.operationsVehicles.onclick();await flush();assert(!nodes.operationsAssignmentEdit);
let authorityRelease;authorityEndpoint=()=>{authorityEndpoint=async()=>new Response(JSON.stringify(authority));return new Promise(resolve=>authorityRelease=()=>resolve(new Response(JSON.stringify(authority))));};
const leaving=event(nodes.NAVIGATION);await flush();release();await old;assert(!nodes.operationsSearch,'delayed list restored actionable rows during newer navigation authority preflight');
authorityRelease();await leaving;
'''.replace('NAVIGATION', navigation))


@pytest.mark.parametrize('older', ['alerts','service_form','registry_save'])
def test_older_operations_completion_cannot_replace_new_assignment_draft(older):
    run_ui(r'''
await open();let release;const original=endpoint;
if('OLDER'==='alerts'){
 endpoint=async(path,options)=>path==='/operations/alerts'?new Promise(resolve=>release=()=>resolve([])):original(path,options);
 context.pending=nodes.operationsAlerts.onclick();
}else if('OLDER'==='service_form'){
 endpoint=async(path,options)=>path.endsWith('/history')&&!release?new Promise(resolve=>release=()=>resolve({trips:[],fuel:[],services:[]})):original(path,options);
 context.pending=run('operationsServiceForm(operationsState.vehicle)');
}else{
 await nodes.operationsEdit.onclick();
 endpoint=async(path,options)=>options?.method==='PATCH'?new Promise(resolve=>release=()=>resolve({...vehicle,version:5})):original(path,options);
 const form=nodes.operationsForm;form.onsubmit({preventDefault(){}});
 context.pending=Promise.resolve();
}
await flush();assert(release);await run("operationsVehicleDetail('vehicle-a')");await edit();fill();
const form=nodes.operationsAssignmentForm;release();await context.pending;await flush();await flush();
assert.equal(form.isConnected,true,'older operation destroyed the current assignment draft');assert.equal(nodes.operationsAssignmentReason.value,'Synthetic assignment reason');
'''.replace('OLDER', older))


def test_old_operations_error_cannot_repaint_assignment_message_but_current_errors_report():
    run_ui(r'''
await open();let reject;const original=endpoint;
endpoint=async(path,options)=>path==='/operations/alerts'?new Promise((_resolve,failure)=>reject=failure):original(path,options);
const old=nodes.operationsAlerts.onclick();await flush();await run("operationsVehicleDetail('vehicle-a')");await edit();nodes.operationsMessage.textContent='Current assignment notice';
reject(Error('Old alert read failed'));await old;assert.equal(nodes.operationsMessage.textContent,'Current assignment notice');
endpoint=async(path,options)=>path==='/operations/alerts'?new Response('{"detail":"Current alert read failed"}',{status:503}):original(path,options);
await nodes.operationsAlerts.onclick();assert.match(nodes.operationsMessage.textContent,/Current alert read failed/);
''')


def test_current_save_reports_failed_destination_read_and_stops_loading():
    run_ui(r'''
await open();const original=endpoint;
endpoint=async(path,options)=>path==='/operations/incidents/incident-a'?options?.method==='PATCH'?{incident_id:'incident-a',version:2,title:'Synthetic incident'}:new Response('{"detail":"Synthetic current detail unavailable"}',{status:503}):original(path,options);
await run("operationsIncidentForm({incident_id:'incident-a',version:1,title:'Synthetic incident'})");await nodes.operationsForm.onsubmit({preventDefault(){}});
assert.match(nodes.operationsMessage.textContent,/Synthetic current detail unavailable/);assert(!nodes.operationsViewLoading,'failed current read still claims it is loading');
''')


@pytest.mark.parametrize('removed', ['nodes.operationsModal.remove()', 'nodes.operationsModal.isConnected=false', 'nodes.operationsContent.isConnected=false'])
def test_absent_modal_never_grants_owner_or_throws_from_new_owner_helpers(removed):
    run_ui(r'''
await open();REMOVED;
const before=requests.length,current=run('operationsBeginView()');assert.equal(current(),false);
const owner=run('operationsVehicleOwner()');assert.equal(owner.current(),false);
await run("operationsVehicleDetail('vehicle-a')");assert.equal(requests.length,before,'missing modal allowed a private read');
'''.replace('REMOVED', removed))
