"""Run real Human handlers, API parsing and SharedSession with deferred transport.

The small DOM records rendered controls; these are Node state tests, not browser QA.
"""
from pathlib import Path
import subprocess

import pytest


HARNESS = r'''
const assert=require('node:assert/strict'),vm=require('node:vm'),fs=require('node:fs');
const root=process.argv[2],nodes=new Map(),listeners={},calls=[];
let buttons=[],promptCount=0,promptResult='Synthetic Human reason',hold=null,postError=null,readError=null;
const turn=()=>new Promise(resolve=>setImmediate(resolve));
const deferred=()=>{let resolve;const promise=new Promise(r=>resolve=r);return {promise,resolve}};
const gate=predicate=>{const entered=deferred(),release=deferred();hold={predicate,entered,release};return {entered:entered.promise,release:release.resolve}};
class Node {
  constructor(id=''){this.id=id;this.textContent='';this.html='';this.dataset={};this.style={};this.disabled=false;this.isConnected=true;this.tagName='BUTTON';this.classes=new Set();this.classList={add:c=>this.classes.add(c),remove:c=>this.classes.delete(c),contains:c=>this.classes.has(c),toggle:(c,on)=>on?this.classes.add(c):this.classes.delete(c)};}
  set innerHTML(value){
    this.html=value;this.textContent=value.replace(/<[^>]*>/g,'');
    if(this.id==='workforceContent'){
      for(const b of buttons)b.isConnected=false;
      buttons=[...value.matchAll(/<button\b([^>]*data-workforce-human="([^"]+)"[^>]*)>/g)].map(m=>{const b=new Node();b.dataset.workforceHuman=m[2];b.disabled=/\bdisabled\b/.test(m[1]);return b});
    }
    for(const match of value.matchAll(/\bid="([^"]+)"/g))if(!nodes.has(match[1]))nodes.set(match[1],new Node(match[1]));
  }
  get innerHTML(){return this.html;}
  remove(){this.isConnected=false;nodes.delete(this.id);}
  closest(selector){if(selector==='#loginView')return null;return this;}
  click(){if(this.disabled||!this.isConnected)return;return this.lastAction=this.onclick?.();}
}
const node=id=>nodes.get(id);
const authority={user_id:'SYNTHETIC',session_id:'SESSION-1',tenant_id:null,permissions:['workforce.read','workforce.review','workforce.approve','workforce.admin']};
const attendance={attendance_id:'A',employee_id:'E',work_date:'2026-10-10',status:'draft',version:1};
const ledger={time_entry_id:'T',employee_id:'E',kind:'comp_grant',minutes:60,occurred_on:'2026-10-10',status:'draft',version:1};
const response=(value,status=200)=>({ok:status<400,status,json:async()=>structuredClone(value)});
async function rawFetch(path,options={}){
  calls.push({path,options});
  if(hold?.predicate(path,options)){const active=hold;hold=null;active.entered.resolve();await active.release.promise;}
  if(path==='/auth/context')return response(authority);
  if(path==='/auth/me')return response({user_id:authority.user_id});
  if(path==='/auth/permissions')return response({permissions:authority.permissions});
  if(options.method==='POST'){
    if(postError)return response({detail:postError.message},postError.status);
    const row=path.includes('/time-entries/')?ledger:attendance;
    const payload=JSON.parse(options.body);
    assert.equal(payload.expected_version,row.version,'Human mutation must retain optimistic version');
    assert.equal(payload.note,'Synthetic Human reason','Human reason must reach mutation');
    row.status=path.endsWith('/review')?'reviewed':'approved';row.version++;
    return response(row);
  }
  if(path.startsWith('/workforce/attendance?'))return readError?response({detail:readError},500):response([attendance]);
  if(path.startsWith('/workforce/time-entries?'))return response([ledger]);
  return response([]);
}
const context={console,Date,URL,URLSearchParams,WeakSet,Promise,location:{origin:'http://synthetic.invalid'},fetch:rawFetch,
  $:node,esc:value=>String(value??''),prompt:()=>{promptCount++;return promptResult},addEventListener(){},
  document:{addEventListener:(name,handler)=>listeners[name]=handler,getElementById:node,createElement:()=>new Node(),body:{append(el){nodes.set(el.id,el)}},querySelectorAll:selector=>buttons.filter(b=>!selector.includes('^=')||b.dataset.workforceHuman.startsWith(selector.split('"')[1]))}};
context.window=context;vm.createContext(context);
vm.runInContext(fs.readFileSync(root+'/frontend/shared-session.js','utf8'),context);
const api=fs.readFileSync(root+'/frontend/index.html','utf8').split('\n').find(line=>line.startsWith('async function api('));
assert(api);vm.runInContext(api,context);
vm.runInContext(fs.readFileSync(root+'/frontend/workforce.js','utf8'),context);
const run=source=>vm.runInContext(source,context);
context.FireAISession.install({reset:()=>run('clearWorkforce()')});
const button=key=>{const result=buttons.find(b=>b.dataset.workforceHuman===key);assert(result,'missing Human control '+key);return result};
const posts=()=>calls.filter(x=>x.options.method==='POST');
const status=()=>node('workforceHumanStatus')?.textContent??'';
const error=()=>node('workforceMessage').textContent;
const allLocked=()=>assert(buttons.every(b=>b.disabled),'all Human controls must stay disabled while pending');
const rowStatus=(table,value)=>assert(node('workforceContent').innerHTML.split('<tbody>')[table+1]?.split('</tbody>')[0].includes('<td>'+value+'</td>'),'rendered status must be '+value);
(async()=>{
  await run('openWorkforce()');await run('workforceAttendance()');calls.length=0;
  SCENARIO
  console.log('SCENARIO COMPLETED');
})().catch(error=>{console.error(error.stack);process.exitCode=1});
'''


def run(tmp_path, scenario):
    script = tmp_path / "human-loading.js"
    script.write_text(HARNESS.replace("  SCENARIO\n", scenario))
    result = subprocess.run(
        ["node", str(script), str(Path(__file__).resolve().parents[2])],
        capture_output=True, text=True, timeout=10,
    )
    assert result.returncode == 0, result.stderr
    assert "SCENARIO COMPLETED" in result.stdout, "scenario left an unresolved async operation"


def test_all_human_controls_lock_before_first_async_boundary(tmp_path):
    run(tmp_path, r'''
const first=gate(path=>path==='/auth/context');
const action=button('attendance:review:A').onclick();
allLocked();assert(status().includes('処理中'),'announce progress separately from errors');
assert(node('workforceModal').innerHTML.includes('id="workforceHumanStatus" role="status" aria-live="polite"'),'progress must have its own accessible live region');
await first.entered;assert.equal(posts().length,0);
node('workforceMessage').textContent='Existing conflict';
await button('time:review:T').onclick();await button('attendance:review:A').onclick();
assert.equal(promptCount,1,'rapid repeats must not prompt again');assert.equal(error(),'Existing conflict','ignored repeats must not clear errors');
first.release();await action;rowStatus(0,'reviewed');assert.equal(posts().length,1);
assert(buttons.every(b=>!b.disabled));assert.equal(status(),'');
''')


def test_postflight_and_refresh_remain_locked_until_rendered(tmp_path):
    run(tmp_path, r'''
await button('attendance:review:A').onclick();
const post=gate((_path,opt)=>opt.method==='POST');
const approval=button('attendance:approve:A').onclick();await post.entered;
const postflight=gate(path=>path==='/auth/context');post.release();await postflight.entered;
assert.equal(attendance.status,'approved','POST accepted before postflight returns');allLocked();
const stale=button('time:review:T');await stale.onclick();assert.equal(posts().length,2);
const refresh=gate(path=>path.startsWith('/workforce/time-entries?'));postflight.release();await refresh.entered;
allLocked();assert(status());await stale.onclick();assert.equal(posts().length,2);
refresh.release();await approval;rowStatus(0,'approved');assert.equal(status(),'');
await stale.onclick();assert.equal(posts().length,2,'detached queued control must not mutate');
await button('time:review:T').onclick();rowStatus(1,'reviewed');
await button('time:approve:T').onclick();rowStatus(1,'approved');
''')


@pytest.mark.parametrize("prompt_result", ["null", "''"])
def test_cancelled_prompt_preserves_errors_and_never_starts_loading(tmp_path, prompt_result):
    run(tmp_path, f"promptResult={prompt_result};" + r'''
node('workforceMessage').textContent='Existing conflict';
await button('attendance:review:A').onclick();
assert.equal(calls.length,0);assert.equal(error(),'Existing conflict');assert.equal(status(),'');
assert(buttons.every(b=>!b.disabled));promptResult='Synthetic Human reason';
await button('attendance:review:A').onclick();rowStatus(0,'reviewed');
''')


def test_shared_session_queued_click_cannot_start_a_second_transition(tmp_path):
    run(tmp_path, r'''
const queued=gate(path=>path==='/auth/context');
const queuedClick=listeners.click({type:'click',target:button('time:review:T'),preventDefault(){},stopImmediatePropagation(){}});
await queued.entered;
const post=gate((_path,opt)=>opt.method==='POST');
const active=button('attendance:review:A').onclick();await post.entered;
queued.release();await queuedClick;await turn();
assert.equal(posts().length,1,'SharedSession queued click must not issue a concurrent mutation');
assert.equal(promptCount,1);post.release();await active;rowStatus(0,'reviewed');
''')


@pytest.mark.parametrize("status_code", [409, 500])
def test_failure_releases_current_controls_and_keeps_failure_visible(tmp_path, status_code):
    run(tmp_path, f"postError={{status:{status_code},message:'Synthetic failure'}};" + r'''
const previouslyDisabled=button('time:review:T');previouslyDisabled.disabled=true;
await button('attendance:review:A').onclick();
assert(error(),'failure must remain visible');assert.equal(status(),'');
assert.equal(button('attendance:review:A').disabled,false);assert(previouslyDisabled.disabled,'keep a pre-existing disabled state');
postError=null;await button('attendance:review:A').onclick();rowStatus(0,'reviewed');assert.equal(error(),'');
''')


@pytest.mark.parametrize("navigation", ["workforceAttendance()", "workforceLeave()", "$('workforceClose').onclick()"])
def test_navigation_or_close_discards_late_transition_ui(tmp_path, navigation):
    run(tmp_path, r'''
const post=gate((_path,opt)=>opt.method==='POST');const old=button('attendance:review:A');
const action=old.onclick();await post.entered;
''' + f"await run({navigation!r});" + r'''
const content=node('workforceContent').innerHTML;node('workforceMessage').textContent='New view message';
await old.onclick();post.release();await action;
assert.equal(posts().length,1,'old-view controls must not start another mutation');
assert.equal(node('workforceContent').innerHTML,content);assert.equal(error(),'New view message');
assert.equal(status(),'');
if(old.isConnected)assert(old.disabled,'closed/obsolete controls must not be re-enabled');
else assert(buttons.every(b=>!b.disabled),'new current view controls must be released');
''')


@pytest.mark.parametrize("change", [
    "authority.session_id='SESSION-2'",
    "authority.permissions=['workforce.read']",
    "postError={status:401,message:'Session expired'}",
    "postError={status:403,message:'Rights revoked'}",
])
def test_session_or_rights_loss_clears_busy_without_late_resurrection(tmp_path, change):
    run(tmp_path, r'''
const post=gate((_path,opt)=>opt.method==='POST');const old=button('attendance:review:A');
const action=old.onclick();await post.entered;
''' + change + r''';post.release();await action;
assert.equal(node('workforceModal'),undefined);assert.equal(node('workforceContent').innerHTML,'');assert.equal(status(),'');
assert.equal(run('workforceState.permissions.length'),0);assert(old.disabled,'invalidated control must not be re-enabled');
await old.onclick();assert.equal(posts().length,1);
postError=null;await run('openWorkforce()');await run('workforceAttendance()');
if(authority.permissions.includes('workforce.review')){await button('time:review:T').onclick();rowStatus(1,'reviewed')}
else assert.equal(buttons.length,0,'removed Human rights must stay removed');
''')


def test_old_completion_cannot_unlock_or_erase_new_session_operation(tmp_path):
    run(tmp_path, r'''
const oldPost=gate((_path,opt)=>opt.method==='POST');
const old=button('attendance:review:A').onclick();await oldPost.entered;
context.FireAISession.invalidate();authority.session_id='SESSION-2';
await run('openWorkforce()');await run('workforceAttendance()');
const newPost=gate((_path,opt)=>opt.method==='POST');
const active=button('time:review:T').onclick();await newPost.entered;
node('workforceMessage').textContent='New session message';
oldPost.release();await old;allLocked();assert(status());assert.equal(error(),'New session message');
newPost.release();await active;rowStatus(1,'reviewed');assert.equal(status(),'');
assert(buttons.every(b=>!b.disabled));
''')


def test_revoked_local_human_permissions_reject_queued_handler(tmp_path):
    run(tmp_path, r'''
const stale=button('attendance:review:A');run("workforceState.permissions=['workforce.read']");
node('workforceMessage').textContent='Existing conflict';await stale.onclick();
assert.equal(promptCount,0);assert.equal(calls.length,0);assert.equal(error(),'Existing conflict');
''')


def test_accepted_transition_with_failed_refresh_explains_safe_navigation_recovery(tmp_path):
    run(tmp_path, r'''
readError='Synthetic refresh unavailable';const old=button('attendance:review:A');
await old.onclick();assert.equal(attendance.status,'reviewed');assert.equal(status(),'');
assert(error().includes('処理は完了'),'distinguish accepted Human action from failed display refresh');
assert(error().includes('メニュー'),'explain how to reload the obsolete display');allLocked();
await old.onclick();assert.equal(posts().length,1,'obsolete controls must not replay accepted action');
readError=null;await node('workforceAttendance').onclick();rowStatus(0,'reviewed');assert.equal(error(),'');
assert(buttons.every(b=>!b.disabled));await button('attendance:approve:A').onclick();rowStatus(0,'approved');
''')
