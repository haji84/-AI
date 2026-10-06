// Small deterministic DOM adapter for running the actual finance form/picker functions.
// This tests async application behavior, not browser layout, file dialogs or HTTP.
const fs=require('fs'),vm=require('vm'),assert=require('node:assert/strict');
const nodes=new Map();
const decode=s=>s.replace(/&quot;/g,'"').replace(/&#39;/g,"'").replace(/&lt;/g,'<').replace(/&gt;/g,'>').replace(/&amp;/g,'&');
class Element{
 constructor(tag='div'){this.tag=tag;this.tagName=tag.toUpperCase();this.children=[];this.isConnected=true;this.disabled=false;this._value='';this.files=[];this.style={};const classes=new Set();this.classList={contains:x=>classes.has(x),add:x=>classes.add(x),remove:x=>classes.delete(x),toggle:(x,on)=>on?classes.add(x):classes.delete(x)};this.textContent='';this.listeners={};}
 set id(id){this._id=id;nodes.set(id,this)}get id(){return this._id}
 set value(value){this._value=String(value);if(this.tag==='input'&&this.type==='file'&&!value)this.files=[]}
 get value(){return this._value}
 set innerHTML(html){
  this.children.forEach(n=>n.remove());this.children=[];this._html=html;
  if(this.tag==='select'){this.options=[...html.matchAll(/<option value="([^"]*)"[^>]*>(.*?)<\/option>/g)].map(m=>({value:decode(m[1]),label:decode(m[2])}));return}
  for(const m of html.matchAll(/<(form|input|select|textarea|button|span|div)\b([^>]*\bid="([^"]+)"[^>]*)>/g)){
   const child=new Element(m[1]);child.id=m[3];child.disabled=/\bdisabled\b/.test(m[2]);child.type=m[2].match(/type="([^"]+)"/)?.[1];child.value=decode(m[2].match(/value="([^"]*)"/)?.[1]??'');
   if(['select','textarea'].includes(child.tag)){const content=html.slice(m.index+m[0].length).split('</'+child.tag+'>')[0];if(child.tag==='select')child.innerHTML=content;else child.value=decode(content)}
   this.children.push(child);
  }
 }
 get innerHTML(){return this._html??''}
 insertAdjacentHTML(_,html){if(this.tag==='select'){const value=this.value;this.innerHTML+=html;this.value=value}else this.innerHTML+=html}
 remove(){this.isConnected=false;this.label?.remove();this.children.forEach(c=>c.remove());if(nodes.get(this.id)===this)nodes.delete(this.id)}
 closest(selector){if(selector==='#loginView')return null;if(selector==='#financeModal')return get('financeModal');if(selector==='button')return this.tag==='button'?this:null;if(selector==='a[href]')return this.tag==='a'?this:null;if(selector.includes(','))return this;return this.label??(this.label=new Element('label'))}
 querySelectorAll(){return [...nodes.values()].filter(node=>node.isConnected&&['button','input','select','textarea'].includes(node.tag)&&node.id?.startsWith('finance')&&node.id!=='financeBtn')}
 dispatchEvent(event){return this['on'+event.type]?.(event)}
 append(child){this.children.push(child)}
 addEventListener(name,fn){(this.listeners[name]??=[]).push(fn)}
 click(){if(this.disabled)return;for(const fn of this.listeners.click??[])fn({target:this});this.lastClick=this.onclick?.();return this.lastClick}
}
for(const id of ['financeContent','financeMessage','financeModal','financeBtn','logoutBtn']){const n=new Element();n.id=id}
const get=id=>nodes.get(id)??null;
let userID='editor',rows=[],uploads=[],pending=null,meGate=null,permissionsFailure=false,postflightMeFailure=false,postflightMeGate=null,sessionExpired=false,navigationFailure=false,proposalsFailure=false,selectedPermissions=['finance.read','document.read','document.create'];
const api=async(path,opt={})=>{
 if(path==='/auth/me'){if(sessionExpired)throw Object.assign(Error('Synthetic session expired'),{status:401});if(postflightMeFailure&&uploads.length){postflightMeFailure=false;throw Object.assign(Error('Synthetic postflight identity unavailable'),{status:503})}if(postflightMeGate&&uploads.length&&!postflightMeGate.used){postflightMeGate.used=true;return await postflightMeGate.promise}if(meGate&&!meGate.used){meGate.used=true;return await meGate.promise}return {user_id:userID}};
 if(path==='/auth/permissions'){if(permissionsFailure&&uploads.length){permissionsFailure=false;throw Error('Synthetic postflight verification failed')}return {permissions:selectedPermissions}};
 if(path==='/documents/upload'){
  uploads.push(opt);if(pending)return await pending.promise;
  return {document_id:'original-'+uploads.length,original_filename:opt.body.get('file').name,sha256:'a'.repeat(64),building_id:null};
 }
 if(path.startsWith('/finance/documents'))return rows;
 if(path.startsWith('/finance/candidates')&&navigationFailure)throw Error('Synthetic navigation failed');
 if(path.startsWith('/finance/proposals')&&proposalsFailure)throw Error('Synthetic reopen unavailable');
 if(path.startsWith('/finance/'))return [];
 throw Error('Unexpected API '+path);
};
const ctx={console,URLSearchParams,FormData,Blob,$:get,esc:x=>String(x??'').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;'),api,document:{contains:node=>node?.isConnected===true,createElement:tag=>new Element(tag),body:new Element(),querySelectorAll:()=>[]},window:{listeners:{},addEventListener(name,fn){(this.listeners[name]??=[]).push(fn)}}};
vm.createContext(ctx);vm.runInContext(fs.readFileSync(process.argv[2],'utf8'),ctx);
const flush=()=>new Promise(resolve=>setImmediate(resolve));
const deferred=()=>{let resolve,reject;const promise=new Promise((yes,no)=>{resolve=yes;reject=no});return {promise,resolve,reject}};
let saved=[];
async function form(keys=['document_id']){
 ctx.financeForm('Synthetic',keys.map(key=>[key,'Original','select']).concat([['amount','Amount','money'],['title','Title']]),{amount:'250.01',title:'Draft preserved'},async data=>saved.push(data),async()=>ctx.financeCandidates());
 for(const key of keys)await ctx.financePicker(key,'/finance/documents','Original');
}
const control=(part,key='document_id')=>get('financePick_'+key+'_'+part);
function choose(key='document_id'){control('file',key).files=[new File(['Synthetic original'],'Synthetic <original>.txt',{type:'text/plain'})];control('file',key).onchange()}
function submit(){get('financeForm').onsubmit({preventDefault(){}})}
const result={document_id:'uploaded',original_filename:'Synthetic <original>.txt',sha256:'b'.repeat(64),building_id:null};

let sharedSession='session-a',contextGate=null,contextFailure=false,delayUploadBody=false,releaseUploadBody;
function installShared(){
 const handlers={};ctx.URL=URL;ctx.Response=Response;ctx.WeakSet=WeakSet;ctx.Event=Event;
 ctx.document.addEventListener=(name,fn)=>handlers[name]=fn;ctx.document.visibilityState='visible';
 ctx.window.location={origin:'http://synthetic.local',pathname:'/ui/'};
 ctx.window.fetch=async(path,opt={})=>{
  if(path==='/auth/context'){
   if(contextFailure&&uploads.length)throw Error('Synthetic post-upload context outage');
   if(contextGate&&!contextGate.used){contextGate.used=true;await contextGate.promise}
   return new Response(JSON.stringify({user_id:userID,session_id:sharedSession,tenant_id:null,permissions:selectedPermissions}));
  }
  const value=await api(path,opt);
  if(path==='/documents/upload'&&delayUploadBody)return new Response(new ReadableStream({start(controller){releaseUploadBody=()=>{controller.enqueue(new TextEncoder().encode(JSON.stringify(value)));controller.close()}}}));
  return new Response(JSON.stringify(value));
 };
 ctx.window.financeSessionPreflight=ctx.financeSessionPreflight;
 vm.runInContext(fs.readFileSync(require('path').join(require('path').dirname(process.argv[2]),'shared-session.js'),'utf8'),ctx);
 ctx.window.FireAISession.install({reset:()=>ctx.clearFinance()});
 ctx.api=async(path,opt={})=>{const response=await ctx.window.fetch(path,opt);const body=await response.json();if(!response.ok)throw Object.assign(Error(body.detail??'Synthetic request failed'),{status:response.status});return body};
 return handlers;
}

(async()=>{
 await ctx.initFinance();
 const mode=process.argv[3];
 if(mode==='permissions'){
  for(const missing of ['document.create','document.read']){selectedPermissions=['finance.read','document.create','document.read'].filter(p=>p!==missing);await ctx.initFinance();await form();assert.equal(control('file'),null);assert.equal(control('upload'),null)}
 }else if(mode==='success'){
  await form();choose();assert.equal(control('upload').disabled,false);await control('upload').onclick();
  assert.equal(uploads.length,1);assert.equal(uploads[0].method,'POST');assert.equal(uploads[0].headers,undefined);assert.deepEqual([...uploads[0].body.keys()],['file']);
  assert.equal(get('financeField_document_id').value,'original-1');assert(control('proof').innerHTML.includes('SHA256 '+'a'.repeat(64)));assert(control('proof').innerHTML.includes('Synthetic &lt;original&gt;.txt'));assert(control('proof').innerHTML.includes('/documents/original-1/download'));
  assert.equal(get('financeField_amount').value,'250.01');assert.equal(get('financeField_title').value,'Draft preserved');assert.equal(control('upload').disabled,true);
  await control('find').onclick();assert.equal(get('financeField_document_id').value,'original-1');assert(get('financeField_document_id').options.some(o=>o.value==='original-1'));
  submit();await flush();assert.equal(saved[0].document_id,'original-1');assert.equal(saved[0].amount,'250.01');
 }else if(mode==='pending'){
  await form();rows=[{...result,document_id:'old'}];await control('find').onclick();get('financeField_document_id').value='old';choose();pending=deferred();
  const run=control('upload').onclick();control('upload').onclick();await flush();assert.equal(uploads.length,1);assert.equal(get('financeSave').disabled,true);assert.equal(control('file').disabled,true);submit();await flush();assert.equal(saved.length,0);
  pending.resolve(result);await run;assert.equal(get('financeField_document_id').value,'uploaded');assert.equal(get('financeSave').disabled,false);submit();await flush();assert.equal(saved[0].document_id,'uploaded');
 }else if(mode==='retry'){
  await form();choose();pending=deferred();const run=control('upload').onclick();await flush();pending.reject(Error('Synthetic rejected'));await run;
  assert.equal(control('status').textContent,'Synthetic rejected');assert.equal(control('upload').disabled,false);assert.equal(get('financeSave').disabled,false);assert.equal(get('financeField_title').value,'Draft preserved');pending=null;await control('upload').onclick();assert.equal(uploads.length,2);assert.equal(get('financeField_document_id').value,'original-2');
 }else if(mode==='cancel'){
  await form();assert.equal(control('upload').disabled,true);await control('upload').onclick();choose();control('file').files=[];control('file').onchange();await control('upload').onclick();assert.equal(uploads.length,0);assert.equal(get('financeSave').disabled,false);
 }else if(['new-form','back','close','session','preflight-session','preflight-navigation','late-error'].includes(mode)){
  await form();choose();const original=control('status');
  if(mode.startsWith('preflight'))meGate=deferred();else pending=deferred();
  const run=control('upload').onclick();await flush();
  if(mode==='new-form'||mode==='late-error')await form();
  if(mode==='back'){await get('financeBack').onclick();await form()}
  if(mode==='close')get('financeModal').classList.add('hidden');
  if(mode==='session')userID='other-editor';
  if(mode==='preflight-session'){meGate.resolve({user_id:'other-editor'})}
  if(mode==='preflight-navigation'){await get('financeBack').onclick();await form();meGate.resolve({user_id:'editor'})}
  if(!mode.startsWith('preflight')){if(mode==='late-error')pending.reject(Error('Stale failed upload'));else pending.resolve(result)}
  await run;
  assert.equal(saved.length,0);
  if(mode.includes('session')){assert.equal(get('financeField_document_id'),null);assert.equal(get('financeModal'),null);assert.equal(vm.runInContext('financeState.identity',ctx),null)}else{assert.equal(get('financeField_document_id').value,'');assert(!control('status').textContent.includes('Stale failed upload'))}
  if(mode.startsWith('preflight'))assert.equal(uploads.length,0);
 }else if(['navigation','nav-background','close-reopen','clear-session','session-expired'].includes(mode)){
  get('financeModal').remove();await ctx.openFinance();await form();choose();pending=deferred();const run=control('upload').onclick();await flush();
  if(mode==='navigation'){for(const fn of get('financeNav').listeners.click??[])fn({target:get('financeCandidates')});await get('financeCandidates').onclick();await form()}
  if(mode==='nav-background')get('financeNav').click();
  if(mode==='close-reopen'){get('financeClose').click();await ctx.openFinance();await form()}
  if(mode==='clear-session')ctx.clearFinance();
  if(mode==='session-expired')sessionExpired=true;
  pending.resolve(result);await run;if(['clear-session','session-expired'].includes(mode)){assert.equal(get('financeModal'),null);assert.equal(vm.runInContext('financeState.permissions.length',ctx),0)}else assert.equal(get('financeField_document_id').value,mode==='nav-background'?'uploaded':'');assert.equal(saved.length,0);
 }else if(['failed-menu','failed-menu-pending','failed-back','failed-back-pending'].includes(mode)){
  get('financeModal').remove();await ctx.openFinance();await form();choose();const originalForm=get('financeForm');let run;
  if(mode.endsWith('pending')){pending=deferred();run=control('upload').onclick();await flush()}
  navigationFailure=true;
  if(mode.startsWith('failed-back'))await get('financeBack').onclick();
  else{for(const fn of get('financeNav').listeners.click??[])fn({target:get('financeCandidates')});await get('financeCandidates').onclick()}
  assert.equal(get('financeForm'),originalForm);assert.equal(get('financeField_title').value,'Draft preserved');if(run){assert.equal(get('financeMessage').textContent,'');pending.resolve(result);await run;if(mode.startsWith('failed-back'))await get('financeBack').onclick();else await get('financeCandidates').onclick()}
  assert(get('financeMessage').textContent.includes('navigation failed'));if(!run)await control('upload').onclick();
  assert.equal(uploads.length,1);assert.equal(get('financeSave').disabled,false);assert.notEqual(get('financeField_document_id').value,'');
 }else if(mode==='postflight-retry'){
  await form();choose();permissionsFailure=true;await control('upload').onclick();assert(control('status').textContent.includes('登録'));assert.equal(get('financeField_document_id').value,'');assert.equal(control('upload').disabled,true);await control('upload').onclick();assert.equal(uploads.length,1);
 }else if(mode==='same-user-read-loss'){
  await form();choose();selectedPermissions=['finance.read','document.create'];await control('upload').onclick();assert.equal(uploads.length,0);assert.equal(get('financeModal'),null);assert.equal(get('financeField_title'),null);
 }else if(mode==='permission-revoked'){
  await form();choose();pending=deferred();const run=control('upload').onclick();await flush();selectedPermissions=['finance.read'];pending.resolve(result);await run;assert.equal(get('financeModal'),null);assert.equal(get('financeField_document_id'),null);assert.equal(vm.runInContext('financeCan("document.read")',ctx),false);
 }else if(['failed-reopen','failed-reopen-pending'].includes(mode)){
  get('financeModal').remove();await ctx.openFinance();await form();choose();let run;
  if(mode.endsWith('pending')){pending=deferred();run=control('upload').onclick();await flush()}
  if(run){assert.equal(get('financeClose').disabled,true);get('financeClose').click();assert(get('financeForm'));pending.resolve(result);await run}pending=null;
  get('financeClose').click();proposalsFailure=true;await ctx.openFinance();
  assert.equal(get('financeForm'),null);assert(get('financeMessage').textContent.includes('reopen unavailable'));assert(get('financeModal'));assert.equal(get('financeBtn').classList.contains('hidden'),false);
  proposalsFailure=false;await get('financeCandidates').onclick();await form();choose();await control('upload').onclick();assert.equal(get('financeSave').disabled,false);assert.notEqual(get('financeField_document_id').value,'');
 }else if(mode==='postflight-identity-retry'){
  await form();choose();postflightMeFailure=true;await control('upload').onclick();assert(control('status').textContent.includes('原本は登録済み'));assert.equal(control('upload').disabled,true);assert.equal(get('financeField_document_id').value,'');assert.equal(control('proof').innerHTML,'');await control('upload').onclick();assert.equal(uploads.length,1);
 }else if(mode==='guarded-upload-result'){
  await form();choose();postflightMeGate=deferred();const run=control('upload').onclick();await flush();assert.equal(uploads.length,1);assert.equal(control('file').files.length,0);assert.equal(get('financeField_document_id').value,'');assert.equal(control('proof').innerHTML,'');assert.equal(get('financeSave').disabled,true);postflightMeGate.resolve({user_id:'editor'});await run;assert.equal(get('financeField_document_id').value,'original-1');
 }else if(['proof-download-denied','proof-download-session'].includes(mode)){
  get('financeModal').remove();await ctx.openFinance();await form();choose();await control('upload').onclick();assert.equal(get('financeModal').onclick,ctx.financeDocumentClick);let prevented=false,opened=false;const blob=deferred();
  ctx.URL={createObjectURL(){opened=true;return 'blob:synthetic'},revokeObjectURL(){}};ctx.fetch=async()=>mode==='proof-download-denied'?{ok:false,status:403,json:async()=>({detail:'Synthetic denied'})}:{ok:true,blob:()=>blob.promise};
  const path=control('proof').innerHTML.match(/href="([^"]+)"/)[1];const run=get('financeModal').onclick({target:{closest:()=>({getAttribute:()=>path})},preventDefault(){prevented=true}});await flush();
  if(mode==='proof-download-session'){userID='other-editor';blob.resolve(new Blob(['Synthetic original']))}await run;assert(prevented);assert.equal(opened,false);assert.equal(get('financeModal'),null);assert.equal(vm.runInContext('financeState.permissions.length',ctx),0);
 }else if(mode==='two-pickers'){
  await form(['before_document_id','after_document_id']);choose('before_document_id');choose('after_document_id');pending=deferred();const first=control('upload','before_document_id').onclick();const second=control('upload','after_document_id').onclick();await flush();assert.equal(get('financeForm').financeUploads,1);assert.equal(uploads.length,1);assert.equal(get('financeSave').disabled,true);pending.resolve(result);await Promise.all([first,second]);assert.equal(get('financeSave').disabled,false);assert.equal(get('financeField_before_document_id').value,'uploaded');assert.equal(get('financeField_after_document_id').value,'');pending=null;await control('upload','after_document_id').onclick();assert.equal(uploads.length,2);assert.equal(get('financeField_after_document_id').value,'original-2');
 }else if(mode==='control-ownership'){
  await form();get('financeField_amount').disabled=true;choose();pending=deferred();const run=control('upload').onclick();assert(get('financeField_title').disabled);assert(get('financeBack').disabled);await flush();let navigation=0;await ctx.financeAction(async()=>navigation++);assert.equal(navigation,0);pending.resolve(result);await run;assert(get('financeField_amount').disabled);assert.equal(get('financeField_title').disabled,false);assert(control('upload').disabled);assert(control('prev').disabled);assert(control('next').disabled);
  const gate=deferred();const render=ctx.financeAction(async()=>{await form();await gate.promise});await flush();choose();assert(control('upload').disabled,'file change must not unlock a control owned by an action');gate.resolve();await render;assert.equal(control('upload').disabled,false);
 }else if(['shared-preflight','shared-preflight-session','shared-upload-session','shared-upload-rights','shared-body-session','shared-postflight-outage','shared-canonical-postflight'].includes(mode)){
  await form();choose();const button=control('upload');const handlers=installShared();await ctx.window.FireAISession.check();
  if(mode==='shared-canonical-postflight'){
   postflightMeFailure=true;await button.onclick();assert.equal(uploads.length,1);assert.equal(get('financeField_document_id').value,'');assert.equal(control('proof').innerHTML,'');assert(control('status').textContent.includes('原本は登録済み'));assert(button.disabled);await button.onclick();assert.equal(uploads.length,1);
  }else if(mode.startsWith('shared-preflight')){
   contextGate=deferred();pending=deferred();const event=handlers.click({type:'click',target:button,preventDefault(){},stopImmediatePropagation(){}});
   assert(get('financeField_title').disabled);assert(get('financeSave').disabled);assert(control('file').disabled);assert.equal(uploads.length,0);
   if(mode==='shared-preflight-session')sharedSession='session-b';contextGate.resolve();await event;await flush();
   if(mode==='shared-preflight-session'){assert.equal(uploads.length,0);assert.equal(get('financeModal'),null)}
   else{assert.equal(uploads.length,1);assert(get('financeField_title').disabled);assert(get('financeSave').disabled);pending.resolve(result);await button.lastClick;assert.equal(get('financeField_document_id').value,'uploaded');assert.equal(get('financeSave').disabled,false)}
  }else{
   if(mode==='shared-body-session')delayUploadBody=true;else pending=deferred();
   const run=button.onclick();await flush();assert.equal(uploads.length,1);assert.equal(get('financeField_document_id').value,'');
   if(mode==='shared-upload-rights')selectedPermissions=['finance.read'];else if(mode==='shared-postflight-outage')contextFailure=true;else sharedSession='session-b';
   if(mode==='shared-body-session')releaseUploadBody();else pending.resolve(result);await run;
   assert.equal(get('financeModal'),null);assert.equal(get('financeField_document_id'),null);assert.equal(vm.runInContext('financeState.identity',ctx),null);await button.onclick();assert.equal(uploads.length,1,'detached old handler must not repeat an accepted upload');
  }
 }else throw Error('Unknown case '+mode);
 console.log('PASS '+mode);
})().catch(e=>{console.error(e);process.exitCode=1});
