"""Actual workforce form controls preserve draft-only CAS and Japan timestamps."""
import pytest
from test_statistics_browser_state import run_ui


@pytest.mark.parametrize('scenario',['save','duplicate','obsolete','refresh-fails'])
def test_actual_draft_checkout_control_has_version_and_view_ownership(scenario):
    run_ui(r'''
authority.permissions.push('workforce.read','workforce.update','workforce.review','personnel.read');
const row={attendance_id:'draft-source',employee_id:'employee-source',work_date:'2026-01-01',check_in_at:'2025-12-31T23:00:00+00:00',check_out_at:null,status:'draft',version:4};
let release,saved=false;endpoint=async(path,options)=>{
 if(path==='/auth/me')return {user_id:authority.user_id};
 if(path.startsWith('/workforce/attendance?')){if(SCENARIO==='refresh-fails'&&saved)throw new Error('Synthetic read failure');return [row,{...row,attendance_id:'approved-source',status:'approved'}];}
 if(path.startsWith('/workforce/time-entries?'))return [];
 if(path==='/workforce/attendance/draft-source'&&options.method==='PATCH'){const data=JSON.parse(options.body);assert.equal(data.expected_version,4);assert.equal(data.check_in_at,'2026-01-01T08:00:00+09:00');assert.equal(data.check_out_at,'2026-01-01T17:00:00+09:00');return new Promise(resolve=>release=()=>{saved=true;resolve({...row,version:5,check_out_at:data.check_out_at});});}
 return regularEndpoint(path);
};
await run('openWorkforceSource(()=>true)');run('workforceState.permissions='+JSON.stringify(authority.permissions));await run('workforceAttendance()');
assert(nodes['workforceEditAttendance_draft-source'],'draft edit control missing');
assert(!nodes['workforceEditAttendance_approved-source'],'approved source must not be editable');
await nodes['workforceEditAttendance_draft-source'].onclick();
assert.equal(nodes.workforceField_check_in_at.value,'2026-01-01T08:00:00');
nodes.workforceField_check_out_at.value='2026-01-01T17:00';
const captured=nodes.workforceSaveAttendanceEdit.onclick;
if(SCENARIO==='obsolete'){run('workforceState.viewGeneration++');nodes.workforceContent.innerHTML='Newer Human view';await captured();assert(!requests.some(r=>r.method==='PATCH'));return;}
const pending=captured();await flush();assert(release,'draft checkout PATCH missing');
assert(nodes.workforceSaveAttendanceEdit.disabled);
if(SCENARIO==='duplicate')await captured();
assert.equal(requests.filter(r=>r.method==='PATCH').length,1);
release();await pending;
if(SCENARIO==='refresh-fails'){assert(nodes.workforceMessage.textContent.includes('更新は完了しました'),'accepted update must be distinguished from refresh failure');await captured();}
assert.equal(requests.filter(r=>r.method==='PATCH').length,1);
'''.replace('SCENARIO',repr(scenario)),modules=('workforce.js',))


def test_cancellation_is_separate_reasoned_human_action_and_approved_is_immutable():
    run_ui(r'''
authority.permissions.push('workforce.read','workforce.review','workforce.update','personnel.read');
const row={attendance_id:'draft-source',employee_id:'employee-source',work_date:'2026-01-01',status:'draft',version:4};
context.prompt=()=> 'Synthetic withdrawal reason';
let release;endpoint=async(path,options)=>{
 if(path==='/auth/me')return {user_id:authority.user_id};
 if(path.startsWith('/workforce/attendance?'))return [row,{...row,attendance_id:'approved-source',status:'approved'}];
 if(path.startsWith('/workforce/time-entries?'))return [];
 if(path==='/workforce/attendance/draft-source/cancel'){const data=JSON.parse(options.body);assert.equal(data.expected_version,4);assert.equal(data.note,'Synthetic withdrawal reason');return new Promise(resolve=>release=()=>{row.status='cancelled';row.version++;resolve(row)});}
 return regularEndpoint(path);
};
await run('openWorkforceSource(()=>true)');run('workforceState.permissions='+JSON.stringify(authority.permissions));await run('workforceAttendance()');
const controls=nodes.workforceContent.querySelectorAll('[data-workforce-human]');
const cancel=controls.find(button=>button.dataset.workforceHuman==='attendance:cancel:draft-source');assert(cancel,'separate cancellation missing');
assert(!controls.some(button=>button.dataset.workforceHuman.includes('approved-source')));
const captured=cancel.onclick,pending=captured();await flush();assert(release);
assert(controls.every(button=>button.disabled));await captured();assert.equal(requests.filter(r=>r.method==='POST').length,1);
assert(nodes['workforceEditAttendance_draft-source'].disabled,'draft editing must also remain locked during a Human mutation');
release();await pending;
assert(!nodes.workforceContent.querySelectorAll('[data-workforce-human]').some(button=>button.dataset.workforceHuman.includes('draft-source')));
''',modules=('workforce.js',))


def test_existing_timestamp_seconds_and_fraction_are_not_silently_truncated():
    run_ui(r'''
assert.equal(run("workforceJapanInput('2025-12-31T23:00:37.123456+00:00')"),'2026-01-01T08:00:37.123456');
assert.equal(run("workforceJapanInput('2026-01-01T08:00:37+09:00')"),'2026-01-01T08:00:37');
assert.equal(run("workforceLocalTime('2026-01-01T08:00:37.123456')"),'2026-01-01T08:00:37.123456+09:00');
''',modules=('workforce.js',))


def test_navigation_during_real_auth_preflight_cancels_old_draft_write():
    run_ui(r'''
authority.permissions.push('workforce.read','workforce.update','personnel.read');
const row={attendance_id:'draft-source',employee_id:'employee-source',work_date:'2026-01-01',check_in_at:'2025-12-31T23:00:00+00:00',check_out_at:null,status:'draft',version:4};
let authRelease,holdAuth=false;
endpoint=async(path,options)=>{
 if(path==='/auth/me')return holdAuth?new Promise(resolve=>authRelease=()=>resolve({user_id:authority.user_id})):{user_id:authority.user_id};
 if(path.startsWith('/workforce/attendance?'))return [row];
 if(path.startsWith('/workforce/time-entries?'))return [];
 return regularEndpoint(path);
};
await run('openWorkforceSource(()=>true)');run('workforceState.permissions='+JSON.stringify(authority.permissions));await run('workforceAttendance()');
await nodes['workforceEditAttendance_draft-source'].onclick();
holdAuth=true;const pending=nodes.workforceSaveAttendanceEdit.onclick();await flush();assert(authRelease);
run('workforceState.viewGeneration++');nodes.workforceContent.innerHTML='Newer Human view';
authRelease();await pending;
assert(!requests.some(request=>request.method==='PATCH'),'old form must not write after navigation during auth');
assert.equal(nodes.workforceContent.innerHTML,'Newer Human view');
''',modules=('workforce.js',))
