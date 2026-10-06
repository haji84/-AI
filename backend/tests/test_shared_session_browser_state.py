"""Native Response bodies and real event ownership in the common-shell guard."""
from pathlib import Path
import json
import subprocess


def test_common_guard_discards_delayed_bodies_on_same_user_relogin_and_permission_loss():
 root=Path(__file__).resolve().parents[2]
 script=r'''
const assert=require('node:assert/strict'),vm=require('node:vm');
let authority={user_id:'synthetic-user',session_id:'session-a',tenant_id:'tenant-a',permissions:['facility.read','document.read']};
let resetCount=0,bodyRelease;const handlers={};
const document={addEventListener:(name,fn)=>handlers[name]=fn,visibilityState:'visible'};
const window={location:{origin:'http://synthetic.local',pathname:'/ui/',replace:()=>{}},addEventListener:(name,fn)=>handlers[name]=fn,fetch:async(path)=>{
 if(String(path).endsWith('/auth/context'))return new Response(JSON.stringify(authority),{headers:{'Content-Type':'application/json'}});
 return new Response(new ReadableStream({start(controller){bodyRelease=text=>{controller.enqueue(new TextEncoder().encode(text));controller.close()}}}),{headers:{'Content-Type':'application/json'}});
}};
const context={window,document,URL,Response,WeakSet,Event,console};vm.createContext(context);
'''+ 'vm.runInContext('+json.dumps((root/'frontend/shared-session.js').read_text())+r''',context);
async function main(){
 assert(context.window.FireAISession,'common guard must be installed');window.FireAISession.install({reset:()=>resetCount++});
 const response=await window.fetch('/facilities');const pending=response.json();authority={...authority,session_id:'session-b'};bodyRelease('{"private":"old session"}');
 await assert.rejects(pending,e=>e.cancelled);assert.equal(resetCount,1);
 const binary=await window.fetch('/documents/synthetic/download');const blob=binary.blob();authority={...authority,permissions:['facility.read']};bodyRelease('private original');
 await assert.rejects(blob,e=>e.cancelled);assert.equal(resetCount,2);
 // Same permissions/session: cloned response bodies still preserve their data.
 const original=await window.fetch('/facilities');const clone=original.clone();bodyRelease('{"ok":true}');
 assert.deepEqual(await original.json(),{ok:true});assert.deepEqual(await clone.json(),{ok:true});
}main().catch(e=>{console.error(e);process.exitCode=1});
'''
 result=subprocess.run(['node','-e',script],capture_output=True,text=True,timeout=15)
 assert result.returncode==0,result.stderr


def test_common_guard_checks_cached_actions_and_does_not_reset_fresh_ui_for_old_errors():
 root=Path(__file__).resolve().parents[2]
 script=r'''
const assert=require('node:assert/strict'),vm=require('node:vm');
let rights=['facility.read'],session='session-a',rejectOld;const handlers={};let resets=0,actions=0;
const document={addEventListener:(name,fn)=>handlers[name]=fn,visibilityState:'visible'};
const window={location:{origin:'http://synthetic.local',pathname:'/ui/',replace:()=>{}},addEventListener:()=>{},fetch:async(path)=>{
 if(String(path).endsWith('/auth/context'))return new Response(JSON.stringify({user_id:'same',session_id:session,tenant_id:'a',permissions:rights}));
 if(path==='/slow')return await new Promise((resolve,reject)=>rejectOld=reject);
 return new Response('{}');
}};
const context={window,document,URL,Response,WeakSet,Event,console};vm.createContext(context);
'''+ 'vm.runInContext('+json.dumps((root/'frontend/shared-session.js').read_text())+r''',context);
async function main(){
 window.FireAISession.install({reset:()=>resets++});await(await window.fetch('/facilities')).json();
 const button={closest:q=>q==='#loginView'?null:button,disabled:false,isConnected:true,click(){actions++}};
 const event={type:'click',target:button,preventDefault(){},stopImmediatePropagation(){}};
 rights=[];await handlers.click(event);assert.equal(actions,0);assert.equal(resets,1);
 const old=window.fetch('/slow');await new Promise(r=>setImmediate(r));
 await window.fetch('/auth/login',{method:'POST'});await(await window.fetch('/facilities')).json();const snapshot=resets;
 rejectOld(Object.assign(new Error('old401'),{status:401}));await assert.rejects(old,e=>e.cancelled);assert.equal(resets,snapshot);
}main().catch(e=>{console.error(e);process.exitCode=1});
'''
 result=subprocess.run(['node','-e',script],capture_output=True,text=True,timeout=15)
 assert result.returncode==0,result.stderr

def test_signed_out_login_renewal_parse_errors_and_context_network_failure():
 root=Path(__file__).resolve().parents[2]
 script=r'''
const assert=require('node:assert/strict'),vm=require('node:vm');let mode='signed-out',resets=0,destination=null,release;
const document={addEventListener(){},visibilityState:'visible'};
const window={location:{origin:'http://synthetic.local',pathname:'/ui/',replace:value=>destination=value},addEventListener(){},fetch:async(path)=>{
 if(path==='/auth/context'){
  if(mode==='network-error')throw new Error('synthetic context unavailable');
  if(mode==='signed-out')return new Response('{}',{status:401});
  if(mode==='expired')return new Response('{}',{status:403,headers:{'X-FireAI-Password-Renewal':'required'}});
  return new Response(JSON.stringify({user_id:'same',session_id:'a',tenant_id:null,permissions:['facility.read']}));
 }
 if(path==='/auth/login')return new Response('{"ok":true}');
 if(path==='/invalid-json')return new Response('not JSON');
 return new Response(new ReadableStream({start(controller){release=()=>{controller.enqueue(new TextEncoder().encode('{"private":"old"}'));controller.close()}}}));
}};
const context={window,document,URL,Response,WeakSet,Event,console};vm.createContext(context);
'''+ 'vm.runInContext('+json.dumps((root/'frontend/auth-session.js').read_text())+r''',context);
'''+ 'vm.runInContext('+json.dumps((root/'frontend/shared-session.js').read_text())+r''',context);
async function main(){
 window.FireAISession.install({reset:()=>resets++});await assert.rejects(window.fetch('/facilities'),e=>e.status===401);assert.equal(resets,0);
 assert.deepEqual(await(await window.fetch('/auth/login',{method:'POST'})).json(),{ok:true});
 mode='expired';await assert.rejects(window.fetch('/facilities'),e=>e.status===403);assert.equal(destination,'/ui/password.html');
 destination=null;window.location.pathname='/ui/password.html';await assert.rejects(window.fetch('/facilities'),e=>e.status===403);assert.equal(destination,null);
 mode='active';const malformed=await window.fetch('/invalid-json');await assert.rejects(malformed.json(),SyntaxError);
 const response=await window.fetch('/facilities'),body=response.json(),before=resets;mode='network-error';release();await assert.rejects(body,e=>e.cancelled);assert.equal(resets,before+1);
}main().catch(e=>{console.error(e);process.exitCode=1});
'''
 result=subprocess.run(['node','-e',script],capture_output=True,text=True,timeout=15)
 assert result.returncode==0,result.stderr
