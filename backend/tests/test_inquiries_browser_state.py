"""Node component state contracts; separate actual Chromium acceptance lives in CI."""
from pathlib import Path
import subprocess

def test_inquiry_shared_pc_identity_revocation_late_response_and_escaping():
 root=Path(__file__).resolve().parents[2]
 js=(root/'frontend/inquiries.js').read_text()
 script=r'''
const assert=require('node:assert/strict'),vm=require('node:vm');
const nodes={inquiryModal:{innerHTML:'restricted',remove(){delete nodes.inquiryModal}},inquiriesBtn:{classList:{add(){}}}};
const context={console,$:id=>nodes[id],api:null};vm.createContext(context);
'''+"vm.runInContext("+__import__('json').dumps(js)+r''',context);
async function main(){
 vm.runInContext("inquiryState.identity='synthetic-old';inquiryState.row={draft:'restricted'};inquiryState.sources=[{}]",context);
 context.api=async url=>({user_id:'synthetic-new'});
 await assert.rejects(vm.runInContext("inquiryAPI('/inquiries')",context),e=>e.cancelled);
 assert.equal(vm.runInContext('inquiryState.row',context),null);assert.equal(nodes.inquiryModal,undefined);
 context.api=async url=>{if(url==='/auth/me')return {user_id:'synthetic-current'};throw Object.assign(new Error('revoked'),{status:403})};
 await assert.rejects(vm.runInContext("inquiryAPI('/inquiries')",context),e=>e.status===403);
 assert.equal(vm.runInContext('inquiryState.permissions.length+inquiryState.sources.length',context),0);
 let resolve;context.api=async url=>url==='/auth/me'?{user_id:'synthetic-current'}:await new Promise(r=>{resolve=r});
 const late=vm.runInContext("inquiryAPI('/inquiries')",context);await new Promise(r=>setImmediate(r));
 vm.runInContext('clearInquiries()',context);resolve({draft:'restricted late answer'});
 await assert.rejects(late,e=>e.cancelled);assert.equal(vm.runInContext('inquiryState.row',context),null);
}main().catch(e=>{console.error(e);process.exitCode=1});
'''
 result=subprocess.run(['node','-e',script],capture_output=True,text=True);assert result.returncode==0,result.stderr
 assert 'esc(r.draft)' in js and 'esc(e.excerpt)' in js

def test_candidate_adoption_blocks_fast_edit_until_server_version_is_rendered():
 # Removing the pending action gate permits the old Edit closure to win this race.
 root=Path(__file__).resolve().parents[2];js=(root/'frontend/inquiries.js').read_text()
 script=r'''
const assert=require('node:assert/strict'),vm=require('node:vm');
const nodes={};
function element(id){return {id,disabled:false,_html:'',get innerHTML(){return this._html},set innerHTML(html){this._html=html;for(const match of html.matchAll(/id="([^"]+)"/g))nodes[match[1]]=element(match[1]);},remove(){delete nodes[this.id]}}}
for(const id of ['inquiryModal','inquiryContent','inquiryMessage','inquiriesBtn'])nodes[id]=element(id);
const row={inquiry_id:'synthetic-inquiry',version:2,year:2026,question:'Synthetic council count',draft:'',claims:[],evidence:[{evidence_id:'synthetic-evidence',source_type:'document',source_id:'synthetic-document',document_id:'synthetic-document',excerpt:'Synthetic count 12 people.',snapshot:{values:[{text:'12',value:'12',unit:'people'}],documents:[{document_id:'synthetic-document',sha256:'synthetic-sha'}],record_version:null,source_date:'2026-10-06',required_permissions:['document.read']},query_parameters:{},created_by:'synthetic-user',retrieved_at:'2026-10-06'}],status:'draft',revision_of:null,provenance:{method:'manual'},review_snapshot:{},reviewed_by:null,reviewed_at:null,approved_by:null,approved_at:null,created_by:'synthetic-user',created_at:'2026-10-06',updated_at:'2026-10-06',deleted:false};
const candidate={candidate_id:'synthetic-candidate',inquiry_id:row.inquiry_id,draft:'Synthetic count 12 people.',claims:[{evidence_id:'synthetic-evidence',text:'12',value:'12',unit:'people',formula:'identity',operands:[]}],model:'deterministic-evidence-extract',model_version:'1',input_provenance:{inquiry_version:2,sources:{}},confidence:null,generated_at:'2026-10-06',created_by:'synthetic-user'};
let releaseAdopt,releaseRefresh,serverVersion=2;
const context={console,$:id=>nodes[id],esc:value=>String(value??''),document:{querySelectorAll:()=>[],querySelector:selector=>{if(!nodes[selector]){nodes[selector]=element(selector);if(selector.includes('claim-evidence'))nodes[selector].value='synthetic-evidence'}return nodes[selector]}},api:async(url,opt={})=>{
 if(url==='/auth/me')return {user_id:'synthetic-user',username:'synthetic',active:true,employee_id:null};
 if(url.endsWith('/candidates'))return [candidate];
 if(url.endsWith('/adopt-candidate')){assert.equal(JSON.parse(opt.body).expected_version,2);return await new Promise(resolve=>{releaseAdopt=()=>{serverVersion=3;resolve({...row,version:3,draft:candidate.draft,claims:candidate.claims})}})}
 if(url==='/inquiries/synthetic-inquiry'){if(serverVersion===2)return row;return await new Promise(resolve=>{releaseRefresh=()=>resolve({...row,version:3,draft:candidate.draft,claims:candidate.claims})})}
 throw new Error('unexpected network boundary '+url);
}};vm.createContext(context);
'''+"vm.runInContext("+__import__('json').dumps(js)+r''',context);
async function flush(){await new Promise(resolve=>setImmediate(resolve))}
async function main(){
 vm.runInContext("inquiryState.permissions=['inquiry.read','inquiry.update','inquiry.create','inquiry.review']",context);
 await vm.runInContext("inquiryDetail('synthetic-inquiry')",context);
 const oldEdit=nodes.inquiryEdit;const adoption=nodes.inquiryAdopt.onclick();await flush();
 assert.equal(oldEdit.disabled,true,'old Edit remains actionable while adoption is pending');
 await oldEdit.onclick();assert(!nodes.inquiryDraft,'fast Edit entered stale version form');
 releaseAdopt();await flush();assert.equal(oldEdit.disabled,true,'Edit unlocked before current record fetch completed');
 releaseRefresh();await adoption;
 assert.equal(nodes.inquiryEdit.disabled,false);assert(nodes.inquiryContent.innerHTML.includes('Version 3'));
 await nodes.inquiryEdit.onclick();assert.equal(nodes.inquiryDraft.value,'Synthetic count 12 people.');
 assert.equal(vm.runInContext('inquiryState.row.version',context),3);
}main().catch(error=>{console.error(error);process.exitCode=1});
'''
 result=subprocess.run(['node','-e',script],capture_output=True,text=True);assert result.returncode==0,result.stderr

def test_cancelled_action_late_401_cannot_clear_or_unlock_fresh_module():
 # Removing generation/operation ownership lets old errors mutate new-session UI.
 root=Path(__file__).resolve().parents[2];js=(root/'frontend/inquiries.js').read_text()
 script=r'''
const assert=require('node:assert/strict'),vm=require('node:vm');
const nodes={};const control=()=>({disabled:false});
const modal=()=>({remove(){delete nodes.inquiryModal}});
Object.assign(nodes,{inquiryModal:modal(),inquiryEdit:control(),inquiryMessage:{textContent:''},inquiriesBtn:{classList:{add(){}}}});
let rejectOld,resolveFresh;
const context={console,$:id=>nodes[id],api:async url=>{
 if(url==='/auth/me')return {user_id:'synthetic-user',username:'synthetic',active:true,employee_id:null};
 if(url==='/inquiries/old')return await new Promise((resolve,reject)=>{rejectOld=reject});
 if(url==='/inquiries/fresh')return await new Promise(resolve=>{resolveFresh=resolve});
 throw new Error('unexpected request '+url);
}};vm.createContext(context);
'''+"vm.runInContext("+__import__('json').dumps(js)+r''',context);
async function flush(){await new Promise(resolve=>setImmediate(resolve))}
async function main(){
 const oldControl=nodes.inquiryEdit;
 const old=vm.runInContext("inquiryAction(()=>inquiryAPI('/inquiries/old'))",context);await flush();
 vm.runInContext('clearInquiries()',context);
 Object.assign(nodes,{inquiryModal:modal(),inquiryEdit:control(),inquiryMessage:{textContent:''}});
 const freshModal=nodes.inquiryModal,freshControl=nodes.inquiryEdit;
 const fresh=vm.runInContext("inquiryAction(()=>inquiryAPI('/inquiries/fresh'))",context);await flush();
 rejectOld(Object.assign(new Error('old session revoked'),{status:401}));await old;
 assert.equal(nodes.inquiryModal,freshModal,'late old401 removed fresh module');
 assert.equal(oldControl.disabled,true,'cancelled old actions reenabled');
 assert.equal(freshControl.disabled,true,'old completion unlocked fresh pending action');
 resolveFresh({});await fresh;assert.equal(freshControl.disabled,false);
 const rejected=vm.runInContext("inquiryAction(()=>{throw Object.assign(new Error('current session revoked'),{status:403})})",context);await rejected;
 assert.equal(freshControl.disabled,false,'failed action kept current controls locked');
}main().catch(error=>{console.error(error);process.exitCode=1});
'''
 result=subprocess.run(['node','-e',script],capture_output=True,text=True);assert result.returncode==0,result.stderr

def test_closing_pending_module_keeps_authorized_navigation_entry():
 root=Path(__file__).resolve().parents[2];js=(root/'frontend/inquiries.js').read_text()
 script=r'''
const assert=require('node:assert/strict'),vm=require('node:vm');const nodes={};
const classes=()=>({hidden:false,add(name){if(name==='hidden')this.hidden=true},remove(name){if(name==='hidden')this.hidden=false},toggle(name,yes){if(name==='hidden')this.hidden=yes}});
function element(){return {id:'',value:'',disabled:false,classList:classes(),style:{},set innerHTML(html){for(const match of html.matchAll(/id="([^"]+)"/g)){nodes[match[1]]=element();nodes[match[1]].id=match[1]}},remove(){delete nodes[this.id]}}}
let resolveOld;
const context={console,URLSearchParams,$:id=>nodes[id],esc:value=>String(value??''),document:{createElement:element,body:{append(el){nodes[el.id]=el}},querySelectorAll:()=>[]},api:async url=>{
 if(url==='/auth/me')return {user_id:'synthetic-user',username:'synthetic',active:true,employee_id:null};
 if(url==='/auth/permissions')return {permissions:['inquiry.read','inquiry.update']};
 if(url.startsWith('/inquiries?'))return [];
 if(url==='/inquiries/delayed')return await new Promise(resolve=>{resolveOld=resolve});
 throw new Error('unexpected request '+url);
}};nodes.inquiriesBtn=element();vm.createContext(context);
'''+"vm.runInContext("+__import__('json').dumps(js)+r''',context);
async function main(){
 await vm.runInContext('openInquiries()',context);
 const old=vm.runInContext("inquiryAction(()=>inquiryAPI('/inquiries/delayed'))",context);await new Promise(resolve=>setImmediate(resolve));
 nodes.inquiryClose.onclick();assert.equal(nodes.inquiryModal,undefined);assert.equal(nodes.inquiriesBtn.classList.hidden,false,'normal Close removed the authorized module entry');
 await vm.runInContext('openInquiries()',context);const reopened=nodes.inquiryModal;
 resolveOld({});await old;assert.equal(nodes.inquiryModal,reopened,'old completion changed reopened module');
}main().catch(error=>{console.error(error);process.exitCode=1});
'''
 result=subprocess.run(['node','-e',script],capture_output=True,text=True);assert result.returncode==0,result.stderr

def test_dynamic_source_is_disabled_until_trailing_candidate_refresh_finishes():
 # Loaded production source controls must reflect the global pending policy.
 root=Path(__file__).resolve().parents[2];js=(root/'frontend/inquiries.js').read_text()
 script=r'''
const assert=require('node:assert/strict'),vm=require('node:vm');
const nodes={};
function element(id){return {id,disabled:false,_html:'',get innerHTML(){return this._html},set innerHTML(html){this._html=html;for(const match of html.matchAll(/id="([^"]+)"/g))nodes[match[1]]=element(match[1]);},remove(){delete nodes[this.id]}}}
for(const id of ['inquiryModal','inquiryContent','inquiryMessage','inquiriesBtn'])nodes[id]=element(id);
const sourceControl=element('source');sourceControl.dataset={inquirySource:'synthetic-evidence'};
const unrelatedControl=element('unrelated');
const row={inquiry_id:'synthetic-inquiry',version:2,year:2026,question:'Synthetic council count',draft:'',claims:[],evidence:[{evidence_id:'synthetic-evidence',source_type:'document',source_id:'synthetic-document',document_id:'synthetic-document',excerpt:'Synthetic count 12 people.',snapshot:{values:[{text:'12',value:'12',unit:'people'}],documents:[{document_id:'synthetic-document',sha256:'synthetic-sha'}],record_version:null,source_date:'2026-10-06',required_permissions:['document.read']},query_parameters:{},created_by:'synthetic-user',retrieved_at:'2026-10-06'}],status:'approved',revision_of:null,provenance:{method:'manual'},review_snapshot:{},reviewed_by:null,reviewed_at:null,approved_by:null,approved_at:null,created_by:'synthetic-user',created_at:'2026-10-06',updated_at:'2026-10-06',deleted:false};
const candidate={candidate_id:'synthetic-candidate',inquiry_id:row.inquiry_id,draft:'Synthetic count 12 people.',claims:[{evidence_id:'synthetic-evidence',text:'12',value:'12',unit:'people',formula:'identity',operands:[]}],model:'deterministic-evidence-extract',model_version:'1',input_provenance:{inquiry_version:2,sources:{}},confidence:null,generated_at:'2026-10-06',created_by:'synthetic-user'};
let releaseCandidates,sourceReads=0,opened=0;
const context={console,$:id=>nodes[id],esc:value=>String(value??''),window:{open(){opened++}},document:{querySelectorAll:selector=>selector==='[data-inquiry-source]'?[sourceControl]:[],querySelector:selector=>{if(!nodes[selector]){nodes[selector]=element(selector);if(selector.includes('claim-evidence'))nodes[selector].value='synthetic-evidence'}return nodes[selector]}},api:async(url,opt={})=>{
 if(url==='/auth/me')return {user_id:'synthetic-user',username:'synthetic',active:true,employee_id:null};
 if(url.endsWith('/candidates'))return await new Promise(resolve=>{releaseCandidates=()=>resolve([])});
 if(url.startsWith('/inquiries/source/')){sourceReads++;return {navigation:{href:'/documents/synthetic-document/download'}}}
 if(url==='/inquiries/synthetic-inquiry')return row;
 throw new Error('unexpected network boundary '+url);
}};vm.createContext(context);
'''+"vm.runInContext("+__import__('json').dumps(js)+r''',context);
async function flush(){await new Promise(resolve=>setImmediate(resolve))}
async function main(){
 vm.runInContext("inquiryState.permissions=['inquiry.read','inquiry.update','inquiry.create','inquiry.review']",context);
 const detail=vm.runInContext("inquiryAction(()=>inquiryDetail('synthetic-inquiry'))",context);await flush();
 assert(nodes.inquiryContent.innerHTML.includes('Human承認済み回答'));
 assert.equal(sourceControl.disabled,true,'visible dynamic source is enabled while its wrapped action would be dropped');
 assert.equal(unrelatedControl.disabled,false,'unrelated module control was changed');
 await sourceControl.onclick();assert.equal(sourceReads,0);assert.equal(opened,0);
 releaseCandidates();await detail;
 assert.equal(sourceControl.disabled,false,'source never became ready after candidate refresh');
 await sourceControl.onclick();assert.equal(sourceReads,1);assert.equal(opened,1);
 assert.equal(sourceControl.disabled,false);

}main().catch(error=>{console.error(error);process.exitCode=1});
'''
 result=subprocess.run(['node','-e',script],capture_output=True,text=True);assert result.returncode==0,result.stderr
