"""Actual shared-session, workforce detail and closed search handoff code."""
import pytest
from test_statistics_browser_state import run_ui


@pytest.mark.parametrize('interruption',['none','header','new_human','new_human_error','popstate'])
def test_exact_search_source_handoff_owns_delayed_body(interruption):
    run_ui(r'''
nodes.unifiedSearchModal=element('unifiedSearchModal');nodes.unifiedSearchSummary=element('unifiedSearchSummary');
context.closeUnifiedSearch=()=>nodes.unifiedSearchModal.classList.add('hidden');
authority.permissions.push('workforce.read','personnel.read');
let release;endpoint=async path=>path.startsWith('/workforce/source-records/')?new Promise(resolve=>release=()=>resolve(INTERRUPTION==='new_human_error'?new Response(JSON.stringify({detail:'obsolete original inaccessible'}),{status:403}):{kind:'roster',record_id:'synthetic-source',version:3,employee:{display_name:'PRIVATE search source'},record:{status:'approved'},required_permissions:['workforce.read','personnel.read']})):regularEndpoint(path);
const pending=run("openUnifiedWorkforceSource('synthetic-source')");await flush();assert(release);
if(INTERRUPTION==='header'){const button=element('assetsBtn');button.header=true;for(const fn of windowHandlers.click??[])fn({type:'click',target:button});}
if(INTERRUPTION==='popstate')for(const fn of windowHandlers.popstate??[])fn({type:'popstate'});
if(INTERRUPTION==='new_human'||INTERRUPTION==='new_human_error'){run('workforceState.viewGeneration++');nodes.workforceContent.innerHTML='Newer Human view';}
release();await pending;
if(INTERRUPTION==='none'){assert(nodes.workforceContent.innerHTML.includes('PRIVATE search source'));assert(nodes.workforceContent.innerHTML.includes('Version 3'));assert.equal(nodes.workforceContent.querySelectorAll('[data-workforce-human]').length,0);}
else assert(!nodes.workforceContent?.innerHTML.includes('PRIVATE search source'));
if(INTERRUPTION==='new_human'||INTERRUPTION==='new_human_error'){assert.equal(nodes.workforceContent.innerHTML,'Newer Human view');assert(nodes.unifiedSearchModal.classList.contains('hidden'));assert.equal(nodes.unifiedSearchSummary.textContent,'');}
'''.replace('INTERRUPTION',repr(interruption)),modules=('workforce.js','unified-source.js'))
