"""Run the real personnel controller with delayed HTTP boundary responses."""
from pathlib import Path
import subprocess


def run(tmp_path, scenario):
    source = Path(__file__).resolve().parents[2] / 'frontend/personnel-intake.js'
    harness = r'''
const fs=require('fs'),vm=require('vm'),assert=require('assert/strict');
let authority={user_id:'SYNTHETIC',session_id:'SESSION',tenant_id:null,permissions:['personnel.read','personnel.manage','document.read','document.create']};
let shown=null,clears=0,calls=[],waiting=null,authorityFailure=null,handler=async()=>[];
const context={window:{},document:{getElementById:()=>null},console,Set,JSON,Promise};
vm.createContext(context);
if(fs.existsSync(process.argv[2]))vm.runInContext(fs.readFileSync(process.argv[2],'utf8'),context);
assert.equal(typeof context.window.createPersonnelIntakeController,'function','personnel intake controller unavailable');
const controller=context.window.createPersonnelIntakeController({
 send:async(path,method,payload)=>{calls.push({path,method,payload});if(path==='/auth/context'){if(authorityFailure)throw authorityFailure;return structuredClone(authority);}return handler(path,method,payload)},
 paint:value=>{shown=value},notify:()=>{},clear:()=>{clears++;shown=null}
});
const tick=()=>new Promise(resolve=>setImmediate(resolve));
const proposal={proposal_id:'NOTICE',status:'candidate',version:1,errors:[],proposed:{employee_code:'SYN01'},source_text:'PRIVATE synthetic original'};
(async()=>{SCENARIO})().catch(e=>{console.error(e.stack);process.exitCode=1});
'''
    script = tmp_path / 'personnel-state.js'
    script.write_text(harness.replace('SCENARIO', scenario))
    result = subprocess.run(['node', str(script), str(source)], text=True, capture_output=True, timeout=10)
    assert result.returncode == 0, result.stderr


def test_slow_old_list_cannot_replace_new_detail(tmp_path):
    run(tmp_path, r'''
handler=async(path)=>path==='/personnel-intake/proposals'?new Promise(resolve=>waiting=resolve):proposal;
const old=controller.load();await tick();assert.ok(waiting);
await controller.detail('NOTICE');assert.equal(shown.proposal.proposal_id,'NOTICE');
waiting([{proposal_id:'OLD PRIVATE'}]);await old;
assert.equal(shown.proposal.proposal_id,'NOTICE');
''')


def test_inflight_session_change_discards_private_detail(tmp_path):
    run(tmp_path, r'''
handler=async()=>new Promise(resolve=>waiting=resolve);
const old=controller.detail('NOTICE');await tick();authority.session_id='REPLACED';waiting(proposal);await old;
assert.equal(shown,null);assert.ok(clears>0);
''')


def test_lost_management_right_prevents_cached_review(tmp_path):
    run(tmp_path, r'''
handler=async()=>proposal;await controller.detail('NOTICE');
authority.permissions=authority.permissions.filter(x=>x!=='personnel.manage');
await controller.decision('review','Synthetic Human reason',true);
assert.equal(calls.filter(x=>x.method==='POST').length,0);assert.equal(shown,null);
''')


def test_human_acknowledgement_and_double_click_guard(tmp_path):
    run(tmp_path, r'''
handler=async()=>proposal;await controller.detail('NOTICE');
await controller.decision('review','Synthetic Human reason',false);
assert.equal(calls.filter(x=>x.method==='POST').length,0);
handler=async()=>new Promise(resolve=>waiting=resolve);
const first=controller.decision('review','Synthetic Human reason',true);await tick();
await controller.decision('review','Synthetic Human reason',true);
assert.equal(calls.filter(x=>x.method==='POST').length,1);
waiting({...proposal,status:'reviewed',version:2});await first;
assert.equal(shown.proposal.status,'reviewed');assert.equal(shown.busy,false);
''')


def test_permission_loss_after_mutation_cannot_restore_private_state(tmp_path):
    run(tmp_path, r'''
handler=async()=>proposal;await controller.detail('NOTICE');
handler=async()=>{authority.permissions=[];return {...proposal,status:'reviewed',version:2}};
await controller.decision('review','Synthetic Human reason',true);
assert.equal(shown,null);assert.ok(clears>0);
''')


def test_conflict_removes_cached_mutation_target(tmp_path):
    run(tmp_path, r'''
handler=async()=>proposal;await controller.detail('NOTICE');
handler=async()=>{throw Object.assign(new Error('source stale'),{status:409})};
await controller.decision('review','Synthetic Human reason',true);
assert.equal(shown.proposal,null);assert.equal(shown.busy,false);
const count=calls.length;await controller.decision('review','Synthetic Human reason',true);
assert.equal(calls.length,count);
''')


def test_focus_check_erases_private_state_while_mutation_is_pending(tmp_path):
    run(tmp_path, r'''
handler=async()=>proposal;await controller.detail('NOTICE');
handler=async()=>new Promise(resolve=>waiting=resolve);
const action=controller.decision('review','Synthetic Human reason',true);await tick();
authority.permissions=[];await controller.check();
assert.equal(shown,null,'permission loss must clear before pending mutation completes');
waiting({...proposal,status:'reviewed',version:2});await action;
assert.equal(shown,null);
''')


def test_unavailable_authority_clears_cached_source_before_reload(tmp_path):
    run(tmp_path, r'''
handler=async()=>proposal;await controller.detail('NOTICE');
assert.equal(shown.proposal.source_text,proposal.source_text);
authorityFailure=Object.assign(new Error('authority unavailable'),{status:503});
const before=calls.filter(x=>x.path.startsWith('/personnel-intake/')).length;
await controller.load();
assert.equal(shown,null,'failed authority verification must erase cached originals');
assert.equal(calls.filter(x=>x.path.startsWith('/personnel-intake/')).length,before);
''')


def test_invalid_authority_context_clears_cached_source_before_reload(tmp_path):
    run(tmp_path, r'''
handler=async()=>proposal;await controller.detail('NOTICE');
authority=null;
const before=calls.filter(x=>x.path.startsWith('/personnel-intake/')).length;
await controller.load();
assert.equal(shown,null,'malformed authority context must erase cached originals');
assert.equal(calls.filter(x=>x.path.startsWith('/personnel-intake/')).length,before);
''')
