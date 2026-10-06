"""Execute actual finance JavaScript against focused DOM/session reproductions."""
from pathlib import Path
import subprocess


def run(tmp_path,scenario):
    harness=r'''
const vm=require('vm'),fs=require('fs');
class Node{constructor(){this.innerHTML='';this.textContent='';this.value='';this.checked=false;this.hidden=false;this.dataset={};this.onclick=null;this.classList={add:()=>{this.hidden=true},remove:()=>{this.hidden=false},toggle:(_c,b)=>{this.hidden=b}};}remove(){this.innerHTML='';this.hidden=true;}}
const nodes=new Map(),node=id=>{if(!nodes.has(id))nodes.set(id,new Node());return nodes.get(id)};
let calls=[],buttons=[],failure=null,pending=null,authorized=true;
const context={console,Date,URLSearchParams,JSON,Promise,$:node,esc:x=>String(x??''),prompt:()=> 'Synthetic Human reason',document:{getElementById:node,querySelectorAll:s=>s.startsWith('[data-finance-human')?buttons.filter(b=>!s.includes('^=')||b.dataset.financeHuman.startsWith(s.split('"')[1])):[],createElement:()=>new Node(),body:{append(){}}},api:async(path,opt)=>{calls.push({path,opt});if(failure)throw failure;if(path==='/auth/me')return {user_id:'SYNTHETIC'};if(path==='/auth/permissions')return {permissions:authorized?['finance.read']:[]};if(path==='/slow')return new Promise(resolve=>pending=resolve);if(path.startsWith('/finance/warnings'))return [{status:'stale_rule',required:1,available:null,shortage:null,reason:'source changed'}];return []}};
vm.createContext(context);vm.runInContext(fs.readFileSync(process.argv[2],'utf8'),context);
const turn=()=>new Promise(resolve=>setImmediate(resolve));
(async()=>{SCENARIO})().catch(e=>{console.error(e.stack);process.exitCode=1});
'''
    file=tmp_path/'finance-harness.js';file.write_text(harness.replace('SCENARIO',scenario))
    result=subprocess.run(['node',str(file),str(Path(__file__).resolve().parents[2]/'frontend/finance.js')],capture_output=True,text=True,timeout=10)
    assert result.returncode==0,result.stderr


def test_authorization_loss_erases_finance_dom_cache_and_drafts(tmp_path):
    run(tmp_path,r'''
vm.runInContext("financeState.permissions=['finance.admin'];financeState.year='PRIVATE';",context);node('financeModal').innerHTML='PRIVATE draft';node('financeContent').innerHTML='PRIVATE roster';
failure=Object.assign(new Error('revoked'),{status:401});try{await vm.runInContext('initFinance()',context)}catch(e){if(e.status!==401)throw e}
if(node('financeModal').innerHTML||node('financeContent').innerHTML||vm.runInContext('financeState.year||financeState.permissions.length',context))throw Error('private finance data survives authorization loss');
''')


def test_late_response_cannot_restore_cleared_session_state(tmp_path):
    run(tmp_path,r'''
const request=vm.runInContext("financeAPI('/slow')",context);await turn();vm.runInContext('clearFinance()',context);pending([{display_name:'PRIVATE old response'}]);
let refused=false;try{await request}catch(e){refused=true}if(!refused)throw Error('late response accepted after session state cleared');
''')


def test_successful_permission_refresh_clears_lost_read_rights(tmp_path):
    run(tmp_path,r"""
vm.runInContext("financeState.permissions=['finance.read'];financeState.year='PRIVATE';",context);node('financeContent').innerHTML='PRIVATE';authorized=false;await vm.runInContext('initFinance()',context);
if(node('financeContent').innerHTML||vm.runInContext('financeState.year',context))throw Error('revoked read rights leave private finance data');
""")


def test_losing_finance_read_clears_financial_draft_with_contract_access_retained(tmp_path):
    run(tmp_path,r"""
vm.runInContext("financeState.permissions=['finance.read','contract.read'];financeState.year='PRIVATE';",context);node('financeContent').innerHTML='PRIVATE budget';
const original=context.api;context.api=async(path,opt)=>path==='/auth/permissions'?{permissions:['contract.read']}:original(path,opt);
await vm.runInContext('initFinance()',context);
if(node('financeContent').innerHTML||vm.runInContext('financeState.year',context))throw Error('finance draft survives lost financial rights');
if(!vm.runInContext("financeCan('contract.read')",context))throw Error('remaining contract access lost');
""")


def test_identity_change_erases_previous_users_state(tmp_path):
    run(tmp_path,r"""
vm.runInContext("financeState.identity='PREVIOUS';financeState.year='PRIVATE';",context);node('financeContent').innerHTML='PRIVATE';
let refused=false;try{await vm.runInContext("financeAPI('/finance/years')",context)}catch(e){refused=e.cancelled}
if(!refused||node('financeContent').innerHTML||calls.some(x=>x.path==='/finance/years'))throw Error('identity change leaked previous financial data');
""")


def test_export_denial_clears_cached_private_state(tmp_path):
    run(tmp_path,r"""
vm.runInContext("financeState.year='PRIVATE'",context);node('financeContent').innerHTML='PRIVATE';
context.fetch=async()=>({ok:false,status:403,json:async()=>({detail:'revoked'})});
try{await vm.runInContext("financeDownload('/finance/export/journal')",context)}catch(e){}
if(node('financeContent').innerHTML||vm.runInContext('financeState.year',context))throw Error('export denial leaves private cache');
""")


def test_inflight_identity_change_cannot_return_previous_users_data(tmp_path):
    run(tmp_path,r"""
let identity='ALICE';const original=context.api;context.api=async(path,opt)=>path==='/auth/me'?{user_id:identity}:original(path,opt);
const request=vm.runInContext("financeAPI('/slow')",context);await turn();identity='BOB';pending(['ALICE PRIVATE']);
let refused=false;try{await request}catch(e){refused=e.cancelled}if(!refused||vm.runInContext('financeState.identity',context))throw Error('external identity change exposes private response');
""")


def test_download_rechecks_identity_after_blob_completion(tmp_path):
    run(tmp_path,r"""
let identity='ALICE',complete;const original=context.api;context.api=async(path,opt)=>path==='/auth/me'?{user_id:identity}:original(path,opt);
context.fetch=async()=>({ok:true,blob:()=>new Promise(resolve=>complete=resolve)});
context.URL={createObjectURL:()=>{throw Error('private blob exposed')},revokeObjectURL(){}};
const request=vm.runInContext("financeDownload('/finance/export/journal')",context);await turn();identity='BOB';complete('ALICE PRIVATE');
let refused=false;try{await request}catch(e){refused=e.cancelled}if(!refused)throw Error('download exposed previous identity');
""")


def test_download_session_expiry_during_blob_clears_private_state(tmp_path):
    run(tmp_path,r"""
let complete;context.fetch=async()=>({ok:true,blob:()=>new Promise(resolve=>complete=resolve)});
context.URL={createObjectURL:()=>{throw Error('private blob exposed')},revokeObjectURL(){}};
vm.runInContext("financeState.year='PRIVATE'",context);node('financeContent').innerHTML='PRIVATE';
const request=vm.runInContext("financeDownload('/finance/export/journal')",context);await turn();failure=Object.assign(new Error('expired'),{status:401});complete('PRIVATE');
try{await request}catch(e){}if(node('financeContent').innerHTML||vm.runInContext('financeState.year',context))throw Error('expired download leaves old state');
""")


def test_document_link_uses_guarded_download_and_clears_denied_state(tmp_path):
    run(tmp_path,r"""
node('financeContent').innerHTML='PRIVATE';context.fetch=async()=>({ok:false,status:403,json:async()=>({detail:'revoked'})});let prevented=false;
context.event={target:{closest:()=>({getAttribute:()=>'/documents/SYNTHETIC/download'})},preventDefault(){prevented=true}};
await vm.runInContext('financeDocumentClick(event)',context);await turn();
if(!prevented||node('financeContent').innerHTML)throw Error('direct source link bypasses protected cleanup');
""")


def test_compound_navigation_requires_both_read_permissions(tmp_path):
    run(tmp_path,r"""
const original=context.api;context.api=async(path,opt)=>path==='/auth/permissions'?{permissions:['contract.read']}:original(path,opt);
await vm.runInContext('openFinance()',context);if(node('financeNav').innerHTML.includes('id="financeEvents"'))throw Error('contract-only user offered finance-protected events');
context.api=async(path,opt)=>path==='/auth/permissions'?{permissions:['finance.read']}:original(path,opt);
await vm.runInContext('openFinance()',context);if(node('financeNav').innerHTML.includes('id="financeAmendments"'))throw Error('finance-only user offered contract-protected amendments');
""")
