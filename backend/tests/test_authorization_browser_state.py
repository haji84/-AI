"""Run actual permission-page JavaScript to reproduce draft CAS and auth loss."""
from pathlib import Path
import subprocess


def run_js(tmp_path,scenario):
    root=Path(__file__).resolve().parents[2]
    harness=r'''
const vm=require('vm'),fs=require('fs');
class Node{constructor(){this.value='';this.textContent='';this.hidden=false;this.disabled=false;this.checked=false;this.options=[];this.inputs=[];this.handlers={};this.fields={};this.children={};this.elements=new Proxy(this.fields,{get:(obj,key)=>obj[key]||(obj[key]=new Node())});}
 addEventListener(name,callback){this.handlers[name]=callback;}
 replaceChildren(){this.options=[];this.textContent='';this.inputs=[];}
 append(...items){this.options.push(...items);}
 reset(){for(const node of Object.values(this.fields)){node.value='';node.checked=false;}}
 querySelectorAll(selector){return selector==='input:checked'?this.inputs.filter(x=>x.checked):this.inputs;}
 querySelector(selector){return this.children[selector]||(this.children[selector]=new Node());}
}
const nodes=new Map(),node=id=>{if(!nodes.has(id))nodes.set(id,new Node());return nodes.get(id);};
let version=1,canManage=false,saved=null,registryReads=0;
const role=()=>({role_id:'synthetic-role',name:'Synthetic viewer',system_role:false,code:'dept_synthetic',version,active:true,permission_codes:version===1?['facility.read']:['facility.read','facility.update']});
const response=data=>({ok:true,status:200,json:async()=>data});
const context={console,URL,location:{origin:'http://example.local'},Set,Map,Option:function(label,value){this.label=label;this.value=value;},FormData:function(form){this[Symbol.iterator]=function*(){for(const [key,field] of Object.entries(form.fields)){if(field.checked)yield[key,'on'];else if(!['active','sensitive_acknowledged'].includes(key))yield[key,field.value];}};},
 window:{confirm:()=>true,prompt:()=>''},document:{getElementById:node,createElement:()=>new Node(),createTextNode:text=>({textContent:text}),querySelectorAll:selector=>selector==='form'?['loginForm','roleForm','ruleForm','grantForm'].map(node):selector==='.sourceEvidence,.roleSelect'?[]:[]},
 fetch:async(path,options={})=>{if(options.method==='PATCH'){saved=JSON.parse(options.body);return {ok:false,status:409,json:async()=>({detail:'version conflict'})};}
 if(path==='/administration/permissions'){registryReads++;return response([{code:'facility.read',description:'Synthetic facility viewer',sensitive:false}]);}
 if(path==='/administration/context')return response({username:'synthetic-user',permissions:[]});
 if(path==='/administration/own-role-explanation')return response({username:'synthetic-user',business_date:'2026-10-07',roles:[],permissions:canManage?[{code:'account.manage'}]:[]});
 if(path.startsWith('/administration/permission-roles'))return response([role()]);return response([]);
 }};
vm.createContext(context);vm.runInContext(fs.readFileSync(process.argv[2],'utf8'),context);
const turn=()=>new Promise(resolve=>setImmediate(resolve));
(async()=>{await turn();await turn();
SCENARIO
})().catch(error=>{console.error(error.stack);process.exitCode=1;});
'''
    script=tmp_path/'permissions-harness.js';script.write_text(harness.replace('SCENARIO',scenario))
    result=subprocess.run(['node',str(script),str(root/'frontend/permissions.js')],capture_output=True,text=True,timeout=10)
    assert result.returncode==0,result.stderr


def test_refresh_does_not_rebase_old_editor_draft_onto_new_server_version(tmp_path):
    run_js(tmp_path,r'''
canManage=true;vm.runInContext('state.canManage=true;',context);await vm.runInContext('refresh()',context);
node('roleEdit').value='synthetic-role';vm.runInContext('editRole()',context);
node('roleForm').elements.reason.value='Human old draft';const choice=new Node();choice.value='facility.read';choice.checked=true;node('permissionChoices').inputs=[choice];
version=2;await vm.runInContext('refresh()',context);
await node('roleForm').handlers.submit({preventDefault(){},target:node('roleForm')});
if(!saved||saved.expected_version!==1)throw Error('old draft silently rebased onto server version '+saved?.expected_version);
''')


def test_expired_management_rights_clear_restricted_lists_and_drafts(tmp_path):
    run_js(tmp_path,r'''
canManage=true;vm.runInContext("state.canManage=true;state.roles=[{name:'PRIVATE role'}];state.accounts=[{username:'PRIVATE account'}];state.staff=[{display_name:'PRIVATE staff'}];state.sources.set('ruleForm',{source_document_id:'PRIVATE source'});",context);
node('manager').hidden=false;node('roleList').textContent='PRIVATE role';node('grantList').textContent='PRIVATE grant';node('ruleForm').elements.title.value='PRIVATE title';
canManage=false;await vm.runInContext('refresh()',context);
if(vm.runInContext('state.canManage||state.roles.length||state.accounts.length||state.staff.length||state.sources.size',context))throw Error('restricted state survives loss of management authority');
if(!node('manager').hidden)throw Error('restricted manager stays visible');
for(const id of ['roleList','grantList'])if(node(id).textContent)throw Error(id+' private records survive');
if(node('ruleForm').elements.title.value)throw Error('private draft survives');
''')


def test_regained_management_authority_reloads_permission_registry(tmp_path):
    run_js(tmp_path,r'''
canManage=true;await vm.runInContext('refresh()',context);
if(!registryReads||!vm.runInContext("state.permissions.some(x=>x.code==='facility.read')",context))throw Error('new management authority has no refreshed permission registry');
''')
