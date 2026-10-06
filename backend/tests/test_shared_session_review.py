"""Fresh-review regressions: actual guard and actual shell functions, synthetic inputs."""
from pathlib import Path
import subprocess


def node(script):
 root=Path(__file__).resolve().parents[2]
 result=subprocess.run(['node','-e',script,str(root)],capture_output=True,text=True,timeout=20)
 assert result.returncode==0,result.stderr


def test_review_svg_cached_click_keeps_actual_drawing_pointer_coordinates():
 node(r'''
const assert=require('node:assert/strict'),vm=require('node:vm'),fs=require('node:fs'),path=require('node:path'),root=process.argv[1],handlers={};let point;
const svg={isConnected:true,closest:selector=>selector==='#loginView'?null:svg,getBoundingClientRect:()=>({left:10,top:20,width:100,height:200}),dispatchEvent(event){ctx.replayed=event;point=vm.runInContext('drawingPointerPosition(replayed,svg)',ctx)}};
class MouseEvent extends Event{constructor(type,options){super(type,options);Object.assign(this,{clientX:options.clientX,clientY:options.clientY})}}
const window={location:{origin:'http://synthetic.local'},addEventListener(){},fetch:async()=>new Response(JSON.stringify({user_id:'u',session_id:'s',tenant_id:null,permissions:['drawing.read']}))};
const ctx={window,document:{addEventListener:(k,f)=>handlers[k]=f},URL,Response,WeakSet,Event,MouseEvent,svg,drawingWorkspaceDimensions:()=>({w:100,h:200})};vm.createContext(ctx);
vm.runInContext(fs.readFileSync(path.join(root,'frontend/shared-session.js'),'utf8'),ctx);
const html=fs.readFileSync(path.join(root,'frontend/index.html'),'utf8');vm.runInContext(html.match(/function drawingPointerPosition\(ev,svg\)\{[\s\S]*?\n\}/)[0],ctx);
window.FireAISession.install();
(async()=>{await handlers.click({type:'click',target:svg,clientX:60,clientY:120,preventDefault(){},stopImmediatePropagation(){}});assert.deepEqual(Array.from(point),[50,100]);})().catch(e=>{console.error(e);process.exitCode=1});
''')


def test_review_old_renewal_header_cannot_redirect_fresh_session():
 node(r'''
const assert=require('node:assert/strict'),vm=require('node:vm'),fs=require('node:fs'),path=require('node:path'),root=process.argv[1];let release,session='old',destination=null;
const window={location:{origin:'http://synthetic.local',pathname:'/ui/',replace:v=>destination=v},addEventListener(){},fetch:async(url)=>{
 if(url==='/auth/context')return new Response(JSON.stringify({user_id:'same',session_id:session,tenant_id:null,permissions:['facility.read']}));
 if(url==='/old')return new Promise(r=>release=()=>r(new Response('{}',{status:403,headers:{'X-FireAI-Password-Renewal':'required'}})));
 if(url==='/auth/login'){session='new';return new Response('{}')};return new Response('{}');
}};
const ctx={window,document:{addEventListener(){}},URL,Response,WeakSet,Event};vm.createContext(ctx);
for(const file of ['auth-session.js','shared-session.js'])vm.runInContext(fs.readFileSync(path.join(root,'frontend',file),'utf8'),ctx);
window.FireAISession.install();
(async()=>{const old=window.fetch('/old');await new Promise(r=>setImmediate(r));await window.fetch('/auth/login',{method:'POST'});await(await window.fetch('/facilities')).json();release();await assert.rejects(old,e=>e.cancelled);assert.equal(destination,null);})().catch(e=>{console.error(e);process.exitCode=1});
''')


def test_review_summary_cannot_reopen_cached_private_data_after_right_loss():
 node(r'''
const assert=require('node:assert/strict'),vm=require('node:vm'),fs=require('node:fs'),path=require('node:path'),root=process.argv[1],handlers={};let permissions=['finance.read'],opened=0,reset=0;
const window={location:{origin:'http://synthetic.local'},addEventListener(){},fetch:async()=>new Response(JSON.stringify({user_id:'u',session_id:'s',tenant_id:null,permissions}))};
const ctx={window,document:{addEventListener:(k,f)=>handlers[k]=f},URL,Response,WeakSet,Event};vm.createContext(ctx);vm.runInContext(fs.readFileSync(path.join(root,'frontend/shared-session.js'),'utf8'),ctx);window.FireAISession.install({reset:()=>reset++});
(async()=>{await(await window.fetch('/finance')).json();permissions=[];let prevented=false;
const summary={tagName:'SUMMARY',isConnected:true,closest:selector=>selector.includes('summary')?summary:null,click:()=>opened++};
await handlers.click({type:'click',target:summary,preventDefault(){prevented=true},stopImmediatePropagation(){}});if(!prevented)opened++;
assert.equal(opened,0);assert.equal(reset,1);})().catch(e=>{console.error(e);process.exitCode=1});
''')


def test_review_cancelled_old_facility_load_keeps_fresh_list():
 node(r'''
const assert=require('node:assert/strict'),vm=require('node:vm'),fs=require('node:fs'),path=require('node:path'),root=process.argv[1];let reject;
const nodes={sortBy:{value:'name'},sortDir:{value:'asc'},searchQ:{value:''},statusFilter:{value:''},facilityList:{innerHTML:'initial'}};
const ctx={$:id=>nodes[id],state:{offset:0,limit:50},URLSearchParams,api:()=>new Promise((r,j)=>reject=j),location:{reload(){throw Error('old reload')}},renderList(){throw Error('old render')}};vm.createContext(ctx);
const html=fs.readFileSync(path.join(root,'frontend/index.html'),'utf8');vm.runInContext(html.match(/async function loadFacilities[^\n]+/)[0],ctx);
(async()=>{const old=vm.runInContext('loadFacilities()',ctx);nodes.facilityList.innerHTML='Synthetic fresh session list';reject(Object.assign(new Error('old cancelled'),{cancelled:true}));await old.catch(e=>{assert(e.cancelled)});assert.equal(nodes.facilityList.innerHTML,'Synthetic fresh session list');})().catch(e=>{console.error(e);process.exitCode=1});
''')


def test_review_actual_preview_renderer_waits_for_guarded_blob_and_current_authority():
 node(r'''
const assert=require('node:assert/strict'),vm=require('node:vm'),fs=require('node:fs'),path=require('node:path'),root=process.argv[1];let nativeRequests=0,blobRelease,lost=false;
const nodes={};function element(id){return {id,value:'',addEventListener(){},dataset:{},style:{},classList:{add(){},remove(){},contains(){return true}},getBoundingClientRect:()=>({width:100,height:200,left:0,top:0}),_html:'',get innerHTML(){return this._html},set innerHTML(value){this._html=value;const img=value.match(/<img id="drawingWorkspaceImage"([^>]*)>/);if(img){const n=element('drawingWorkspaceImage');const src=img[1].match(/\ssrc="([^"]*)"/);const guarded=img[1].match(/data-preview-url="([^"]*)"/);if(guarded)n.dataset.previewUrl=guarded[1];Object.defineProperty(n,'src',{set:v=>{if(v.startsWith('/drawing-analyses/'))nativeRequests++;n._src=v},get:()=>n._src});if(src)n.src=src[1];nodes.drawingWorkspaceImage=n}}}}
const document={getElementById:id=>nodes[id]??(nodes[id]=element(id)),querySelectorAll:()=>[],addEventListener(){}};
const check=async()=>{if(lost)throw Object.assign(new Error('changed'),{cancelled:true})};
const window={FireAISession:{install(){},check},addEventListener(){}};
const urls=class extends URL{};urls.createObjectURL=()=>{assert(!lost,'old pixels minted after authority loss');return 'blob:synthetic'};urls.revokeObjectURL=()=>{};
const ctx={window,document,URL:urls,URLSearchParams,console,setTimeout(){},fetch:async()=>({ok:true,blob:()=>new Promise(r=>blobRelease=r)}),alert(){throw Error('stale alert')}};vm.createContext(ctx);
const html=fs.readFileSync(path.join(root,'frontend/index.html'),'utf8');const main=[...html.matchAll(/<script(?:\s[^>]*)?>([\s\S]*?)<\/script>/g)].map(x=>x[1]).find(x=>x.includes('const state='));vm.runInContext(main,ctx);
vm.runInContext("state.drawingWorkspace={analysis:{drawing_analysis_id:'synthetic-analysis',status:'analyzed',analysis_method:'deterministic'}};state.drawingDoc={document_id:'synthetic-doc',original_filename:'synthetic drawing'};state.drawingPreviewInfo={preview_mode:'image_direct',page_count:1};renderDrawingWorkspace()",ctx);
(async()=>{await new Promise(r=>setImmediate(r));assert.equal(nativeRequests,0,'native img src bypasses fetch/body guard');assert(blobRelease,'guarded preview blob was not requested');lost=true;blobRelease(new Blob(['synthetic old pixels']));await new Promise(r=>setImmediate(r));await new Promise(r=>setImmediate(r));assert(!nodes.drawingWorkspaceImage.src,'old preview installed after authority loss');})().catch(e=>{console.error(e);process.exitCode=1});
''')


def test_finance_pending_action_locks_new_controls_and_preserves_read_only_fields():
 node(r'''
const assert=require('node:assert/strict'),vm=require('node:vm'),fs=require('node:fs'),path=require('node:path'),root=process.argv[1];let release,calls=0;
const controls=[{disabled:false},{disabled:true}],nodes={financeMessage:{textContent:''},financeModal:{querySelectorAll:()=>controls},financeBtn:{disabled:false}};
const ctx={$:id=>nodes[id],document:{querySelectorAll:()=>controls},window:{},console};vm.createContext(ctx);vm.runInContext(fs.readFileSync(path.join(root,'frontend/finance.js'),'utf8'),ctx);
(async()=>{ctx.work=()=>{calls++;return new Promise(r=>release=r)};const pending=vm.runInContext('financeAction(work)',ctx);assert(controls[0].disabled,'navigation remains active while references load');await vm.runInContext('financeAction(work)',ctx);assert.equal(calls,1,'second action races pending form');const dynamic={disabled:false};controls.push(dynamic);ctx.dynamic=dynamic;vm.runInContext('financeLockNewControls()',ctx);assert(dynamic.disabled);ctx.control=controls[0];vm.runInContext('financeControlReady(control,true)',ctx);release();await pending;assert(controls[0].disabled,'new read-only state lost');assert(controls[1].disabled,'existing read-only state lost');assert.equal(dynamic.disabled,false);})().catch(e=>{console.error(e);process.exitCode=1});
''')


def test_cancelled_module_initialization_stops_old_login_chain():
 node(r'''
const assert=require('node:assert/strict'),vm=require('node:vm'),fs=require('node:fs'),path=require('node:path'),root=process.argv[1];
(async()=>{for(const [file,name,apiName] of [['assets.js','initAssets','api'],['operations.js','initOperations','api'],['emergency.js','initEmergency','api'],['workforce.js','initWorkforce','workforceAPI'],['inquiries.js','initInquiries','inquiryAPI']]){const error=Object.assign(new Error('obsolete login'),{cancelled:true}),ctx={[apiName]:async()=>{throw error}};vm.createContext(ctx);const source=fs.readFileSync(path.join(root,'frontend',file),'utf8').split('\n').find(line=>line.startsWith('async function '+name+'('));vm.runInContext(source,ctx);await assert.rejects(ctx[name](),e=>e===error,file+' swallowed the obsolete login');}})().catch(e=>{console.error(e);process.exitCode=1});
''')


def test_finance_change_preflight_locks_form_before_async_authority_probe():
 node(r'''
const assert=require('node:assert/strict'),vm=require('node:vm'),fs=require('node:fs'),path=require('node:path'),root=process.argv[1],handlers={};let release,ran=0;
const account={disabled:false},kind={tagName:'SELECT',disabled:false,isConnected:true,closest:selector=>selector==='#loginView'?null:kind,dispatchEvent(){assert.equal(account.disabled,false,'preflight lock not released for handler');return ctx.financeAction(async()=>{ran++})}};
const controls=[kind,account],nodes={financeMessage:{textContent:''},financeModal:{querySelectorAll:()=>controls}};
const window={location:{origin:'http://synthetic.local'},addEventListener(){},fetch:()=>new Promise(r=>release=()=>r(new Response(JSON.stringify({user_id:'u',session_id:'s',tenant_id:null,permissions:['finance.read']}))))};
const ctx={window,$:id=>nodes[id],document:{addEventListener:(k,f)=>handlers[k]=f},URL,Response,WeakSet,Event};vm.createContext(ctx);
for(const file of ['finance.js','shared-session.js'])vm.runInContext(fs.readFileSync(path.join(root,'frontend',file),'utf8'),ctx);window.FireAISession.install();
(async()=>{const pending=handlers.change({type:'change',target:kind,preventDefault(){},stopImmediatePropagation(){}});assert(account.disabled,'account remains editable while deferred change awaits authority');release();await pending;await new Promise(r=>setImmediate(r));assert.equal(ran,1);assert.equal(account.disabled,false)})().catch(e=>{console.error(e);process.exitCode=1});
''')
