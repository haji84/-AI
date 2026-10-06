"""Run real page JavaScript in a minimal DOM to exercise auth/cancellation races."""
from pathlib import Path
import subprocess


def run_js(tmp_path,scenario):
    root=Path(__file__).resolve().parents[2]
    harness=r'''
const vm=require('vm'),fs=require('fs');
const nodes=new Map();
class Node {
 constructor(){this.value='';this.textContent='';this.hidden=false;this.disabled=false;this.options=[];this.handlers={};}
 addEventListener(name,callback){this.handlers[name]=callback;}
 replaceChildren(){this.options=[];this.textContent='';}
 appendChild(item){this.options.push(item);if(!this.value&&item.value)this.value=item.value;return item;}
 reset(){this.value='';}
}
const node=id=>{if(!nodes.has(id))nodes.set(id,new Node());return nodes.get(id);};
let account='first',pendingOlder=null;
const response=data=>({ok:true,status:200,json:async()=>data});
const context={console,URLSearchParams,Set,FormData:function(){this.get=()=>'';},Option:function(label,value){this.label=label;this.value=value;},
 window:{confirm:()=>true},document:{getElementById:node,createElement:()=>new Node(),querySelectorAll:()=>[]},
 fetch:async path=>{
  if(path==='/learning/context')return response({user_id:account,username:account,permissions:['learning.read','learning.record','document.read','intake.read','fire_investigation.read'],tasks:['ocr','audio_correction'],production_mode:false});
  if(path.includes('offset=100'))return await new Promise(resolve=>{pendingOlder=resolve;});
  if(path.startsWith('/learning/champions/')&&!path.endsWith('/history'))return response({version:1,artifact_id:null});
  return response([]);
 }};
vm.createContext(context);vm.runInContext(fs.readFileSync(process.argv[2],'utf8'),context);
const turn=()=>new Promise(resolve=>setImmediate(resolve));
(async()=>{await turn();await turn();
SCENARIO
})().catch(error=>{console.error(error.stack);process.exitCode=1;});
'''
    script=tmp_path/'harness.js';script.write_text(harness.replace('SCENARIO',scenario))
    result=subprocess.run(['node',str(script),str(root/'frontend/learning.js')],capture_output=True,text=True,timeout=10)
    assert result.returncode==0,result.stderr


def test_logout_and_next_account_remove_restricted_drafts(tmp_path):
    run_js(tmp_path,r'''
vm.runInContext("state.cases=[{input:'PRIVATE evidence',expected:'secret'}];el('setEvidence').textContent='PRIVATE';el('suggestion').textContent='PRIVATE';el('humanReason').value='PRIVATE';",context);
await node('logoutButton').handlers.click();account='second';await vm.runInContext('start()',context);
if(vm.runInContext('state.cases.length',context)!==0)throw Error('private draft survives logout');
for(const id of ['setEvidence','suggestion'])if(node(id).textContent)throw Error(id+' survives logout');
if(node('humanReason').value)throw Error('private reason survives logout');
''')


def test_old_pagination_cannot_cross_task_or_account(tmp_path):
    run_js(tmp_path,r'''
vm.runInContext('state.correctionOffset=100;',context);
const load=node('correctionOlder').handlers.click();await turn();
vm.runInContext("state.task='audio_correction';",context);
pendingOlder(response([{correction_id:'old-ocr',task:'ocr',review_status:'approved',synthetic:true,input_text:'old',output_text:'x'}]));await load;
if(vm.runInContext("state.corrections.some(row=>row.correction_id==='old-ocr')",context))throw Error('old correction crosses task');
''')


def test_logout_invalidates_pending_response_before_next_account(tmp_path):
    run_js(tmp_path,r'''
vm.runInContext('state.correctionOffset=100;',context);
const load=node('correctionOlder').handlers.click();await turn();
await node('logoutButton').handlers.click();account='second';await vm.runInContext('start()',context);
pendingOlder(response([{correction_id:'restricted-first',task:'ocr',review_status:'approved',synthetic:true,input_text:'PRIVATE',output_text:'secret'}]));await load;
if(vm.runInContext("state.corrections.some(row=>row.correction_id==='restricted-first')",context))throw Error('restricted response crosses account');
if(!node('message').textContent.includes('second'))throw Error('stale response overwrites current status');
''')
