"""Execute the actual facility shell and session guard in Node, with synthetic HTTP."""
from pathlib import Path
import subprocess


def run_shell(tmp_path, scenario):
    root = Path(__file__).resolve().parents[2]
    script = r'''
const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
class Node {
 constructor(id){this.id=id;this.innerHTML='';this.textContent='';this.value='';this.hidden=false;this.disabled=false;this.classList={add(){},remove(){},toggle(){}};}
 addEventListener(){}
}
const nodes=new Map(),node=id=>{if(!nodes.has(id))nodes.set(id,new Node(id));return nodes.get(id);};
let permissions=['facility.read'],session='synthetic-a',calls=[],alerts=[],delayedPath=null,release=null;
const facility={building_id:'synthetic-facility',name:'Synthetic visible facility',status:'active',version:1};
const response=data=>new Response(JSON.stringify(data),{headers:{'Content-Type':'application/json'}});
const context={console,URL,URLSearchParams,Response,WeakSet,Event,setTimeout,clearTimeout,
 location:{origin:'http://synthetic.local',pathname:'/ui/',reload(){}},addEventListener(){},
 document:{getElementById:node,querySelectorAll:()=>[],addEventListener(){}},alert:text=>alerts.push(text),
 fetch:async(path)=>{
  if(path==='/auth/context')return response({user_id:'synthetic-user',session_id:session,tenant_id:null,permissions});
  calls.push(path);
  if(path==='/auth/permissions')return response({permissions});
  if(path===delayedPath)return await new Promise(resolve=>release=()=>resolve(response([{inspection_id:'PRIVATE old',inspected_at:'2026-10-02',findings:[]}])));
  if(path.endsWith('/detail'))return response({facility,detail:{},contact:{},floors:[]});
  if(path.endsWith('/history')||path.endsWith('/legacy-review'))return response([]);
  if(path.endsWith('/dashboard'))return response({building_id:facility.building_id,
   inspections_total:permissions.includes('inspection.read')?0:null,
   open_findings:permissions.includes('inspection.read')?0:null,latest_inspection_at:null,
   submission_statuses:permissions.includes('submission.read')?[{code:'fire_plan',name:'消防計画',state:'not_submitted'}]:null});
  for(const [suffix,code] of [['/inspections?','inspection.read'],['/submissions?','submission.read'],['/equipment','equipment.read'],['/drawing-analyses','drawing.read']]){
   if(path.includes(suffix))return permissions.includes(code)?response([]):new Response('{"detail":"forbidden"}',{status:403});
  }
  if(path.startsWith('/facilities?'))return response({items:[facility],total:1});
  throw Error('Unexpected HTTP '+path);
 }
};context.window=context;vm.createContext(context);
vm.runInContext(fs.readFileSync(process.argv[2]+'/frontend/shared-session.js','utf8'),context);
const html=fs.readFileSync(process.argv[2]+'/frontend/index.html','utf8');
for(const match of html.matchAll(/<script(?:\s[^>]*)?>([\s\S]*?)<\/script>/gi))if(match[1].trim())vm.runInContext(match[1],context);
const execute=source=>vm.runInContext(source,context),turn=()=>new Promise(resolve=>setImmediate(resolve));
(async()=>{
SCENARIO
})().catch(error=>{console.error(error.stack);process.exitCode=1;});
'''
    harness = tmp_path / 'facility-shell.js'
    harness.write_text(script.replace('SCENARIO', scenario))
    result = subprocess.run(['node', str(harness), str(root)], capture_output=True, text=True, timeout=15)
    assert result.returncode == 0, result.stderr


def test_facility_only_reader_opens_detail_without_forbidden_module_requests(tmp_path):
    run_shell(tmp_path, r'''
await execute("selectFacility('synthetic-facility')");
assert.deepEqual(alerts,[]);
assert.equal(execute('state.detail.facility.name'),'Synthetic visible facility');
assert(!calls.some(path=>/\/inspections\?|\/submissions\?|\/equipment$|\/drawing-analyses$/.test(path)),calls.join('\n'));
const rendered=node('detailView').innerHTML;
for(const label of ['査察情報は閲覧権限がありません','届出情報は閲覧権限がありません','設置設備情報は閲覧権限がありません','図面解析情報は閲覧権限がありません'])assert(rendered.includes(label),label);
for(const misleading of ['査察 0件','未完了指摘 0件','登録確認なし・要否未判定','査察履歴なし','届出記録なし','設置設備記録なし','図面解析記録なし'])assert(!rendered.includes(misleading),misleading);
for(const key of ['inspections','submissions','equipment','drawings'])assert.equal(execute('state.'+key),null,key);
''')


def test_partial_source_rights_preserve_authorized_empty_values(tmp_path):
    run_shell(tmp_path, r'''
permissions=['facility.read','inspection.read','equipment.read'];
await execute("selectFacility('synthetic-facility')");
assert.deepEqual(alerts,[]);
assert(calls.some(path=>path.startsWith('/inspections?')));
assert(calls.some(path=>path.endsWith('/equipment')));
assert(!calls.some(path=>path.startsWith('/submissions?')||path.endsWith('/drawing-analyses')));
const rendered=node('detailView').innerHTML;
for(const expected of ['査察 0件','未完了指摘 0件','査察履歴なし','設置設備記録なし','届出情報は閲覧権限がありません'])assert(rendered.includes(expected),expected);
assert(!rendered.includes('登録確認なし・要否未判定'));
''')


def test_delayed_facility_response_is_discarded_when_source_rights_change(tmp_path):
    run_shell(tmp_path, r'''
permissions=['facility.read','inspection.read'];delayedPath='/inspections?building_id=synthetic-facility';
const pending=execute("selectFacility('synthetic-facility')");
for(let i=0;i<100&&!release;i++)await turn();assert(release,'delayed inspection request started');
permissions=['facility.read'];await assert.rejects(context.FireAISession.check(),error=>error.cancelled);
// The shared reset also supersedes this navigation; the shell quietly drops
// its cancelled result. The authority check above must still reject it.
release();await pending;
assert.deepEqual(alerts,[]);
assert.equal(execute('state.detail'),null);
assert(!node('detailView').innerHTML.includes('PRIVATE old'));
delayedPath=null;session='synthetic-b';calls=[];
await execute("selectFacility('synthetic-facility')");
assert.equal(execute('state.inspections'),null);
assert(!calls.some(path=>path.startsWith('/inspections?')));
assert(node('detailView').innerHTML.includes('査察情報は閲覧権限がありません'));
''')
