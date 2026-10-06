"""Exercise real administration JS against configured and unset Human policy."""
from pathlib import Path
import subprocess
import pytest


@pytest.mark.parametrize('days',[None,30])
def test_administration_shows_policy_and_disables_unavailable_choice(tmp_path,days):
    root=Path(__file__).resolve().parents[2]
    script=tmp_path/'admin-policy.js'
    script.write_text(r'''
const vm=require('vm'),fs=require('fs');const nodes=new Map();
class Node {
 constructor(){this.value='';this.textContent='';this.hidden=false;this.disabled=false;this.options=[];this.dataset={};this.elements=new Proxy({}, {get:(_,key)=>node('field-'+key)});}
 addEventListener(){} replaceChildren(){this.options=[];} appendChild(item){this.options.push(item);return item;}
 querySelector(){return new Node();} querySelectorAll(){return [];} append(){}
}
const node=id=>{if(!nodes.has(id))nodes.set(id,new Node());return nodes.get(id);};node('field-mode').value='policy';
const days=JSON.parse(process.argv[3]);
const context={console,Set,URLSearchParams,Option:function(label,value){this.label=label;this.value=value;},
 document:{getElementById:node,createElement:()=>new Node(),createTextNode:()=>new Node(),querySelectorAll:()=>[]},
 fetch:async path=>({ok:true,status:200,json:async()=>path==='/administration/context'?{permissions:['account.manage'],username:'synthetic',business_date:'2026-10-06',department:'synthetic',password_max_age_days:days}:[]})};
vm.createContext(context);vm.runInContext(fs.readFileSync(process.argv[2],'utf8'),context);
setImmediate(()=>setImmediate(()=>{
 try{
  if(days===null){
   if(!node('passwordPolicy').textContent.includes('未設定'))throw Error('unset policy hidden from Human');
   if(!node('expiryPolicyOption').disabled||node('field-mode').value==='policy')throw Error('unavailable policy remains selected');
  }else{
   if(!node('passwordPolicy').textContent.includes(String(days)))throw Error('configured day count hidden from Human');
   if(node('expiryPolicyOption').disabled)throw Error('configured policy disabled');
  }
 }catch(error){console.error(error.stack);process.exitCode=1;}
}));
''')
    import json
    result=subprocess.run(['node',str(script),str(root/'frontend/admin.js'),json.dumps(days)],capture_output=True,text=True,timeout=10)
    assert result.returncode==0,result.stderr
