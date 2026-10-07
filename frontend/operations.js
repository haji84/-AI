// Shared /ui/ shell: session cookie, escaping, API helper and modal styling.
const operationsState={viewGeneration:0,permissions:[],incident:null,vehicle:null,dispatch:null,vehicleView:null,assignment:null,listType:'incidents',offset:0,q:''};
function clearOperations(){operationsInvalidateVehicleView();Object.assign(operationsState,{permissions:[],incident:null,vehicle:null,dispatch:null,vehicleView:null,assignment:null,listType:'incidents',offset:0,q:''});if($('operationsModal'))$('operationsModal').remove();$('operationsBtn')?.classList.add('hidden')}
const operationsCan=p=>operationsState.permissions.includes(p);
const operationsJSON=(method,data)=>({method,headers:{'Content-Type':'application/json'},body:JSON.stringify(data)});
async function operationsAction(fn){const message=$('operationsMessage');if(!message)return;message.textContent='';let ticket=operationsState.viewGeneration;try{const result=fn();ticket=operationsState.viewGeneration;await result}catch(e){if(e.cancelled||ticket!==operationsState.viewGeneration||$('operationsMessage')!==message)return;$('operationsViewLoading')?.remove();$('operationsMessage').textContent=e.status===409?'更新競合または根拠変更があります。「再読込」で最新記録を開いてください。':(Array.isArray(e.body?.detail)?e.body.detail.map(d=>d.loc.join('.')+': '+d.msg).join(' / '):String(e.message))}}
async function initOperations(isCurrent=()=>true){try{if(!isCurrent())return;const r=await api('/auth/permissions');if(!isCurrent())return;if(operationsState.vehicleView&&(!r.permissions.includes('fleet.read')||(operationsState.assignment&&!r.permissions.includes('fleet.update')))){clearOperations();}operationsState.permissions=r.permissions;$('operationsBtn').classList.toggle('hidden',!r.permissions.some(p=>p.startsWith('incident.')||p.startsWith('fleet.')))}catch(e){if(e.cancelled)throw e;}}
function operationsButton(id,label,permission){return !permission||operationsCan(permission)?`<button class="btn" id="${id}" type="button">${esc(label)}</button>`:''}
function operationsBind(id,fn){if($(id))$(id).onclick=()=>operationsAction(fn)}
const operationKinds=[['fire','火災'],['rescue','救助'],['emergency_support','救急支援'],['watch','警戒'],['storm','風水害'],['other','その他']];
function operationsOptions(rows,key,label,blank=true){return [...(blank?[['','未指定']]:[]),...rows.map(r=>[r[key],label(r)])]}
function operationsField([key,label,type='text',options=[]],values={}){
  let value=values[key]??'';
  if(type==='datetime-local'&&value){const d=new Date(/(Z|[+-]\d\d:\d\d)$/.test(value)?value:value+'Z');if(!Number.isNaN(d.valueOf()))value=new Date(d.getTime()-d.getTimezoneOffset()*60000).toISOString().slice(0,16)}
  const attrs=`id="operationsField_${key}" name="${key}"`;
  const input=type==='select'?`<select ${attrs}>${options.map(([v,l])=>`<option value="${esc(v)}" ${String(value)===String(v)?'selected':''}>${esc(l)}</option>`).join('')}</select>`:type==='textarea'?`<textarea ${attrs}>${esc(value)}</textarea>`:`<input ${attrs} type="${type}" ${type==='number'?`step="${key.includes('odometer')?'0.1':'0.01'}" min="0"`:''} value="${esc(value)}">`;
  return `<label class="field">${esc(label)}${input}</label>`;
}
function operationsValues(fields,patch=false){const values={};for(const [key,,type] of fields){let value=$(`operationsField_${key}`).value;if(value===''){if(patch)values[key]=null;continue}if(type==='datetime-local')value=new Date(value).toISOString();if(key==='active')value=value==='true';values[key]=value}return values}
function operationsForm(title,fields,values,save,back){
  const current=operationsBeginView();if(!current())return;
  $('operationsContent').innerHTML=`<h2>${esc(title)}</h2><form id="operationsForm"><div class="grid2">${fields.map(f=>operationsField(f,values)).join('')}</div><div class="toolbar"><button class="btn primary" type="submit">保存</button><button class="btn" id="operationsFormBack" type="button">戻る</button></div></form>`;
  $('operationsForm').onsubmit=e=>{e.preventDefault();if(current())return operationsAction(()=>save(operationsValues(fields,Boolean(values.version)),current))};operationsBind('operationsFormBack',()=>current()?back():undefined);
}
async function openOperations(isCurrent=()=>true){
  if(!isCurrent())return;await initOperations(isCurrent);if(!isCurrent())return;
  if(!$('operationsModal')){
    const el=document.createElement('div');el.id='operationsModal';el.className='modalWrap';el.style.zIndex='72';
    el.innerHTML='<div class="modal" style="width:min(1220px,98vw)"><div class="modalHead"><b>事案・出動 / 車両運用</b><span class="grow"></span><button class="btn" id="operationsClose">閉じる</button></div><div class="modalBody"><div id="operationsMessage" class="dangerText" role="alert"></div><div id="operationsNav" class="toolbar"></div><div id="operationsContent"></div></div></div>';
    document.body.append(el);$('operationsClose').onclick=()=>{operationsInvalidateVehicleView();$('operationsContent').innerHTML='';el.classList.add('hidden');};
  }
  $('operationsModal').classList.remove('hidden');
  $('operationsNav').innerHTML=operationsButton('operationsIncidents','事案','incident.read')+operationsButton('operationsVehicles','車両','fleet.read')+operationsButton('operationsSummary','月次・年次集計',null)+operationsButton('operationsAlerts','期限・故障警告','fleet.read')+operationsButton('operationsRates','手当設定','incident.read')+operationsButton('operationsExchange','取込・出力');
  operationsBind('operationsIncidents',()=>operationsList('incidents',0,''));operationsBind('operationsVehicles',()=>operationsList('vehicles',0,''));operationsBind('operationsSummary',operationsSummary);operationsBind('operationsAlerts',operationsAlerts);operationsBind('operationsRates',operationsRates);operationsBind('operationsExchange',operationsExchange);
  const modal=$('operationsModal'),owned=()=>isCurrent()&&$('operationsModal')===modal&&Boolean(modal?.isConnected)&&!modal.classList.contains('hidden');
  await operationsAction(()=>operationsCan('incident.read')?operationsList('incidents',0,'',owned):operationsCan('fleet.read')?operationsList('vehicles',0,'',owned):operationsSummary());
}
async function operationsList(type=operationsState.listType,offset=0,q=operationsState.q,isCurrent=()=>true){
  let owned=isCurrent;try{
  if(!isCurrent())return;operationsInvalidateVehicleView();Object.assign(operationsState,{listType:type,offset,q});const domain=type==='incidents'?'incident':'fleet';
  const ticket=operationsState.viewGeneration,modal=$('operationsModal');owned=type==='vehicles'?operationsVehicleOwner(isCurrent).current:()=>isCurrent()&&ticket===operationsState.viewGeneration&&$('operationsModal')===modal&&Boolean(modal?.isConnected)&&!modal.classList.contains('hidden');
  if(!owned())return;$('operationsContent').innerHTML='<p id="operationsViewLoading" role="status">一覧を読み込み中…</p>';
  const rows=await api('/operations/'+type+'?'+new URLSearchParams({q,offset:String(offset),limit:'50'}));if(!owned())return;
  $('operationsContent').innerHTML=`<div class="toolbar"><label>検索<input id="operationsQ" value="${esc(q)}"></label><button class="btn" id="operationsSearch">検索</button>${operationsButton('operationsNew','新規登録',domain+'.create')}</div><table><thead><tr><th>番号 / コード</th><th>名称</th><th>状態</th><th>住所 / 距離</th><th></th></tr></thead><tbody>${rows.map(r=>`<tr><td>${esc(r.number??r.source?.number??r.code??'')}</td><td>${esc(r.title??r.name)}</td><td>${esc(r.status??(r.active?'使用中':'休止'))}</td><td>${esc(r.address??r.source?.address??r.odometer??'')}</td><td><button class="btn" data-operations-open="${esc(r.incident_id??r.vehicle_id)}">開く</button></td></tr>`).join('')}</tbody></table><div class="toolbar"><button class="btn" id="operationsPrev">前へ</button><button class="btn" id="operationsNext">次へ</button></div>`;
  operationsBind('operationsSearch',()=>operationsList(type,0,$('operationsQ').value));$('operationsQ').onkeydown=e=>{if(e.key==='Enter')$('operationsSearch').click()};operationsBind('operationsNew',()=>type==='incidents'?operationsIncidentForm():operationsVehicleForm());
  document.querySelectorAll('[data-operations-open]').forEach(b=>b.onclick=()=>operationsAction(()=>type==='incidents'?operationsIncidentDetail(b.dataset.operationsOpen):operationsVehicleDetail(b.dataset.operationsOpen)));
  $('operationsPrev').disabled=offset===0;$('operationsNext').disabled=rows.length<50;operationsBind('operationsPrev',()=>operationsList(type,Math.max(0,offset-50),q));operationsBind('operationsNext',()=>operationsList(type,offset+50,q));
}catch(error){if(owned())throw error;}}
async function operationsIncidentForm(row=null){
  const linked=Boolean(row&&(row.emergency_case_id||row.fire_investigation_case_id||row.source_restricted));
  const fields=[['kind','種別','select',operationKinds],['title','事案名'],...(!linked?[['occurred_at','覚知日時','datetime-local'],['address','住所'],['number','番号']]:[]),['notes','記録','textarea']];
  operationsForm(row?'事案訂正':'事案登録',fields,row??{},async(values,isCurrent)=>{
    if(row)await api('/operations/incidents/'+row.incident_id,operationsJSON('PATCH',{expected_version:row.version,...values}));
    else{const source=$('operationsSourceType').value;const id=$('operationsSourceID').value;if(source&&id){delete values.address;delete values.number;delete values.occurred_at;values[source]=id;values.kind=source==='emergency_case_id'?'emergency_support':'fire'}else if(source)throw new Error('元事案を選択してください');row=await api('/operations/incidents',operationsJSON('POST',values))}
    if(isCurrent())await operationsAction(()=>operationsIncidentDetail(row.incident_id));
  },()=>row?operationsIncidentDetail(row.incident_id):operationsList('incidents'));
  if(!row){
    const panel=document.createElement('div');panel.innerHTML=`<p class="notice">元の救急・火災調査事案とリンクする場合、住所・日時・番号は元記録を参照します。</p><label class="field">元事案<select id="operationsSourceType"><option value="">リンクなし</option>${operationsCan('emergency.case.read')?'<option value="emergency_case_id">救急事案</option>':''}${operationsCan('fire_investigation.read')?'<option value="fire_investigation_case_id">火災調査</option>':''}</select></label><div class="toolbar"><label>元事案検索<input id="operationsSourceQuery"></label><button class="btn" type="button" id="operationsFindSource">候補検索</button></div><label class="field">選択<select id="operationsSourceID"><option value="">未選択</option></select></label>`;
    $('operationsForm').prepend(panel);operationsBind('operationsFindSource',operationsFindSource);$('operationsSourceType').onchange=()=>operationsAction(async()=>{const linked=Boolean($('operationsSourceType').value);for(const key of ['address','number','occurred_at'])$(`operationsField_${key}`).disabled=linked;await operationsFindSource()});
  }
}
async function operationsFindSource(){
  const type=$('operationsSourceType').value;if(!type){$('operationsSourceID').innerHTML='<option value="">未選択</option>';return}
  const rows=await api((type==='emergency_case_id'?'/emergency/cases':'/fire-investigations')+'?'+new URLSearchParams({q:$('operationsSourceQuery').value,limit:'200'}));
  $('operationsSourceID').innerHTML='<option value="">未選択</option>'+rows.map(r=>`<option value="${esc(r[type])}">${esc(r.dispatch_number??r.case_number??'番号未設定')} / ${esc(r.call_date??r.title??'')} / ${esc(r.incident_address??r.location_text??'')}</option>`).join('');
}
async function operationsIncidentDetail(id,isCurrent=()=>true){if(!isCurrent())return;const viewCurrent=operationsBeginView(),current=()=>isCurrent()&&viewCurrent();try{if(!current())return;
  const row=await api('/operations/incidents/'+id);if(!current())return;
  const dispatches=row.source_restricted?[]:await api('/operations/incidents/'+id+'/dispatches');if(!current())return;operationsState.incident=row;
  $('operationsContent').innerHTML=`<h2>${esc(row.title)}</h2><p>${esc(row.kind)} / ${esc(row.status)} / ${esc(row.source?.number??row.number??'')} / ${esc(row.source?.address??row.address??'')}</p><p>${esc(row.notes)}</p>${row.source?`<p class="notice">元事案ID ${esc(row.source.source_id)} v${row.source.version} / ${esc(row.source.occurred_at??row.source.call_date??'')} ${esc(row.source.call_time??'')}</p>`:''}${row.source_restricted?'<p class="notice">元記録の参照権限が必要です。</p>':''}<div class="toolbar">${operationsButton('operationsReload','再読込')}${row.status==='active'&&!row.source_restricted?operationsButton('operationsEdit','事案訂正','incident.update')+operationsButton('operationsDispatchNew','出動登録','incident.create')+operationsButton('operationsCancel','事案取消','incident.admin'):''}</div><h3>出動隊</h3><table><thead><tr><th>隊</th><th>出場</th><th>帰署</th><th>状態</th><th>正式手当</th><th></th></tr></thead><tbody>${dispatches.map(d=>`<tr><td>${esc(d.unit)}</td><td>${esc(d.departed_at)}</td><td>${esc(d.returned_at)}</td><td>${esc(d.status)}</td><td>${esc(d.official_amount??'')}</td><td><button class="btn" data-operations-dispatch="${esc(d.dispatch_id)}">開く</button></td></tr>`).join('')}</tbody></table>`;
  operationsBind('operationsReload',()=>operationsIncidentDetail(id));operationsBind('operationsEdit',()=>operationsIncidentForm(row));operationsBind('operationsDispatchNew',()=>operationsDispatchForm());operationsBind('operationsCancel',()=>operationsHumanAction('/incidents/'+id+'/cancel',row,()=>operationsIncidentDetail(id),'事案を取消'));
  document.querySelectorAll('[data-operations-dispatch]').forEach(b=>b.onclick=()=>operationsAction(()=>operationsDispatchDetail(b.dataset.operationsDispatch)));
}catch(error){if(current())throw error;}}
async function operationsVehicleForm(row=null){
  const fields=[...(!row?[['code','車両コード'],['odometer','初期距離 km','number']]:[]),['name','名称'],['registration','登録番号'],...(row?[['active','運用状態','select',[['true','使用中'],['false','休止']]]]:[]),['notes','記録','textarea']];
  operationsForm(row?'車両訂正':'車両登録',fields,row??{odometer:0},async(values,isCurrent)=>{const r=await api(row?'/operations/vehicles/'+row.vehicle_id:'/operations/vehicles',operationsJSON(row?'PATCH':'POST',row?{expected_version:row.version,...values}:values));if(isCurrent())await operationsAction(()=>operationsVehicleDetail(r.vehicle_id))},()=>row?operationsVehicleDetail(row.vehicle_id):operationsList('vehicles'));
}
async function operationsDispatchForm(row=null){
  const current=operationsBeginView();if(!current())return;
  const vehicles=operationsCan('fleet.read')?await api('/operations/vehicles?limit=200'):[];if(!current())return;
  const fields=[['unit','出動隊'],['vehicle_id','車両','select',operationsOptions(vehicles,'vehicle_id',v=>v.code+' / '+v.name)],['departed_at','出場','datetime-local'],['arrived_at','現着','datetime-local'],['returned_at','帰署','datetime-local'],['activity','活動','textarea'],['report','報告','textarea'],...(operationsCan('document.read')?[['document_id','共通原本ID（任意）']]:[])];
  operationsForm(row?'出動訂正':'出動登録',fields,row??{},async(values,isCurrent)=>{const r=await api(row?'/operations/dispatches/'+row.dispatch_id:'/operations/incidents/'+operationsState.incident.incident_id+'/dispatches',operationsJSON(row?'PATCH':'POST',{expected_version:row?.version??operationsState.incident.version,...values}));if(isCurrent())await operationsAction(()=>operationsDispatchDetail(r.dispatch_id))},()=>row?operationsDispatchDetail(row.dispatch_id):operationsIncidentDetail(operationsState.incident.incident_id));
}
async function operationsDispatchDetail(id,isCurrent=()=>true){if(!isCurrent())return;const viewCurrent=operationsBeginView(),current=()=>isCurrent()&&viewCurrent();try{if(!current())return;
  const d=await api('/operations/dispatches/'+id);if(!current())return;
  const crew=operationsCan('incident.crew.read')?await api('/operations/dispatches/'+id+'/crew'):[];if(!current())return;operationsState.dispatch=d;
  const editable=d.status==='draft';
  $('operationsContent').innerHTML=`<h2>${esc(d.unit)} / ${esc(d.status)}</h2><p>出場 ${esc(d.departed_at)} / 現着 ${esc(d.arrived_at)} / 帰署 ${esc(d.returned_at)}</p><p>車両ID ${esc(d.vehicle_id??'未指定')}</p><p>${esc(d.activity)}</p><p>${esc(d.report)}</p><p>手当候補 ${esc(d.candidate_amount??'未計算')} / 正式手当 ${esc(d.official_amount??'未承認')}</p>${d.calculation?`<details><summary>計算根拠</summary><pre>${esc(JSON.stringify(d.calculation,null,2))}</pre></details>`:''}<p>確認者 ${esc(d.reviewed_by??'')} / 承認者 ${esc(d.approved_by??'')} / ${esc(d.review_note??'')}</p><p>取消 ${esc(d.cancellation_note??'')}</p><div class="toolbar">${operationsButton('operationsReload','再読込')}${operationsButton('operationsParent','事案へ')}${editable?operationsButton('operationsEdit','出動訂正','incident.update')+operationsButton('operationsCrewNew','隊員登録','incident.crew.manage')+operationsButton('operationsCalculate','承認済み単価で候補計算','incident.update')+operationsButton('operationsReview','Human確認','incident.review'):''}${d.status==='reviewed'?operationsButton('operationsApprove','Human正式承認','incident.approve'):''}${d.status!=='cancelled'?operationsButton('operationsCancel','出動取消','incident.admin'):''}</div><h3>隊員</h3><table><thead><tr><th>共通職員ID</th><th>役割</th><th></th></tr></thead><tbody>${crew.map(c=>`<tr><td>${esc(c.employee_id)}</td><td>${esc(c.role)}</td><td>${editable&&operationsCan('incident.crew.manage')?`<button class="btn" data-operations-crew-remove="${esc(c.crew_id)}">解除</button>`:''}</td></tr>`).join('')}</tbody></table>`;
  operationsBind('operationsReload',()=>operationsDispatchDetail(id));operationsBind('operationsParent',()=>operationsIncidentDetail(d.incident_id));operationsBind('operationsEdit',()=>operationsDispatchForm(d));operationsBind('operationsCrewNew',()=>operationsCrewForm(d));operationsBind('operationsCalculate',()=>operationsCalculate(d));
  for(const [button,action,label] of [['operationsReview','/review','出動報告・手当候補を確認'],['operationsApprove','/approve','出動報告・手当を正式承認'],['operationsCancel','/cancel','出動を取消']])operationsBind(button,()=>operationsHumanAction('/dispatches/'+id+action,d,()=>operationsDispatchDetail(id),label));
  document.querySelectorAll('[data-operations-crew-remove]').forEach(b=>b.onclick=()=>operationsAction(()=>operationsHumanAction('/crew/'+b.dataset.operationsCrewRemove+'/remove',d,()=>operationsDispatchDetail(id),'隊員割当を解除')));
}catch(error){if(current())throw error;}}
async function operationsCrewForm(d){
  const current=operationsBeginView();if(!current())return;
  const employees=await api('/operations/employees');if(!current())return;const fields=[['employee_id','共通職員','select',operationsOptions(employees,'employee_id',e=>(e.employee_code??'')+' / '+e.display_name)],['role','役割']];
  operationsForm('隊員割当',fields,{},async(values,isCurrent)=>{await api('/operations/dispatches/'+d.dispatch_id+'/crew',operationsJSON('POST',{expected_version:d.version,...values}));if(isCurrent())await operationsAction(()=>operationsDispatchDetail(d.dispatch_id))},()=>operationsDispatchDetail(d.dispatch_id));
}
async function operationsCalculate(d){
  const current=operationsBeginView();if(!current())return;
  const rates=(await api('/operations/allowance-rates')).filter(r=>r.status==='approved');if(!current())return;const fields=[['rate_id','承認済み単価','select',operationsOptions(rates,'rate_id',r=>r.label+' / '+r.amount+' / '+r.basis+' / '+r.rounding)]];
  operationsForm('手当候補計算（正式決定はHuman承認）',fields,{},async(values,isCurrent)=>{await api('/operations/dispatches/'+d.dispatch_id+'/calculate',operationsJSON('POST',{expected_version:d.version,...values}));if(isCurrent())await operationsAction(()=>operationsDispatchDetail(d.dispatch_id))},()=>operationsDispatchDetail(d.dispatch_id));
}
async function operationsHumanAction(path,row,back,label,extra={}){
  operationsForm(label,[['note','確認・決定理由','textarea']],{},async(values,isCurrent)=>{if(!values.note)throw new Error('確認・決定理由を入力してください');await api('/operations'+path,operationsJSON('POST',{expected_version:row.version,...extra,...values}));if(isCurrent())await operationsAction(()=>back())},back);
}
async function operationsRates(){const current=operationsBeginView();if(!current())return;
  const rates=await api('/operations/allowance-rates');if(!current())return;$('operationsContent').innerHTML='<p class="notice">組織で承認された単価と根拠を登録してください。既定の法定・財務単価はありません。単価はHuman承認後に候補計算へ使用できます。承認済み単価は変更できません。</p>'+operationsButton('operationsRateNew','単価草案登録','incident.admin')+`<table><thead><tr><th>コード / 単価</th><th>計算単位</th><th>根拠</th><th>状態</th><th></th></tr></thead><tbody>${rates.map(r=>`<tr><td>${esc(r.code)} / ${esc(r.label)} / ${esc(r.amount)}</td><td>${esc(r.basis)} / ${esc(r.rounding)}</td><td>${esc(r.approval_reference)}</td><td>${esc(r.status)}</td><td>${r.status==='draft'&&operationsCan('incident.approve')?`<button class="btn" data-operations-rate="${esc(r.rate_id)}">Human承認</button>`:''}</td></tr>`).join('')}</tbody></table>`;
  operationsBind('operationsRateNew',()=>{const fields=[['code','単価コード'],['label','名称'],['amount','金額','number'],['basis','計算単位','select',[['per_dispatch','1出動'],['per_crew','隊員数'],['per_hour','出場から帰署の時間']]],['rounding','組織が承認した端数処理','select',[['','選択してください'],['half_up','小数2桁に四捨五入'],['half_even','小数2桁に偶数丸め'],['down','小数2桁で切捨て']]],['approval_reference','組織が承認した根拠','textarea']];operationsForm('単価草案',fields,{},async(values,isCurrent)=>{await api('/operations/allowance-rates',operationsJSON('POST',values));if(isCurrent())await operationsAction(()=>operationsRates())},operationsRates)});
  document.querySelectorAll('[data-operations-rate]').forEach(b=>b.onclick=()=>operationsAction(()=>operationsHumanAction('/allowance-rates/'+b.dataset.operationsRate+'/approve',rates.find(r=>r.rate_id===b.dataset.operationsRate),operationsRates,'単価をHuman承認')));
}
async function operationsVehicleDetail(id,isCurrent=()=>true,assignmentOffset=0,saved=false){
  if(!isCurrent())return;
  const owner=operationsVehicleOwner(isCurrent);if(!owner.current())return;
  owner.content.innerHTML='<p role="status">'+(saved?'配属は保存済みです。最新記録を読み込み中…':'車両・配属を読み込み中…')+'</p>';
  try{
  const v=await api('/operations/vehicles/'+id);if(!owner.current())return;
  const h=await api('/operations/vehicles/'+id+'/history');if(!owner.current())return;
  const assignments=await api('/operations/vehicles/'+id+'/assignments?'+new URLSearchParams({limit:'50',offset:String(assignmentOffset)}));if(!owner.current())return;operationsState.vehicle=v;
  $('operationsContent').innerHTML=`<h2>${esc(v.code)} / ${esc(v.name)}</h2><p>${v.active?'使用中':'休止'} / 距離 ${esc(v.odometer)} km / 車両割当燃料在庫 ${esc(v.fuel_stock)} L</p><p>次回車検・点検 ${esc(v.next_inspection_on??'未設定')} / 次回整備 ${esc(v.next_service_on??'未設定')} / 次回整備距離 ${esc(v.next_service_odometer??'未設定')}</p><p>${esc(v.notes)}</p><div class="toolbar">${operationsButton('operationsReload','再読込')}${operationsButton('operationsEdit','車両訂正','fleet.update')}${v.active?operationsButton('operationsTripNew','運行登録','fleet.create')+operationsButton('operationsFuelNew','燃料登録','fleet.create')+operationsButton('operationsServiceNew','点検・車検・修理・故障','fleet.create'):''}</div>${operationsAssignmentPanel(assignments)}<h3>運行履歴</h3>${operationsHistoryTable(h.trips,['started_at','ended_at','start_odometer','end_odometer','purpose','dispatch_id','driver_employee_id'])}<h3>燃料履歴</h3>${operationsHistoryTable(h.fuel,['occurred_at','kind','liters','amount','notes'])}<h3>点検・整備履歴</h3><table><thead><tr><th>日付</th><th>種別 / 内容</th><th>費用</th><th>状態</th><th>期限候補</th><th></th></tr></thead><tbody>${h.services.map(s=>`<tr><td>${esc(s.performed_on)}</td><td>${esc(s.kind)} / ${esc(s.description)}${s.resolved_by_service_id?' / 解消済み':''}</td><td>${esc(s.cost)}</td><td>${esc(s.status)}</td><td>${esc(s.next_inspection_on??'')} / ${esc(s.next_service_on??'')} / ${esc(s.next_service_odometer??'')}</td><td>${s.status==='draft'&&operationsCan('fleet.review')?`<button class="btn" data-operations-service="${s.service_id}" data-action="review">Human確認</button>`:''}${s.status==='reviewed'&&operationsCan('fleet.approve')?`<button class="btn" data-operations-service="${s.service_id}" data-action="approve">Human承認・期限反映</button>`:''}${['draft','reviewed'].includes(s.status)&&operationsCan('fleet.admin')?`<button class="btn" data-operations-service="${s.service_id}" data-action="cancel">取消</button>`:''}</td></tr>`).join('')}</tbody></table><p class="notice">運行・燃料は追記履歴です。承認済み整備は編集できません。未承認の期限は車両へ反映されません。</p>`;
  operationsBind('operationsAssignmentEdit',()=>owner.current()?operationsAssignmentEditor(v,assignments):undefined);
  operationsBind('operationsAssignmentPrev',()=>operationsVehicleDetail(id,()=>true,Math.max(0,assignmentOffset-50)));
  operationsBind('operationsAssignmentNext',()=>operationsVehicleDetail(id,()=>true,assignmentOffset+50));
  operationsBind('operationsReload',()=>operationsVehicleDetail(id));operationsBind('operationsEdit',()=>operationsVehicleForm(v));operationsBind('operationsTripNew',()=>operationsTripForm(v));operationsBind('operationsFuelNew',()=>operationsFuelForm(v));operationsBind('operationsServiceNew',()=>operationsServiceForm(v));
  document.querySelectorAll('[data-operations-service]').forEach(b=>b.onclick=()=>operationsAction(()=>operationsHumanAction('/services/'+b.dataset.operationsService+'/'+b.dataset.action,h.services.find(s=>s.service_id===b.dataset.operationsService),()=>operationsVehicleDetail(id),b.dataset.action==='approve'?'点検・整備と期限を正式承認':'点検・整備の確認 / 取消',b.dataset.action==='approve'?{expected_vehicle_version:v.version,...(h.services.find(s=>s.service_id===b.dataset.operationsService).resolves_fault_id?{expected_fault_version:h.services.find(s=>s.service_id===h.services.find(r=>r.service_id===b.dataset.operationsService).resolves_fault_id)?.version}:{})}:{})));
}catch(error){
  if(!owner.current())return;
  const message=operationsAssignmentError(error);if(!message)return;
  owner.content.innerHTML=`<p role="alert">${saved?'配属は保存済みです。再送信せずに表示のみ再試行してください。':'車両・配属を取得できません。'} ${esc(message)}</p><button type="button" class="btn" id="operationsAssignmentRetry">表示を再試行</button>`;
  $('operationsAssignmentRetry').onclick=()=>operationsVehicleDetail(id,()=>true,assignmentOffset,saved);
}}
function operationsHistoryTable(rows,keys){return `<div style="overflow:auto"><table><thead><tr>${keys.map(k=>`<th>${esc(k)}</th>`).join('')}</tr></thead><tbody>${rows.map(r=>`<tr>${keys.map(k=>`<td>${esc(r[k]??'')}</td>`).join('')}</tr>`).join('')}</tbody></table></div>`}
async function operationsTripForm(v){
  const current=operationsBeginView();if(!current())return;
  let dispatches=[];
  if(operationsCan('incident.read')){const incidents=await api('/operations/incidents?limit=200');for(const i of incidents.filter(i=>!i.source_restricted&&i.status==='active')){const ds=await api('/operations/incidents/'+i.incident_id+'/dispatches');dispatches.push(...ds.filter(d=>d.vehicle_id===v.vehicle_id&&d.status!=='cancelled').map(d=>({...d,label:i.title+' / '+d.unit})))}}
  const employees=operationsCan('incident.crew.read')?await api('/operations/employees'):[];if(!current())return;
  const fields=[['started_at','出発','datetime-local'],['ended_at','終了','datetime-local'],['start_odometer','開始距離 km','number'],['end_odometer','終了距離 km','number'],['purpose','用途','textarea'],...(operationsCan('incident.read')?[['dispatch_id','関連出動','select',operationsOptions(dispatches,'dispatch_id',d=>d.label)]]:[]),...(operationsCan('incident.crew.read')?[['driver_employee_id','運転者','select',operationsOptions(employees,'employee_id',e=>e.display_name)]]:[]),...(operationsCan('document.read')?[['document_id','原本ID（任意）']]:[])];
  operationsForm('運行登録',fields,{start_odometer:v.odometer},async(values,isCurrent)=>{await api('/operations/vehicles/'+v.vehicle_id+'/trips',operationsJSON('POST',{expected_version:v.version,...values}));if(isCurrent())await operationsAction(()=>operationsVehicleDetail(v.vehicle_id))},()=>operationsVehicleDetail(v.vehicle_id));
}
async function operationsFuelForm(v){
  const fields=[['kind','区分','select',[['receipt','車両割当在庫の受入'],['issue','割当在庫から払出'],['refuel','外部給油（割当在庫増減なし）']]],['liters','量 L','number'],['amount','購入費 / 払出評価額（払出は参考値）','number'],['occurred_at','日時','datetime-local'],['notes','記録','textarea'],...(operationsCan('document.read')?[['document_id','伝票原本ID（任意）']]:[])];
  operationsForm('燃料登録',fields,{amount:0},async(values,isCurrent)=>{await api('/operations/vehicles/'+v.vehicle_id+'/fuel',operationsJSON('POST',{expected_version:v.version,...values}));if(isCurrent())await operationsAction(()=>operationsVehicleDetail(v.vehicle_id))},()=>operationsVehicleDetail(v.vehicle_id));
}
async function operationsServiceForm(v){
  const current=operationsBeginView();if(!current())return;
  const faults=(await api('/operations/vehicles/'+v.vehicle_id+'/history')).services.filter(s=>s.kind==='fault'&&s.status!=='cancelled'&&!s.resolved_by_service_id);if(!current())return;
  const fields=[['kind','区分','select',[['inspection','点検'],['vehicle_inspection','車検'],['repair','修理'],['fault','故障'],['service','整備']]],['resolves_fault_id','修理で解消する故障（該当する場合）','select',operationsOptions(faults,'service_id',s=>s.performed_on+' / '+s.description)],['performed_on','実施日','date'],['description','内容','textarea'],['cost','費用','number'],['next_inspection_on','次回点検・車検日','date'],['next_service_on','次回整備日','date'],['next_service_odometer','次回整備距離 km','number'],...(operationsCan('document.read')?[['document_id','原本ID（任意）']]:[])];
  operationsForm('点検・整備草案',fields,{cost:0},async(values,isCurrent)=>{await api('/operations/vehicles/'+v.vehicle_id+'/services',operationsJSON('POST',{expected_version:v.version,...values}));if(isCurrent())await operationsAction(()=>operationsVehicleDetail(v.vehicle_id))},()=>operationsVehicleDetail(v.vehicle_id));
}
async function operationsAlerts(){const current=operationsBeginView();if(!current())return;const rows=await api('/operations/alerts');if(!current())return;$('operationsContent').innerHTML='<h2>30日以内の期限・走行距離超過・未解消故障</h2>'+operationsHistoryTable(rows,['code','kind','due_on','days_remaining','due_odometer','description']);}
async function operationsSummary(){operationsInvalidateVehicleView();
  $('operationsContent').innerHTML='<h2>月次・年次集計</h2><div class="toolbar"><label>年<input id="operationsYear" type="number" min="1900" max="9998"></label><label>月（空欄は年次）<input id="operationsMonth" type="number" min="1" max="12"></label><button class="btn" id="operationsAggregate">集計</button></div><div id="operationsStats"></div>';
  $('operationsYear').value=new Date().getFullYear();operationsBind('operationsAggregate',async()=>{const q=new URLSearchParams({year:$('operationsYear').value});if($('operationsMonth').value)q.set('month',$('operationsMonth').value);let html='';for(const [permission,path,label] of [['incident.aggregate','statistics','事案・出動'],['fleet.aggregate','fleet-statistics','車両運用']]){if(!operationsCan(permission))continue;const r=await api('/operations/'+path+'?'+q);html+=`<h3>${label}</h3>${path==='fleet-statistics'?`<p>燃料購入費（受入・外部給油） ${esc(r.fuel_purchase_expense)} / 払出評価額（参考、購入費に含めません） ${esc(r.fuel_issue_valuation)}</p>`:''}<pre>${esc(JSON.stringify(r,null,2))}</pre>`}$('operationsStats').innerHTML=html||'<p>集計権限が必要です。</p>'});
}
async function operationsDownload(url){const r=await fetch(url);if(!r.ok){let body={};try{body=await r.json()}catch{}throw new Error(body.detail??'出力できません')}const blob=await r.blob();const objectURL=URL.createObjectURL(blob);const link=document.createElement('a');link.href=objectURL;link.download=r.headers.get('Content-Disposition')?.match(/filename="([^"]+)"/)?.[1]??'operations-export.csv';document.body.append(link);link.click();link.remove();URL.revokeObjectURL(objectURL)}
async function operationsExchange(){operationsInvalidateVehicleView();
  const datasets=[['incidents','事案','incident'],['dispatches','出動','incident'],['vehicles','車両','fleet'],['trips','運行','fleet'],['fuel','燃料','fleet'],['services','点検・整備','fleet'],...(operationsCan('incident.crew.read')&&operationsCan('incident.crew.manage')?[['crew','隊員','incident']]:[])];
  const imports=datasets.filter(([, ,domain])=>operationsCan(domain+'.import')&&operationsCan(domain+'.create')&&operationsCan(domain+'.read'));
  const exports=[...datasets.map(([key,label,domain])=>[key,label,domain]),['summary','事案月次・年次','incident'],['fleet-summary','車両月次・年次','fleet'],...(operationsCan('incident.crew.read')?[['crew','隊員詳細','incident']]:[])].filter(([key,,domain])=>operationsCan(domain+'.export')&&operationsCan(domain+(['summary','fleet-summary'].includes(key)?'.aggregate':'.read')));
  $('operationsContent').innerHTML=`<h2>CSV・XLSX取込 / 出力</h2><p class="notice">取込はプレビュー後に明示的に確定します。確認済み・正式承認状態を取り込むことはできません。テンプレートの列名を使用し、関連ID・expected_versionを指定してください。</p><div class="toolbar"><label>取込対象<select id="operationsImportDataset">${imports.map(([k,l])=>`<option value="${k}">${l}</option>`).join('')}</select></label><button class="btn" id="operationsImportTemplate">CSVテンプレート</button><label>ファイル<input id="operationsImportFile" type="file" accept=".csv,.xlsx"></label><button class="btn" id="operationsImportPreview">プレビュー</button></div><div id="operationsPreview"></div><hr><div class="toolbar"><label>出力対象<select id="operationsExportDataset">${exports.map(([k,l])=>`<option value="${k}">${l}</option>`).join('')}</select></label><label>形式<select id="operationsExportFormat"><option value="csv">CSV</option><option value="xlsx">XLSX</option></select></label><label>集計年<input id="operationsExportYear" type="number" value="${new Date().getFullYear()}"></label><label>集計月<input id="operationsExportMonth" type="number" min="1" max="12"></label><button class="btn" id="operationsExport">出力</button></div>`;
  $('operationsImportPreview').disabled=!imports.length;$('operationsImportTemplate').disabled=!imports.length;$('operationsExport').disabled=!exports.length;
  operationsBind('operationsImportTemplate',()=>operationsDownload('/operations/import-template/'+$('operationsImportDataset').value));
  operationsBind('operationsImportPreview',async()=>{const file=$('operationsImportFile').files[0];if(!file)throw new Error('ファイルを選択してください');const body=new FormData();body.append('file',file);const p=await api('/operations/import/'+$('operationsImportDataset').value,{method:'POST',body});$('operationsPreview').innerHTML=`<p>${p.rows}行 / ファイルSHA256 ${esc(p.file_sha256)} / 有効期限 ${esc(p.expires_at)}</p><pre>${esc(JSON.stringify(p.sample,null,2))}</pre><button class="btn primary" id="operationsImportConfirm">確認して全行を取り込む</button>`;operationsBind('operationsImportConfirm',async()=>{const r=await api('/operations/import-previews/'+p.preview_id+'/confirm',operationsJSON('POST',{expected_version:p.version,file_sha256:p.file_sha256}));$('operationsPreview').textContent=`取込完了 ${r.inserted}行 / 元ファイルSHA256 ${r.file_sha256}`})});
  operationsBind('operationsExport',()=>{const q=new URLSearchParams({format:$('operationsExportFormat').value,year:$('operationsExportYear').value});if($('operationsExportMonth').value)q.set('month',$('operationsExportMonth').value);return operationsDownload('/operations/export/'+$('operationsExportDataset').value+'?'+q)});
}

function operationsBeginView(){
  operationsInvalidateVehicleView();
  const ticket=operationsState.viewGeneration,modal=$('operationsModal'),content=$('operationsContent');
  const current=()=>ticket===operationsState.viewGeneration&&$('operationsModal')===modal&&Boolean(modal?.isConnected)&&!modal.classList.contains('hidden')&&Boolean(content?.isConnected)&&$('operationsContent')===content;
  if(current())content.innerHTML='<p id="operationsViewLoading" role="status">読み込み中…</p>';
  return current;
}

// A vehicle detail/edit owns its exact modal and generation. SharedSession still
// owns authority checks; these tickets only prevent old UI responses taking over.
function operationsInvalidateVehicleView(){
  operationsState.viewGeneration++;
  const owner=operationsState.vehicleView;
  if(owner?.interrupt)window.removeEventListener('click',owner.interrupt,true);
  operationsState.vehicleView=null;operationsState.assignment=null;
}
function operationsVehicleOwner(isCurrent=()=>true){
  operationsInvalidateVehicleView();
  const modal=$('operationsModal'),content=$('operationsContent');
  const owner={modal,content,interrupted:false,pendingTarget:null};
  owner.current=()=>operationsState.vehicleView===owner&&!owner.interrupted&&isCurrent()&&$('operationsModal')===modal&&Boolean(modal?.isConnected)&&!modal.classList.contains('hidden')&&Boolean(content?.isConnected)&&$('operationsContent')===content;
  owner.interrupt=event=>{
    const target=event.target?.closest?.('button, a');
    if(!target||target.disabled||target===owner.pendingTarget)return;
    if(!['operationsClose','operationsIncidents','operationsVehicles','operationsSummary','operationsAlerts','operationsRates','operationsExchange','operationsReload','operationsEdit','operationsTripNew','operationsFuelNew','operationsServiceNew','operationsAssignmentBack'].includes(target.id))return;
    owner.pendingTarget=target;owner.interrupted=true;
    if($('operationsAssignmentSave'))$('operationsAssignmentSave').disabled=true;
    if($('operationsAssignmentMessage'))$('operationsAssignmentMessage').textContent='画面を切り替えています…';
  };
  operationsState.vehicleView=owner;window.addEventListener('click',owner.interrupt,true);
  return owner;
}
function operationsAssignmentError(error){
  if(error.cancelled)return '';
  if(error.status===401||error.status===403){clearOperations();return '';}
  const detail=Array.isArray(error.body?.detail)?error.body.detail.map(d=>d.msg).join(' / '):error.message;
  return (error.status===409?'更新競合、または変更内容が同一です。最新記録を再読込し、内容を確認してください。 ':'')+String(detail);
}
function operationsOrganizationLabel(org){return org?`${org.code} / ${org.name}`:'未配属';}
function operationsAssignmentCurrent(current){
  if(!current)return '未記録（現在の配属は不明）';
  if(current.state==='unassigned')return '未配属（Human確認済み）';
  const recorded=operationsOrganizationLabel(current.recorded_organization),live=current.organization;
  return recorded+(live?(live.name!==current.recorded_organization?.name||live.code!==current.recorded_organization?.code?` / 現在の組織名: ${operationsOrganizationLabel(live)}`:'')+(live.active?'':' / 現在は無効な組織'):' / 現在の組織情報は利用できません');
}
function operationsAssignmentPanel(data){
  const history=data.items.map(change=>`<tr><td>${esc(change.changed_at)}<br>記録者 ${esc(change.changed_by)}</td><td>${esc(change.before_organization?operationsOrganizationLabel(change.before_organization):'配属記録なし（未記録または未配属）')} → ${esc(operationsOrganizationLabel(change.after_organization))}</td><td>${esc(change.reason)}</td><td>${esc(change.source_evidence)}</td><td>v${esc(change.vehicle_version_before)} → v${esc(change.vehicle_version_after)}<br>${change.human_confirmation?.acknowledged?'Human確認済み':''}<br>${esc(change.human_confirmation?.user_id)} / ${esc(change.human_confirmation?.at)}</td></tr>`).join('');
  return `<section id="operationsAssignmentPanel"><h3>現在の配属</h3><p id="operationsAssignmentCurrent">${esc(operationsAssignmentCurrent(data.current))}</p><p>車両 Version ${esc(data.vehicle_version)} / 車両の休止と配属は別に記録します。</p><div class="toolbar">${operationsCan('fleet.read')&&operationsCan('fleet.update')?operationsButton('operationsAssignmentEdit','配属を記録・訂正'):''}</div><h3>配属履歴</h3><p class="notice">組織名は記録時点の名称です。Human記録の参照情報は原本検証済みの証拠ではありません。Human確認は管理職の承認ではありません。</p>${data.items.length?`<div style="overflow:auto"><table><thead><tr><th>記録日時 / 記録者</th><th>変更前 → 変更後</th><th>理由</th><th>Human記録の参照情報</th><th>版 / 確認</th></tr></thead><tbody>${history}</tbody></table></div>`:data.total?'<p>このページの履歴はありません。</p>':'<p>配属履歴はまだありません。</p>'}<p>${esc(data.total)}件 / ${data.items.length?esc(data.offset+1)+'件目から表示':'このページの表示なし'}</p><div class="toolbar"><button type="button" class="btn" id="operationsAssignmentPrev"${data.offset===0?' disabled':''}>前の履歴</button><button type="button" class="btn" id="operationsAssignmentNext"${data.offset+data.items.length>=data.total?' disabled':''}>次の履歴</button></div></section>`;
}
async function operationsAssignmentEditor(vehicle,data,draft=null){
  if(!operationsCan('fleet.read')||!operationsCan('fleet.update'))return;
  const owner=operationsVehicleOwner(),edit={owner,vehicle,data,busy:false,accepted:false,lookup:0,organizations:[],selected:draft?.selected??null};
  if(!owner.current())return;operationsState.assignment=edit;
  owner.content.innerHTML=`<h2>${esc(vehicle.code)} / ${esc(vehicle.name)} の配属を記録</h2><form id="operationsAssignmentForm"><p>変更前: ${esc(operationsAssignmentCurrent(data.current))}</p><label class="field">変更内容<select id="operationsAssignmentAction"><option value="assign">配属・転属・配属記録の訂正</option><option value="unassign">未配属をHuman確認</option></select></label><div id="operationsAssignmentPicker"><div class="toolbar"><label>組織名・コードで検索<input id="operationsAssignmentQuery"></label><button type="button" class="btn" id="operationsAssignmentSearch">組織を検索</button></div><label class="field">配属先組織<select id="operationsAssignmentOrganization"><option value="">選択してください</option></select></label><p id="operationsAssignmentLookup" role="status"></p><div class="toolbar"><button type="button" class="btn" id="operationsAssignmentOrgPrev">前の候補</button><button type="button" class="btn" id="operationsAssignmentOrgNext">次の候補</button></div></div><p>変更後: <strong id="operationsAssignmentAfter"></strong></p><label class="field">変更・確認の理由（必須）<textarea id="operationsAssignmentReason" maxlength="4000" required></textarea></label><label class="field">Human記録の参照情報（必須）<textarea id="operationsAssignmentSource" maxlength="4000" required placeholder="例: 配置通知の件名・番号と確認した箇所"></textarea></label><p class="notice">参照情報はHumanが記録する説明です。原本検証済みの証拠や原本へのリンクではありません。日時・記録者・版は自動記録されます。</p><label><input type="checkbox" id="operationsAssignmentAcknowledged" required> 変更前・変更後、理由、参照情報をHumanとして確認しました（管理職承認ではありません）</label><p id="operationsAssignmentMessage" class="dangerText" role="alert"></p><div class="toolbar"><button type="submit" class="btn primary" id="operationsAssignmentSave">確認した配属を保存</button><button type="button" class="btn" id="operationsAssignmentReload">最新記録を再読込</button><button type="button" class="btn" id="operationsAssignmentBack">下書きを破棄して車両へ戻る</button></div></form>`;
  const form=$('operationsAssignmentForm');edit.form=form;
  $('operationsAssignmentAction').value=draft?.action??'assign';
  $('operationsAssignmentReason').value=draft?.reason??'';$('operationsAssignmentSource').value=draft?.source??'';
  $('operationsAssignmentAcknowledged').checked=false;
  const update=()=>{
    const unassigned=$('operationsAssignmentAction').value==='unassign';
    $('operationsAssignmentPicker').classList.toggle('hidden',unassigned);
    $('operationsAssignmentAfter').textContent=unassigned?'未配属（Human確認済み）':edit.selected?operationsOrganizationLabel(edit.selected):'組織を選択してください';
    $('operationsAssignmentAcknowledged').checked=false;
  };
  $('operationsAssignmentAction').onchange=update;
  $('operationsAssignmentOrganization').onchange=()=>{edit.selected=edit.organizations.find(row=>row.organization_id===$('operationsAssignmentOrganization').value)??null;update();};
  $('operationsAssignmentReason').oninput=$('operationsAssignmentSource').oninput=()=>{$('operationsAssignmentAcknowledged').checked=false;};
  $('operationsAssignmentSearch').onclick=()=>operationsAssignmentLookup(edit,0,$('operationsAssignmentQuery').value);
  $('operationsAssignmentQuery').onkeydown=e=>{if(e.key==='Enter'){e.preventDefault();$('operationsAssignmentSearch').click();}};
  $('operationsAssignmentBack').onclick=()=>operationsVehicleDetail(vehicle.vehicle_id);
  $('operationsAssignmentReload').onclick=()=>operationsAssignmentReload(edit);
  form.onsubmit=e=>{e.preventDefault();return operationsAssignmentSave(edit);};
  update();await operationsAssignmentLookup(edit,0,'');
}
function operationsAssignmentEditable(edit){return edit.owner.current()&&operationsState.assignment===edit&&$('operationsAssignmentForm')===edit.form&&edit.form.isConnected&&operationsCan('fleet.update')&&!edit.busy&&!edit.accepted;}
function operationsAssignmentBusy(edit){
  edit.busy=true;edit.disabled=Array.from(edit.form.querySelectorAll('button, input, select, textarea'),node=>[node,node.disabled]);
  for(const [node] of edit.disabled)if(node.id!=='operationsAssignmentBack')node.disabled=true;
}
function operationsAssignmentRestore(edit){edit.busy=false;for(const [node,disabled] of edit.disabled??[])node.disabled=disabled;}
function operationsAssignmentDraft(edit){return {action:$('operationsAssignmentAction').value,selected:edit.selected,reason:$('operationsAssignmentReason').value,source:$('operationsAssignmentSource').value};}
async function operationsAssignmentLookup(edit,offset,q){
  if(!operationsAssignmentEditable(edit))return;
  const ticket=++edit.lookup;edit.organizations=[];edit.lookupBusy=true;$('operationsAssignmentSave').disabled=true;$('operationsAssignmentReload').disabled=true;
  const select=$('operationsAssignmentOrganization');select.disabled=true;select.innerHTML='<option value="">候補を読み込み中…</option>';
  $('operationsAssignmentOrgPrev').disabled=true;$('operationsAssignmentOrgNext').disabled=true;
  $('operationsAssignmentLookup').textContent='組織候補を読み込み中…';
  const current=()=>edit.owner.current()&&operationsState.assignment===edit&&ticket===edit.lookup&&!edit.busy;
  try{
    const data=await api('/operations/fleet-organizations?'+new URLSearchParams({q,offset:String(offset),limit:'100'}));if(!current())return;
    edit.organizations=data.items;
    // Preserve a named selection across search pages, but never silently update
    // its optimistic-lock version: a refreshed target must be chosen again.
    let selected=edit.selected;
    const refreshed=selected&&data.items.find(row=>row.organization_id===selected.organization_id);
    if(selected&&((refreshed&&(refreshed.version!==selected.version||refreshed.name!==selected.name||refreshed.code!==selected.code))||(!refreshed&&!q&&offset===0&&data.total<=data.items.length))){
      edit.selected=null;selected=null;$('operationsAssignmentAcknowledged').checked=false;
      if($('operationsAssignmentAction').value==='assign')$('operationsAssignmentAfter').textContent='組織を選択してください';
      $('operationsAssignmentMessage').textContent='選択した組織の情報・利用状態が変わりました。配属先を選び直してください。';
    }
    select.innerHTML='<option value="">選択してください</option>'+(selected&&!data.items.some(row=>row.organization_id===selected.organization_id)?`<option value="${esc(selected.organization_id)}">${esc(operationsOrganizationLabel(selected))}（選択保持）</option>`:'')+data.items.map(row=>`<option value="${esc(row.organization_id)}">${esc(operationsOrganizationLabel(row))}</option>`).join('');
    select.value=selected?.organization_id??'';select.disabled=false;
    $('operationsAssignmentLookup').textContent=`有効な組織 ${data.total}件 / このページ ${data.items.length}件`;
    $('operationsAssignmentOrgPrev').disabled=offset===0;$('operationsAssignmentOrgNext').disabled=offset+data.items.length>=data.total;
    $('operationsAssignmentOrgPrev').onclick=()=>operationsAssignmentLookup(edit,Math.max(0,offset-100),q);
    $('operationsAssignmentOrgNext').onclick=()=>operationsAssignmentLookup(edit,offset+100,q);
  }catch(error){if(current()){const message=operationsAssignmentError(error);if(message)$('operationsAssignmentLookup').textContent='組織を取得できません。検索で再試行してください。 '+message;}}finally{if(current()){edit.lookupBusy=false;$('operationsAssignmentSave').disabled=false;$('operationsAssignmentReload').disabled=false;}}
}
async function operationsAssignmentReload(edit){
  if(!operationsAssignmentEditable(edit)||edit.lookupBusy)return;
  const draft=operationsAssignmentDraft(edit),owner=edit.owner;
  operationsAssignmentBusy(edit);
  $('operationsAssignmentMessage').textContent='最新の車両・配属を読み込み中…';
  try{
    const vehicle=await api('/operations/vehicles/'+edit.vehicle.vehicle_id);if(!owner.current())return;
    const data=await api('/operations/vehicles/'+edit.vehicle.vehicle_id+'/assignments?limit=50&offset=0');if(!owner.current())return;
    operationsState.vehicle=vehicle;
    await operationsAssignmentEditor(vehicle,data,draft);
  }catch(error){if(owner.current()){const message=operationsAssignmentError(error);if(message){operationsAssignmentRestore(edit);$('operationsAssignmentMessage').textContent='再読込できません。下書きを保持しています。 '+message;}}}
}
async function operationsAssignmentSave(edit){
  if(!operationsAssignmentEditable(edit)||edit.lookupBusy)return;
  const draft=operationsAssignmentDraft(edit),message=$('operationsAssignmentMessage');
  if(!draft.reason.trim()){message.textContent='理由を入力してください。';return;}
  if(!draft.source.trim()){message.textContent='Human記録の参照情報を入力してください。';return;}
  if(draft.action==='assign'&&!draft.selected){message.textContent='配属先の組織を選択してください。';return;}
  if(!$('operationsAssignmentAcknowledged').checked){message.textContent='変更内容をHumanとして確認してください。';return;}
  // Set before SharedSession/check or any other asynchronous boundary.
  operationsAssignmentBusy(edit);edit.lookup++;message.textContent='保存中です。送信済みの変更は「戻る」では取り消されません。';
  const payload={expected_version:edit.data.vehicle_version,action:draft.action,...(draft.action==='assign'?{organization_id:draft.selected.organization_id,expected_organization_version:draft.selected.version}:{}),reason:draft.reason.trim(),source_evidence:draft.source.trim(),human_acknowledged:true};
  try{
    await api('/operations/vehicles/'+edit.vehicle.vehicle_id+'/assignments',operationsJSON('POST',payload));
    edit.accepted=true;if(!edit.owner.current())return;
    await operationsVehicleDetail(edit.vehicle.vehicle_id,()=>true,0,true);
  }catch(error){
    if(!edit.owner.current())return;
    const text=operationsAssignmentError(error);if(!text)return;
    operationsAssignmentRestore(edit);
    message.textContent=text;
  }
}
