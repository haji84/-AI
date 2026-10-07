"""Home-panel behavior with the production session guard and native Response bodies.

Only the DOM and HTTP transport are synthetic. The browser journey separately
checks this contract in Chromium against the real application and database.
"""
import json
from pathlib import Path
import subprocess

import pytest


ROOT = Path(__file__).resolve().parents[2]


def run_ui(body, modules=()):
    module = ROOT / 'frontend/work-queue.js'
    assert module.exists(), 'The shared-shell personal work queue has not been implemented'
    harness = r'''
const assert=require('node:assert/strict'),vm=require('node:vm');
const nodes={},handlers={},windowHandlers={};let children=[];
function element(id,attrs=''){
 const classes=new Set(attrs.includes('hidden')?['hidden']:[]);
 return {id,disabled:/\bdisabled\b/.test(attrs),value:'',isConnected:true,textContent:'',dataset:{},
  classList:{add:n=>classes.add(n),remove:n=>classes.delete(n),contains:n=>classes.has(n),toggle(n,yes){if(yes)classes.add(n);else classes.delete(n)}},
  setAttribute(name,value){this[name]=String(value)},
  closest(selector){if(selector==='#loginView')return null;if(selector==='#workQueuePanel')return this===nodes.workQueuePanel||children.includes(this)?nodes.workQueuePanel:null;if(selector==='header')return this===nodes.workQueueBtn||this===nodes.otherHeader?{}:null;return this},
  _html:'',get innerHTML(){return this._html},set innerHTML(html){
   this._html=html;
   if(id!=='workQueuePanel')return;
   for(const child of children){child.isConnected=false;if(child.id)delete nodes[child.id]}children=[];
   for(const match of html.matchAll(/<(button|select|div|p|span|section|article)\b([^>]*)>/g)){
    const attrs=match[2],key=attrs.match(/\bid="([^"]+)"/)?.[1];
    const source=attrs.match(/data-work-queue-open="([^"]+)"/)?.[1];
    if(!key&&source===undefined)continue;
    const child=element(key??'',attrs);child.tagName=match[1].toUpperCase();
    if(source!==undefined)child.dataset.workQueueOpen=source;
    children.push(child);if(key)nodes[key]=child;
   }
  },querySelectorAll(selector){return children.filter(n=>selector==='[data-work-queue-open]'?n.dataset.workQueueOpen!==undefined:selector==='button, select'?['BUTTON','SELECT'].includes(n.tagName):false)}
 };
}
nodes.workQueuePanel=element('workQueuePanel','hidden');nodes.workQueueBtn=element('workQueueBtn','hidden');nodes.otherHeader=element('otherHeader');
let authority={user_id:'synthetic-user',session_id:'session-a',tenant_id:'tenant-a',permissions:['asset.read','asset.borrower.read','fleet.read','violation.read','inquiry.read']};
let endpoint=async()=>envelope(),requests=[],resetCount=0;
let authorityEndpoint=async()=>new Response(JSON.stringify(authority));
function envelope(items=[],extra={}){return {schema_version:'work-queue-v1',as_of:'2026-10-07',through:'2026-11-06',business_timezone:'Asia/Tokyo',scope:'all',limit:50,offset:0,total:items.length,counts:{},items,...extra}}
function card(extra={}){return {key:'asset:synthetic-asset:calibration',module:'operational_assets',kind:'calibration',title:'Synthetic calibration',source_type:'operational_asset',source_id:'synthetic-asset',source_version:2,status:'due',due_on:'2026-10-06',overdue:true,relationships:['available_to_my_role','shared_deadline'],required_permissions:['asset.read'],navigation:{surface:'asset',id:'synthetic-asset'},provenance:{source_api:'/assets/alerts',as_of:'2026-10-07'},...extra}}
const document={addEventListener(name,fn){(handlers[name]??=[]).push(fn)},visibilityState:'visible',querySelectorAll:selector=>nodes.workQueuePanel.querySelectorAll(selector)};
const window={location:{origin:'http://synthetic.local'},addEventListener(name,fn){(windowHandlers[name]??=[]).push(fn)},removeEventListener(name,fn){windowHandlers[name]=(windowHandlers[name]??[]).filter(handler=>handler!==fn)},fetch:async(path,options)=>{
 if(path==='/auth/context')return authorityEndpoint();
 requests.push(String(path));const value=await endpoint(String(path),options);return value instanceof Response?value:new Response(JSON.stringify(value));
}};
const context={window,document,URL,URLSearchParams,Response,WeakSet,Event,console,$:id=>nodes[id],esc:value=>String(value??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c])),fetch:(...args)=>window.fetch(...args)};vm.createContext(context);
function run(source){return vm.runInContext(source,context)}
const flush=()=>new Promise(resolve=>setImmediate(resolve));
const sourceButtons=()=>children.filter(node=>node.dataset.workQueueOpen!==undefined);
async function click(node){
 const pending=[];
 async function dispatch(){
  const event={type:'click',target:node,preventDefault(){},stopImmediatePropagation(){this.stopped=true}};
  for(const handler of [...windowHandlers.click??[]]){await handler(event);if(event.stopped)return}
  for(const handler of handlers.click??[]){await handler(event);if(event.stopped)return}
  if(!node.disabled&&node.isConnected)return node.onclick?.();
 }
 node.click=()=>{const task=dispatch();pending.push(task);return task};
 await node.click();while(pending.length)await Promise.all(pending.splice(0));
}
'''
    # Use exactly the shell's API implementation, including cancelled-body errors.
    api_line = next(line for line in (ROOT / 'frontend/index.html').read_text().splitlines()
                    if line.startswith('async function api('))
    script = harness + '\n'.join(
        f'vm.runInContext({json.dumps(source)},context);'
        for source in [(ROOT / 'frontend/shared-session.js').read_text(), api_line,
                       *((ROOT / 'frontend' / name).read_text() for name in modules), module.read_text()]
    ) + r'''
window.FireAISession.install({reset(){resetCount++;run('clearWorkQueue()')}});
async function main(){
''' + body + r'''
}let completed=false;main().then(()=>{completed=true}).catch(error=>{completed=true;console.error(error);process.exitCode=1});
process.on('beforeExit',()=>{if(!completed){console.error('UI scenario did not finish');process.exitCode=1}});
'''
    result = subprocess.run(['node', '-e', script], capture_output=True, text=True, timeout=20)
    assert result.returncode == 0, result.stderr


def test_loading_cards_escaped_relationships_and_server_business_date():
    # Raw HTML, invented assignment, or deriving "today" from the browser fails this.
    run_ui(r'''
await run('initWorkQueue()');assert.equal(nodes.workQueueBtn.classList.contains('hidden'),false);
let release;endpoint=()=>new Promise(resolve=>release=resolve);
const loading=run('openWorkQueue()');await flush();
assert.equal(nodes.workQueuePanel.classList.contains('hidden'),false);
assert.match(nodes.workQueuePanel.innerHTML,/読み込み中/);
release(envelope([card({title:'<img src=x onerror="bad()">',relationships:['created_by_me','borrowed_by_me','available_to_my_role','shared_deadline']})]));await loading;
const html=nodes.workQueuePanel.innerHTML;
assert(html.includes('&lt;img src=x onerror=&quot;bad()&quot;&gt;'));assert(!html.includes('<img'));
for(const label of ['自分が作成','自分が借用','権限に応じた業務','共通の期限','期限超過','2026-10-07','Asia/Tokyo'])assert(html.includes(label),label);
assert(!html.includes('担当者'));assert(!html.includes('割り当て'));assert.equal(sourceButtons().length,1);
assert.equal(nodes.workQueuePrev.disabled,true);assert.equal(nodes.workQueueNext.disabled,true);
''')


def test_scope_pagination_refresh_empty_and_failed_fetch_are_distinct():
    # Stale totals/cards on error, wrong offsets, or losing related scope fails this.
    run_ui(r'''
endpoint=async path=>{const query=new URL(path,window.location.origin).searchParams;const offset=Number(query.get('offset'));return envelope(Array.from({length:offset?1:50},(_,i)=>card({key:'key-'+(offset+i)})),{total:51,offset,scope:query.get('scope')})};
await run('openWorkQueue()');assert.equal(nodes.workQueueNext.disabled,false);
await nodes.workQueueNext.onclick();assert.equal(new URL(requests.at(-1),window.location.origin).searchParams.get('offset'),'50');assert.equal(nodes.workQueueNext.disabled,true);assert.equal(nodes.workQueuePrev.disabled,false);
await nodes.workQueuePrev.onclick();assert.equal(new URL(requests.at(-1),window.location.origin).searchParams.get('offset'),'0');
nodes.workQueueScope.value='related';await nodes.workQueueScope.onchange();let query=new URL(requests.at(-1),window.location.origin).searchParams;assert.equal(query.get('scope'),'related');assert.equal(query.get('offset'),'0');
endpoint=async()=>new Response('{"detail":"Synthetic backend unavailable"}',{status:503});await nodes.workQueueRefresh.onclick();
assert.match(nodes.workQueuePanel.innerHTML,/取得できません/);assert.match(nodes.workQueuePanel.innerHTML,/Synthetic backend unavailable/);assert(!nodes.workQueuePanel.innerHTML.includes('対象の業務はありません'));assert.equal(sourceButtons().length,0);
endpoint=async()=>envelope([],{scope:'related'});await nodes.workQueueRefresh.onclick();assert.match(nodes.workQueuePanel.innerHTML,/対象の業務はありません/);assert(!nodes.workQueuePanel.innerHTML.includes('取得できません'));assert.equal(nodes.workQueueScope.value,'related');
''')


def test_newer_refresh_hide_and_old_errors_cannot_overwrite_current_panel():
    # Removing request ownership lets older data or errors replace the fresh result.
    run_ui(r'''
await run('initWorkQueue()');
let releases=[];endpoint=()=>new Promise((resolve,reject)=>releases.push({resolve,reject}));
const old=run('openWorkQueue()');await flush();const fresh=nodes.workQueueRefresh.onclick();await flush();
releases[1].resolve(envelope([card({title:'Fresh current card'})]));await fresh;
releases[0].resolve(envelope([card({title:'Stale old card'})]));await old;
assert(nodes.workQueuePanel.innerHTML.includes('Fresh current card'));assert(!nodes.workQueuePanel.innerHTML.includes('Stale old card'));
const hidden=nodes.workQueueRefresh.onclick();await flush();run('hideWorkQueue()');releases[2].resolve(envelope([card({title:'Hidden private card'})]));await hidden;
assert.equal(nodes.workQueuePanel.innerHTML,'');assert.equal(nodes.workQueuePanel.classList.contains('hidden'),true);assert.equal(nodes.workQueueBtn.classList.contains('hidden'),false);
const failedOld=run('openWorkQueue()');await flush();run('clearWorkQueue()');const reopened=run('openWorkQueue()');await flush();
releases[4].resolve(envelope([card({title:'Reopened current card'})]));await reopened;releases[3].reject(Object.assign(new Error('late old 401'),{status:401}));await failedOld;
assert(nodes.workQueuePanel.innerHTML.includes('Reopened current card'));assert.equal(nodes.workQueuePanel.classList.contains('hidden'),false);
''')


@pytest.mark.parametrize('authority_change', [
    "{...authority,user_id:'different-user'}",
    "{...authority,session_id:'session-b'}",
    "{...authority,tenant_id:'tenant-b'}",
    "{...authority,permissions:['inquiry.read']}",
])
def test_real_shared_session_clears_delayed_body_on_authority_change(authority_change):
    # A same-user new session and rights/tenant changes must be as strong as logout.
    run_ui(r'''
endpoint=async()=>envelope([card({title:'Old private card'})]);await run('openWorkQueue()');
let release;endpoint=async()=>new Response(new ReadableStream({start(controller){release=()=>{controller.enqueue(new TextEncoder().encode(JSON.stringify(envelope([card({title:'Late private card'})]))));controller.close()}}}));
const delayed=nodes.workQueueRefresh.onclick();await flush();
''' + f'authority={authority_change};' + r'''
release();await delayed;assert.equal(resetCount,1);assert.equal(nodes.workQueuePanel.innerHTML,'');assert.equal(nodes.workQueuePanel.classList.contains('hidden'),true);assert.equal(nodes.workQueueBtn.classList.contains('hidden'),true);
assert.equal(run('workQueueState.data'),null);
''')


def test_source_navigation_is_allowlisted_and_rechecks_cached_authority():
    # Dispatching an arbitrary server function/URL, wrong source ID, or a cached
    # source action after revocation fails this test.
    run_ui(r'''
const opened=[];
for(const [surface,open,detail,modal,action] of [['asset','openAssets','assetsDetail','assetsModal','assetsAction'],['vehicle','openOperations','operationsVehicleDetail','operationsModal','operationsAction'],['violation','openViolations','violationDetail','violationModal','violationAction'],['inquiry','openInquiries','inquiryDetail','inquiryModal','inquiryAction']]){
 context[open]=async()=>{opened.push(open);nodes[modal]=element(modal)};context[detail]=async id=>opened.push([detail,id]);context[action]=async fn=>fn();
 endpoint=async()=>envelope([card({navigation:{surface,id:'specific-source'}})]);await run('openWorkQueue()');await sourceButtons()[0].onclick();
 assert.deepEqual(opened.splice(0),[open,[detail,'specific-source']]);
}
for(const navigation of [{surface:'javascript:bad()',id:'x'},{surface:'asset',id:'../../auth/logout'},{surface:'asset',id:'" onclick="bad()'}]){
 endpoint=async()=>envelope([card({navigation})]);await run('openWorkQueue()');assert.equal(sourceButtons().filter(x=>!x.disabled).length,0);assert.equal(opened.length,0);
}
endpoint=async()=>envelope([card()]);await run('openWorkQueue()');const cached=sourceButtons()[0];authority={...authority,permissions:[]};await click(cached);await flush();
assert.equal(opened.length,0);assert.equal(nodes.workQueuePanel.innerHTML,'');assert.equal(resetCount,1);
''')


def test_closed_or_superseded_source_open_cannot_jump_to_late_detail():
    # A module's asynchronous list completion must not reopen the selected record
    # after Close, a newer queue navigation, or a shared-shell reset.
    run_ui(r'''
let release,details=0;context.openAssets=async()=>{nodes.assetsModal=element('assetsModal');await new Promise(resolve=>release=resolve)};context.assetsDetail=async()=>details++;context.assetsAction=async fn=>fn();
endpoint=async()=>envelope([card()]);await run('openWorkQueue()');
const opening=sourceButtons()[0].onclick();await flush();nodes.assetsModal.classList.add('hidden');release();await opening;assert.equal(details,0);
await run('openWorkQueue()');const old=sourceButtons()[0].onclick();await flush();run('hideWorkQueue()');release();await old;assert.equal(details,0);
''')


def test_home_replaces_facility_pane_and_owns_main_navigation():
    # Home must hide the facility placeholder/detail and invalidate pending detail.
    run_ui(r'''
nodes.noSelection=element('noSelection');nodes.detailView=element('detailView');
let navigation=0;window.beginMainNavigation=()=>++navigation;
await run('openWorkQueue()');
assert.equal(navigation,1);assert.equal(nodes.noSelection.classList.contains('hidden'),true);assert.equal(nodes.detailView.classList.contains('hidden'),true);
''')


def test_shrinking_source_result_does_not_claim_zero_tasks_on_empty_later_page():
    # Sources can close between pages; an empty page is not an empty whole queue.
    run_ui(r'''
endpoint=async()=>envelope(Array.from({length:50},()=>card()),{total:51});await run('openWorkQueue()');
endpoint=async()=>envelope([],{total:20,offset:50});await nodes.workQueueNext.onclick();
assert(!nodes.workQueuePanel.innerHTML.includes('対象の業務はありません。'));assert.match(nodes.workQueuePanel.innerHTML,/このページの業務はありません/);assert.equal(nodes.workQueuePrev.disabled,false);
''')


@pytest.mark.parametrize('mutation', [
    "modal.isConnected=false;delete nodes.assetsModal;",
    "nodes.assetsModal=element('assetsModal');",
])
def test_delayed_authority_check_requires_the_exact_live_source_modal(mutation):
    # A stale connected-looking reference is insufficient after modal replacement.
    run_ui(r'''
let release,details=0;context.assetsAction=async fn=>fn();context.assetsDetail=async()=>details++;
context.openAssets=async()=>{nodes.assetsModal=element('assetsModal');let first=true;authorityEndpoint=async()=>{if(!first)return new Response(JSON.stringify(authority));first=false;return new Promise(resolve=>release=()=>resolve(new Response(JSON.stringify(authority))))}};
endpoint=async()=>envelope([card()]);await run('openWorkQueue()');
const opening=sourceButtons()[0].onclick();await flush();assert(release,'real SharedSession check was not pending');const modal=nodes.assetsModal;
''' + mutation + r'''
release();await opening;assert.equal(details,0,'delayed queue detail took over the replacement/removed modal');assert.equal(run('workQueueState.opening'),false);
''')


@pytest.mark.parametrize('phase', ['open', 'check'])
@pytest.mark.parametrize('new_action', ['close_reopen', 'another_record'])
def test_newer_module_action_cancels_queued_detail_during_open_or_check(phase, new_action):
    # Window capture must see the new intent before SharedSession's asynchronous
    # document guard redispatches it, even if the modal becomes visible again.
    run_ui(r'''
let release,details=0,view='queue-opening';context.assetsAction=async fn=>fn();context.assetsDetail=async()=>{details++;view='stale-queue-record'};
context.openAssets=async()=>{nodes.assetsModal=element('assetsModal');
''' + (r'''
await new Promise(resolve=>release=resolve);
''' if phase == 'open' else r'''
let first=true;authorityEndpoint=async()=>{if(!first)return new Response(JSON.stringify(authority));first=false;return new Promise(resolve=>release=()=>resolve(new Response(JSON.stringify(authority))))};
''') + r'''
};endpoint=async()=>envelope([card()]);await run('openWorkQueue()');
const opening=sourceButtons()[0].onclick();await flush();assert(release,'source open/check was not pending');
const newer=element('moduleNavigation');newer.onclick=()=>{
''' + (r'''
nodes.assetsModal.classList.add('hidden');nodes.assetsModal.classList.remove('hidden');view='reopened-list';
''' if new_action == 'close_reopen' else "view='newer-record';") + r'''
};await click(newer);assert.notEqual(view,'queue-opening','actual guarded newer click did not finish');const expected=view;
release();await opening;assert.equal(details,0,'queued source detail beat newer module navigation');assert.equal(view,expected);assert.equal(run('workQueueState.opening'),false);
assert.equal((windowHandlers.click??[]).length,0,'temporary navigation listener leaked');
''')


def test_violation_source_open_uses_the_canonical_module_action_guard():
    run_ui(r'''
let depth=0;context.violationAction=async fn=>{depth++;try{return await fn()}finally{depth--}};
context.openViolations=async()=>{assert(depth>0,'violation opening bypassed the canonical action guard');nodes.violationModal=element('violationModal')};
let opened=false;context.violationDetail=async()=>{assert(depth>0);opened=true};
endpoint=async()=>envelope([card({navigation:{surface:'violation',id:'specific-case'}})]);await run('openWorkQueue()');await sourceButtons()[0].onclick();assert.equal(opened,true);
''')


def test_late_login_initialization_does_not_replace_newer_main_navigation():
    # Removing the shell's login navigation ticket makes the delayed default
    # Home overwrite a facility or Home the user opened while modules initialized.
    shell = (ROOT / 'frontend/index.html').read_text()
    login = next(line for line in shell.splitlines() if line.startswith('async function login('))
    if 'initWorkQueue' not in login:
        pytest.skip('The frontend-only task branch does not contain lead-owned login wiring')
    generation = next(line for line in shell.splitlines() if line.startswith('let mainNavigationGeneration='))
    navigate = next(line for line in shell.splitlines() if line.startswith('function beginMainNavigation('))
    script = r'''
const assert=require('node:assert/strict'),vm=require('node:vm');
const nodes={};const node=id=>nodes[id]??=( {value:'synthetic',textContent:'',classList:{add(){},remove(){},toggle(){}}} );
let release,opened=0;
const context={console,$:node,api:async()=>({permissions:[]}),initEmergency:()=>new Promise(resolve=>release=resolve),openWorkQueue:async()=>opened++};
for(const name of ['initOperations','initAssets','initFinance','initWorkforce','initViolations','initInquiries','initHazardous','initStatistics','loadFacilities','initWorkQueue'])context[name]=async()=>{};
vm.createContext(context);
''' + '\n'.join(f'vm.runInContext({json.dumps(source)},context);' for source in [generation, navigate, login]) + r'''
async function main(){
 const pending=vm.runInContext('login()',context);await new Promise(resolve=>setImmediate(resolve));assert(release);
 vm.runInContext('beginMainNavigation()',context);release();await pending;
 assert.equal(opened,0,'late login replaced the newer main-pane navigation');
 const ordinary=vm.runInContext('login()',context);await new Promise(resolve=>setImmediate(resolve));release();await ordinary;
 assert.equal(opened,1,'uninterrupted login did not open the default Home');
}main().catch(error=>{console.error(error);process.exitCode=1});
'''
    result = subprocess.run(['node', '-e', script], capture_output=True, text=True, timeout=20)
    assert result.returncode == 0, result.stderr


REAL_MODULE_SETUP = r'''
for(const id of ['assetsModal','assetsBtn','assetsMessage','assetsContent','assetsNav','assetsQ','assetsLotQ','assetsPrev','assetsNext',
 'operationsModal','operationsBtn','operationsMessage','operationsContent','operationsNav','operationsQ','operationsPrev','operationsNext',
 'violationModal','violationBtn','violationMessage','violationContent','violationNav','violationQ','violationPrev','violationNext',
 'inquiryModal','inquiriesBtn','inquiryMessage','inquiryContent','inquiryResults','inquiryYear','inquiryQuery','inquiryPrev','inquiryNext','inquiryCandidateContent'])nodes[id]=element(id);
const asset={asset_id:'synthetic-asset',code:'OLD-QUEUE',name:'Delayed queue record',category:'durable',unit:'piece',reorder_threshold:0,active:true};
const vehicle={vehicle_id:'synthetic-vehicle',code:'OLD-VEHICLE',name:'Delayed vehicle',active:true,odometer:0,fuel_stock:0};
const violation={case_id:'synthetic-case',possible_issue:'Delayed violation',status:'confirmed',missing_information:[],confirmation_steps:[],measures:[],corrections:[]};
const inquiry={inquiry_id:'synthetic-inquiry',question:'Delayed inquiry',year:2026,status:'draft',version:1,draft:'',claims:[],evidence:[],provenance:{}};
const candidate={candidate_id:'synthetic-candidate',draft:'Delayed candidate',model:'synthetic',model_version:'1',input_provenance:{}};
async function ordinary(path){
 if(path==='/auth/me')return {user_id:authority.user_id};
 if(path==='/auth/permissions')return {permissions:authority.permissions};
 if(path.startsWith('/work-queue?'))return envelope([card()]);
 if(path==='/assets/registry/synthetic-asset')return asset;
 if(path==='/assets/registry/synthetic-asset/history')return {services:[],movements:[]};
 if(path==='/operations/vehicles/synthetic-vehicle')return vehicle;
 if(path==='/operations/vehicles/synthetic-vehicle/history')return {trips:[],fuel:[],services:[]};
 if(path==='/violations/synthetic-case')return violation;
 if(path==='/inquiries/synthetic-inquiry')return inquiry;
 if(path==='/inquiries/synthetic-inquiry/candidates')return [candidate];
 return [];
}
endpoint=ordinary;
'''


def test_actual_asset_detail_cannot_overwrite_a_newer_guarded_list():
    run_ui(REAL_MODULE_SETUP + r'''
let release;endpoint=async path=>path==='/assets/registry/synthetic-asset'?new Promise(resolve=>release=()=>resolve(asset)):ordinary(path);
await run('openWorkQueue()');const old=sourceButtons()[0].onclick();await flush();assert(release,'actual asset detail did not start');
nodes.otherHeader.onclick=()=>run('assetsAction(()=>assetsList())');await click(nodes.otherHeader);
assert(nodes.assetsContent.innerHTML.includes('assetsSearch'));release();await old;
assert(!nodes.assetsContent.innerHTML.includes('Delayed queue record'),'old actual detail overwrote the newer list');assert.equal(run('assetsState.asset'),null);
''', modules=('assets.js',))


@pytest.mark.parametrize('module,surface,modal,state', [
    ('assets.js', 'asset', 'assetsModal', 'assetsState'),
    ('operations.js', 'vehicle', 'operationsModal', 'operationsState'),
    ('violations.js', 'violation', 'violationModal', 'violationState'),
    ('inquiries.js', 'inquiry', 'inquiryModal', 'inquiryState'),
])
def test_actual_source_open_cannot_reappear_after_newer_home(module, surface, modal, state):
    run_ui(REAL_MODULE_SETUP + f"nodes.{modal}.classList.add('hidden');\n" + r'''
let release,first=true;endpoint=async path=>{if(path==='/auth/permissions'&&first){first=false;return new Promise(resolve=>release=()=>resolve({permissions:authority.permissions}))}return path.startsWith('/work-queue?')?envelope([card({navigation:{surface:SURFACE,id:'synthetic-asset'}})]):ordinary(path)};
await run('openWorkQueue()');const old=sourceButtons()[0].onclick();await flush();assert(release,'actual module permission request did not start');
nodes.otherHeader.onclick=()=>run('openWorkQueue()');await click(nodes.otherHeader);release();await old;
'''.replace('SURFACE', json.dumps(surface)) + f"assert.equal(nodes.{modal}.classList.contains('hidden'),true,'old module opened after newer Home');assert.equal(run('{state}.permissions.length'),0);\n",
           modules=(module,))


@pytest.mark.parametrize('module,call,path,content', [
    ('assets.js', "assetsDetail('synthetic-asset','',()=>allowed)", '/assets/registry/synthetic-asset', 'assetsContent'),
    ('assets.js', "assetsDetail('synthetic-asset','',()=>allowed)", '/assets/registry/synthetic-asset/history', 'assetsContent'),
    ('operations.js', "operationsVehicleDetail('synthetic-vehicle',()=>allowed)", '/operations/vehicles/synthetic-vehicle', 'operationsContent'),
    ('operations.js', "operationsVehicleDetail('synthetic-vehicle',()=>allowed)", '/operations/vehicles/synthetic-vehicle/history', 'operationsContent'),
    ('violations.js', "violationDetail('synthetic-case',()=>allowed)", '/violations/synthetic-case', 'violationContent'),
    ('inquiries.js', "inquiryDetail('synthetic-inquiry',()=>allowed)", '/inquiries/synthetic-inquiry', 'inquiryContent'),
    ('inquiries.js', "inquiryDetail('synthetic-inquiry',()=>allowed)", '/inquiries/synthetic-inquiry/candidates', 'inquiryCandidateContent'),
])
def test_actual_detail_continuations_honor_source_ownership(module, call, path, content):
    run_ui(REAL_MODULE_SETUP + r'''
context.allowed=true;let release;endpoint=async path=>path===DELAYED?new Promise(resolve=>release=async()=>resolve(await ordinary(path))):ordinary(path);
'''.replace('DELAYED', json.dumps(path)) +
           ("run(\"violationState.permissions=['violation.read']\");\n" if module == 'violations.js' else '') +
           f"const pending=run({json.dumps(call)});await flush();assert(release,'actual delayed boundary was not reached');\n" +
           f"context.allowed=false;nodes.{content}.innerHTML='Newer module view';await release();await pending;assert.equal(nodes.{content}.innerHTML,'Newer module view');\n",
           modules=(module,))


@pytest.mark.parametrize('module,call,path,content', [
    ('assets.js', 'openAssets(()=>allowed)', '/assets/registry?', 'assetsContent'),
    ('operations.js', 'openOperations(()=>allowed)', '/operations/vehicles?', 'operationsContent'),
    ('violations.js', 'openViolations(()=>allowed)', '/violations?', 'violationContent'),
    ('inquiries.js', 'openInquiries(()=>allowed)', '/inquiries?', 'inquiryResults'),
])
def test_actual_initial_lists_discard_late_owned_results(module, call, path, content):
    run_ui(REAL_MODULE_SETUP + r'''
context.allowed=true;let release;endpoint=async path=>path.startsWith(DELAYED)?new Promise(resolve=>release=()=>resolve([])):ordinary(path);
'''.replace('DELAYED', json.dumps(path)) +
           f"const pending=run({json.dumps(call)});await flush();assert(release,'actual initial list request did not start');\n" +
           f"context.allowed=false;nodes.{content}.innerHTML='Newer initial view';release();await pending;assert.equal(nodes.{content}.innerHTML,'Newer initial view');\n",
           modules=(module,))


def test_actual_violation_guard_preserves_newer_message_after_cancelled_queue_detail():
    run_ui(REAL_MODULE_SETUP + r'''
let release;endpoint=async path=>path==='/violations/synthetic-case'?new Promise(resolve=>release=()=>resolve(violation)):path.startsWith('/work-queue?')?envelope([card({navigation:{surface:'violation',id:'synthetic-case'}})]):ordinary(path);
await run('openWorkQueue()');const old=sourceButtons()[0].onclick();await flush();assert(release);
nodes.otherHeader.onclick=()=>{nodes.violationMessage.textContent='Newer view message'};await click(nodes.otherHeader);release();await old;
assert.equal(nodes.violationMessage.textContent,'Newer view message','old canonical action cleared a newer view message');
''', modules=('violations.js',))
