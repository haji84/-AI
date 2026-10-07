"""Common search must reuse the register's permission and module boundary."""
import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from test_hazardous_register import hazardous_env, learning_environment, install, record, revoke


def search(client, query, module=True):
    from app.routers import search as unified
    if not getattr(client.app.state, 'hazardous_search_installed', False):
        client.app.include_router(unified.router)
        client.app.state.hazardous_search_installed = True
    params = {'q': query}
    if module:
        params['modules'] = 'hazardous_materials'
    return client.get('/search', params=params)


def test_search_uses_registry_pointer_without_copying_evidence(hazardous_env):
    client, _, refs = hazardous_env
    parent = install(client, refs, name='Synthetic-Hazard-Search')
    source = record(client, parent, refs, title='Private evidence title outside registry search')
    response = search(client, parent['name'])
    assert response.status_code == 200, response.text
    body = response.json()
    assert body['total_hits'] == 1
    hit = body['hits'][0]
    assert hit['source_id'] == parent['installation_id']
    assert hit['building_id'] == parent['building_id']
    assert hit['navigation'] == {'surface': 'hazardous_materials', 'record_id': parent['installation_id']}
    assert hit['evidence']['record_version'] == parent['version']
    assert source['record_id'] not in response.text
    assert source['title'] not in response.text
    assert refs['proof'] not in response.text


@pytest.mark.parametrize('right', ['hazardous.read', 'facility.read'])
def test_search_requires_both_registry_and_facility_rights(hazardous_env, right):
    client, engine, refs = hazardous_env
    parent = install(client, refs, name='Synthetic-Hazard-Restricted')
    revoke(engine, right)
    forbidden = search(client, parent['name'])
    assert forbidden.status_code == 403, forbidden.text
    response = search(client, parent['name'], module=False)
    assert response.status_code == 200, response.text
    assert parent['installation_id'] not in response.text
    assert 'hazardous_materials' not in response.json()['searched_modules']


def test_disabled_register_does_not_return_search_hits(hazardous_env):
    from app.models import FeatureFlag
    client, engine, refs = hazardous_env
    parent = install(client, refs, name='Synthetic-Hazard-Disabled')
    with Session(engine) as db:
        db.scalar(select(FeatureFlag).where(FeatureFlag.key == 'module.hazardous_materials.enabled')).enabled = False
        db.commit()
    response = search(client, parent['name'])
    assert response.status_code == 200, response.text
    assert response.json()['hits'] == []
    assert response.json()['total_hits'] == 0
    assert parent['installation_id'] not in response.text


def test_shared_search_opens_installation_before_facility_fallback(tmp_path):
    from pathlib import Path
    import subprocess
    root = Path(__file__).resolve().parents[2]
    script = tmp_path / 'hazardous-search-navigation.js'
    script.write_text(r'''
const fs=require('fs'),vm=require('vm'),assert=require('assert');
const html=fs.readFileSync(process.argv[2],'utf8');
const start=html.indexOf('function unifiedSearchAction('),end=html.indexOf('async function runUnifiedSearch(',start);
assert(start>=0&&end>start);
const opened=[];
const context={esc:v=>String(v),alert:message=>{throw Error(message);},closeUnifiedSearch(){},hazardousAction:async fn=>fn(),hazardousDetail:async id=>opened.push(id),selectFacility(){throw Error('installation incorrectly navigated to its facility');}};
vm.createContext(context);vm.runInContext(html.slice(start,end),context);
(async()=>{
 const button=vm.runInContext("unifiedSearchAction({module:'hazardous_materials',source_type:'hazardous_installation',source_id:'installation-1',building_id:'building-1',navigation:{surface:'hazardous_materials',record_id:'installation-1'}})",context);
 assert(button.includes('installation-1'));
 await vm.runInContext("openUnifiedSearchHit('hazardous_materials','hazardous_installation','installation-1','building-1','')",context);
 assert.deepEqual(opened,['installation-1']);
})().catch(error=>{console.error(error.stack);process.exitCode=1;});
''')
    result = subprocess.run(['node', str(script), str(root / 'frontend/index.html')], capture_output=True, text=True, timeout=10)
    assert result.returncode == 0, result.stderr
