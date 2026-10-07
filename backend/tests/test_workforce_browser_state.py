"""Execute actual workforce JavaScript against focused DOM/session reproductions."""
from pathlib import Path
import subprocess


def run(tmp_path,scenario):
    harness=r'''
const vm=require('vm'),fs=require('fs');
class Node{constructor(){this.innerHTML='';this.textContent='';this.value='';this.checked=false;this.hidden=false;this.dataset={};this.onclick=null;this.classList={add:()=>{this.hidden=true},remove:()=>{this.hidden=false},toggle:(_c,b)=>{this.hidden=b}};}remove(){this.innerHTML='';this.hidden=true;}}
const nodes=new Map(),node=id=>{if(!nodes.has(id))nodes.set(id,new Node());return nodes.get(id)};
let calls=[],buttons=[],failure=null,pending=null,authorized=true;
const context={console,Date,URLSearchParams,JSON,Promise,$:node,esc:x=>String(x??''),prompt:()=> 'Synthetic Human reason',document:{getElementById:node,querySelectorAll:s=>s.startsWith('[data-workforce-human')?buttons.filter(b=>!s.includes('^=')||b.dataset.workforceHuman.startsWith(s.split('"')[1])):[],createElement:()=>new Node(),body:{append(){}}},api:async(path,opt)=>{calls.push({path,opt});if(failure)throw failure;if(path==='/auth/me')return {user_id:'SYNTHETIC'};if(path==='/auth/permissions')return {permissions:authorized?['workforce.read']:[]};if(path==='/slow')return new Promise(resolve=>pending=resolve);if(path.startsWith('/workforce/warnings'))return [{status:'stale_rule',required:1,available:null,shortage:null,reason:'source changed'}];return []}};
vm.createContext(context);vm.runInContext(fs.readFileSync(process.argv[2],'utf8'),context);
const turn=()=>new Promise(resolve=>setImmediate(resolve));
(async()=>{SCENARIO})().catch(e=>{console.error(e.stack);process.exitCode=1});
'''
    file=tmp_path/'workforce-harness.js';file.write_text(harness.replace('SCENARIO',scenario))
    result=subprocess.run(['node',str(file),str(Path(__file__).resolve().parents[2]/'frontend/workforce.js')],capture_output=True,text=True,timeout=10)
    assert result.returncode==0,result.stderr


def test_attendance_and_linked_time_buttons_keep_their_own_handlers(tmp_path):
    run(tmp_path,r'''
const attendance=new Node(),time=new Node();attendance.dataset.workforceHuman='attendance:review:A';time.dataset.workforceHuman='time:review:T';buttons=[attendance,time];
context.attendanceRows=[{attendance_id:'A',version:1}];context.timeRows=[{time_entry_id:'T',attendance_id:'A',version:2}];
vm.runInContext("workforceState.permissions=['workforce.review'];workforceBindHuman(attendanceRows,'attendance',async()=>{});workforceBindHuman(timeRows,'time',async()=>{});",context);
await attendance.onclick();await turn();await time.onclick();await turn();
if(!calls.some(x=>x.path==='/workforce/attendance/A/review')||!calls.some(x=>x.path==='/workforce/time-entries/T/review'))throw Error('Human button bound to wrong record '+JSON.stringify(calls));
''')


def test_stale_staffing_rule_shows_unknown_not_zero_shortage(tmp_path):
    run(tmp_path,r'''
await vm.runInContext("workforceWarnings('2026-10-10')",context);
if(!node('workforceContent').innerHTML.includes('判定不可'))throw Error('stale staffing rule presented as zero shortage');
''')


def test_authorization_loss_erases_workforce_dom_cache_and_drafts(tmp_path):
    run(tmp_path,r'''
vm.runInContext("workforceState.permissions=['workforce.admin'];workforceState.employees=[{display_name:'PRIVATE'}];",context);node('workforceModal').innerHTML='PRIVATE draft';node('workforceContent').innerHTML='PRIVATE roster';
failure=Object.assign(new Error('revoked'),{status:401});await vm.runInContext('initWorkforce()',context);
if(node('workforceModal').innerHTML||node('workforceContent').innerHTML||vm.runInContext('workforceState.employees.length||workforceState.permissions.length',context))throw Error('private workforce data survives authorization loss');
''')


def test_late_response_cannot_restore_cleared_session_state(tmp_path):
    run(tmp_path,r'''
const request=vm.runInContext("workforceAPI('/slow')",context);await turn();vm.runInContext('clearWorkforce()',context);pending([{display_name:'PRIVATE old response'}]);
let refused=false;try{await request}catch(e){refused=true}if(!refused)throw Error('late response accepted after session state cleared');
''')


def test_successful_permission_refresh_clears_lost_read_rights(tmp_path):
    run(tmp_path,r"""
vm.runInContext("workforceState.permissions=['workforce.read'];workforceState.employees=[{display_name:'PRIVATE'}];",context);node('workforceContent').innerHTML='PRIVATE';authorized=false;await vm.runInContext('initWorkforce()',context);
if(node('workforceContent').innerHTML||vm.runInContext('workforceState.employees.length',context))throw Error('revoked read rights leave private workforce data');
""")


def test_late_roster_cannot_overwrite_new_attendance_view(tmp_path):
    run(tmp_path,r"""
let complete;const original=context.api;context.api=async(path,opt)=>path.startsWith('/workforce/rosters')?new Promise(resolve=>complete=resolve):original(path,opt);
const old=vm.runInContext("workforceRoster('2026-10-10')",context);await turn();await vm.runInContext('workforceAttendance()',context);complete([]);
try{await old}catch(e){if(!e.cancelled)throw e}
if(node('workforceContent').innerHTML.includes('workforceRosterDate')||!node('workforceContent').innerHTML.includes('勤怠'))throw Error('late initial roster overwrote selected attendance');
""")
