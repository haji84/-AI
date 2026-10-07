// Shared PC workforce surface. Uses existing session, workforceAPI(), esc(), and modal styles.
const workforceState={permissions:[],employees:[],organizations:[],shifts:[],date:new Date().toLocaleDateString('sv-SE',{timeZone:'Asia/Tokyo'}),identity:null,generation:0,viewGeneration:0};
let workforcePendingHuman=null;
function clearWorkforce(){
  workforcePendingHuman=null;
  workforceState.generation++;workforceState.viewGeneration++;Object.assign(workforceState,{identity:null,permissions:[],employees:[],organizations:[],shifts:[]});
  for(const id of ['workforceContent','workforceNav','workforceMessage','workforceHumanStatus'])if($(id))$(id).innerHTML='';
  if($('workforceModal')){$('workforceModal').innerHTML='';$('workforceModal').remove();}
  if($('workforceBtn'))$('workforceBtn').classList.add('hidden');
}
function workforceAssertView(view){if(view!==workforceState.viewGeneration)throw Object.assign(new Error('superseded workforce view'),{cancelled:true});}
async function workforceAPI(url,opt={}){
  const ticket=workforceState.generation,view=workforceState.viewGeneration;
  try{
    const identity=await api('/auth/me');
    if(ticket!==workforceState.generation)throw Object.assign(new Error('session state changed'),{cancelled:true});
    if(workforceState.identity&&identity.user_id!==workforceState.identity){clearWorkforce();throw Object.assign(new Error('session identity changed'),{cancelled:true});}
    workforceState.identity=identity.user_id;
    const result=await api(url,opt);
    if(ticket!==workforceState.generation)throw Object.assign(new Error('late workforce response discarded'),{cancelled:true});
    workforceAssertView(view);return result;
  }catch(e){if(e.status===401||e.status===403)clearWorkforce();throw e;}
}
async function workforceList(url){
  const result=[];let offset=0;const limit=1000;
  while(true){const separator=url.includes('?')?'&':'?';const rows=await workforceAPI(url+separator+new URLSearchParams({offset,limit}));result.push(...rows);if(rows.length<limit)return result;offset+=rows.length;}
}
function workforceKey(kind,row){return row[{roster:'roster_entry_id',leave:'leave_entry_id',attendance:'attendance_id',time:'time_entry_id',staffing:'staffing_rule_id','work-rule':'shift_type_id'}[kind]];}
function workforceLocalTime(value){return value.length===16?value+':00+09:00':value+'+09:00';}
const workforceCan=p=>workforceState.permissions.includes(p);
const workforceJSON=(method,data)=>({method,headers:{'Content-Type':'application/json'},body:JSON.stringify(data)});
async function workforceAction(fn){try{await fn();if($('workforceMessage'))$('workforceMessage').textContent=''}catch(e){if(e.cancelled)return;if($('workforceMessage'))$('workforceMessage').textContent=e.status===409?'更新競合または根拠変更があります。最新データを再読込してください。':String(e.message)}}
async function initWorkforce(){try{const r=await workforceAPI('/auth/permissions');if(!r.permissions.includes('workforce.read'))clearWorkforce();workforceState.permissions=r.permissions;$('workforceBtn')?.classList.toggle('hidden',!r.permissions.some(p=>p.startsWith('workforce.')))}catch(e){if(e.cancelled)throw e;}}
function workforceButton(id,label,permission){return !permission||workforceCan(permission)?`<button class="btn" id="${id}" type="button">${esc(label)}</button>`:''}
function workforceBind(id,fn){if($(id))$(id).onclick=()=>workforceAction(fn)}
function workforceOptions(rows,key,label,blank=true){return [...(blank?[['','未指定']]:[]),...rows.map(r=>[r[key],label(r)])]}
function workforceField([key,label,type='text',options=[]],values={}){
  const value=values[key]??'';
  const input=type==='select'?`<select id="workforceField_${key}">${options.map(([v,l])=>`<option value="${esc(v)}" ${String(v)===String(value)?'selected':''}>${esc(l)}</option>`).join('')}</select>`:type==='textarea'?`<textarea id="workforceField_${key}">${esc(value)}</textarea>`:`<input id="workforceField_${key}" type="${type}" value="${esc(value)}">`;
  return `<label class="field">${esc(label)}${input}</label>`;
}
function workforceValues(fields){
  const out={};
  for(const [key,,type] of fields){
    const el=$('workforceField_'+key);if(!el)continue;let v=el.value;
    if(v==='')continue;
    if(type==='number')v=Number(v);
    if(type==='checkbox')v=el.checked;
    out[key]=v;
  }
  return out;
}
async function workforceRefs(){
  const [employees,organizations,shifts]=await Promise.all([workforceList('/workforce/employees'),workforceAPI('/workforce/organizations'),workforceAPI('/workforce/shift-types')]);
  Object.assign(workforceState,{employees,organizations,shifts});
}
async function openWorkforce(){
  await initWorkforce();if(workforceCan('workforce.read'))await workforceRefs();
  if(!$('workforceModal')){
    const el=document.createElement('div');el.id='workforceModal';el.className='modalWrap';el.style.zIndex='73';
    el.innerHTML='<div class="modal" style="width:min(1240px,98vw)"><div class="modalHead"><b>勤務・人員配置</b><span class="grow"></span><button class="btn" id="workforceClose">閉じる</button></div><div class="modalBody"><div id="workforceMessage" class="dangerText" role="alert"></div><div id="workforceHumanStatus" role="status" aria-live="polite"></div><div id="workforceNav" class="toolbar"></div><div id="workforceContent"></div></div></div>';
    document.body.append(el);$('workforceClose').onclick=()=>{workforceState.viewGeneration++;el.classList.add('hidden')};
  }
  $('workforceModal').classList.remove('hidden');
  $('workforceNav').innerHTML=
    workforceButton('workforceRoster','勤務表','workforce.read')+
    workforceButton('workforceWarnings','最低人員','workforce.read')+
    workforceButton('workforceLeave','休暇','workforce.read')+
    workforceButton('workforceAttendance','勤怠・時間外','workforce.read')+
    workforceButton('workforceSettings','勤務設定','workforce.admin')+
    workforceButton('workforceStats','集計','workforce.aggregate')+
    workforceButton('workforceExchange','取込・出力',workforceCan('workforce.import')?'workforce.import':'workforce.export');
  workforceBind('workforceRoster',()=>workforceRoster(workforceState.date));
  workforceBind('workforceWarnings',()=>workforceWarnings(workforceState.date));
  workforceBind('workforceLeave',workforceLeave);
  workforceBind('workforceAttendance',workforceAttendance);
  workforceBind('workforceSettings',workforceSettings);
  workforceBind('workforceStats',workforceStats);
  workforceBind('workforceExchange',workforceExchange);
  if(workforceCan('workforce.read'))await workforceRoster(workforceState.date);else if(workforceCan('workforce.aggregate'))await workforceStats();else if(workforceCan('workforce.import')||workforceCan('workforce.export'))await workforceExchange();else $('workforceContent').textContent='勤務記録の表示にはworkforce.read権限が必要です。';
}
async function workforceRoster(day){
  const view=++workforceState.viewGeneration;
  workforceState.date=day||workforceState.date;await workforceRefs();
  const rows=await workforceList('/workforce/rosters?'+new URLSearchParams({from_date:workforceState.date,to_date:workforceState.date}));
  const employee=id=>workforceState.employees.find(x=>x.employee_id===id);
  const org=id=>workforceState.organizations.find(x=>x.organization_id===id);
  const shift=id=>workforceState.shifts.find(x=>x.shift_type_id===id);
  workforceAssertView(view);$('workforceContent').innerHTML=`<div class="toolbar"><label>勤務日<input id="workforceRosterDate" type="date" value="${esc(workforceState.date)}"></label><button class="btn" id="workforceRosterLoad">表示</button>${workforceButton('workforceRosterNew','配置追加','workforce.create')}</div>
  <table><thead><tr><th>職員</th><th>所属/配置先</th><th>勤務</th><th>時間</th><th>状態</th><th></th></tr></thead><tbody>
  ${rows.map(r=>`<tr><td>${esc(employee(r.employee_id)?.display_name??r.employee_id)}</td><td>${esc(org(r.organization_id)?.name??r.organization_id)}${r.support_placement?' / 応援':''}</td><td>${esc(shift(r.shift_type_id)?.name??r.shift_type_id)}</td><td>${esc(r.starts_at)} → ${esc(r.ends_at)} / ${esc(r.payable_minutes)}分</td><td>${esc(r.status)}</td><td>${workforceHumanButtons('roster',r)}</td></tr>`).join('')}</tbody></table>`;
  workforceBind('workforceRosterLoad',()=>workforceRoster($('workforceRosterDate').value));workforceBind('workforceRosterNew',workforceRosterForm);workforceBindHuman(rows,'roster',workforceRoster);
}
function workforceHumanButtons(kind,row){
  if(row.status==='draft'&&workforceCan('workforce.review'))return `<button class="btn" data-workforce-human="${kind}:review:${workforceKey(kind,row)}">Human確認</button>`;
  if(row.status==='reviewed'&&workforceCan('workforce.approve'))return `<button class="btn primary" data-workforce-human="${kind}:approve:${workforceKey(kind,row)}">Human承認</button>`;
  return '';
}
function workforceHumanAllowed(button){
  const [,action]=button.dataset.workforceHuman.split(':');
  if(action==='approve-work-rule')return ['workforce.admin','workforce.review','workforce.approve'].every(workforceCan);
  return action==='review'?workforceCan('workforce.review'):action==='approve'&&workforceCan('workforce.approve');
}
function workforceLockHumanControls(){
  if(!workforcePendingHuman)return;
  for(const button of document.querySelectorAll('[data-workforce-human]')){
    if(!workforcePendingHuman.controls.has(button))workforcePendingHuman.controls.set(button,{disabled:button.disabled,view:workforceState.viewGeneration});
    button.disabled=true;
  }
}
function workforceBindHuman(rows,kind,back){
  const generation=workforceState.generation,view=workforceState.viewGeneration;
  const current=()=>generation===workforceState.generation&&view===workforceState.viewGeneration&&!$('workforceModal')?.classList?.contains?.('hidden');
  document.querySelectorAll(`[data-workforce-human^="${kind}:"]`).forEach(b=>b.onclick=async()=>{
    // A queued click may outlive its view or arrive while another kind is refreshing.
    if(workforcePendingHuman||b.disabled||b.isConnected===false||!current()||!workforceHumanAllowed(b))return;
    const [,action,id]=b.dataset.workforceHuman.split(':');const row=rows.find(x=>workforceKey(kind,x)===id);
    if(!row)return;
    const note=prompt('Human確認・決定理由','確認済み');if(!note||!current()||!workforceHumanAllowed(b))return;
    const operation={generation,view,controls:new Map()};workforcePendingHuman=operation;
    workforceLockHumanControls();
    if($('workforceHumanStatus'))$('workforceHumanStatus').textContent='Human確認・承認を処理中です。完了までお待ちください。';
    if($('workforceMessage'))$('workforceMessage').textContent='';
    const base={roster:'rosters',leave:'leave',attendance:'attendance',time:'time-entries',staffing:'staffing-rules','work-rule':'shift-types'}[kind];
    let accepted=false;
    try{
      await workforceAPI('/workforce/'+base+'/'+id+'/'+action,workforceJSON('POST',{expected_version:row.version,note}));
      accepted=true;
      const refresh=back(workforceState.date);operation.view=workforceState.viewGeneration;await refresh;
    }catch(e){
      if(!e.cancelled&&workforcePendingHuman===operation&&generation===workforceState.generation&&operation.view===workforceState.viewGeneration&&$('workforceMessage'))$('workforceMessage').textContent=accepted?'Human処理は完了しましたが、最新表示を取得できません。上のメニューから再読込してください。':e.status===409?'更新競合または根拠変更があります。最新データを再読込してください。':String(e.message);
    }finally{
      if(workforcePendingHuman===operation){
        workforcePendingHuman=null;
        for(const [button,state] of operation.controls)if(button.isConnected!==false&&generation===workforceState.generation&&state.view===workforceState.viewGeneration)button.disabled=state.disabled||!workforceHumanAllowed(button);
        if($('workforceHumanStatus'))$('workforceHumanStatus').textContent='';
      }
    }
  });
  workforceLockHumanControls();
}
async function workforceRosterForm(){
  const view=++workforceState.viewGeneration;
  await workforceRefs();
  const fields=[
    ['employee_id','職員','select',workforceOptions(workforceState.employees,'employee_id',x=>(x.employee_code??'')+' / '+x.display_name,false)],
    ['organization_id','配置先','select',workforceOptions(workforceState.organizations,'organization_id',x=>x.code+' / '+x.name,false)],
    ['shift_type_id','勤務区分','select',workforceOptions(workforceState.shifts.filter(x=>x.active),'shift_type_id',x=>x.code+' / '+x.name,false)],
    ['work_date','勤務日','date'],['note','備考','textarea']
  ];
  workforceAssertView(view);$('workforceContent').innerHTML=`<h2>勤務配置追加</h2><div class="grid2">${fields.map(f=>workforceField(f,{work_date:workforceState.date})).join('')}</div><label><input id="workforceSupport" type="checkbox"> 主所属以外への応援配置</label><div class="toolbar"><button class="btn primary" id="workforceSaveRoster">Draft保存</button><button class="btn" id="workforceBack">戻る</button></div>`;
  workforceBind('workforceSaveRoster',async()=>{await workforceAPI('/workforce/rosters',workforceJSON('POST',{...workforceValues(fields),support_placement:$('workforceSupport').checked}));await workforceRoster($('workforceField_work_date').value)});
  workforceBind('workforceBack',()=>workforceRoster(workforceState.date));
}
async function workforceWarnings(day){
  const view=++workforceState.viewGeneration;
  workforceState.date=day||workforceState.date;
  const rows=await workforceAPI('/workforce/warnings?'+new URLSearchParams({on_date:workforceState.date}));
  workforceAssertView(view);$('workforceContent').innerHTML=`<div class="toolbar"><label>基準日<input id="workforceWarningDate" type="date" value="${esc(workforceState.date)}"></label><button class="btn" id="workforceWarningLoad">再計算</button></div>
  <p class="notice">最低人員・資格条件はHuman承認済みRuleだけを使用します。休暇承認済みの職員は可用人数から除外します。</p>
  <table><thead><tr><th>組織</th><th>勤務</th><th>資格</th><th>必要</th><th>可用</th><th>不足</th></tr></thead><tbody>${rows.map(r=>`<tr><td>${esc(r.organization_id)}</td><td>${esc(r.shift_type_id)}</td><td>${esc(r.qualification_code??'指定なし')}</td><td>${r.required}</td><td>${r.available??'不明'}</td><td>${r.shortage==null?'判定不可（根拠変更）':r.shortage?'<b>'+r.shortage+'</b>':'0'}</td></tr>`).join('')}</tbody></table>`;
  workforceBind('workforceWarningLoad',()=>workforceWarnings($('workforceWarningDate').value));
}
async function workforceLeave(){
  const view=++workforceState.viewGeneration;
  const rows=await workforceList('/workforce/leave');
  const employee=id=>workforceState.employees.find(x=>x.employee_id===id);
  workforceAssertView(view);$('workforceContent').innerHTML=`<div class="toolbar">${workforceButton('workforceLeaveNew','休暇Ledger追加','workforce.create')}</div>
  <p class="notice">残数は承認済みLedgerから再計算します。Draft/Review中は正式残数に反映しません。</p>
  <table><thead><tr><th>職員</th><th>種別</th><th>操作</th><th>分</th><th>日付</th><th>状態</th><th></th></tr></thead><tbody>${rows.map(r=>`<tr><td>${esc(employee(r.employee_id)?.display_name??r.employee_id)}</td><td>${esc(r.leave_type)}</td><td>${esc(r.kind)}</td><td>${r.quantity_minutes}</td><td>${esc(r.effective_on)}</td><td>${esc(r.status)}</td><td>${workforceHumanButtons('leave',r)}</td></tr>`).join('')}</tbody></table>`;
  workforceBind('workforceLeaveNew',workforceLeaveForm);workforceBindHuman(rows,'leave',workforceLeave);
}
async function workforceLeaveForm(){
  const view=++workforceState.viewGeneration;
  const fields=[
    ['employee_id','職員','select',workforceOptions(workforceState.employees,'employee_id',x=>(x.employee_code??'')+' / '+x.display_name,false)],
    ['leave_type','休暇種別','select',[['annual','年休'],['special','特別休暇'],['compensatory','代休/補償時間']]],
    ['kind','Ledger操作','select',[['grant','付与'],['use','使用'],['adjustment_add','加算訂正'],['adjustment_subtract','減算訂正'],['expire','失効']]],
    ['quantity_minutes','分','number'],['effective_on','適用日','date'],['leave_start_at','休暇開始（日本時間）','datetime-local'],['leave_end_at','休暇終了（日本時間）','datetime-local'],['expires_on','期限','date'],['private_reason','理由（機微情報）','textarea']
  ];
  workforceAssertView(view);$('workforceContent').innerHTML=`<h2>休暇Ledger Draft</h2><div class="grid2">${fields.map(f=>workforceField(f,{effective_on:workforceState.date})).join('')}</div><div class="toolbar"><button class="btn primary" id="workforceSaveLeave">Draft保存</button><button class="btn" id="workforceBack">戻る</button></div>`;
  workforceBind('workforceSaveLeave',async()=>{const data=workforceValues(fields);for(const k of ['leave_start_at','leave_end_at'])if(data[k])data[k]=workforceLocalTime(data[k]);await workforceAPI('/workforce/leave',workforceJSON('POST',data));await workforceLeave()});workforceBind('workforceBack',workforceLeave);
}
async function workforceAttendance(){
  const view=++workforceState.viewGeneration;
  const [attendance,times]=await Promise.all([workforceList('/workforce/attendance'),workforceList('/workforce/time-entries')]);
  const employee=id=>workforceState.employees.find(x=>x.employee_id===id);
  workforceAssertView(view);$('workforceContent').innerHTML=`<div class="toolbar">${workforceButton('workforceAttendanceNew','勤怠Draft','workforce.create')}${workforceButton('workforceTimeNew','時間外/代休Ledger','workforce.create')}</div>
  <h3>勤怠</h3><table><thead><tr><th>職員</th><th>日</th><th>入</th><th>出</th><th>勤務分</th><th>状態</th><th></th></tr></thead><tbody>${attendance.map(r=>`<tr><td>${esc(employee(r.employee_id)?.display_name??r.employee_id)}</td><td>${esc(r.work_date)}</td><td>${esc(r.check_in_at)}</td><td>${esc(r.check_out_at??'')}</td><td>${esc(r.worked_minutes??'')}</td><td>${esc(r.status)}</td><td>${workforceHumanButtons('attendance',r)}</td></tr>`).join('')}</tbody></table>
  <h3>時間外・代休</h3><table><thead><tr><th>職員</th><th>種別</th><th>分</th><th>日</th><th>状態</th><th></th></tr></thead><tbody>${times.map(r=>`<tr><td>${esc(employee(r.employee_id)?.display_name??r.employee_id)}</td><td>${esc(r.kind)}</td><td>${r.minutes}</td><td>${esc(r.occurred_on)}</td><td>${esc(r.status)}</td><td>${workforceHumanButtons('time',r)}</td></tr>`).join('')}</tbody></table>`;
  workforceBind('workforceAttendanceNew',workforceAttendanceForm);workforceBind('workforceTimeNew',workforceTimeForm);
  workforceBindHuman(attendance,'attendance',workforceAttendance);workforceBindHuman(times,'time',workforceAttendance);
}
async function workforceAttendanceForm(){
  const view=++workforceState.viewGeneration;
  const rosters=await workforceList('/workforce/rosters?status=approved');
  const fields=[
    ['roster_entry_id','Human承認済み勤務配置','select',workforceOptions(rosters,'roster_entry_id',x=>x.work_date+' / '+(workforceState.employees.find(e=>e.employee_id===x.employee_id)?.display_name??x.employee_id))],
    ['employee_id','職員','select',workforceOptions(workforceState.employees,'employee_id',x=>(x.employee_code??'')+' / '+x.display_name,false)],
    ['work_date','勤務日','date'],['check_in_at','出勤日時（日本時間）','datetime-local'],['check_out_at','退勤日時（日本時間）','datetime-local']
  ];
  workforceAssertView(view);$('workforceContent').innerHTML=`<h2>勤怠Draft</h2><div class="grid2">${fields.map(f=>workforceField(f,{work_date:workforceState.date})).join('')}</div><div class="toolbar"><button class="btn primary" id="workforceSaveAttendance">Draft保存</button><button class="btn" id="workforceBack">戻る</button></div>`;
  workforceBind('workforceSaveAttendance',async()=>{const data=workforceValues(fields);for(const k of ['check_in_at','check_out_at'])if(data[k])data[k]=workforceLocalTime(data[k]);await workforceAPI('/workforce/attendance',workforceJSON('POST',data));await workforceAttendance()});workforceBind('workforceBack',workforceAttendance);
}
async function workforceTimeForm(){
  const view=++workforceState.viewGeneration;
  const fields=[
    ['employee_id','職員','select',workforceOptions(workforceState.employees,'employee_id',x=>(x.employee_code??'')+' / '+x.display_name,false)],
    ['kind','種別','select',[['overtime','時間外'],['comp_grant','代休/補償時間付与'],['comp_use','代休/補償時間使用']]],
    ['minutes','分','number'],['occurred_on','日付','date'],['note','備考','textarea']
  ];
  workforceAssertView(view);$('workforceContent').innerHTML=`<h2>時間Ledger Draft</h2><div class="grid2">${fields.map(f=>workforceField(f,{occurred_on:workforceState.date})).join('')}</div><div class="toolbar"><button class="btn primary" id="workforceSaveTime">Draft保存</button><button class="btn" id="workforceBack">戻る</button></div>`;
  workforceBind('workforceSaveTime',async()=>{await workforceAPI('/workforce/time-entries',workforceJSON('POST',workforceValues(fields)));await workforceAttendance()});workforceBind('workforceBack',workforceAttendance);
}
async function workforceSettings(){
  const view=++workforceState.viewGeneration;
  await workforceRefs();const rules=await workforceList('/workforce/staffing-rules');
  workforceAssertView(view);$('workforceContent').innerHTML=`<div class="toolbar">${workforceButton('workforceShiftNew','勤務区分追加','workforce.admin')}${workforceButton('workforceRuleNew','最低人員Rule追加','workforce.admin')}${workforceButton('workforceQualificationNew','職員資格追加','workforce.admin')}</div>
  <h3>勤務区分</h3><table><tbody>${workforceState.shifts.map(s=>`<tr><td>${esc(s.code)} / ${esc(s.name)}</td><td>${esc(s.start_time)}-${esc(s.end_time)} / 支払対象${s.payable_minutes}分</td><td>${s.active?'有効':'停止'}</td><td>${s.work_rule_approved_by?'勤務Rule承認済み':workforceCan('workforce.approve')&&workforceCan('workforce.admin')&&workforceCan('workforce.review')?`<button class="btn" data-workforce-human="work-rule:approve-work-rule:${s.shift_type_id}">勤務RuleをHuman承認</button>`:'勤務Rule未承認'}</td></tr>`).join('')}</tbody></table>
  <h3>最低人員Rule</h3><table><thead><tr><th>組織</th><th>勤務</th><th>必要</th><th>資格</th><th>期間</th><th>状態</th><th></th></tr></thead><tbody>${rules.map(r=>`<tr><td>${esc(r.organization_id)}</td><td>${esc(r.shift_type_id)}</td><td>${r.min_staff}</td><td>${esc(r.qualification_code??'')}</td><td>${esc(r.effective_from)}-${esc(r.effective_to??'')}</td><td>${esc(r.status)}</td><td>${workforceHumanButtons('staffing',r)}</td></tr>`).join('')}</tbody></table>`;
  workforceBind('workforceShiftNew',workforceShiftForm);workforceBind('workforceRuleNew',workforceRuleForm);workforceBind('workforceQualificationNew',workforceQualificationForm);workforceBindHuman(rules,'staffing',workforceSettings);workforceBindHuman(workforceState.shifts,'work-rule',workforceSettings);
}
async function workforceShiftForm(){
  const view=++workforceState.viewGeneration;
  const fields=[['code','コード'],['name','名称'],['start_time','開始','time'],['end_time','終了','time'],['timezone_name','Timezone'],['payable_minutes','勤務扱い分','number'],['work_segments','勤務開始からの勤務区間（分）のJSON配列。休憩は含めない','textarea']];
  workforceAssertView(view);$('workforceContent').innerHTML=`<h2>勤務区分</h2><div class="grid2">${fields.map(f=>workforceField(f,{timezone_name:'Asia/Tokyo'})).join('')}</div><label><input id="workforceCrossMidnight" type="checkbox"> 日跨ぎ勤務</label><div class="toolbar"><button class="btn primary" id="workforceSaveShift">保存</button><button class="btn" id="workforceBack">戻る</button></div>`;
  workforceBind('workforceSaveShift',async()=>{const data=workforceValues(fields);if(data.work_segments)data.work_segments=JSON.parse(data.work_segments);await workforceAPI('/workforce/shift-types',workforceJSON('POST',{...data,cross_midnight:$('workforceCrossMidnight').checked}));await workforceSettings()});workforceBind('workforceBack',workforceSettings);
}
async function workforceRuleForm(){
  const view=++workforceState.viewGeneration;
  const fields=[
    ['organization_id','組織','select',workforceOptions(workforceState.organizations,'organization_id',x=>x.code+' / '+x.name,false)],
    ['shift_type_id','勤務区分','select',workforceOptions(workforceState.shifts,'shift_type_id',x=>x.code+' / '+x.name,false)],
    ['min_staff','最低人員','number'],['qualification_code','必要資格コード'],['effective_from','有効開始','date'],['effective_to','有効終了','date'],['rule_note','根拠・備考','textarea']
  ];
  workforceAssertView(view);$('workforceContent').innerHTML=`<h2>最低人員Rule Draft</h2><p class="notice">制度値をAIが決めません。Human確認・承認後のみ不足判定へ使用します。</p><div class="grid2">${fields.map(f=>workforceField(f,{effective_from:workforceState.date})).join('')}</div><div class="toolbar"><button class="btn primary" id="workforceSaveRule">Draft保存</button><button class="btn" id="workforceBack">戻る</button></div>`;
  workforceBind('workforceSaveRule',async()=>{await workforceAPI('/workforce/staffing-rules',workforceJSON('POST',workforceValues(fields)));await workforceSettings()});workforceBind('workforceBack',workforceSettings);
}
async function workforceQualificationForm(){
  const view=++workforceState.viewGeneration;
  const fields=[
    ['employee_id','職員','select',workforceOptions(workforceState.employees,'employee_id',x=>(x.employee_code??'')+' / '+x.display_name,false)],
    ['code','資格コード'],['label','資格名'],['valid_from','有効開始','date'],['valid_to','有効終了','date'],['document_id','根拠Document ID']
  ];
  workforceAssertView(view);$('workforceContent').innerHTML=`<h2>資格登録</h2><div class="grid2">${fields.map(f=>workforceField(f,{valid_from:workforceState.date})).join('')}</div><div class="toolbar"><button class="btn primary" id="workforceSaveQualification">保存</button><button class="btn" id="workforceBack">戻る</button></div>`;
  workforceBind('workforceSaveQualification',async()=>{await workforceAPI('/workforce/qualifications',workforceJSON('POST',workforceValues(fields)));await workforceSettings()});workforceBind('workforceBack',workforceSettings);
}
async function workforceStats(){
  const view=++workforceState.viewGeneration;
  workforceAssertView(view);$('workforceContent').innerHTML=`<div class="toolbar"><label>年<input id="workforceYear" type="number" min="2000" max="2200" value="${new Date().getFullYear()}"></label><label>月<input id="workforceMonth" type="number" min="1" max="12"></label><button class="btn" id="workforceStatsLoad">集計</button></div><pre id="workforceStatsResult"></pre>`;
  workforceBind('workforceStatsLoad',async()=>{const p=new URLSearchParams({year:$('workforceYear').value});if($('workforceMonth').value)p.set('month',$('workforceMonth').value);$('workforceStatsResult').textContent=JSON.stringify(await workforceAPI('/workforce/statistics?'+p),null,2)});await $('workforceStatsLoad').onclick();
}
async function workforceDownload(url){const identity=workforceState.identity,ticket=workforceState.generation;await workforceAPI('/auth/permissions');const r=await fetch(url);if(r.status===401||r.status===403)clearWorkforce();if(!r.ok)throw new Error('出力できません');if(ticket!==workforceState.generation||identity!==workforceState.identity)throw Object.assign(new Error('stale export discarded'),{cancelled:true});const a=document.createElement('a'),u=URL.createObjectURL(await r.blob());a.href=u;a.download=r.headers.get('Content-Disposition')?.match(/filename="([^"]+)"/)?.[1]??'workforce.csv';document.body.append(a);a.click();a.remove();URL.revokeObjectURL(u)}
async function workforceExchange(){
  const view=++workforceState.viewGeneration;
  workforceAssertView(view);$('workforceContent').innerHTML=`<h2>勤務表取込・出力</h2><p class="notice">CSV/XLSXは schema_version=workforce-v1、employee_code、organization_code、shift_code、work_date、support_placement、note の列順で検証します。プレビュー後に全行を明示確定します。</p>
  ${workforceCan('workforce.import')?'<label>ファイル<input type="file" id="workforceImportFile" accept=".csv,.xlsx"></label><label>元Document ID（任意）<input id="workforceImportDocument"></label><button class="btn" id="workforcePreviewImport">検証</button><div id="workforceImportPreview"></div>':''}
  ${workforceCan('workforce.export')?'<div class="toolbar"><label>開始<input id="workforceExportFrom" type="date"></label><label>終了<input id="workforceExportTo" type="date"></label><select id="workforceExportFormat"><option value="csv">CSV</option><option value="xlsx">XLSX</option></select><button class="btn" id="workforceExport">出力</button></div>':''}`;
  workforceBind('workforcePreviewImport',async()=>{const file=$('workforceImportFile').files[0];if(!file)throw new Error('ファイルを選択してください');const body=new FormData();body.append('file',file);if($('workforceImportDocument').value)body.append('document_id',$('workforceImportDocument').value);const p=await workforceAPI('/workforce/import/rosters',{method:'POST',body});$('workforceImportPreview').innerHTML=`<p>${p.rows}行 / SHA256 ${esc(p.file_sha256)}</p><pre>${esc(JSON.stringify(p.sample,null,2))}</pre><button class="btn primary" id="workforceConfirmImport">確認して確定</button>`;workforceBind('workforceConfirmImport',async()=>{const r=await workforceAPI('/workforce/import-previews/'+p.preview_id+'/confirm',workforceJSON('POST',{expected_version:p.version,file_sha256:p.file_sha256}));$('workforceImportPreview').textContent='確定 '+r.inserted+'行'})});
  workforceBind('workforceExport',()=>{const p=new URLSearchParams({format:$('workforceExportFormat').value});if($('workforceExportFrom').value)p.set('from_date',$('workforceExportFrom').value);if($('workforceExportTo').value)p.set('to_date',$('workforceExportTo').value);return workforceDownload('/workforce/export/rosters?'+p)});
}

