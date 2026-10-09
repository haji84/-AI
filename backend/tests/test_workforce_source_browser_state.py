"""Real statistics and workforce code share exact modal/navigation ownership."""
import pytest
from test_statistics_browser_state import run_ui


def test_old_normal_request_denial_cannot_close_new_exact_source():
    run_ui(r'''
authority.permissions.push('workforce.read','personnel.read');
let release;endpoint=async path=>path==='/workforce/old-pending'?new Promise(resolve=>release=()=>resolve(new Response(JSON.stringify({detail:'old request denied'}),{status:403}))):path.startsWith('/workforce/source-records/')?{kind:'roster',record_id:'synthetic-source',version:2,employee:{display_name:'PRIVATE current employee'},record:{status:'approved'},required_permissions:['workforce.read','personnel.read']}:regularEndpoint(path);
const sourceEndpoint=endpoint;endpoint=async path=>path==='/auth/me'?{user_id:authority.user_id}:sourceEndpoint(path);
const pending=run("workforceAPI('/workforce/old-pending').catch(error=>({cancelled:error.cancelled}))");await flush();assert(release);
await run('openStatistics()');await run("statisticsOpenSource({navigation:{surface:'workforce_roster',id:'synthetic-source'}})");
assert(nodes.workforceContent.innerHTML.includes('PRIVATE current employee'));
release();const result=await pending;
assert.equal(result.cancelled,true);
assert(nodes.workforceModal&&!nodes.workforceModal.classList.contains('hidden'));
assert(nodes.workforceContent.innerHTML.includes('PRIVATE current employee'));
''', modules=('workforce.js',))


@pytest.mark.parametrize('kind', ['roster','attendance','time'])
def test_statistics_opens_exact_readonly_workforce_source_with_live_rights(kind):
    run_ui(r'''
const kind=__KIND__;
authority.permissions.push('workforce.read','personnel.read','workforce.aggregate');
endpoint=async path=>path.startsWith('/workforce/source-records/')?{kind,record_id:'synthetic-source',version:2,employee:{display_name:'PRIVATE current employee'},record:{status:'approved',work_date:'2026-01-01',occurred_on:'2026-01-01',worked_minutes:990,minutes:100},required_permissions:['workforce.read','personnel.read']}:regularEndpoint(path);
await run('openStatistics()');await run('statisticsOpenSource('+JSON.stringify({navigation:{surface:'workforce_'+kind,id:'synthetic-source'}})+')');
assert(nodes.workforceModal&&!nodes.workforceModal.classList.contains('hidden'));
assert(nodes.workforceContent.innerHTML.includes('PRIVATE current employee'));
assert(nodes.workforceContent.innerHTML.includes('Version 2'));
assert(requests.some(r=>r.path==='/workforce/source-records/'+kind+'/synthetic-source'));
assert.equal(nodes.workforceContent.querySelectorAll('[data-workforce-human]').length,0);
'''.replace('__KIND__',repr(kind)), modules=('workforce.js',))


@pytest.mark.parametrize('interruption', ['home','human','human_error','rights'])
def test_deferred_workforce_source_body_cannot_restore_private_or_close_new_view(interruption):
    run_ui(r'''
authority.permissions.push('workforce.read','personnel.read');
let release;endpoint=async path=>path.startsWith('/workforce/source-records/')?new Promise(resolve=>release=()=>resolve(INTERRUPTION==='human_error'?new Response(JSON.stringify({detail:'synthetic source document inaccessible'}),{status:403}):{kind:'roster',record_id:'synthetic-source',version:1,employee:{display_name:'PRIVATE delayed employee'},record:{status:'approved'},required_permissions:['workforce.read','personnel.read']})):regularEndpoint(path);
await run('openStatistics()');const pending=run("statisticsOpenSource({navigation:{surface:'workforce_roster',id:'synthetic-source'}})");await flush();assert(release,'exact source request not started');
if(INTERRUPTION==='home')run('closeStatistics()');
if(INTERRUPTION==='human'||INTERRUPTION==='human_error'){run('workforceState.viewGeneration++');nodes.workforceContent.innerHTML='Newer Human view';}
if(INTERRUPTION==='rights')authority={...authority,permissions:authority.permissions.filter(p=>p!=='personnel.read')};
release();await pending;
assert(!nodes.workforceContent?.innerHTML.includes('PRIVATE delayed employee'));
if(INTERRUPTION==='human'||INTERRUPTION==='human_error')assert.equal(nodes.workforceContent.innerHTML,'Newer Human view');
else assert(!nodes.workforceModal||nodes.workforceModal.classList.contains('hidden'));
'''.replace('INTERRUPTION',repr(interruption)), modules=('workforce.js',))
