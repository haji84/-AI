"""Statistics state regressions execute production UI, API and session guards.

Only the DOM and HTTP boundary are synthetic. Metric values are deliberately
beyond JavaScript's exact-number range; changing their rendering to Number fails.
"""
import json
from pathlib import Path
import subprocess

import pytest


ROOT = Path(__file__).resolve().parents[2]


def run_ui(body, modules=()):
    module = ROOT / 'frontend/statistics.js'
    assert module.exists(), 'Observed statistics UI is not implemented'
    harness = r'''
const assert=require('node:assert/strict'),vm=require('node:vm');
const nodes={},handlers={},windowHandlers={};
function element(id='',attrs='',tag='div'){
 const classes=new Set(attrs.match(/class="([^"]*)"/)?.[1].split(' ')??[]);
 const node={id,tagName:tag.toUpperCase(),isConnected:true,children:[],dataset:{},style:{},disabled:/\bdisabled\b/.test(attrs),checked:/\bchecked\b/.test(attrs),value:attrs.match(/value="([^"]*)"/)?.[1]??'',textContent:'',
  classList:{add:n=>classes.add(n),remove:n=>classes.delete(n),contains:n=>classes.has(n),toggle(n,yes){if(yes)classes.add(n);else classes.delete(n)}},
  setAttribute(name,value){this[name]=String(value)},getAttribute(name){return this[name]},
  closest(selector){if(selector==='#loginView')return null;if(selector==='header')return this.header?{}:null;if(selector==='#statisticsModal')return this.id.startsWith('statistics')?nodes.statisticsModal:null;return this},
  append(child){child.parentElement=this;this.children.push(child);if(child.id)nodes[child.id]=child},
  remove(){this.isConnected=false;for(const child of this.children)child.remove();if(nodes[this.id]===this)delete nodes[this.id]},
  _html:'',get innerHTML(){return this._html},set innerHTML(html){this._html=html;for(const child of this.children)child.remove();this.children=[];
   for(const match of html.matchAll(/<(button|input|select|textarea|div|p|span|section|article|form|a)\b([^>]*)>/g)){
    const attrs=match[2],key=attrs.match(/\bid="([^"]+)"/)?.[1];if(!key&&!attrs.includes('data-statistics-'))continue;
    const child=element(key??'',attrs,match[1]);for(const m of attrs.matchAll(/data-([a-z-]+)="([^"]*)"/g))child.dataset[m[1].replace(/-([a-z])/g,(_,x)=>x.toUpperCase())]=m[2];this.append(child);
   }
  },querySelectorAll(selector){const all=this.children.flatMap(c=>[c,...c.querySelectorAll('*')]);if(selector==='*')return all;if(selector==='button, input, select, textarea')return all.filter(c=>['BUTTON','INPUT','SELECT','TEXTAREA'].includes(c.tagName));const data=selector.match(/^\[data-([a-z-]+)\]$/)?.[1];if(data){const key=data.replace(/-([a-z])/g,(_,x)=>x.toUpperCase());return all.filter(c=>c.dataset[key]!==undefined)}return []}
 };if(id)nodes[id]=node;return node;
}
const document={body:element('body'),createElement:tag=>element('', '',tag),getElementById:id=>nodes[id],addEventListener(name,fn){(handlers[name]??=[]).push(fn)},querySelectorAll:selector=>document.body.querySelectorAll(selector),visibilityState:'visible'};
document.body.append(element('statisticsBtn','class="hidden"','button'));
nodes.statisticsBtn.header=true;
let authority={user_id:'synthetic-user',session_id:'a',tenant_id:'hq-a',permissions:['statistics.read','statistics.record','statistics.export','emergency.report.read','incident.aggregate','fleet.aggregate']};
let requests=[],downloads=[],resetCount=0,endpoint=async()=>{throw new Error('unexpected endpoint')};
let authorityEndpoint=async()=>new Response(JSON.stringify(authority));
const window={location:{origin:'http://synthetic.local'},addEventListener(name,fn){(windowHandlers[name]??=[]).push(fn)},removeEventListener(name,fn){windowHandlers[name]=(windowHandlers[name]??[]).filter(x=>x!==fn)},fetch:async(path,options={})=>{
 if(path==='/auth/context')return authorityEndpoint();
 if(path==='/auth/permissions')return new Response(JSON.stringify({permissions:authority.permissions}));
 requests.push({path:String(path),method:options.method??'GET',body:options.body?JSON.parse(options.body):null});
 const result=await endpoint(String(path),options);return result instanceof Response?result:new Response(JSON.stringify(result));
}};
class TestURL extends URL{};TestURL.createObjectURL=blob=>{downloads.push({blob});return 'blob:synthetic'};TestURL.revokeObjectURL=()=>{};
const createElement=document.createElement;document.createElement=tag=>{const e=createElement(tag);if(tag==='a')e.click=()=>{downloads.at(-1).filename=e.download};return e};
const context={window,document,URL:TestURL,URLSearchParams,Response,ReadableStream,TextEncoder,WeakSet,Event,console,$:id=>nodes[id],esc:value=>String(value??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c])),fetch:(...args)=>window.fetch(...args)};vm.createContext(context);
const run=source=>vm.runInContext(source,context),flush=()=>new Promise(resolve=>setImmediate(resolve));
function metric(key='emergency.cases',value='0',extra={}){return {key,label:key,source_module:'emergency',unit:'件',denominator:'not_applicable',date_basis:'EmergencyCase.call_date (DATE)',definition_version:'v1',status:'observed',value,coverage_status:'unknown',exclusions:[{reason:'missing_date',count:2,grain:'case',scope:'department_all_dates'}],limitations:['Legacy timestamps retain their limitations.'],...extra}}
function snapshot(extra={}){return {query_version:'observed-v1',period:{start_date:'2026-01-01',end_date:'2026-01-31',business_timezone:'Asia/Tokyo',start_at_utc:'2025-12-31T15:00:00Z',end_before_utc:'2026-01-31T15:00:00Z',date_basis_version:'local-date-v1'},captured_at:'2026-10-07T09:00:00Z',coverage_status:'unknown',metrics:[metric(),metric('fleet.distance_km','9007199254740993.10'),metric('operations.incidents',null,{status:'unavailable'})],public_checksum:'safe-public-checksum',...extra}}
function report(extra={}){return {report_id:'report-a',version:1,state:'saved',predecessor_id:null,successor_id:null,created_at:'2026-10-07T09:00:00Z',confirmed_at:null,snapshot:snapshot(),...extra}}
function catalog(){return {query_version:'observed-v1',business_timezone:'Asia/Tokyo',coverage_status:'unknown',metrics:snapshot().metrics.map(m=>({...m,available:m.status==='observed'}))}}
function regularEndpoint(path){if(path==='/statistics/metrics')return catalog();if(path==='/statistics/query')return snapshot();if(path==='/statistics/reports')return report();if(path.startsWith('/statistics/reports?'))return {items:[report()],total:1,limit:20,offset:0};if(path.endsWith('/history?limit=20&offset=0'))return {items:[{action:'saved',version:1,occurred_at:'2026-10-07T09:00:00Z'}],total:1,limit:20,offset:0};if(path==='/statistics/reports/report-a')return report();throw new Error('unexpected '+path)}
endpoint=regularEndpoint;
function choose(){nodes.statisticsStart.value='2026-01-01';nodes.statisticsEnd.value='2026-01-31';for(const node of nodes.statisticsContent.querySelectorAll('[data-statistics-metric]'))node.checked=node.dataset.statisticsMetric!=='operations.incidents'}
async function invoke(id){assert(nodes[id],id+' not present');return nodes[id].onclick?.()}
function html(){return nodes.statisticsContent?.innerHTML??''}
async function click(node){if(node.disabled)return;const pending=[];async function dispatch(){const e={type:'click',target:node,preventDefault(){},stopImmediatePropagation(){this.stopped=true}};for(const handler of windowHandlers.click??[]){await handler(e);if(e.stopped)return}for(const handler of handlers.click??[]){await handler(e);if(e.stopped)return}if(!node.disabled&&node.isConnected)return node.onclick?.()};node.click=()=>{const task=dispatch();pending.push(task);return task};await node.click();while(pending.length)await Promise.all(pending.splice(0))}
'''
    api = next(line for line in (ROOT / 'frontend/index.html').read_text().splitlines()
               if line.startswith('async function api('))
    script = harness + '\n'.join(f'vm.runInContext({json.dumps(source)},context);' for source in [
        (ROOT / 'frontend/shared-session.js').read_text(), api,
        *((ROOT / 'frontend' / name).read_text() for name in modules), module.read_text(),
    ]) + '''
window.FireAISession.install({reset(){resetCount++;run('clearStatistics()')}});
async function main(){
''' + body + '''
}let finished=false;main().then(()=>finished=true).catch(error=>{finished=true;console.error(error);process.exitCode=1});
process.on('beforeExit',()=>{if(!finished){console.error('UI scenario did not finish');process.exitCode=1}});
'''
    result = subprocess.run(['node', '-e', script], capture_output=True, text=True, timeout=20)
    assert result.returncode == 0, result.stderr


def test_explicit_dates_validation_and_exact_observed_values():
    # Missing validation, zero/unavailable conflation or Number conversion fails.
    run_ui(r'''
await run('openStatistics()');assert.equal(nodes.statisticsStart.value,'');assert.equal(nodes.statisticsEnd.value,'');
assert(html().includes('Asia/Tokyo'));assert(html().includes('unknown'));
await invoke('statisticsQuery');assert.equal(requests.filter(r=>r.method==='POST').length,0);assert.match(html(),/開始日/);
choose();nodes.statisticsStart.value='2026-02-30';await invoke('statisticsQuery');assert.equal(requests.filter(r=>r.method==='POST').length,0);
choose();nodes.statisticsEnd.value='2025-12-31';await invoke('statisticsQuery');assert.equal(requests.filter(r=>r.method==='POST').length,0);
choose();await invoke('statisticsQuery');
assert.deepEqual(requests.find(r=>r.method==='POST').body,{start_date:'2026-01-01',end_date:'2026-01-31',metric_keys:['emergency.cases','fleet.distance_km']});
for(const value of ['9007199254740993.10','観測値: 0','利用不可','unknown','department_all_dates','missing_date','Legacy timestamps','2025-12-31T15:00:00Z','local-date-v1'])assert(html().includes(value),value);
assert(!html().includes('9007199254740994'));assert(!html().includes('総合計'));
''')


def test_unsupported_financial_and_historical_measures_are_explicitly_unavailable():
    run_ui(r'''
await run('openStatistics()');for(const term of ['財務・通貨','過去時点の職員数・車両数','会計年度・前年比較','網羅性の宣言','正式原本様式','未対応'])assert(html().includes(term),term);
choose();await invoke('statisticsSave');for(const term of ['財務・通貨','過去時点の職員数・車両数','未対応'])assert(html().includes(term),term);
''')


def test_save_recaptures_selected_query_and_confirm_keeps_unknown_coverage():
    # Reusing preview values, inventing timezone or stale version fails.
    run_ui(r'''
await run('openStatistics()');choose();await invoke('statisticsQuery');
endpoint=path=>path==='/statistics/reports'?report({snapshot:snapshot({metrics:[metric('emergency.cases','7')]})}):path.endsWith('/confirm')?report({version:2,state:'confirmed',confirmed_at:'2026-10-07T09:10:00Z',snapshot:snapshot({metrics:[metric('emergency.cases','7')]})}):regularEndpoint(path);
await invoke('statisticsSave');assert(html().includes('観測値: 7'));assert(html().includes('保存済み'));
const save=requests.find(r=>r.path==='/statistics/reports');assert.deepEqual(Object.keys(save.body).sort(),['end_date','metric_keys','start_date']);
await invoke('statisticsConfirm');assert(!requests.some(r=>r.path.endsWith('/confirm')));
nodes.statisticsAcknowledge.checked=true;nodes.statisticsReviewNote.value='Reviewed observed values';await invoke('statisticsConfirm');
assert.deepEqual(requests.find(r=>r.path.endsWith('/confirm')).body,{expected_version:1,acknowledged:true,review_note:'Reviewed observed values'});
for(const text of ['Human確認済み','unknown','2026-10-07T09:10:00Z','歴史的な網羅性','正式承認'])assert(html().includes(text),text);
''')


def test_replacement_retains_predecessor_and_only_sends_version_and_reason():
    run_ui(r'''
await run('openStatistics()');choose();await invoke('statisticsSave');
endpoint=path=>path.endsWith('/replacements')?report({report_id:'report-b',predecessor_id:'report-a'}):regularEndpoint(path);
nodes.statisticsReplacementReason.value='Corrected source';await invoke('statisticsReplace');
assert.deepEqual(requests.find(r=>r.path.endsWith('/replacements')).body,{expected_version:1,reason:'Corrected source'});
assert(html().includes('新しい保存版'));assert(html().includes('report-a'));assert(html().includes('report-b'));
''')


def test_busy_from_first_async_boundary_and_repeated_save_is_single_write():
    run_ui(r'''
await run('openStatistics()');choose();let release;endpoint=path=>path==='/statistics/reports'?new Promise(resolve=>release=resolve):regularEndpoint(path);
const handler=nodes.statisticsSave.onclick;const saving=handler();assert.equal(nodes.statisticsSave.disabled,true);assert.equal(nodes.statisticsModal['aria-busy'],'true');await handler();await flush();assert.equal(requests.filter(r=>r.path==='/statistics/reports').length,1);
release(report());await saving;assert.equal(nodes.statisticsModal['aria-busy'],'false');
''')


def test_recoverable_error_preserves_inputs_and_conflict_requires_read_refresh():
    run_ui(r'''
await run('openStatistics()');choose();endpoint=()=>new Response('{"detail":"Synthetic unavailable"}',{status:503});await invoke('statisticsQuery');
assert.equal(nodes.statisticsStart.value,'2026-01-01');assert.equal(nodes.statisticsEnd.value,'2026-01-31');assert(html().includes('Synthetic unavailable'));
endpoint=regularEndpoint;await invoke('statisticsSave');nodes.statisticsAcknowledge.checked=true;nodes.statisticsReviewNote.value='Keep my review';endpoint=()=>new Response('{"detail":"stale snapshot"}',{status:409});await invoke('statisticsConfirm');
assert(html().includes('変更'));assert.equal(nodes.statisticsReviewNote.value,'Keep my review');assert.equal(nodes.statisticsConfirm.disabled,true);assert(nodes.statisticsReload);
endpoint=regularEndpoint;await invoke('statisticsReload');assert.equal(requests.at(-1).method,'GET');assert.equal(requests.at(-1).path,'/statistics/reports/report-a');
''')


def test_read_only_role_can_query_and_read_but_has_no_write_or_export_controls():
    run_ui(r'''
authority.permissions=['statistics.read','emergency.report.read'];await run('initStatistics()');assert.equal(nodes.statisticsBtn.classList.contains('hidden'),false);await run('openStatistics()');choose();await invoke('statisticsQuery');assert(!nodes.statisticsSave);
await invoke('statisticsSaved');await nodes.statisticsContent.querySelectorAll('[data-statistics-report]')[0].onclick();
assert(html().includes('保存済み'));assert(!nodes.statisticsConfirm);assert(!nodes.statisticsReplace);assert(!nodes.statisticsCSV);assert(!nodes.statisticsXLSX);
''')


@pytest.mark.parametrize('dismiss', ["run('closeStatistics()')", "run('statisticsShowQuery()')", "run('clearStatistics()')"])
def test_delayed_query_cannot_repaint_close_back_or_session_reset(dismiss):
    run_ui(r'''
await run('openStatistics()');choose();let release;endpoint=()=>new Promise(resolve=>release=resolve);const pending=invoke('statisticsQuery');await flush();
''' + dismiss + r''';release(snapshot({metrics:[metric('emergency.cases','987654321')]}));await pending;
assert(!html().includes('987654321'));assert.equal(run('statisticsState.busy'),false);
''')


@pytest.mark.parametrize('change', ["{...authority,user_id:'other'}", "{...authority,session_id:'b'}", "{...authority,tenant_id:'hq-b'}", "{...authority,permissions:['statistics.read']}"])
def test_real_shared_session_discards_delayed_body_after_authority_change(change):
    run_ui(r'''
await run('openStatistics()');choose();let release;endpoint=()=>new Response(new ReadableStream({start(controller){release=()=>{controller.enqueue(new TextEncoder().encode(JSON.stringify(snapshot())));controller.close()}}}));const pending=invoke('statisticsQuery');await flush();
''' + f'authority={change};' + r'''
release();await pending;assert.equal(resetCount,1);assert(!nodes.statisticsModal);assert.equal(run('statisticsState.preview'),null);assert.equal(nodes.statisticsBtn.classList.contains('hidden'),true);
''')


def test_exports_use_guarded_blob_server_filename_and_discard_account_change():
    run_ui(r'''
await run('openStatistics()');choose();await invoke('statisticsSave');endpoint=()=>new Response('synthetic,csv',{headers:{'Content-Disposition':'attachment; filename="statistics-safe.csv"'}});await invoke('statisticsCSV');assert.equal(downloads.length,1);assert.equal(downloads[0].filename,'statistics-safe.csv');
let release;endpoint=()=>new Response(new ReadableStream({start(controller){release=()=>{controller.enqueue(new TextEncoder().encode('private late csv'));controller.close()}}}),{headers:{'Content-Disposition':'attachment; filename="statistics-safe.csv"'}});const pending=invoke('statisticsCSV');await flush();authority={...authority,user_id:'other'};release();await pending;assert.equal(downloads.length,1);assert(!nodes.statisticsModal);
''')


def test_newer_report_navigation_owns_view_and_source_pointers_are_allowlisted():
    run_ui(r'''
await run('openStatistics()');let release;endpoint=path=>path==='/statistics/reports/report-a'?new Promise(resolve=>release=resolve):regularEndpoint(path);const pending=run("statisticsLoadReport('report-a')");await flush();run('statisticsShowQuery()');release(report({snapshot:snapshot({metrics:[metric('emergency.cases','777777')]})}));await pending;assert(!html().includes('777777'));
assert.equal(run("statisticsNavigation({navigation:{surface:'javascript:alert(1)',id:'x'}})"),null);assert.equal(run("statisticsNavigation({navigation:{surface:'vehicle',id:'../../auth/logout'}})"),null);
''')


def test_back_and_close_cancel_at_intent_before_shared_session_preflight():
    run_ui(r'''
await run('openStatistics()');choose();let release;endpoint=()=>new Promise(resolve=>release=resolve);const pending=invoke('statisticsQuery');await flush();
assert.equal(nodes.statisticsBack.disabled,false);await click(nodes.statisticsBack);release(snapshot({metrics:[metric('emergency.cases','666666')]}));await pending;assert(!html().includes('666666'));
endpoint=regularEndpoint;await run('openStatistics()');choose();let responseRelease;endpoint=()=>new Promise(resolve=>responseRelease=resolve);const closing=invoke('statisticsQuery');await flush();
let authRelease;authorityEndpoint=()=>new Promise(resolve=>authRelease=()=>resolve(new Response(JSON.stringify(authority))));const close=click(nodes.statisticsClose);await flush();assert(!nodes.statisticsModal,'Close must hide before authority preflight finishes');
authorityEndpoint=async()=>new Response(JSON.stringify(authority));responseRelease(snapshot());authRelease();await close;await closing;assert(!nodes.statisticsModal);
''')


def test_actual_save_click_shows_busy_during_authority_preflight_and_submits_once():
    run_ui(r'''
await run('openStatistics()');choose();let release,checks=0;authorityEndpoint=()=>++checks===1?new Promise(resolve=>release=()=>resolve(new Response(JSON.stringify(authority)))):new Response(JSON.stringify(authority));
const button=nodes.statisticsSave;const pending=click(button);await flush();assert.equal(nodes.statisticsModal['aria-busy'],'true');assert.equal(button.disabled,true);assert.equal(nodes.statisticsStart.disabled,true);assert.equal(nodes.statisticsBack.disabled,false);await click(button);
release();await pending;assert.equal(requests.filter(r=>r.method==='POST').length,1);assert(html().includes('保存済み'));assert.equal(nodes.statisticsModal['aria-busy'],'false');
''')


def test_newer_list_intent_survives_old_query_during_authority_preflight():
    run_ui(r'''
await run('openStatistics()');choose();let releaseQuery;endpoint=path=>path==='/statistics/query'?new Promise(resolve=>releaseQuery=resolve):regularEndpoint(path);const query=invoke('statisticsQuery');await flush();
let releaseAuth,checks=0;authorityEndpoint=()=>++checks===1?new Promise(resolve=>releaseAuth=()=>resolve(new Response(JSON.stringify(authority)))):new Response(JSON.stringify(authority));const pending=click(nodes.statisticsSaved);await flush();releaseQuery(snapshot());await query;
assert(!html().includes('観測値: 0'),'older result rendered over newer list intent');releaseAuth();await pending;assert.equal(run('statisticsState.view'),'list');assert(html().includes('保存記録を開く'));
''')


def test_newer_navigation_cancels_a_queued_write_before_its_preflight_resolves():
    run_ui(r'''
await run('openStatistics()');choose();let release,checks=0;authorityEndpoint=()=>++checks===1?new Promise(resolve=>release=()=>resolve(new Response(JSON.stringify(authority)))):new Response(JSON.stringify(authority));const saving=click(nodes.statisticsSave);await flush();await click(nodes.statisticsSaved);release();await saving;
assert.equal(run('statisticsState.view'),'list');assert.equal(requests.filter(r=>r.method==='POST').length,0);
''')


def test_header_entry_preflight_is_visible_and_close_prevents_late_open():
    run_ui(r'''
await run('initStatistics()');let release,checks=0;authorityEndpoint=()=>++checks===1?new Promise(resolve=>release=()=>resolve(new Response(JSON.stringify(authority)))):new Response(JSON.stringify(authority));
const opening=click(nodes.statisticsBtn);await flush();assert(nodes.statisticsModal);assert.equal(nodes.statisticsModal['aria-busy'],'true');assert.equal(nodes.statisticsBtn.disabled,true);assert.equal(requests.length,0);
await click(nodes.statisticsClose);release();await opening;assert(!nodes.statisticsModal);assert.equal(requests.length,0);assert.equal(nodes.statisticsBtn.disabled,false);
''')


def test_accepted_write_survives_failed_history_refresh_and_retry_is_read_only():
    run_ui(r'''
await run('openStatistics()');choose();await invoke('statisticsSave');const posts=requests.filter(r=>r.method==='POST').length;
endpoint=()=>new Response('{"detail":"history unavailable"}',{status:503});await invoke('statisticsHistory');assert(html().includes('保存済み'));assert(html().includes('history unavailable'));assert(html().includes('観測値: 0'));
endpoint=regularEndpoint;await invoke('statisticsHistory');assert.equal(requests.filter(r=>r.method==='POST').length,posts);assert(html().includes('操作履歴'));
''')


def test_busy_navigation_preserves_metric_choices_and_failed_reads_offer_retry():
    run_ui(r'''
await run('openStatistics()');choose();let release;endpoint=()=>new Promise(resolve=>release=resolve);const pending=invoke('statisticsQuery');await flush();run('closeStatistics()');release(snapshot());await pending;
endpoint=regularEndpoint;await run('openStatistics()');assert.deepEqual(Array.from(nodes.statisticsContent.querySelectorAll('[data-statistics-metric]')).filter(n=>n.checked).map(n=>n.dataset.statisticsMetric),['emergency.cases','fleet.distance_km']);
endpoint=()=>new Response('{"detail":"read unavailable"}',{status:503});await run("statisticsLoadReport('report-a')");assert(!html().includes('読み込み中'));assert(nodes.statisticsReload);endpoint=regularEndpoint;await invoke('statisticsReload');assert(html().includes('保存済み'));
endpoint=()=>new Response('{"detail":"catalog unavailable"}',{status:503});await run('openStatistics()');assert(!html().includes('読み込み中'));assert(nodes.statisticsRetryCatalog);
''')


def test_drilldown_denial_keeps_aggregate_snapshot_and_escaping_is_inert():
    run_ui(r'''
await run('openStatistics()');choose();endpoint=path=>path==='/statistics/reports'?report({snapshot:snapshot({metrics:[metric('emergency.cases','0',{label:'<img src=x onerror=bad()>',definition:'<script>bad()</script>'})]})}):regularEndpoint(path);await invoke('statisticsSave');
assert(html().includes('&lt;img'));assert(!html().includes('<img'));assert(!html().includes('<script>'));
endpoint=()=>new Response('{"detail":"detail permission required"}',{status:403});await run("statisticsDrill('emergency.cases',0)");assert(html().includes('観測値: 0'));assert(html().includes('別の権限'));assert(nodes.statisticsModal);assert.equal(resetCount,0);
''')


@pytest.mark.parametrize('phase', ['permissions', 'list'])
def test_emergency_source_open_does_not_create_or_repaint_after_cancel(phase):
    run_ui(r'''
document.body.append(element('emergencyBtn'));authority.permissions.push('emergency.case.read');await run('openStatistics()');choose();await invoke('statisticsSave');
let release;const previousFetch=window.fetch;
''' + (r'''
// Delay the real Response body, leaving the real session guard in place.
const previousEndpoint=authorityEndpoint;let count=0;authorityEndpoint=async()=>{if(++count===2)return new Promise(resolve=>release=()=>resolve(new Response(JSON.stringify(authority))));return previousEndpoint()};
''' if phase == 'permissions' else r'''
endpoint=path=>path.startsWith('/emergency/cases?')?new Promise(resolve=>release=()=>resolve([])):regularEndpoint(path);
''') + r'''
const pending=run("statisticsOpenSource({navigation:{surface:'emergency_case',id:'source-a'}})");await flush();assert(release);run('closeStatistics()');const before=nodes.emergencyContent?.innerHTML;release();await pending;
''' + ("assert(!nodes.emergencyModal);assert.deepEqual(Array.from(run('emergencyState.permissions')),[]);" if phase == 'permissions' else "assert.equal(nodes.emergencyContent?.innerHTML,before);") + r'''
''', modules=('emergency.js',))


@pytest.mark.parametrize('surface,path,next_path,state_key', [
    ('incident', '/operations/incidents/source-a', '/operations/incidents/source-a/dispatches', 'incident'),
    ('dispatch', '/operations/dispatches/source-a', '/operations/dispatches/source-a/crew', 'dispatch'),
    ('emergency_case', '/emergency/cases/source-a', '/emergency/cases/source-a/patients', 'case'),
])
@pytest.mark.parametrize('phase', ['detail', 'related'])
@pytest.mark.parametrize('interruption', ['close', 'newer'])
def test_original_record_functions_do_not_render_after_newer_navigation(surface, path, next_path, state_key, phase, interruption):
    # The actual original-record entry/detail code receives the statistics owner.
    run_ui(r'''
authority.permissions.push('incident.read','incident.crew.read','emergency.case.read','emergency.patient.read');
document.body.append(element('operationsBtn'));document.body.append(element('emergencyBtn'));
const original=regularEndpoint;let release;
const detail={title:'STALE SOURCE',kind:'other',status:'active',source_restricted:false,unit:'STALE SOURCE',incident_id:'source-a',call_date:'STALE SOURCE'};
endpoint=path=>{if(path.startsWith('/operations/incidents?')||path.startsWith('/emergency/cases?'))return [];
''' + f'''if(path==={json.dumps(path)})return {'new Promise(resolve=>release=()=>resolve(detail))' if phase == 'detail' else 'detail'};
if(path==={json.dumps(next_path)})return {'new Promise(resolve=>release=()=>resolve([]))' if phase == 'related' else '[]'};
''' + r'''return original(path)};
await run('openStatistics()');choose();await invoke('statisticsSave');
''' + f'''const pending=run({json.dumps(f"statisticsOpenSource({{navigation:{{surface:'{surface}',id:'source-a'}}}})")});await flush();assert(release,'source read was not pending');
const modal=nodes.{"emergencyModal" if surface == "emergency_case" else "operationsModal"};
const content=nodes.{"emergencyContent" if surface == "emergency_case" else "operationsContent"};
''' + (r'''const newer=element('sourceNewer','', 'button');newer.onclick=()=>{content.innerHTML='NEWER SCREEN'};await click(newer);
''' if interruption == 'newer' else r'''modal.classList.add('hidden');
''') + r'''
release();await pending;assert(!content.innerHTML.includes('STALE SOURCE'));
''' + f'''assert.equal(run('{"emergencyState" if surface == "emergency_case" else "operationsState"}.{state_key}'),null);
''' + r'''
assert.equal(windowHandlers.click.length,1,'temporary source navigation listener leaked');
''', modules=('operations.js', 'emergency.js'))
