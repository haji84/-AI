"""Actual team controls keep Human reasons, canonical assignment IDs and view ownership."""
from test_statistics_browser_state import run_ui
import pytest


def test_assignment_fetch_failure_is_visible_without_undefined_error_helper():
    run_ui(r'''
authority.permissions.push('workforce.read','workforce.admin','personnel.read');
endpoint=async(path)=>{
 if(path==='/auth/me')return {user_id:authority.user_id};
 if(path==='/administration/staff/employee-a/assignments')throw new Error('Synthetic personnel service unavailable');
 return regularEndpoint(path);
};
await run('openWorkforceSource(()=>true)');run('workforceState.permissions='+JSON.stringify(authority.permissions));
run("workforceState.employees=[{employee_id:'employee-a',display_name:'Synthetic member'}]");
run("workforceTeamMemberForm({team_id:'team-a',organization_id:'org-a',version:1})");
nodes.workforceField_employee_id.value='employee-a';await nodes.workforceField_employee_id.onchange();
assert(nodes.workforceMessage.textContent.includes('Synthetic personnel service unavailable'));
assert(!requests.some(request=>request.method==='POST'));
''',modules=('workforce.js','workforce-teams.js'))


def test_team_ui_creates_only_explicit_human_group_once():
    run_ui(r'''
authority.permissions.push('workforce.read','workforce.admin','personnel.read');
let created=false,release;
endpoint=async(path,options)=>{
 if(path==='/auth/me')return {user_id:authority.user_id};
 if(path==='/workforce/teams'&&options.method==='POST'){
  assert.deepEqual(JSON.parse(options.body),{organization_id:'org-a',code:'Synthetic team',name:'Synthetic group',reason:'Synthetic Human setup'});
  return new Promise(resolve=>release=()=>{created=true;resolve({team_id:'team-a',version:1})});
 }
 if(path.startsWith('/workforce/teams?'))return {items:created?[{team_id:'team-a',organization_id:'org-a',code:'Synthetic team',name:'Synthetic group',active:true,version:1}]:[],limit:100,offset:0};
 return regularEndpoint(path);
};
await run('openWorkforceSource(()=>true)');run('workforceState.permissions='+JSON.stringify(authority.permissions));
run("workforceState.organizations=[{organization_id:'org-a',code:'SYN',name:'Synthetic station'}]");
await run('workforceTeams()');await nodes.workforceTeamNew.onclick();
nodes.workforceField_organization_id.value='org-a';nodes.workforceField_code.value='Synthetic team';nodes.workforceField_name.value='Synthetic group';nodes.workforceField_reason.value='Synthetic Human setup';
const captured=nodes.workforceTeamSave.onclick,pending=captured();await flush();assert(release);assert(nodes.workforceTeamSave.disabled);
await captured();assert.equal(requests.filter(request=>request.method==='POST').length,1);
release();await pending;assert(nodes.workforceContent.innerHTML.includes('Synthetic group'));
assert.equal(requests.filter(request=>request.method==='POST').length,1);
''',modules=('workforce.js','workforce-teams.js'))


@pytest.mark.parametrize('navigation',[False,True])
def test_membership_uses_selected_canonical_assignment_and_cancels_obsolete_write(navigation):
    run_ui(r'''
authority.permissions.push('workforce.read','workforce.admin','personnel.read');
const team={team_id:'team-a',name:'Synthetic group',organization_id:'org-a',active:true,version:5};
let created=false,holdAuth=false,authRelease;
endpoint=async(path,options)=>{
 if(path==='/auth/me')return holdAuth?new Promise(resolve=>authRelease=()=>resolve({user_id:authority.user_id})):{user_id:authority.user_id};
 if(path==='/administration/staff/employee-a/assignments')return [{assignment_id:'assignment-a',organization_id:'org-a',kind:'primary',valid_from:'2026-01-01',version:7,role_ids:['not-a-grant']},{assignment_id:'other-org',organization_id:'org-b',kind:'primary',valid_from:'2026-01-01',version:1}];
 if(path==='/workforce/teams/team-a/members'&&options.method==='POST'){
  assert.deepEqual(JSON.parse(options.body),{employee_id:'employee-a',assignment_id:'assignment-a',valid_from:'2026-01-01',reason:'Synthetic Human membership',expected_team_version:5,expected_assignment_version:7});created=true;
  return {team_version:6,membership:{membership_id:'member-a'}};
 }
 if(path.startsWith('/workforce/teams/team-a/members?'))return {team:{...team,version:created?6:5},items:created?[{membership_id:'member-a',employee_name:'Synthetic member',valid_from:'2026-01-01',assignment_version:7,version:1,active:true,operational_status:'current'}]:[]};
 return regularEndpoint(path);
};
await run('openWorkforceSource(()=>true)');run('workforceState.permissions='+JSON.stringify(authority.permissions));run("workforceState.employees=[{employee_id:'employee-a',display_name:'Synthetic member'}]");
await run("workforceTeamMembers('team-a')");await nodes.workforceTeamMemberNew.onclick();
nodes.workforceField_employee_id.value='employee-a';await nodes.workforceField_employee_id.onchange();
assert(nodes.workforceField_assignment_id.innerHTML.includes('assignment-a'));assert(!nodes.workforceField_assignment_id.innerHTML.includes('other-org'));assert(!nodes.workforceContent.innerHTML.includes('not-a-grant'));
nodes.workforceField_assignment_id.value='assignment-a';nodes.workforceField_valid_from.value='2026-01-01';nodes.workforceField_reason.value='Synthetic Human membership';
if(NAVIGATION){
 holdAuth=true;const pending=nodes.workforceTeamMemberSave.onclick();await flush();assert(authRelease);
 run('workforceState.viewGeneration++');nodes.workforceContent.innerHTML='Newer Human view';authRelease();await pending;
 assert(!requests.some(request=>request.method==='POST'));assert.equal(nodes.workforceContent.innerHTML,'Newer Human view');
}else{await nodes.workforceTeamMemberSave.onclick();assert.equal(requests.filter(request=>request.method==='POST').length,1);assert(nodes.workforceContent.innerHTML.includes('Synthetic member'));}
'''.replace('NAVIGATION','true' if navigation else 'false'),modules=('workforce.js','workforce-teams.js'))


def test_current_module_disable_clears_previous_private_team_surface():
    run_ui(r'''
authority.permissions.push('workforce.read','personnel.read');
endpoint=async(path)=>{
 if(path==='/auth/me')return {user_id:authority.user_id};
 if(path.startsWith('/workforce/teams?'))throw Object.assign(new Error('Synthetic module disabled'),{status:503});
 return regularEndpoint(path);
};
await run('openWorkforceSource(()=>true)');run('workforceState.permissions='+JSON.stringify(authority.permissions));nodes.workforceContent.innerHTML='PRIVATE previous team view';
try{await run('workforceTeams()')}catch(error){assert.equal(error.status,503)}
assert(!nodes.workforceModal,'current disabled team module must clear its private surface');
''',modules=('workforce.js','workforce-teams.js'))
