"""Real measurement-console flow; synthetic records only, no report upload."""
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import time
import urllib.request

import pytest

BROWSER = pytest.mark.skipif(os.environ.get('FIRE_AI_TEST_BROWSER') != '1', reason='actual Chromium runs in dedicated CI job')


@pytest.fixture
def console_server(tmp_path):
    root = Path(__file__).resolve().parents[2]
    env = {key: value for key, value in os.environ.items() if not key.startswith('FIRE_AI_')}
    env.update(PYTHONPATH=str(root / 'backend'), FIRE_AI_DATABASE_URL='sqlite+pysqlite:///' + str(tmp_path / 'synthetic.db'),
        FIRE_AI_STORAGE_ROOT=str(tmp_path / 'storage'), FIRE_AI_PRODUCTION_MODE='false')
    subprocess.run([sys.executable, '-m', 'app.bootstrap', '--username', 'acceptance-browser',
        '--display-name', 'Synthetic acceptance reviewer', '--password', 'synthetic-acceptance-password'],
        cwd=root, env=env, check=True, capture_output=True)
    with socket.socket() as allocation:
        allocation.bind(('127.0.0.1', 0)); port = allocation.getsockname()[1]
    base = f'http://127.0.0.1:{port}'
    with (tmp_path / 'server.log').open('w') as logs:
        server = subprocess.Popen([sys.executable, '-m', 'uvicorn', 'app.main:app', '--host', '127.0.0.1', '--port', str(port)],
            cwd=root, env=env, stdout=logs, stderr=logs)
        try:
            for _ in range(100):
                try:
                    urllib.request.urlopen(base + '/health', timeout=.2).close(); break
                except OSError:
                    if server.poll() is not None:
                        raise AssertionError('synthetic acceptance server stopped')
                    time.sleep(.1)
            else:
                raise AssertionError('synthetic acceptance server did not start')
            yield base
        finally:
            server.terminate()
            try: server.wait(timeout=10)
            except subprocess.TimeoutExpired: server.kill(); server.wait(timeout=5)


def sign_in(context, base):
    response = context.request.post(base + '/auth/login', data={'username': 'acceptance-browser', 'password': 'synthetic-acceptance-password'})
    assert response.status == 200


@BROWSER
def test_sample_preview_save_history_and_safe_nulls(console_server, tmp_path):
    from playwright.sync_api import expect, sync_playwright
    with sync_playwright() as p:
        browser = p.chromium.launch(executable_path=os.environ.get('FIRE_AI_TEST_CHROMIUM'))
        context = browser.new_context(); sign_in(context, console_server)
        page = context.new_page(); errors = []
        page.on('pageerror', lambda error: errors.append(str(error)))
        page.goto(console_server + '/ui/emergency-acceptance.html')
        expect(page.get_by_role('heading', name='救急報告書チェックの完成評価')).to_be_visible()
        expect(page.locator('#sampleButton')).to_be_enabled()
        page.locator('#sampleButton').click()
        expect(page.locator('#syntheticBanner')).to_be_visible()
        expect(page.locator('#syntheticBanner')).to_contain_text('実測値ではありません')
        expect(page.locator('#metricCards')).to_contain_text('読取不能')
        expect(page.locator('#metricCards')).to_contain_text('未検査')
        expect(page.locator('#targetRecall')).to_have_value('')
        expect(page.locator('#summaryState')).not_to_contain_text('本番完成')
        expect(page.locator('#saveButton')).to_be_enabled()
        page.locator('#saveButton').click()
        expect(page.locator('#selectionStatus')).to_contain_text('評価記録を保存しました')
        expect(page.locator('[data-evaluation-id]')).to_have_count(1)
        expect(page.locator('#releaseGates')).to_contain_text('未登録')
        expect(page.locator('#savedPanel')).to_be_visible()
        artifacts = Path(os.environ.get('FIRE_AI_BROWSER_ARTIFACTS', str(tmp_path / 'artifacts')))
        artifacts.mkdir(parents=True, exist_ok=True)
        page.screenshot(path=str(artifacts / 'emergency-acceptance-synthetic-saved.png'), full_page=True)
        page.set_viewport_size({'width': 390, 'height': 844})
        assert page.evaluate('document.documentElement.scrollWidth <= window.innerWidth')
        page.screenshot(path=str(artifacts / 'emergency-acceptance-synthetic-mobile.png'), full_page=True)
        page.set_viewport_size({'width': 1280, 'height': 720})
        assert page.evaluate('Object.keys(localStorage).length + Object.keys(sessionStorage).length') == 0
        page.reload()
        expect(page.locator('[data-evaluation-id]')).to_have_count(1)
        page.locator('[data-evaluation-id]').click()
        expect(page.locator('#syntheticBanner')).to_be_visible()
        expect(page.locator('#saveButton')).to_be_disabled()
        # Empty but valid observations must remain unmeasured, not zero-percent success.
        empty = {'dataset_kind': 'synthetic', 'reports': []}
        page.locator('#measurementFile').set_input_files({'name': 'synthetic-empty.json', 'mimeType': 'application/json', 'buffer': json.dumps(empty).encode()})
        expect(page.locator('#metricCards')).to_contain_text('未測定')
        expect(page.locator('#saveButton')).to_be_enabled()
        page.locator('#measurementFile').set_input_files({'name': 'synthetic-invalid.json', 'mimeType': 'application/json', 'buffer': b'{"patient_name":"DO_NOT_ECHO_PRIVATE_VALUE"}'})
        expect(page.locator('#saveButton')).to_be_disabled()
        expect(page.locator('#resultsPanel')).to_be_hidden()
        expect(page.locator('body')).not_to_contain_text('DO_NOT_ECHO_PRIVATE_VALUE')
        expect(page.locator('#measurementFile')).to_have_value('')
        artifacts = Path(os.environ.get('FIRE_AI_BROWSER_ARTIFACTS', str(tmp_path / 'artifacts')))
        artifacts.mkdir(parents=True, exist_ok=True)
        page.screenshot(path=str(artifacts / 'emergency-acceptance-safe-error.png'), full_page=True)
        assert errors == []
        browser.close()


@BROWSER
def test_permission_denial_and_session_reset_prevent_old_data(console_server):
    from playwright.sync_api import expect, sync_playwright
    with sync_playwright() as p:
        browser = p.chromium.launch(executable_path=os.environ.get('FIRE_AI_TEST_CHROMIUM'))
        context = browser.new_context(); sign_in(context, console_server)
        page = context.new_page()
        page.goto(console_server + '/ui/emergency-acceptance.html')
        expect(page.locator('#sampleButton')).to_be_enabled()
        page.locator('#sampleButton').click()
        expect(page.locator('#resultsPanel')).to_be_visible()
        # An old selection/preview must be discarded when authority changes.
        page.evaluate('window.FireAISession.invalidate()')
        expect(page.locator('#resultsPanel')).to_be_hidden()
        expect(page.locator('#saveButton')).to_be_disabled()
        expect(page.locator('#sampleButton')).to_be_disabled()
        expect(page.locator('#historyList')).to_be_empty()
        expect(page.locator('#targetRecall')).to_have_value('')
        page.route('**/auth/context', lambda route: route.fulfill(status=403, content_type='application/json', body='{"detail":"denied"}'))
        page.reload()
        expect(page.locator('#pageMessage')).to_contain_text('権限')
        expect(page.locator('#sampleButton')).to_be_disabled()
        expect(page.locator('#historyList')).to_be_empty()
        browser.close()


@BROWSER
def test_late_preview_cannot_restore_reset_page(console_server):
    from playwright.sync_api import expect, sync_playwright
    with sync_playwright() as p:
        browser = p.chromium.launch(executable_path=os.environ.get('FIRE_AI_TEST_CHROMIUM'))
        context = browser.new_context(); sign_in(context, console_server)
        page = context.new_page(); pending = []
        page.route('**/emergency/acceptance/preview', lambda route: pending.append(route))
        page.goto(console_server + '/ui/emergency-acceptance.html')
        expect(page.locator('#sampleButton')).to_be_enabled()
        page.locator('#sampleButton').click()
        for _ in range(100):
            if pending: break
            page.wait_for_timeout(20)
        assert pending
        page.evaluate('window.FireAISession.invalidate()')
        pending.pop().fulfill(status=200, content_type='application/json', body=json.dumps({
            'dataset_kind': 'synthetic', 'production_complete': False, 'status': 'DEVELOPMENT_ONLY',
            'metrics': {}, 'blockers': [], 'counts': {}}))
        expect(page.locator('#resultsPanel')).to_be_hidden()
        expect(page.locator('#saveButton')).to_be_disabled()
        expect(page.locator('#sampleButton')).to_be_disabled()
        browser.close()



def run_console_js(body):
    root = Path(__file__).resolve().parents[2]
    module = root / 'frontend/emergency-acceptance.js'
    html = root / 'frontend/emergency-acceptance.html'
    assert module.exists() and html.exists(), 'measurement console is not implemented'
    harness = r"""
const fs=require('fs'),vm=require('vm'),assert=require('node:assert/strict');
const nodes={},handlers={},windowHandlers={};
function node(tag='div',id='',attrs=''){
 const listeners={},classes=new Set();let ownText='';
 const e={id,tagName:tag.toUpperCase(),children:[],dataset:{},style:{},isConnected:true,hidden:/\bhidden\b/.test(attrs),disabled:/\bdisabled\b/.test(attrs),value:'',files:[],checked:false,
 classList:{add:x=>classes.add(x),remove:x=>classes.delete(x),toggle(x,on){if(on)classes.add(x);else classes.delete(x)}},
 set textContent(v){ownText=String(v??'');this.children=[]},get textContent(){return ownText+this.children.map(c=>typeof c==='string'?c:c.textContent).join('')},
 append(...items){this.children.push(...items)},replaceChildren(...items){ownText='';this.children=[...items]},setAttribute(k,v){this[k]=String(v)},getAttribute(k){return this[k]},
 addEventListener(k,f){listeners[k]=f},querySelectorAll(){return []},closest(){return this},
 async fire(k){const e={target:this,preventDefault(){}};return (listeners[k]||this['on'+k])?.(e)},focus(){}};
 if(id)nodes[id]=e;return e;
}
const markup=fs.readFileSync(process.argv[2],'utf8');
for(const m of markup.matchAll(/<([a-z]+)\b([^>]*\bid="([^"]+)"[^>]*)>/g))node(m[1],m[3],m[2]);
const document={getElementById:id=>nodes[id],createElement:t=>node(t),createTextNode:t=>String(t),addEventListener(k,f){handlers[k]=f},visibilityState:'visible',querySelectorAll(){return []}};
let authority={user_id:'synthetic-user',session_id:'a',tenant_id:null,permissions:['emergency.case.read','emergency.patient.read','emergency.report.read','emergency.report.create','emergency.report.review']};
let requests=[],endpoint=async()=>{throw new Error('unexpected endpoint')};
const window={location:{origin:'http://synthetic.local',pathname:'/ui/emergency-acceptance.html',replace(){}},addEventListener(k,f){windowHandlers[k]=f},fetch:async(path,options={})=>{
 if(path==='/auth/context')return new Response(JSON.stringify(authority));
 requests.push({path,method:options.method??'GET',body:options.body?JSON.parse(options.body):null});
 const result=await endpoint(path,options);return result instanceof Response?result:new Response(JSON.stringify(result));}};
const context={window,document,fetch:(...args)=>window.fetch(...args),URL,URLSearchParams,Response,WeakSet,Event,structuredClone,crypto:require('node:crypto').webcrypto,console,setTimeout,clearTimeout};
vm.createContext(context);
const input={dataset_kind:'synthetic',reports:[],targets:{}};
const summary={dataset_kind:'synthetic',production_complete:false,status:'DEVELOPMENT_ONLY',counts:{},blockers:['DEVELOPMENT_ONLY'],metrics:{
 corrections:{status:'NOT_MEASURED',baseline:{numerator:0,denominator:0,rate:null,pending:0},assisted:{numerator:0,denominator:0,rate:null,pending:0},reduction_percent:null,percentage_points:null},
 recall:{status:'NOT_MEASURED',detected_errors:0,actual_errors:0,rate:null,unresolved:0},false_alerts:{status:'NOT_MEASURED',count:0,reviewed_reports:0,per_report:null,false_fraction:null,unresolved:0},
 time:{status:'NOT_MEASURED',baseline:{reports:0,missing:0,mean_minutes:null,median_minutes:null},assisted:{reports:0,missing:0,mean_minutes:null,median_minutes:null},reduction_percent:null},
 read_states:{status:'NOT_MEASURED',matched:0,verified:0,accuracy:null,unresolved:0,unreadable:0,unchecked:0,unsafe_clear:0}}};
let saved=[];
function record(){return {evaluation_id:'00000000-0000-4000-8000-000000000001',version:1,dataset_kind:'synthetic',status:'recorded',created_at:'2026-11-21T00:00:00Z',summary,measurement:input,evidence:[],release_gates:[],can_review:false,production_complete:false}}
endpoint=(path,options)=>{if(path.includes('/evaluations?'))return saved;if(path.endsWith('/sample'))return input;if(path.endsWith('/preview'))return summary;if(path.endsWith('/evaluations')&&options.method==='POST'){saved=[record()];return saved[0]}if(path.includes('/evaluations/'))return record();throw new Error(path)};
vm.runInContext(fs.readFileSync(process.argv[3],'utf8'),context);
vm.runInContext(fs.readFileSync(process.argv[1],'utf8'),context);
const flush=()=>new Promise(r=>setImmediate(r));
async function settled(){for(let i=0;i<8;i++)await flush()}
async function invoke(id,k='click'){await nodes[id].fire(k);await settled()}
async function main(){await settled();
"""
    script = harness + body + '\n}\nmain().catch(e=>{console.error(e);process.exitCode=1});'
    completed = subprocess.run(['node', '-e', script, str(module), str(html), str(root / 'frontend/shared-session.js')], capture_output=True, text=True, timeout=20)
    assert completed.returncode == 0, completed.stderr


def test_console_nulls_and_failed_import_do_not_claim_success():
    run_console_js(r"""
assert.equal(nodes.sampleButton.disabled,false);await invoke('sampleButton');
assert.equal(nodes.resultsPanel.hidden,false);assert.equal(nodes.syntheticBanner.hidden,false);
assert.match(nodes.syntheticBanner.textContent,/実測値ではありません/);
assert.match(nodes.metricCards.textContent,/未測定/);assert.match(nodes.metricCards.textContent,/読取不能/);assert.match(nodes.metricCards.textContent,/未検査/);
assert.equal(nodes.targetRecall.value,'');assert.equal(nodes.saveButton.disabled,false);
await invoke('saveButton');assert.equal(saved.length,1);assert.equal(nodes.saveButton.disabled,true);
nodes.measurementFile.files=[{name:'synthetic-invalid.json',size:20,text:async()=>'{"patient_name":"DO_NOT_ECHO_PRIVATE_VALUE"}'}];
endpoint=(path)=>path.endsWith('/preview')?new Response('{"detail":"DO_NOT_ECHO_PRIVATE_VALUE"}',{status:422}):[];
await invoke('measurementFile','change');
assert.equal(nodes.resultsPanel.hidden,true);assert.equal(nodes.saveButton.disabled,true);assert.equal(nodes.measurementFile.value,'');
assert(!Object.values(nodes).some(n=>n.textContent.includes('DO_NOT_ECHO_PRIVATE_VALUE')));
""")


def test_console_reset_discards_late_preview_and_retry_keeps_request_id():
    run_console_js(r"""
await invoke('sampleButton');let attempts=[];const regular=endpoint;
endpoint=(path,opts)=>{if(path.endsWith('/evaluations')&&opts.method==='POST'){attempts.push(JSON.parse(opts.body).request_id);if(attempts.length===1)throw new Error('network interruption');return record()}return regular(path,opts)};
await invoke('saveButton');assert.equal(nodes.saveButton.disabled,false);await invoke('saveButton');assert.equal(attempts.length,2);assert.equal(attempts[0],attempts[1]);
let release;endpoint=(path,opts)=>path.endsWith('/preview')?new Promise(r=>release=r):regular(path,opts);
const action=nodes.sampleButton.fire('click');await settled();assert.equal(typeof release,'function');
window.FireAISession.invalidate();release(summary);await action;await settled();
assert.equal(nodes.resultsPanel.hidden,true);assert.equal(nodes.sampleButton.disabled,true);assert.equal(nodes.saveButton.disabled,true);assert.equal(nodes.historyList.children.length,0);assert.equal(nodes.targetRecall.value,'');
""")



def test_console_replacement_and_blockers_keep_explicit_meaning():
    run_console_js(r"""
summary.blockers=['FORM_APPROVAL_REQUIRED','HOLDOUT_NOT_CONFIRMED','UNKNOWN_TRUTH','UNSAFE_CLEAR','DO_NOT_ECHO_PRIVATE_CODE'];
await invoke('sampleButton');assert.match(nodes.blockerList.textContent,/帳票と入力欄/);assert.match(nodes.blockerList.textContent,/学習に使用していない/);assert.match(nodes.blockerList.textContent,/確定していない検査項目/);assert.match(nodes.blockerList.textContent,/誤って/);assert(!nodes.blockerList.textContent.includes('DO_NOT_ECHO_PRIVATE_CODE'));
await invoke('saveButton');await invoke('reviseButton');
nodes.measurementFile.files=[{name:'synthetic-correction.json',size:60,text:async()=>JSON.stringify(input)}];await invoke('measurementFile','change');await invoke('saveButton');
const saves=requests.filter(r=>r.path.endsWith('/evaluations')&&r.method==='POST');
assert.equal(saves.length,2);assert.equal(saves[1].body.supersedes_id,record().evaluation_id);assert.equal(saves[1].body.expected_previous_version,1);
assert.notEqual(saves[0].body.request_id,saves[1].body.request_id);
""")


def test_console_superseded_record_cannot_be_reviewed_or_revised():
    run_console_js(r"""
const old={...record(),superseded_by:'00000000-0000-4000-8000-000000000002',can_review:true};saved=[old];
const regular=endpoint;endpoint=(path,opts)=>path.includes('/evaluations/')?old:regular(path,opts);
await invoke('refreshHistory');await nodes.historyList.children[0].fire('click');await settled();
assert.match(nodes.reviewMessage.textContent,/新しい評価版があるため、この版は確認できません/);
assert.equal(nodes.reviseButton.disabled,true);assert.equal(nodes.reviewAcknowledgement.disabled,true);
nodes.reviewAcknowledgement.checked=true;await invoke('reviewAcknowledgement','change');
assert.equal(nodes.confirmReview.disabled,true);assert.equal(nodes.rejectReview.disabled,true);
await invoke('reviseButton');assert.equal(nodes.savedPanel.hidden,false);assert.equal(nodes.saveButton.disabled,true);
""")


def test_console_partial_truth_metrics_never_look_fully_verified():
    run_console_js(r"""
summary.metrics.recall={status:'PENDING',detected_errors:1,actual_errors:1,rate:1,unresolved:2,late_warnings:0};
summary.metrics.false_alerts={status:'PENDING',count:0,reviewed_reports:1,per_report:0,false_fraction:null,unresolved:1};
await invoke('sampleButton');
assert.match(nodes.metricCards.children[1].textContent,/正解確認済みの範囲/);
assert.match(nodes.metricCards.children[1].textContent,/未確定分を含む全体の発見率は未測定/);
assert.match(nodes.metricCards.children[2].textContent,/確認できた誤警告の暫定値/);
assert.match(nodes.metricCards.children[2].textContent,/未確定分により増える可能性/);
assert.match(nodes.metricCards.children[2].textContent,/未測定/);
""")
