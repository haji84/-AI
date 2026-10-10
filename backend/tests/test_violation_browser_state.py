"""Execute actual violation JavaScript against focused DOM/session reproductions."""
from pathlib import Path
import subprocess
import pytest


@pytest.mark.parametrize('scenario',['pending-save','view-switch','replacement','revoked','double-click'])
def test_picker_authority_preserves_form_selection_order(scenario):
    root=Path(__file__).resolve().parents[2]
    result=subprocess.run(['node',str(Path(__file__).with_name('violation_selection_harness.js')),str(root),scenario],capture_output=True,text=True,timeout=10)
    assert result.returncode==0,result.stderr


def run(tmp_path,scenario):
    harness=r'''
const vm=require('vm'),fs=require('fs');
class Node{constructor(){this.innerHTML='';this.textContent='';this.value='';this.checked=false;this.hidden=false;this.dataset={};this.onclick=null;this.classList={add:()=>{this.hidden=true},remove:()=>{this.hidden=false},toggle:(_c,b)=>{this.hidden=b}};}remove(){this.innerHTML='';this.hidden=true;}}
const nodes=new Map(),node=id=>{if(!nodes.has(id))nodes.set(id,new Node());return nodes.get(id)};
let calls=[],buttons=[],failure=null,pending=null,authorized=true,rights=['violation.read'];
const context={window:{},console,Date,URLSearchParams,JSON,Promise,$:node,esc:x=>String(x??''),prompt:()=> 'Synthetic Human reason',document:{getElementById:node,querySelectorAll:s=>s.startsWith('[data-violation-human')?buttons.filter(b=>!s.includes('^=')||b.dataset.violationHuman.startsWith(s.split('"')[1])):[],createElement:()=>new Node(),body:{append(){}}},api:async(path,opt)=>{calls.push({path,opt});if(failure)throw failure;if(path==='/auth/me')return {user_id:'SYNTHETIC'};if(path==='/auth/permissions')return {permissions:authorized?rights:[]};if(path==='/slow')return new Promise(resolve=>pending=resolve);if(path.startsWith('/violation/warnings'))return [{status:'stale_rule',required:1,available:null,shortage:null,reason:'source changed'}];return []}};
vm.createContext(context);vm.runInContext(fs.readFileSync(process.argv[2],'utf8'),context);
const turn=()=>new Promise(resolve=>setImmediate(resolve));
(async()=>{SCENARIO})().catch(e=>{console.error(e.stack);process.exitCode=1});
'''
    file=tmp_path/'violation-harness.js';file.write_text(harness.replace('SCENARIO',scenario))
    result=subprocess.run(['node',str(file),str(Path(__file__).resolve().parents[2]/'frontend/violations.js')],capture_output=True,text=True,timeout=10)
    assert result.returncode==0,result.stderr


def test_late_response_is_rejected_after_permission_revocation(tmp_path):
    run(tmp_path,r"""
vm.runInContext("violationState.permissions=['violation.read'];",context);
node('violationContent').innerHTML='PRIVATE';const request=vm.runInContext("violationAPI('/slow')",context);await turn();authorized=false;pending({private:'PRIVATE'});
let denied=false;try{await request}catch(e){denied=true}if(!denied||node('violationContent').innerHTML)throw Error('revoked data accepted');
""")


def test_late_response_is_rejected_after_view_switch(tmp_path):
    run(tmp_path,r"""
const request=vm.runInContext("violationAPI('/slow')",context);await turn();vm.runInContext('violationState.viewGeneration++',context);pending({private:'OLD'});
let denied=false;try{await request}catch(e){denied=Boolean(e.cancelled)}if(!denied)throw Error('old view response accepted');
""")


def test_identity_change_erases_private_drafts(tmp_path):
    run(tmp_path,r"""
await vm.runInContext("violationAPI('/ready')",context);node('violationModal').innerHTML='PRIVATE draft';const original=context.api;context.api=async(path,opt)=>path==='/auth/me'?{user_id:'OTHER'}:original(path,opt);
try{await vm.runInContext("violationAPI('/ready')",context)}catch{}
if(node('violationModal').innerHTML||vm.runInContext('violationState.permissions.length',context))throw Error('other identity sees private draft');
""")


def test_cached_screens_and_forms_recheck_authority_before_rendering(tmp_path):
    run(tmp_path,r"""
context.cachedCase={case_id:'C',status:'confirmed',version:1,measures:[],corrections:[]};context.cachedMeasure={measure_id:'M',status:'confirmed',kind:'order',instruction:'PRIVATE ORDER',review_snapshot:{rules:['PRIVATE LAW']}};context.cachedTask={action_id:'T',status:'open',description:'PRIVATE TASK',version:1};failure=Object.assign(new Error('revoked'),{status:403});
for(const expression of ['violationMeasureDetail(cachedCase,cachedMeasure)','violationCorrectionForm(cachedCase,cachedTask)','violationDecision("PRIVATE DECISION",cachedTask,"/path",async()=>{})']){
 node('violationContent').innerHTML='';calls=[];try{await vm.runInContext(expression,context)}catch{}
 if(!calls.length||node('violationContent').innerHTML.includes('PRIVATE'))throw Error('cached private data rendered without authority: '+expression);
}
""")


def test_correction_cancel_reopen_buttons_match_approval_authority(tmp_path):
    run(tmp_path,r"""
context.caseRow={case_id:'C',status:'confirmed',version:1};context.taskRow={action_id:'T',status:'open',description:'Synthetic',version:1};
rights=['violation.read','violation.approve'];vm.runInContext('violationState.permissions='+JSON.stringify(rights),context);await vm.runInContext('violationCorrectionDetail(caseRow,taskRow)',context);
if(!node('violationContent').innerHTML.includes('id="violationCancel"'))throw Error('reviewer cannot cancel');context.taskRow.status='completed';await vm.runInContext('violationCorrectionDetail(caseRow,taskRow)',context);if(!node('violationContent').innerHTML.includes('id="violationReopen"'))throw Error('reviewer cannot reopen');
rights=['violation.read','violation.update'];vm.runInContext('violationState.permissions='+JSON.stringify(rights),context);context.taskRow.status='open';await vm.runInContext('violationCorrectionDetail(caseRow,taskRow)',context);if(node('violationContent').innerHTML.includes('id="violationCancel"'))throw Error('editor sees forbidden cancellation');
""")
