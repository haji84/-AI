"""Deterministic real-source learning refresh ownership and pending UI checks."""
from pathlib import Path
import subprocess


def run_refresh_js(tmp_path, scenario):
    root = Path(__file__).resolve().parents[2]
    script = tmp_path / 'learning-refresh.js'
    script.write_text(r'''
const vm=require('vm'),fs=require('fs'),assert=require('assert');
const nodes=new Map();
class Node {
 constructor(tag=''){this.tag=tag;this.value='';this.ownText='';this.hidden=false;this.disabled=false;this.options=[];this.children=this.options;this.handlers={};}
 set textContent(value){this.ownText=String(value);this.children.length=0;}
 get textContent(){return this.ownText+this.children.map(child=>child.textContent||'').join('');}
 addEventListener(name,callback){this.handlers[name]=callback;}
 replaceChildren(){this.children.length=0;this.ownText='';if(['task','artifactSelect','setSelect','correctionSource','evaluationSources'].includes(this.tag))this.value='';}
 appendChild(item){this.children.push(item);if(!this.value&&item.value)this.value=item.value;return item;}
 reset(){this.value='';}
}
const node=id=>{if(!nodes.has(id))nodes.set(id,new Node(id));return nodes.get(id);};
const response=(data,status=200)=>({ok:status<400,status,json:async()=>data});
const fixed=name=>({evaluation_set_id:name,name,synthetic:true,cases:[{input:name,expected:'Synthetic answer'}],source_evidence:[],cases_sha256:'synthetic-hash',review_status:'pending',version:1});
const correction=name=>({correction_id:name,input_text:name,output_text:'synthetic answer',synthetic:true,review_status:'approved'});
const deferred=()=>{let resolve,reject;const promise=new Promise((yes,no)=>{resolve=yes;reject=no;});return {promise,resolve,reject};};
let account='first',permissions=['learning.read','learning.record','document.read','intake.read','fire_investigation.read'];
let intercept=()=>undefined;
const context={console,URLSearchParams,Set,FormData:function(){this.get=()=>'';},Option:function(label,value){this.label=label;this.value=value;},window:{confirm:()=>true},document:{getElementById:node,createElement:tag=>new Node(tag),querySelectorAll:()=>[]},
 fetch:async path=>{
  const result=intercept(path);if(result!==undefined)return result;
  if(path==='/learning/context')return response({username:account,permissions,tasks:['ocr','audio_correction'],production_mode:false});
  if(path.startsWith('/learning/champions/')&&!path.endsWith('/history'))return response({version:1,artifact_id:null});
  return response([]);
 }};
vm.createContext(context);vm.runInContext(fs.readFileSync(process.argv[2],'utf8'),context);
const turn=()=>new Promise(resolve=>setImmediate(resolve));
const evaluate=source=>vm.runInContext(source,context);
const load=()=>node('refreshButton').handlers.click();
const findButtons=label=>{const result=[];function visit(n){if(n.tag==='button'&&n.textContent===label)result.push(n);for(const child of n.children||[])visit(child);}visit(node('evaluationSets'));return result;};
(async()=>{await evaluate('initialStartup');
SCENARIO
})().catch(error=>{console.error(error.stack);process.exitCode=1;});
'''.replace('SCENARIO', scenario))
    result = subprocess.run(['node', str(script), str(root / 'frontend/learning.js')], capture_output=True, text=True, timeout=10)
    assert result.returncode == 0, result.stderr


def test_task_switch_clears_prior_ready_view_before_first_await(tmp_path):
    run_refresh_js(tmp_path, r'''
evaluate("state.sets=[{evaluation_set_id:'old',name:'old OCR set',cases:[],source_evidence:[],synthetic:true,review_status:'pending'}];render();");
node('humanReason').value='Synthetic draft reason';node('setForm').value='Synthetic draft name';
const pending=deferred();intercept=path=>path==='/learning/champions/audio_correction'?pending.promise:undefined;
node('task').value='audio_correction';node('task').handlers.change();
assert.equal(node('taskContent').disabled,true,'task content must be unavailable before the first await');
assert.doesNotMatch(node('champion').textContent,/Baseline/,'previous task Baseline must not look current');
assert.match(node('champion').textContent,/読込|読み込/,'task transition must explain the pending state');
assert.equal(node('evaluationSets').textContent,'','previous task evidence actions must be removed');
for(const id of ['task','refreshButton','logoutButton'])assert.equal(node(id).disabled,false,id+' must remain usable');
assert.equal(node('humanReason').value,'Synthetic draft reason');assert.equal(node('setForm').value,'Synthetic draft name');
pending.resolve(response({version:1,artifact_id:null}));await turn();
assert.equal(node('taskContent').disabled,false);assert.match(node('champion').textContent,/Baseline/);
''')


def test_older_same_task_refresh_cannot_erase_new_private_evidence_button(tmp_path):
    run_refresh_js(tmp_path, r'''
let created=false,hold=true;const older=deferred();
intercept=path=>{if(path==='/learning/evaluation-sets?task=audio_correction')return response(created?[fixed('PRIVATE synthetic evidence')]:[]);if(path==='/learning/champions/audio_correction'&&hold){hold=false;return older.promise;}};
node('task').value='audio_correction';node('task').handlers.change();await turn();
created=true;await load();assert.match(node('evaluationSets').textContent,/PRIVATE synthetic evidence/);assert.equal(findButtons('入力・正解を見る').length,1);
older.resolve(response({version:1,artifact_id:null}));await turn();
assert.equal(findButtons('入力・正解を見る').length,1,'older empty snapshot erased the latest evidence button');
assert.match(node('evaluationSets').textContent,/PRIVATE synthetic evidence/);assert.equal(node('taskContent').disabled,false);
''')


def test_superseded_refresh_cannot_release_newer_pending_state(tmp_path):
    run_refresh_js(tmp_path, r'''
const older=deferred(),newer=deferred();let calls=0;
intercept=path=>path==='/learning/champions/ocr'?(++calls===1?older.promise:newer.promise):undefined;
const first=load(),second=load();
older.resolve(response({version:1,artifact_id:null}));await first;
assert.equal(node('taskContent').disabled,true,'older completion released newer pending controls');
assert.doesNotMatch(node('champion').textContent,/Baseline/);
newer.resolve(response({version:2,artifact_id:null}));await second;
assert.equal(node('taskContent').disabled,false);assert.match(node('champion').textContent,/2/);
''')


def test_superseded_refresh_error_cannot_replace_current_message_or_view(tmp_path):
    run_refresh_js(tmp_path, r'''
const older=deferred();let hold=true;
intercept=path=>path==='/learning/champions/ocr'&&hold?(hold=false,older.promise):undefined;
const first=load();await load();node('message').textContent='current account status';
older.reject(new Error('obsolete load failed'));await first;
assert.equal(node('message').textContent,'current account status');assert.match(node('champion').textContent,/Baseline/);assert.equal(node('taskContent').disabled,false);
''')


def test_current_refresh_error_leaves_actions_unavailable_until_retry(tmp_path):
    run_refresh_js(tmp_path, r'''
intercept=path=>path==='/learning/champions/ocr'?Promise.reject(new Error('synthetic current read failed')):undefined;
await load();assert.match(node('message').textContent,/synthetic current read failed/);
assert.equal(node('taskContent').disabled,true,'failed read must not release stale actions');
assert.doesNotMatch(node('champion').textContent,/Baseline/);assert.match(node('champion').textContent,/失敗|取得でき|読み込め/);
assert.equal(node('refreshButton').disabled,false);assert.equal(node('logoutButton').disabled,false);
intercept=()=>undefined;await load();assert.equal(node('taskContent').disabled,false);assert.match(node('champion').textContent,/Baseline/);
assert.doesNotMatch(node('message').textContent,/synthetic current read failed/,'successful retry must clear its obsolete error');
''')


def test_logout_invalidates_refresh_and_pending_controls(tmp_path):
    run_refresh_js(tmp_path, r'''
const old=deferred();intercept=path=>path==='/learning/champions/ocr'?old.promise:undefined;
const pending=load();await node('logoutButton').handlers.click();
old.resolve(response({version:8,artifact_id:null}));await pending;
assert.equal(node('workspace').hidden,true);assert.equal(node('champion').textContent,'');assert.equal(node('evaluationSets').textContent,'');
assert.equal(node('taskContent').disabled,true);assert.match(node('message').textContent,/ログアウト/);
''')


def test_old_account_refresh_cannot_repopulate_or_release_new_account_view(tmp_path):
    run_refresh_js(tmp_path, r'''
const old=deferred();let hold=true;
intercept=path=>{if(path==='/learning/evaluation-sets?task=ocr'&&account==='first')return response([fixed('PRIVATE first account')]);if(path==='/learning/champions/ocr'&&hold){hold=false;return old.promise;}};
const pending=load();await node('logoutButton').handlers.click();account='second';await evaluate('start()');
old.resolve(response({version:8,artifact_id:null}));await pending;
assert.equal(node('workspace').hidden,false);assert.equal(node('taskContent').disabled,false);assert.equal(node('evaluationSets').textContent,'');
assert.match(node('message').textContent,/second/);assert.doesNotMatch(node('champion').textContent,/8/);
''')


def test_older_pagination_cannot_repaint_during_new_refresh(tmp_path):
    run_refresh_js(tmp_path, r'''
const oldPage=deferred(),newRefresh=deferred();
intercept=path=>path.includes('offset=100')?oldPage.promise:path==='/learning/champions/ocr'?newRefresh.promise:undefined;
evaluate('state.correctionOffset=100');const page=node('correctionOlder').handlers.click();const refresh=load();
oldPage.resolve(response([correction('OBSOLETE pagination evidence')]));await page;
assert.equal(node('corrections').textContent,'','pagination repainted a superseded view');assert.equal(node('taskContent').disabled,true);
newRefresh.resolve(response({version:1,artifact_id:null}));await refresh;
assert.equal(node('corrections').textContent,'');assert.equal(node('taskContent').disabled,false);
''')


def test_refresh_keeps_permission_denied_review_buttons_disabled(tmp_path):
    run_refresh_js(tmp_path, r'''
intercept=path=>path==='/learning/evaluation-sets?task=ocr'?response([fixed('Synthetic visible set')]):undefined;
await load();assert.equal(node('taskContent').disabled,false);
const reviews=findButtons('正解を確認済みにする');assert.equal(reviews.length,1);assert.equal(reviews[0].disabled,true,'refresh must not grant learning.review');
''')


def test_abandoned_start_cannot_report_old_account_after_new_login(tmp_path):
    run_refresh_js(tmp_path, r'''
const old=deferred();let hold=true;
intercept=path=>path==='/learning/champions/ocr'&&hold?(hold=false,old.promise):undefined;
const firstStart=evaluate('start()');await turn();
await node('logoutButton').handlers.click();account='second';await evaluate('start()');
old.resolve(response({version:9,artifact_id:null}));await firstStart;
assert.match(node('message').textContent,/second/,'old start reported success in the new account');assert.equal(node('taskContent').disabled,false);
''')


def test_current_refresh_unauthorized_clears_session_without_false_start_success(tmp_path):
    run_refresh_js(tmp_path, r'''
intercept=path=>path==='/learning/champions/ocr'?response({detail:'not authenticated'},401):undefined;
await evaluate('start()');
assert.equal(node('workspace').hidden,true);assert.equal(node('loginSection').hidden,false);assert.equal(node('taskContent').disabled,true);
assert.equal(node('champion').textContent,'');assert.doesNotMatch(node('message').textContent,/first/,'expired session must not report login success');
assert.match(node('message').textContent,/ログイン|not authenticated/,'current 401 must explain why login is required');
''')


def test_pending_fieldset_contains_task_actions_but_not_navigation():
    from html.parser import HTMLParser

    class ScopeParser(HTMLParser):
        def __init__(self):
            super().__init__()
            self.in_task_content = False
            self.inside = set()
            self.outside = set()
            self.initially_disabled = False

        def handle_starttag(self, tag, attrs):
            attrs = dict(attrs)
            if tag == 'fieldset' and attrs.get('id') == 'taskContent':
                self.in_task_content = True
                self.initially_disabled = 'disabled' in attrs
            if attrs.get('id'):
                (self.inside if self.in_task_content else self.outside).add(attrs['id'])

        def handle_endtag(self, tag):
            if tag == 'fieldset':
                self.in_task_content = False

    parser = ScopeParser()
    parser.feed((Path(__file__).resolve().parents[2] / 'frontend/learning.html').read_text())
    assert parser.initially_disabled
    assert {'sourceSearch', 'correctionForm', 'buildButton', 'caseForm', 'setForm', 'evaluationSets', 'evaluateButton', 'history', 'suggestForm'} <= parser.inside
    assert {'task', 'refreshButton', 'logoutButton', 'humanReason', 'champion'} <= parser.outside


def test_same_task_refresh_preserves_chosen_artifact_and_fixed_set(tmp_path):
    run_refresh_js(tmp_path, r'''
const sets=[{...fixed('set-one'),review_status:'approved'},{...fixed('set-two'),review_status:'approved'}];
const artifacts=['candidate-one','candidate-two'].map(artifact_id=>({artifact_id,artifact_sha256:artifact_id,training_evidence:[]}));
let pending=null;
intercept=path=>path==='/learning/evaluation-sets?task=ocr'?response(sets):path==='/learning/artifacts?task=ocr'?response(artifacts):path==='/learning/champions/ocr'&&pending?pending.promise:undefined;
await load();node('artifactSelect').value='candidate-two';node('setSelect').value='set-two';
pending=deferred();const first=load(),second=load();pending.resolve(response({version:1,artifact_id:null}));await first;await second;
assert.equal(node('artifactSelect').value,'candidate-two','refresh silently changed the Human candidate choice');
assert.equal(node('setSelect').value,'set-two','refresh silently changed the Human fixed-set choice');
''')


def test_human_save_reports_success_only_after_current_refresh(tmp_path):
    run_refresh_js(tmp_path, r'''
await evaluate('perform(async()=>true)');assert.match(node('message').textContent,/保存・確認しました/);
const old=deferred();let hold=true;
intercept=path=>path==='/learning/champions/ocr'&&hold?(hold=false,old.promise):undefined;
const save=evaluate('perform(async()=>true)');await turn();await load();node('message').textContent='newer task status';
old.resolve(response({version:1,artifact_id:null}));await save;
assert.equal(node('message').textContent,'newer task status','obsolete save refresh must not overwrite current status');
''')
