"""Actual hazardous module and SharedSession behavior under deferred native responses."""
from pathlib import Path
import subprocess
import os
import json


def run(tmp_path, scenario):
    root = Path(__file__).resolve().parents[2]
    assert (root / 'frontend/hazardous.js').exists(), 'hazardous register UI is missing'
    harness = r'''
const assert=require('node:assert/strict'),vm=require('node:vm'),fs=require('node:fs');
const nodes=new Map();
class Node {
 constructor(id=''){this.id=id;this.textContent='';this.value='';this.checked=false;this.disabled=false;this.isConnected=true;this.dataset={};this.children=[];this.style={};this._html='';this.classList={add:()=>this.hidden=true,remove:()=>this.hidden=false,toggle:(_c,v)=>this.hidden=v,contains:()=>Boolean(this.hidden)};}
 set innerHTML(v){for(const child of this.children)child.remove();this.children=[];this._html=v;for(const match of v.matchAll(/id="([^"]+)"/g)){const child=new Node(match[1]);this.children.push(child);nodes.set(match[1],child);}}
 get innerHTML(){return this._html;}
 append(...children){this.children.push(...children);for(const child of children){child.isConnected=true;if(child.id)nodes.set(child.id,child);}}
 remove(){this.isConnected=false;for(const child of this.children)child.remove();this.children=[];if(nodes.get(this.id)===this)nodes.delete(this.id);}
 querySelectorAll(){return [];}
 querySelector(){return null;}
 setAttribute(){} click(){if(this.onclick)return this.onclick();}
}
const add=id=>{const n=new Node(id);nodes.set(id,n);return n;};add('hazardousBtn');
let authority={user_id:'synthetic',session_id:'session-a',tenant_id:'tenant-a',permissions:['hazardous.read','hazardous.create','hazardous.update','hazardous.review','facility.read','document.read','document.create','legal_source.read','inspection.read','violation.read']};
let calls=[],routes=new Map(),handlers={},resetCount=0;
const response=data=>new Response(JSON.stringify(data),{headers:{'Content-Type':'application/json'}});
const document={body:new Node(),createElement:()=>new Node(),getElementById:id=>nodes.get(id)||null,querySelectorAll:()=>[],addEventListener:(k,v)=>handlers[k]=v,visibilityState:'visible'};
const window={location:{origin:'http://synthetic.local',pathname:'/ui/'},addEventListener:(k,v)=>handlers[k]=v,fetch:async(path,opt={})=>{
 calls.push({path:String(path),opt});if(path==='/auth/context')return response(authority);if(path==='/auth/me')return response({user_id:authority.user_id});if(path==='/auth/permissions')return response({permissions:authority.permissions});
 const match=[...routes.entries()].find(([key])=>String(path).startsWith(key));if(match)return match[1](path,opt);
 return response([]);
}};
const context={window,document,URL,URLSearchParams,Response,WeakSet,Event,FormData,Blob,Date,console,setTimeout,clearTimeout,$:id=>nodes.get(id)||null,esc:x=>String(x??'').replaceAll('&','&amp;').replaceAll('<','&lt;').replaceAll('"','&quot;')};
vm.createContext(context);vm.runInContext(fs.readFileSync(process.argv[2],'utf8'),context);
context.fetch=(...args)=>window.fetch(...args);context.api=async(path,opt={})=>{const r=await window.fetch(path,opt);const data=await r.json();if(!r.ok)throw Object.assign(new Error(data.detail?.message||data.detail||'request failed'),{status:r.status});return data;};
vm.runInContext(fs.readFileSync(process.argv[3],'utf8'),context);window.FireAISession.install({reset:()=>{resetCount++;vm.runInContext('clearHazardous()',context);}});
const evaluate=s=>vm.runInContext(s,context),turn=()=>new Promise(resolve=>setImmediate(resolve));
const installation={installation_id:'installation-a',building_id:'building-a',name:'Synthetic installation',category_label:'Human entered category',location_detail:'Synthetic area',notes:'',materials:[],status:'active',version:1,evidence_records:[],history:[]};
(async()=>{SCENARIO})().catch(e=>{console.error(e.stack);process.exitCode=1;});
'''
    file = tmp_path / 'hazardous-harness.js'
    file.write_text(harness.replace('SCENARIO', scenario))
    result = subprocess.run(['node', str(file), str(root / 'frontend/shared-session.js'), str(root / 'frontend/hazardous.js'), os.environ.get('FIRE_AI_TEST_VIOLATIONS_SOURCE', str(root / 'frontend/violations.js'))], capture_output=True, text=True, timeout=20)
    assert result.returncode == 0, result.stderr


def test_exact_material_strings_and_unit_pairs(tmp_path):
    run(tmp_path, r'''
const material={name:'Synthetic',category_label:'Human category',quantity:'999999999999999999.123456',quantity_unit:'L',capacity:'1.000001',capacity_unit:'L'};
context.material=material;const actual=evaluate('hazardousMaterialValues(material)');assert.equal(actual.quantity,material.quantity);assert.equal(actual.capacity,material.capacity);
for(const quantity of ['-1','1e3','1.1234567','1000000000000000000','', 'NaN']){context.material={...material,quantity};assert.throws(()=>evaluate('hazardousMaterialValues(material)'));}
for(const value of ['00','01','00.1','000000000000000001.000001']){for(const key of ['quantity','capacity']){context.material={...material,[key]:value};assert.throws(()=>evaluate('hazardousMaterialValues(material)'),/先頭の0/);}}
context.material={...material,capacity:'',capacity_unit:'L'};assert.throws(()=>evaluate('hazardousMaterialValues(material)'));
context.material={...material,quantity:'0',capacity:'',capacity_unit:''};assert.equal(evaluate('hazardousMaterialValues(material).capacity'),null);
''')



def test_decimal_client_matches_real_backend_material_schema(tmp_path):
    """Prevent browser-only fixtures from accepting strings rejected by the API."""
    from pydantic import ValidationError
    from app.hazardous_schemas import Material

    base = {'name': 'Synthetic', 'category_label': 'Human category',
            'quantity': '1.000001', 'quantity_unit': 'L',
            'capacity': '999999999999999999.123456', 'capacity_unit': 'm³'}
    spellings = ['0', '0.000000', '0.000001', '1', '1.000001',
                 '999999999999999999', '999999999999999999.123456',
                 '00', '01', '00.1', '01.000001', '000000000000000001.000001',
                 '1000000000000000000', '1.1234567', '-1', '-0', '+1',
                 '.1', '1.', '1e3', 'NaN', 'Infinity', 1, 0.000001]
    inputs = [{**base, field: value} for field in ('quantity', 'capacity') for value in spellings]
    inputs += [{**base, 'capacity': capacity, 'capacity_unit': unit}
               for capacity, unit in [('', ''), (None, None), ('', 'L'), (None, 'L'), ('1', ''), ('1', None)]]
    cases = []
    for material in inputs:
        # Empty optional form controls intentionally become null in the API payload.
        payload = {**material, 'capacity': None if material['capacity'] == '' else material['capacity'],
                   'capacity_unit': None if material['capacity_unit'] == '' else material['capacity_unit']}
        try:
            expected = Material.model_validate(payload).model_dump()
        except ValidationError:
            expected = None
        cases.append({'material': material, 'expected': expected})
    run(tmp_path, 'const materialCases=' + json.dumps(cases, ensure_ascii=False) + r'''
for(const item of materialCases){
 context.material=item.material;let actual=null;
 try{actual=JSON.parse(JSON.stringify(evaluate('hazardousMaterialValues(material)')));}catch{}
 assert.deepEqual(actual,item.expected,'Client/server disagreement for '+JSON.stringify(item.material));
}
''')


def test_late_open_and_detail_cannot_reopen_closed_view(tmp_path):
    run(tmp_path, r'''
let release;routes.set('/hazardous/installations/installation-a',()=>new Promise(r=>release=r));
const pending=evaluate('hazardousDetail("installation-a")');await turn();evaluate('closeHazardous()');release(response(installation));await assert.rejects(pending,e=>e.cancelled);assert(!nodes.get('hazardousModal'));
let permissionsRelease;const original=context.api;context.api=async(path,opt)=>path==='/auth/permissions'?new Promise(r=>permissionsRelease=r):original(path,opt);
const opening=evaluate('openHazardous()');await turn();evaluate('closeHazardous()');permissionsRelease({permissions:authority.permissions});await assert.rejects(opening,e=>e.cancelled);assert(!nodes.get('hazardousModal'));
''')


def test_newer_list_navigation_owns_render_and_old_error_is_quiet(tmp_path):
    run(tmp_path, r'''
await evaluate('openHazardous()');let release;routes.set('/hazardous/installations?',path=>String(path).includes('q=old')?new Promise(r=>release=r):response([{...installation,name:'New list'}]));
const old=evaluate('hazardousAction(()=>hazardousList("old"))');await turn();await evaluate('hazardousList("new")');assert(nodes.get('hazardousContent').innerHTML.includes('New list'));
release(new Response('{"detail":"obsolete failure"}',{status:409}));await old;assert(nodes.get('hazardousContent').innerHTML.includes('New list'));assert(!nodes.get('hazardousMessage').textContent.includes('obsolete'));
''')


def test_shared_session_change_clears_private_state_before_delayed_body(tmp_path):
    run(tmp_path, r'''
await evaluate('openHazardous()');let release;routes.set('/hazardous/installations/installation-a',()=>new Response(new ReadableStream({start(controller){release=()=>{controller.enqueue(new TextEncoder().encode(JSON.stringify(installation)));controller.close();};}})));
const pending=evaluate('hazardousDetail("installation-a")');await turn();authority={...authority,session_id:'session-b'};release();await assert.rejects(pending,e=>e.cancelled);assert.equal(resetCount,1);assert(!nodes.get('hazardousModal'));assert.equal(evaluate('hazardousState.permissions.length'),0);
''')


def test_source_permission_loss_and_stale_mutation_cannot_leak_or_post(tmp_path):
    run(tmp_path, r'''
await evaluate('openHazardous()');const ticket=evaluate('hazardousTicket()');context.ticket=ticket;
authority={...authority,permissions:authority.permissions.filter(p=>p!=='document.read')};await assert.rejects(evaluate('hazardousAPI("/hazardous/installations",{method:"POST"},ticket,"hazardous.create")'),e=>e.cancelled);assert(!nodes.get('hazardousModal'));assert(!calls.some(x=>x.path==='/hazardous/installations'&&x.opt.method==='POST'));
await evaluate('openHazardous()');context.ticket=evaluate('hazardousTicket()');evaluate('closeHazardous()');await assert.rejects(evaluate('hazardousAPI("/hazardous/installations",{method:"POST"},ticket,"hazardous.create")'),e=>e.cancelled);assert(!calls.some(x=>x.path==='/hazardous/installations'&&x.opt.method==='POST'));
''')


def test_cached_list_action_stays_invalid_before_and_after_background_reset(tmp_path):
    run(tmp_path, r'''
for(const resetFirst of [false,true]){
 await evaluate('openHazardous()');
 const cached=nodes.get('hazardousListNav').onclick;
 authority={...authority,session_id:resetFirst?'session-c':'session-b'};
 if(resetFirst)await assert.rejects(window.FireAISession.check(),e=>e.cancelled);
 const requests=calls.filter(x=>x.path.startsWith('/hazardous/')).length;
 await cached();
 assert(!nodes.get('hazardousModal'));
 assert.equal(evaluate('hazardousState.permissions.length'),0);
 assert.equal(calls.filter(x=>x.path.startsWith('/hazardous/')).length,requests);
}
assert.equal(resetCount,2);
''')


def test_source_queries_reject_out_of_order_results_and_cancelled_navigation(tmp_path):
    run(tmp_path, r'''
await evaluate('openHazardous()');let release;routes.set('/hazardous/sources/documents?',path=>String(path).includes('q=old')?new Promise(r=>release=r):response([{id:'fresh',label:'Fresh original',sha256:'hash'}]));
context.picker={request:0};context.ticket=evaluate('hazardousTicket()');const old=evaluate('hazardousSourceQuery("documents","old",0,{},picker,ticket)');await turn();const fresh=await evaluate('hazardousSourceQuery("documents","new",0,{},picker,ticket)');assert.equal(fresh[0].id,'fresh');release(response([{id:'old',label:'Old original'}]));await assert.rejects(old,e=>e.cancelled);
''')


def test_direct_detail_and_granular_actions(tmp_path):
    run(tmp_path, r'''
routes.set('/hazardous/installations/installation-a',()=>response(installation));await evaluate('hazardousDetail("installation-a")');assert(nodes.get('hazardousModal'));assert(nodes.get('hazardousContent').innerHTML.includes('Synthetic installation'));assert(nodes.get('hazardousContent').innerHTML.includes('hazardousRetire'));assert(!calls.some(x=>x.path.startsWith('/hazardous/installations?')));
authority={...authority,permissions:['hazardous.read','facility.read']};evaluate('clearHazardous()');window.FireAISession.invalidate();await evaluate('hazardousDetail("installation-a")');assert(!nodes.get('hazardousContent').innerHTML.includes('id="hazardousEdit"'));assert(!nodes.get('hazardousContent').innerHTML.includes('id="hazardousRecordNew"'));
''')


def test_decisions_require_human_acknowledgement_and_both_versions(tmp_path):
    run(tmp_path, r'''
context.installation=installation;context.record={record_id:'record-a',version:3};context.values={reason:'Human checked original',human_acknowledged:false};
for(const verb of ['confirm','cancel','retire']){context.verb=verb;assert.throws(()=>evaluate('hazardousDecisionPayload(installation,record,verb,values)'));}
context.values.human_acknowledged=true;const confirm=evaluate('hazardousDecisionPayload(installation,record,"confirm",values)');assert.equal(confirm.expected_version,3);assert.equal(confirm.expected_installation_version,1);assert.equal(confirm.human_acknowledged,true);
const retire=evaluate('hazardousDecisionPayload(installation,null,"retire",values)');assert.equal(retire.expected_version,1);assert(!('expected_installation_version' in retire));
const revision=evaluate('hazardousDecisionPayload(installation,record,"revisions",values)');assert(!('human_acknowledged' in revision));context.values.reason=' ';assert.throws(()=>evaluate('hazardousDecisionPayload(installation,record,"confirm",values)'));
''')


def test_cached_record_and_form_revalidate_authority_before_private_render(tmp_path):
    run(tmp_path, r'''
await evaluate('openHazardous()');context.installation={...installation,name:'PRIVATE cached name'};context.record={record_id:'record-a',title:'PRIVATE cached evidence',status:'draft',version:1,document_ids:[],legal_source_version_ids:[],inspection_ids:[],violation_case_ids:[]};
authority={...authority,permissions:['hazardous.read']};
for(const operation of ['hazardousInstallationForm(installation)','hazardousRecordForm(installation,record)','hazardousDecision(installation,record,"confirm")']){
 try{await evaluate(operation);}catch(error){}assert(!nodes.get('hazardousContent')?.innerHTML.includes('PRIVATE'));
}
assert(!nodes.get('hazardousModal'));
''')


def test_record_detail_sources_actions_and_historical_confirmation(tmp_path):
    run(tmp_path, r'''
const record={record_id:'record-a',title:'Synthetic permit evidence',kind:'permit',recorded_on:'2026-10-01',status:'confirmed',version:1,confirmation_current:false,document_ids:['document-a'],legal_source_version_ids:[],inspection_ids:[],violation_case_ids:[],sources:{documents:[{id:'document-a',label:'Original permit.txt',sha256:'1234'}]},source_snapshot:{documents:[{document_id:'document-a',sha256:'1234',filename:'Original permit.txt'}]}};
routes.set('/hazardous/installations/installation-a',()=>response({...installation,evidence_records:[record]}));await evaluate('hazardousRecordDetail("installation-a","record-a")');const html=nodes.get('hazardousContent').innerHTML;assert(html.includes('過去の確認'));assert(html.includes('Original permit.txt'));assert(html.includes('hazardousRevision'));assert(!html.includes('id="hazardousRecordEdit"'));assert(!html.includes('id="hazardousConfirm"'));assert(html.includes('hazardousCancel'));
''')


def test_current_navigation_error_is_visible(tmp_path):
    run(tmp_path, r'''
await evaluate('openHazardous()');routes.set('/hazardous/installations?',()=>new Response('{"detail":"Synthetic conflict"}',{status:409}));
await nodes.get('hazardousListNav').onclick();assert(nodes.get('hazardousMessage').textContent.includes('Synthetic conflict'));
routes.set('/hazardous/installations?',()=>response([{...installation,name:'Recovered after error'}]));await nodes.get('hazardousListNav').onclick();assert(nodes.get('hazardousContent').innerHTML.includes('Recovered after error'));
''')


def test_human_submit_posts_once_with_ack_and_supplied_versions_then_conflict_stays_reviewable(tmp_path):
    run(tmp_path, r'''
context.installation=installation;context.record={record_id:'record-a',title:'Synthetic draft',version:4};
await evaluate('hazardousDecision(installation,record,"confirm")');nodes.get('hazardousField_reason').value='Synthetic Human original check';nodes.get('hazardousField_human_acknowledged').checked=true;
let release;routes.set('/hazardous/installations/installation-a/records/record-a/confirm',()=>new Promise(r=>release=r));
const submit=nodes.get('hazardousForm').onsubmit({preventDefault(){}});await turn();const duplicate=nodes.get('hazardousForm').onsubmit({preventDefault(){}});await duplicate;
const posted=calls.filter(x=>x.path.endsWith('/confirm')&&x.opt.method==='POST');assert.equal(posted.length,1);const body=JSON.parse(posted[0].opt.body);assert.equal(body.expected_version,4);assert.equal(body.expected_installation_version,1);assert.equal(body.human_acknowledged,true);
release(new Response('{"detail":"stale version"}',{status:409}));await submit;assert(nodes.get('hazardousMessage').textContent.includes('stale version'));assert.equal(nodes.get('hazardousSave').disabled,false);assert.equal(nodes.get('hazardousField_reason').value,'Synthetic Human original check');
''')


def test_cancel_uses_edit_permission_while_confirmation_requires_review(tmp_path):
    run(tmp_path, r'''
const record={record_id:'record-a',title:'Synthetic draft',kind:'permit',recorded_on:'2026-10-01',status:'draft',version:1,sources:{},source_snapshot:{}};
routes.set('/hazardous/installations/installation-a',()=>response({...installation,evidence_records:[record]}));authority={...authority,permissions:['hazardous.read','facility.read','hazardous.update']};await evaluate('hazardousRecordDetail("installation-a","record-a")');assert(nodes.get('hazardousContent').innerHTML.includes('id="hazardousCancel"'));assert(!nodes.get('hazardousContent').innerHTML.includes('id="hazardousConfirm"'));
context.installation=installation;context.record=record;await evaluate('hazardousDecision(installation,record,"cancel")');assert(nodes.get('hazardousForm'));
''')


def test_source_availability_requires_legal_and_original_access(tmp_path):
    run(tmp_path, r'''
authority={...authority,permissions:['hazardous.read','facility.read','legal_source.read']};await evaluate('openHazardous()');assert.equal(evaluate('hazardousSourceAvailable("legal")'),false);assert.equal(evaluate('hazardousSourceAvailable("facilities")'),true);
context.record={sources:{legal:[{id:'legal-a',label:'Synthetic law',sha256:'abc',source_url:'javascript:alert(1)',raw_document_id:'raw-a'}]}};assert(!evaluate('hazardousSourcesMarkup(record)').includes('href="javascript:'));
''')


def test_record_form_source_pickers_submit_selected_ids_and_scope_same_building(tmp_path):
    run(tmp_path, r'''
context.installation=installation;
for(const [kind,id,label] of [['documents','doc-a','Synthetic original'],['legal','legal-a','Synthetic law'],['inspections','inspection-a','Synthetic inspection'],['violations','case-a','Synthetic case']])routes.set('/hazardous/sources/'+kind+'?',()=>response([{id,label,sha256:'synthetic-hash'}]));
let saved;routes.set('/hazardous/installations/installation-a/records',(path,opt)=>{saved={...JSON.parse(opt.body),record_id:'record-a',status:'draft',version:1,sources:{},source_snapshot:{}};return response(saved);});routes.set('/hazardous/installations/installation-a',()=>response({...installation,evidence_records:[saved]}));
await evaluate('hazardousRecordForm(installation)');assert.equal(nodes.get('hazardousSave').disabled,false);
for(const [kind,id] of [['documents','doc-a'],['legal','legal-a'],['inspections','inspection-a'],['violations','case-a']]){nodes.get('hazardousPicker_'+kind+'_choice').value=id;await nodes.get('hazardousPicker_'+kind+'_select').onclick();}
for(const [key,value] of Object.entries({kind:'notification',title:'Synthetic notification',reference_no:'SYN-1',recorded_on:'2026-10-01',due_on:'2026-10-31',notes:'Synthetic'}))nodes.get('hazardousField_'+key).value=value;
await nodes.get('hazardousForm').onsubmit({preventDefault(){}});assert.equal(saved.expected_installation_version,1);assert.deepEqual(saved.document_ids,['doc-a']);assert.deepEqual(saved.legal_source_version_ids,['legal-a']);assert.deepEqual(saved.inspection_ids,['inspection-a']);assert.deepEqual(saved.violation_case_ids,['case-a']);
for(const kind of ['documents','inspections','violations'])assert(calls.some(call=>call.path.startsWith('/hazardous/sources/'+kind+'?')&&call.path.includes('building_id=building-a')));
assert(nodes.get('hazardousContent').innerHTML.includes('Synthetic notification'));
''')


def test_initial_request_failure_is_visible(tmp_path):
    run(tmp_path, r'''
routes.set('/hazardous/installations?',()=>new Response('{"detail":"Synthetic unavailable"}',{status:503}));await evaluate('hazardousAction(openHazardous)');assert(nodes.get('hazardousMessage')?.textContent.includes('Synthetic unavailable'));
''')


def test_related_violation_open_cannot_create_modal_after_hazardous_close(tmp_path):
    # Depends on PR68's real optional isCurrent contract. Before integrating that
    # dependency, point FIRE_AI_TEST_VIOLATIONS_SOURCE at its actual module file.
    run(tmp_path, r'''
vm.runInContext(fs.readFileSync(process.argv[4],'utf8'),context);await evaluate('openHazardous()');
const button=new Node();button.dataset.hazardousViolation='case-a';document.querySelectorAll=selector=>selector==='[data-hazardous-violation]'?[button]:[];
context.installation=installation;context.record={record_id:'record-a'};evaluate('hazardousBindSources(installation,record,hazardousTicket())');
const original=context.api;let count=0,release;context.api=async(path,opt)=>path==='/auth/permissions'&&++count===2?new Promise(resolve=>release=resolve):original(path,opt);
const pending=button.onclick();await turn();assert(release,'related module initialization must be pending');evaluate('closeHazardous()');release({permissions:authority.permissions});await pending;assert(!nodes.get('violationModal'),'a closed originating view must not create a related modal');
''')


def test_successful_confirmation_followed_by_detail_failure_has_read_only_recovery(tmp_path):
    run(tmp_path, r'''
context.installation=installation;context.record={record_id:'record-a',title:'Synthetic draft',version:1};
routes.set('/hazardous/installations/installation-a/records/record-a/confirm',()=>response({...context.record,status:'confirmed'}));routes.set('/hazardous/installations/installation-a',()=>new Response('{"detail":"Synthetic detail unavailable"}',{status:503}));
await evaluate('hazardousDecision(installation,record,"confirm")');nodes.get('hazardousField_reason').value='Human confirmation';nodes.get('hazardousField_human_acknowledged').checked=true;await nodes.get('hazardousForm').onsubmit({preventDefault(){}});
assert(nodes.get('hazardousMessage').textContent.includes('Synthetic detail unavailable'));assert(nodes.get('hazardousContent').innerHTML.includes('完了'));assert(!nodes.get('hazardousContent').innerHTML.includes('<form'));assert(nodes.get('hazardousSavedReload'));
routes.set('/hazardous/installations/installation-a',()=>response({...installation,evidence_records:[{...context.record,status:'confirmed',sources:{},source_snapshot:{},confirmation_current:true}]}));await nodes.get('hazardousSavedReload').onclick();assert(nodes.get('hazardousContent').innerHTML.includes('現行の事実'));assert.equal(calls.filter(x=>x.path.endsWith('/confirm')&&x.opt.method==='POST').length,1);
''')


def test_original_upload_blocks_early_save_and_attaches_original_before_unlocking(tmp_path):
    run(tmp_path, r'''
context.installation=installation;await evaluate('hazardousRecordForm(installation)');
for(const [key,value] of Object.entries({kind:'permit',title:'Synthetic permit',recorded_on:'2026-10-01'}))nodes.get('hazardousField_'+key).value=value;
const file=new Blob(['Synthetic original'],{type:'text/plain'});file.name='synthetic-original.txt';nodes.get('hazardousUploadFile').files=[file];
let release,saved;routes.set('/documents/upload',()=>new Promise(resolve=>release=resolve));routes.set('/hazardous/installations/installation-a/records',(path,opt)=>{saved={...JSON.parse(opt.body),record_id:'record-a',status:'draft',version:1,sources:{},source_snapshot:{}};return response(saved);});routes.set('/hazardous/installations/installation-a',()=>response({...installation,evidence_records:[saved]}));
const upload=nodes.get('hazardousUpload').onclick();await turn();assert.equal(nodes.get('hazardousSave').disabled,true);assert(nodes.get('hazardousFormStatus').textContent.includes('登録中'));await nodes.get('hazardousForm').onsubmit({preventDefault(){}});assert(!saved,'save must not race the original upload');
release(new Response('{"detail":"Synthetic upload failure"}',{status:503}));await upload;assert.equal(nodes.get('hazardousSave').disabled,false);assert.equal(nodes.get('hazardousUploadFile').files[0],file);assert.equal(nodes.get('hazardousField_title').value,'Synthetic permit');assert(nodes.get('hazardousMessage').textContent.includes('Synthetic upload failure'));
const retry=nodes.get('hazardousUpload').onclick();await turn();assert.equal(nodes.get('hazardousSave').disabled,true);release(response({document_id:'doc-uploaded',original_filename:'synthetic-original.txt',sha256:'synthetic-hash'}));await retry;assert.equal(nodes.get('hazardousSave').disabled,false);assert(nodes.get('hazardousPicker_documents_selected').innerHTML.includes('synthetic-original.txt'));await nodes.get('hazardousForm').onsubmit({preventDefault(){}});assert.deepEqual(saved.document_ids,['doc-uploaded']);
''')


def test_related_violation_detail_does_not_render_after_target_closes(tmp_path):
    run(tmp_path, r'''
vm.runInContext(fs.readFileSync(process.argv[4],'utf8'),context);await evaluate('openHazardous()');
const button=new Node();button.dataset.hazardousViolation='case-a';document.querySelectorAll=selector=>selector==='[data-hazardous-violation]'?[button]:[];
context.installation=installation;context.record={record_id:'record-a'};evaluate('hazardousBindSources(installation,record,hazardousTicket())');let release;routes.set('/violations/case-a',()=>new Promise(resolve=>release=resolve));
const pending=button.onclick();await turn();assert(release,'related detail must be pending');nodes.get('violationClose').onclick();release(response({case_id:'case-a',possible_issue:'STALE PRIVATE CASE',status:'candidate',missing_information:[],confirmation_steps:[],measures:[],corrections:[]}));await pending;assert(!nodes.get('violationContent').innerHTML.includes('STALE PRIVATE CASE'));assert(nodes.get('hazardousModal'),'cancelled related navigation must preserve the originating view');
''')


def test_post_save_failure_does_not_replace_a_newer_navigation(tmp_path):
    run(tmp_path, r'''
context.installation=installation;context.record={record_id:'record-a',title:'Synthetic draft',version:1};let release;
routes.set('/hazardous/installations/installation-a/records/record-a/confirm',()=>response({...context.record,status:'confirmed'}));routes.set('/hazardous/installations/installation-a',()=>new Promise(resolve=>release=resolve));
await evaluate('hazardousDecision(installation,record,"confirm")');nodes.get('hazardousField_reason').value='Human confirmation';nodes.get('hazardousField_human_acknowledged').checked=true;const submit=nodes.get('hazardousForm').onsubmit({preventDefault(){}});await turn();assert(release);
await evaluate('hazardousList()');const current=nodes.get('hazardousContent').innerHTML;release(new Response('{"detail":"Obsolete saved detail failure"}',{status:503}));await submit;assert.equal(nodes.get('hazardousContent').innerHTML,current);assert(!nodes.get('hazardousMessage').textContent.includes('Obsolete'));
''')


def test_deadline_refresh_removes_obsolete_buttons_until_current_results_render(tmp_path):
    run(tmp_path, r'''
const deadline={...installation,title:'Same synthetic deadline',due_on:'2026-10-10',status:'draft'};
let visibleButton;
document.querySelectorAll=selector=>{
 if(selector!=='[data-hazardous-installation]'||!nodes.get('hazardousContent')?.innerHTML.includes('data-hazardous-installation'))return [];
 visibleButton=new Node();visibleButton.dataset.hazardousInstallation='installation-a';nodes.get('hazardousContent').children.push(visibleButton);return [visibleButton];
};
routes.set('/hazardous/deadlines?',()=>response([deadline]));routes.set('/hazardous/installations/installation-a',()=>response(installation));await evaluate('hazardousDeadlines()');const obsoleteButton=visibleButton;
let release;routes.set('/hazardous/deadlines?',()=>new Promise(resolve=>release=resolve));nodes.get('hazardousDueBefore').value='2026-10-11';const refresh=nodes.get('hazardousDueSearch').onclick();await turn();assert(release);
await obsoleteButton.onclick();assert(!calls.some(call=>call.path==='/hazardous/installations/installation-a'),'the previous button owner is already invalid');
assert(!nodes.get('hazardousContent').innerHTML.includes('data-hazardous-installation'),'obsolete visible controls must disappear as soon as their ownership expires');assert.equal(obsoleteButton.isConnected,false);assert(nodes.get('hazardousContent').innerHTML.includes('読込中'));
release(response([deadline]));await refresh;assert(nodes.get('hazardousContent').innerHTML.includes('Same synthetic deadline'));await visibleButton.onclick();assert(nodes.get('hazardousContent').innerHTML.includes('id="hazardousEdit"'));
''')


def test_failed_view_read_retries_same_filter_without_restoring_obsolete_controls(tmp_path):
    run(tmp_path, r'''
routes.set('/hazardous/deadlines?',()=>response([{...installation,title:'Obsolete deadline',due_on:'2026-10-10',status:'draft'}]));await evaluate('hazardousDeadlines()');
routes.set('/hazardous/deadlines?',()=>new Response('{"detail":"Synthetic deadlines unavailable"}',{status:503}));nodes.get('hazardousDueBefore').value='2026-10-11';await nodes.get('hazardousDueSearch').onclick();
assert(nodes.get('hazardousMessage').textContent.includes('Synthetic deadlines unavailable'));assert(!nodes.get('hazardousContent').innerHTML.includes('Obsolete deadline'));assert(!nodes.get('hazardousContent').innerHTML.includes('読込中'));assert(nodes.get('hazardousReadRetry'));
routes.set('/hazardous/deadlines?',()=>response([{...installation,title:'Recovered current deadline',due_on:'2026-10-10',status:'draft'}]));await nodes.get('hazardousReadRetry').onclick();
assert(nodes.get('hazardousContent').innerHTML.includes('Recovered current deadline'));const reads=calls.filter(call=>call.path.startsWith('/hazardous/deadlines?'));assert(reads.at(-1).path.includes('due_before=2026-10-11'));assert(!nodes.get('hazardousLoading'));
''')


def test_evaluation_source_permission_loss_cancels_delayed_body(tmp_path):
    run(tmp_path, r'''
authority.permissions.push('legal_rule.read','legal_rule.evaluate');await evaluate('openHazardous()');
const candidate={evaluation_id:'evaluation-a',installation_id:'installation-a',status:'candidate',version:1,evaluation_date:'2026-10-09',coverage_status:'unavailable',formal_decision:false,is_stale:false,input_snapshot:{installation,profile:{name:'Synthetic profile'}},results:[],rules_snapshot:[]};
let release;routes.set('/hazardous/evaluations/evaluation-a',()=>new Response(new ReadableStream({start(controller){release=()=>{controller.enqueue(new TextEncoder().encode(JSON.stringify(candidate)));controller.close();};}})));
const pending=evaluate('hazardousEvaluationDetail("evaluation-a")');await turn();
authority={...authority,permissions:authority.permissions.filter(p=>p!=='document.read')};
release();await assert.rejects(pending,e=>e.cancelled);assert.equal(resetCount,1);assert(!nodes.get('hazardousModal'));
''')
