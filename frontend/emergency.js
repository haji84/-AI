// Uses the application's existing session, modal styles, escaping and API helper.
const emergencyState={permissions:[],case:null,patients:[],offset:0};
const emergencyCan=p=>emergencyState.permissions.includes(p);
const emergencyJSON=(method,data)=>({method,headers:{'Content-Type':'application/json'},body:JSON.stringify(data)});
async function emergencyAction(action){try{await action()}catch(e){$('emergencyMessage').textContent=e.status===409?'別の更新または根拠変更があります。一覧を読み直してください。':String(e.message)}}
async function initEmergency(){try{const r=await api('/auth/permissions');emergencyState.permissions=r.permissions;$('emergencyBtn').classList.toggle('hidden',!r.permissions.some(p=>p.startsWith('emergency.')))}catch{}}
async function openEmergency(){
  await initEmergency();
  if(!$('emergencyModal')){
    const modal=document.createElement('div');modal.id='emergencyModal';modal.className='modalWrap';
    modal.innerHTML=`<div class="modal"><div class="modalHead"><b>救急業務</b><span class="grow"></span><button class="btn" id="emergencyClose">閉じる</button></div><div class="modalBody"><div id="emergencyMessage" class="dangerText" role="alert"></div><div class="toolbar"><button class="btn" id="emergencyListButton">事案</button><button class="btn" id="emergencySummaryButton">月次・年次集計</button><button class="btn" id="emergencyCreateButton">事案登録</button><label>旧台帳取込<input type="file" id="emergencyImportFile" accept=".xlsx,.xlsm"></label></div><div id="emergencyContent"></div></div></div>`;
    document.body.append(modal);
    $('emergencyClose').onclick=()=>modal.classList.add('hidden');
    $('emergencyListButton').onclick=()=>emergencyAction(()=>emergencyList(0));
    $('emergencySummaryButton').onclick=()=>emergencyAction(emergencySummaryForm);
    $('emergencyCreateButton').onclick=()=>emergencyAction(emergencyCreateForm);
    $('emergencyImportFile').onchange=()=>emergencyAction(async()=>{const f=$('emergencyImportFile').files[0];if(!f)return;const form=new FormData();form.append('file',f);const r=await api('/emergency/import/workbook',{method:'POST',body:form});$('emergencyMessage').textContent=`取込結果: ${r.status} 事案${r.cases_inserted} 傷病者${r.patients_inserted} 未確認隊員${r.unresolved_crew}`;});
  }
  $('emergencyModal').classList.remove('hidden');
  $('emergencyCreateButton').hidden=!emergencyCan('emergency.case.create');
  $('emergencyImportFile').parentElement.hidden=!emergencyCan('emergency.import');
  $('emergencyListButton').hidden=!emergencyCan('emergency.case.read');
  $('emergencySummaryButton').hidden=!emergencyCan('emergency.report.read');
  await emergencyAction(()=>emergencyCan('emergency.case.read')?emergencyList(0):emergencySummaryForm());
}
async function emergencyList(offset=0){
  emergencyState.offset=offset;
  const rows=await api(`/emergency/cases?offset=${offset}&limit=50`);
  $('emergencyContent').innerHTML=`<table><thead><tr><th>覚知日</th><th>署所・番号</th><th>住所</th><th></th></tr></thead><tbody>${rows.map(c=>`<tr><td>${esc(c.call_date)}</td><td>${esc(c.station_code)} / ${esc(c.dispatch_number)}</td><td>${esc(c.incident_address)}</td><td><button class="btn" data-case="${esc(c.emergency_case_id)}">開く</button></td></tr>`).join('')}</tbody></table><div class="toolbar"><button class="btn" id="emergencyPrev">前へ</button><button class="btn" id="emergencyNext">次へ</button></div>`;
  document.querySelectorAll('[data-case]').forEach(b=>b.onclick=()=>emergencyAction(()=>emergencyDetail(b.dataset.case)));
  $('emergencyPrev').disabled=offset===0;$('emergencyNext').disabled=rows.length<50;
  $('emergencyPrev').onclick=()=>emergencyAction(()=>emergencyList(Math.max(0,offset-50)));
  $('emergencyNext').onclick=()=>emergencyAction(()=>emergencyList(offset+50));
}
function emergencyFields(fields,values={}){return fields.map(([key,label,type])=>`<label class="field">${esc(label)}<input id="emergencyField_${key}" type="${type||'text'}" value="${esc(values[key]??'')}"></label>`).join('')}
function emergencyValues(fields){return Object.fromEntries(fields.map(([key,,type])=>[key,$(`emergencyField_${key}`).value||null]))}
async function emergencyCreateForm(){
  const fields=[['call_date','覚知日','date'],['station_code','署所コード'],['dispatch_number','出場番号'],['call_time','覚知時刻','time'],['dispatch_time','出場時刻','time'],['scene_arrival_time','現着時刻','time'],['incident_address','住所']];
  $('emergencyContent').innerHTML=`<div class="grid2">${emergencyFields(fields)}</div><button class="btn primary" id="emergencySave">登録</button>`;
  $('emergencySave').onclick=()=>emergencyAction(async()=>{const c=await api('/emergency/cases',emergencyJSON('POST',emergencyValues(fields)));await emergencyDetail(c.emergency_case_id)});
}
async function emergencyDetail(id){
  const c=await api(`/emergency/cases/${id}`);emergencyState.case=c;
  const canPatients=emergencyCan('emergency.patient.read');
  const patients=canPatients?await api(`/emergency/cases/${id}/patients`):[];emergencyState.patients=patients;
  $('emergencyContent').innerHTML=`<h2>${esc(c.call_date)} / ${esc(c.station_code)} / ${esc(c.dispatch_number)}</h2><p>${esc(c.incident_address)}</p><div class="toolbar">${emergencyCan('emergency.case.update')?'<button class="btn" id="emergencyEditCase">事案訂正</button>':''}${canPatients&&emergencyCan('emergency.crew.read')?'<button class="btn" id="emergencyCheck">入力チェック</button>':''}${emergencyCan('emergency.patient.create')?'<button class="btn" id="emergencyAddPatient">傷病者登録</button>':''}</div><div id="emergencyChecks"></div>${patients.map(p=>`<div class="card"><b>傷病者${p.patient_number}</b><p>傷病名: ${esc(p.diagnosis_text)} / 搬送先コード: ${esc(p.hospital_code)} / 重症度コード: ${esc(p.severity_code)}</p><div class="toolbar">${emergencyCan('emergency.patient.update')?`<button class="btn" data-patient-edit="${esc(p.emergency_patient_id)}">訂正</button><button class="btn" data-treatment="${esc(p.emergency_patient_id)}">処置登録</button>`:''}${emergencyCan('emergency.clinical.generate')?`<button class="btn" data-candidate="${esc(p.emergency_patient_id)}">CPA・アレルギー候補作成</button>`:''}<button class="btn" data-flags="${esc(p.emergency_patient_id)}">候補・確認状態</button></div><div id="emergencyFlags_${p.emergency_patient_id}"></div></div>`).join('')}`;
  if($('emergencyEditCase'))$('emergencyEditCase').onclick=()=>emergencyAction(()=>emergencyEditCase(c));
  if($('emergencyCheck'))$('emergencyCheck').onclick=()=>emergencyAction(async()=>{const r=await api(`/emergency/cases/${id}/checks`);$('emergencyChecks').innerHTML=r.issues.length?r.issues.map(x=>`<p class="notice">${esc(x.field)}: ${esc(x.message)}</p>`).join(''):'入力チェックの警告はありません。'});
  if($('emergencyAddPatient'))$('emergencyAddPatient').onclick=()=>emergencyAction(()=>emergencyPatientForm(null));
  document.querySelectorAll('[data-patient-edit]').forEach(b=>b.onclick=()=>emergencyAction(()=>emergencyPatientForm(patients.find(p=>p.emergency_patient_id===b.dataset.patientEdit))));
  document.querySelectorAll('[data-treatment]').forEach(b=>b.onclick=()=>emergencyAction(()=>emergencyTreatmentForm(b.dataset.treatment)));
  document.querySelectorAll('[data-flags]').forEach(b=>b.onclick=()=>emergencyAction(()=>emergencyFlags(b.dataset.flags)));
  document.querySelectorAll('[data-candidate]').forEach(b=>b.onclick=()=>emergencyAction(async()=>{const p=patients.find(p=>p.emergency_patient_id===b.dataset.candidate);await api(`/emergency/patients/${p.emergency_patient_id}/clinical-candidates`,emergencyJSON('POST',{expected_version:p.version}));await emergencyFlags(p.emergency_patient_id)}));
}
async function emergencyEditCase(c){
  const fields=[['call_date','覚知日','date'],['call_time','覚知時刻','time'],['dispatch_time','出場時刻','time'],['scene_arrival_time','現着時刻','time'],['leave_scene_time','引揚時刻','time'],['return_station_time','帰署時刻','time'],['incident_address','住所'],['command_text','指令内容']];
  $('emergencyContent').innerHTML=`<div class="grid2">${emergencyFields(fields,c)}</div><button class="btn primary" id="emergencySave">訂正保存</button>`;
  $('emergencySave').onclick=()=>emergencyAction(async()=>{await api(`/emergency/cases/${c.emergency_case_id}`,emergencyJSON('PATCH',{expected_version:c.version,...emergencyValues(fields)}));await emergencyDetail(c.emergency_case_id)});
}
async function emergencyPatientForm(p){
  const fields=[...(!p?[['patient_number','傷病者番号','number']]:[]),['age','年齢','number'],['diagnosis_text','傷病名'],['condition_text','傷病者状態'],['hospital_code','搬送先コード'],['severity_code','重症度コード']];
  $('emergencyContent').innerHTML=`<div class="grid2">${emergencyFields(fields,p||{})}</div><button class="btn primary" id="emergencySave">保存</button>`;
  $('emergencySave').onclick=()=>emergencyAction(async()=>{const data=emergencyValues(fields);if(data.age!==null)data.age=Number(data.age);if(!p)data.patient_number=Number(data.patient_number);await api(p?`/emergency/patients/${p.emergency_patient_id}`:`/emergency/cases/${emergencyState.case.emergency_case_id}/patients`,emergencyJSON(p?'PATCH':'POST',p?{expected_version:p.version,...data}:data));await emergencyDetail(emergencyState.case.emergency_case_id)});
}
async function emergencyTreatmentForm(pid){
  $('emergencyContent').innerHTML='<label class="field">処置<select id="emergencyTreatment"><option value="cpr">心肺蘇生</option><option value="chest_compressions">胸骨圧迫</option><option value="ventilation">人工呼吸</option><option value="aed">AED</option><option value="defibrillation">除細動</option><option value="oxygen">酸素</option><option value="other">その他</option></select></label><label class="field">処置内容<textarea id="emergencyTreatmentNote"></textarea></label><button class="btn primary" id="emergencySave">処置登録</button>';
  $('emergencySave').onclick=()=>emergencyAction(async()=>{await api(`/emergency/patients/${pid}/treatments`,emergencyJSON('POST',{code:$('emergencyTreatment').value,notes:$('emergencyTreatmentNote').value}));await emergencyDetail(emergencyState.case.emergency_case_id)});
}
async function emergencyFlags(pid){
  const flags=await api(`/emergency/patients/${pid}/clinical-flags`);
  const box=$(`emergencyFlags_${pid}`);
  box.innerHTML='<p class="notice">自動抽出は候補です。心肺蘇生の処置記録だけではCPAを確定しません。元記録の確認が必要です。</p>'+flags.map(f=>`<div class="card">${esc(f.flag_type)} / ${esc(f.review_status)}${f.stale?' / 根拠変更あり':''}<details><summary>根拠</summary><pre>${esc(JSON.stringify(f.evidence,null,2))}</pre></details>${emergencyCan('emergency.clinical.review')&&f.review_status==='unreviewed'&&!f.stale?`<button class="btn" data-flag="${esc(f.flag_id)}" data-version="${f.version}" data-decision="confirmed">確認して採用</button><button class="btn" data-flag="${esc(f.flag_id)}" data-version="${f.version}" data-decision="rejected">不採用</button>`:''}</div>`).join('');
  box.querySelectorAll('[data-flag]').forEach(b=>b.onclick=()=>emergencyAction(async()=>{await api(`/emergency/clinical-flags/${b.dataset.flag}/review`,emergencyJSON('POST',{expected_version:Number(b.dataset.version),decision:b.dataset.decision}));await emergencyFlags(pid)}));
}
async function emergencySummaryForm(){
  $('emergencyContent').innerHTML='<p>搬送先・重症度・地区集計は共通の救急集計画面を使用します。</p><a class="btn" href="/ui/emergency.html">救急集計を開く</a><div class="toolbar"><label>確認済み臨床分類の年<input id="emergencyYear" type="number" min="1900" max="9998"></label><label>月（空欄は年次）<input id="emergencyMonth" type="number" min="1" max="12"></label><button class="btn" id="emergencyAggregate">確認済み分類集計</button></div><div id="emergencyStats"></div>';
  $('emergencyYear').value=new Date().getFullYear();
  $('emergencyAggregate').onclick=()=>emergencyAction(async()=>{const query=`year=${encodeURIComponent($('emergencyYear').value)}`+($('emergencyMonth').value?`&month=${encodeURIComponent($('emergencyMonth').value)}`:'');const r=await api(`/emergency/clinical-statistics?${query}`);$('emergencyStats').innerHTML=`<p class="notice">Human確認済みで根拠変更のない分類だけを集計します。根拠変更で除外した分類: ${r.stale_confirmed_flags}</p><pre>${esc(JSON.stringify(r.verified_clinical_counts,null,2))}</pre>`});
}
