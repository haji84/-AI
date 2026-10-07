'use strict';
// Source-backed register. Quantities stay decimal strings; Human evidence confirmation
// records an observation of originals, never a permit issue or compliance decision.
const hazardousState = {permissions: [], generation: 0, viewGeneration: 0};
const hazardousCan = permission => hazardousState.permissions.includes(permission);
const hazardousCancelled = () => Object.assign(new Error('画面・セッション・権限が変更されました。'), {cancelled: true});
const hazardousJSON = (method, data) => ({method, headers: {'Content-Type': 'application/json'}, body: JSON.stringify(data)});
const hazardousLabels = {active:'使用中', retired:'廃止', draft:'草案・未確認', confirmed:'Human証拠確認済', cancelled:'取消', superseded:'改訂前の履歴', permit:'許可の記録', notification:'届出の記録', change:'変更の記録'};
const hazardousSourceRights = {facilities:'facility.read', documents:'document.read', legal:'legal_source.read', inspections:'inspection.read', violations:'violation.read'};
const hazardousSourceAvailable = kind => hazardousCan(hazardousSourceRights[kind]) && (kind !== 'legal' || hazardousCan('document.read'));
const hazardousPath = id => '/hazardous/installations/' + encodeURIComponent(id);
const hazardousTicket = () => ({generation:hazardousState.generation, view:hazardousState.viewGeneration});
const hazardousOwns = ticket => ticket.generation === hazardousState.generation && ticket.view === hazardousState.viewGeneration;
function hazardousAssert(ticket) { if (!hazardousOwns(ticket)) throw hazardousCancelled(); }
function hazardousBegin(retry=null) {
  hazardousState.viewGeneration++;
  if ($('hazardousMessage')) $('hazardousMessage').textContent = '';
  const ticket = {...hazardousTicket(),retry};
  if ($('hazardousModal')) {
    hazardousShell(ticket);
    $('hazardousContent').innerHTML='<p id="hazardousLoading" role="status" aria-live="polite">読込中…</p>';
  }
  return ticket;
}
function closeHazardous() {
  hazardousState.viewGeneration++;
  $('hazardousModal')?.remove();
}
function clearHazardous() {
  hazardousState.generation++;
  hazardousState.permissions = [];
  closeHazardous();
  $('hazardousBtn')?.classList.add('hidden');
}
async function hazardousAuthority(ticket, permission='hazardous.read') {
  hazardousAssert(ticket);
  await window.FireAISession.check();
  hazardousAssert(ticket);
  const result = await api('/auth/permissions');
  hazardousAssert(ticket);
  const permissions = result.permissions ?? [];
  if (hazardousState.permissions.some(p => !permissions.includes(p))) {
    clearHazardous(); throw hazardousCancelled();
  }
  hazardousState.permissions = permissions;
  $('hazardousBtn')?.classList.toggle('hidden', !(hazardousCan('hazardous.read') && hazardousCan('facility.read')));
  if (!hazardousCan('hazardous.read') || !hazardousCan('facility.read') || !hazardousCan(permission)) {
    throw Object.assign(new Error('この操作の権限がありません。'), {status:403});
  }
}
async function hazardousAPI(path, options={}, ticket=hazardousTicket(), permission='hazardous.read') {
  try {
    await hazardousAuthority(ticket, permission);
    const result = await api(path, options);
    hazardousAssert(ticket);
    await hazardousAuthority(ticket, permission);
    hazardousAssert(ticket);
    return result;
  } catch (error) {
    if (!hazardousOwns(ticket)) throw hazardousCancelled();
    if (error.status === 401 || error.status === 403) clearHazardous();
    if ((!options.method || options.method==='GET') && typeof ticket.retry==='function') error.hazardousRetry=ticket.retry;
    throw error;
  }
}
async function initHazardous() {
  const ticket = hazardousTicket();
  try { await hazardousAuthority(ticket); }
  catch (error) {
    if (error.cancelled) return;
    if (hazardousOwns(ticket)) clearHazardous();
    if (![401,403].includes(error.status)) throw error;
  }
}
async function hazardousAction(action, owner=null) {
  let pending, ticket;
  try {
    if (owner) hazardousAssert(owner);
    pending = action(); ticket = hazardousTicket();
    await pending;
  } catch (error) {
    if (error.cancelled || (ticket && !hazardousOwns(ticket)) || (!ticket && owner && !hazardousOwns(owner))) return;
    if (!$('hazardousModal') && ticket && hazardousCan('hazardous.read')) hazardousShell(ticket);
    if ($('hazardousLoading') || typeof error.hazardousRetry==='function') {
      $('hazardousContent').innerHTML='<p>画面を読み込めませんでした。</p>'+(typeof error.hazardousRetry==='function'?hazardousButton('hazardousReadRetry','この画面を再読込'):'<p>上の一覧・期限から開き直してください。</p>');
      if(typeof error.hazardousRetry==='function')hazardousBind('hazardousReadRetry',error.hazardousRetry,ticket);
    }
    if ($('hazardousMessage')) $('hazardousMessage').textContent = error.status === 409
      ? '他の更新または根拠の変更を検出しました。再読込して確認し直してください。草案の根拠が変わった場合は、訂正保存後にHuman確認してください。 ' + error.message
      : error.message;
  }
}
async function hazardousAfterSave(load) {
  // The mutation has succeeded. A failed follow-up read must never invite a
  // second POST or leave the now-obsolete edit form silently disabled.
  const pending=load(),ticket=hazardousTicket();
  try { await pending; }
  catch(error) {
    if(error.cancelled||!hazardousOwns(ticket))throw hazardousCancelled();
    hazardousShell(ticket);
    $('hazardousContent').innerHTML='<h2>登録・更新は完了しました</h2><p>詳細の再読込に失敗しました。更新を繰り返さず、再読込してください。</p>'+hazardousButton('hazardousSavedReload','保存した記録を再読込');
    $('hazardousMessage').textContent=error.message;
    hazardousBind('hazardousSavedReload',()=>hazardousAfterSave(load),ticket);
  }
}
function hazardousBind(id, action, ticket=hazardousTicket()) {
  const node = $(id);
  if (node) node.onclick = () => hazardousAction(action, ticket);
}
function hazardousButton(id, text, permission=null) {
  return !permission || hazardousCan(permission) ? `<button class="btn" type="button" id="${esc(id)}">${esc(text)}</button>` : '';
}
function hazardousTable(headers, rows) {
  return `<div class="scroll"><table><thead><tr>${headers.map(h=>`<th>${esc(h)}</th>`).join('')}</tr></thead><tbody>${rows.map(row=>`<tr>${row.map(cell=>`<td>${cell}</td>`).join('')}</tr>`).join('')}</tbody></table></div>`;
}
function hazardousShell(ticket) {
  hazardousAssert(ticket);
  if (!$('hazardousModal')) {
    const modal = document.createElement('div');
    modal.id = 'hazardousModal'; modal.className = 'modalWrap'; modal.style.zIndex = '76';
    modal.innerHTML = '<div class="modal" style="width:min(1240px,98vw)"><div class="modalHead"><b>危険物台帳</b><span class="grow"></span><button class="btn" type="button" id="hazardousClose">閉じる</button></div><div class="modalBody"><p class="muted">職員が原本に基づく事実を記録します。許可の発行・法令適合の判定は行いません。</p><div id="hazardousMessage" class="dangerText" role="alert"></div><div id="hazardousNav" class="toolbar"></div><div id="hazardousContent"></div></div></div>';
    document.body.append(modal);
  }
  $('hazardousClose').onclick = closeHazardous;
  $('hazardousNav').innerHTML = hazardousButton('hazardousListNav','施設・設備一覧') + hazardousButton('hazardousDeadlinesNav','記録の期限');
  hazardousBind('hazardousListNav',()=>hazardousList(),ticket);
  hazardousBind('hazardousDeadlinesNav',()=>hazardousDeadlines(),ticket);
}
async function openHazardous() { return hazardousList(); }
async function hazardousList(q='', offset=0, status='') {
  const ticket = hazardousBegin(()=>hazardousList(q,offset,status));
  const rows = await hazardousAPI('/hazardous/installations?' + new URLSearchParams({q,limit:100,offset,...(status?{status}:{})}), {}, ticket);
  hazardousShell(ticket);
  $('hazardousContent').innerHTML = '<h2>施設・設備一覧</h2><div class="toolbar"><label>名称・区分の検索 <input id="hazardousQ" value="'+esc(q)+'"></label><label>状態 <select id="hazardousStatus"><option value="">すべて</option><option value="active" '+(status==='active'?'selected':'')+'>使用中</option><option value="retired" '+(status==='retired'?'selected':'')+'>廃止</option></select></label>'+hazardousButton('hazardousSearch','検索')+hazardousButton('hazardousPrev','前へ')+hazardousButton('hazardousNext','次へ')+hazardousButton('hazardousNew','施設・設備を登録','hazardous.create')+'</div>'+
    (rows.length ? hazardousTable(['名称','対象物','入力された区分','状態','操作'],rows.map(r=>[esc(r.name),esc(r.building_name??'登録対象物'),esc(r.category_label),esc(hazardousLabels[r.status]),`<button class="btn" type="button" data-hazardous-installation="${esc(r.installation_id)}">詳細・根拠</button>`])):'<p>該当する記録はありません。新規登録は「施設・設備を登録」から始めます。</p>');
  $('hazardousPrev').disabled = !offset; $('hazardousNext').disabled = rows.length < 100;
  hazardousBind('hazardousSearch',()=>hazardousList($('hazardousQ').value,0,$('hazardousStatus').value),ticket);
  hazardousBind('hazardousPrev',()=>hazardousList(q,Math.max(0,offset-100),status),ticket);
  hazardousBind('hazardousNext',()=>hazardousList(q,offset+100,status),ticket);
  hazardousBind('hazardousNew',()=>hazardousInstallationForm(),ticket);
  hazardousBindInstallations(ticket);
}
function hazardousBindInstallations(ticket) {
  document.querySelectorAll('[data-hazardous-installation]').forEach(button=>{
    button.onclick = () => hazardousAction(()=>hazardousDetail(button.dataset.hazardousInstallation),ticket);
  });
}
async function hazardousDetail(id) {
  const ticket = hazardousBegin(()=>hazardousDetail(id));
  const row = await hazardousAPI(hazardousPath(id),{},ticket);
  hazardousShell(ticket);
  const active = row.status === 'active';
  $('hazardousContent').innerHTML = `<h2>${esc(row.name)}</h2><p>${esc(row.building_name??'登録対象物')} / ${esc(row.category_label)} / ${esc(hazardousLabels[row.status])} / 版 ${esc(row.version)}</p><p>設置場所: ${esc(row.location_detail??'未登録')}</p><p>${esc(row.notes??'')}</p><div class="toolbar">${hazardousButton('hazardousReload','再読込')}${active?hazardousButton('hazardousEdit','施設・数量を訂正','hazardous.update')+hazardousButton('hazardousRecordNew','許可・届出・変更を記録','hazardous.create')+hazardousButton('hazardousRetire','廃止を記録','hazardous.update'):''}</div><h3>品名・数量・容量</h3><p class="muted">入力単位を保持します。単位換算・合算・法令区分の推定は行いません。</p>` + hazardousTable(['品名','入力された区分','数量','容量'],(row.materials??[]).map(m=>[esc(m.name),esc(m.category_label),esc(m.quantity)+' '+esc(m.quantity_unit),m.capacity===null||m.capacity===undefined?'未登録':esc(m.capacity)+' '+esc(m.capacity_unit)]))+
    '<h3>許可・届出・変更の証拠記録</h3>' + ((row.evidence_records??[]).length ? hazardousTable(['種類・名称','記録日','設定した期限','証拠確認','操作'],row.evidence_records.map(r=>[esc(hazardousLabels[r.kind])+' / '+esc(r.title),esc(r.recorded_on),esc(r.due_on??'未設定'),esc(hazardousRecordStatus(r)),`<button class="btn" type="button" data-hazardous-record="${esc(r.record_id)}">原本・確認・訂正</button>`])) : '<p>記録なし</p>') + hazardousHistory(row.history??[]);
  hazardousBind('hazardousReload',()=>hazardousDetail(id),ticket);
  hazardousBind('hazardousEdit',()=>hazardousInstallationForm(row),ticket);
  hazardousBind('hazardousRecordNew',()=>hazardousRecordForm(row),ticket);
  hazardousBind('hazardousRetire',()=>hazardousDecision(row,null,'retire'),ticket);
  document.querySelectorAll('[data-hazardous-record]').forEach(button=>{
    button.onclick=()=>hazardousAction(()=>hazardousRecordDetail(id,button.dataset.hazardousRecord),ticket);
  });
}
function hazardousRecordStatus(row) {
  return row.status === 'confirmed' ? (row.confirmation_current ? '現行の事実・原本をHuman確認済' : '過去の確認（現行の事実・原本は未確認）') : hazardousLabels[row.status]??row.status;
}
function hazardousHistory(rows) {
  return '<h3>変更履歴</h3>' + (rows.length ? rows.map(h=>`<details class="card"><summary>${esc(h.action??h.event_type??'変更')} / ${esc(h.changed_at??h.created_at??'')} / ${esc(h.reason??'')}</summary><p>実施者: ${esc(h.actor_name??h.changed_by??h.actor_user_id??h.created_by??'記録参照')}</p><pre style="white-space:pre-wrap;overflow-wrap:anywhere">${esc(JSON.stringify(h,null,2))}</pre></details>`).join('') : '<p>履歴なし</p>');
}
async function hazardousDeadlines(dueBefore='', offset=0) {
  const ticket = hazardousBegin(()=>hazardousDeadlines(dueBefore,offset));
  const rows = await hazardousAPI('/hazardous/deadlines?'+new URLSearchParams({limit:100,offset,...(dueBefore?{due_before:dueBefore}:{})}),{},ticket);
  hazardousShell(ticket);
  $('hazardousContent').innerHTML='<h2>記録された期限</h2><p>職員が登録した期限です。法令上の期限を計算する機能ではありません。</p><div class="toolbar"><label>指定日まで <input type="date" id="hazardousDueBefore" value="'+esc(dueBefore)+'"></label>'+hazardousButton('hazardousDueSearch','表示')+hazardousButton('hazardousDuePrev','前へ')+hazardousButton('hazardousDueNext','次へ')+'</div>'+hazardousTable(['施設・記録','期限','証拠確認','操作'],rows.map(r=>[esc(r.installation_name??r.name??'')+' / '+esc(r.title),esc(r.due_on),esc(hazardousRecordStatus(r)),`<button class="btn" type="button" data-hazardous-installation="${esc(r.installation_id)}">台帳を開く</button>`]));
  $('hazardousDuePrev').disabled=!offset; $('hazardousDueNext').disabled=rows.length<100;
  hazardousBind('hazardousDueSearch',()=>hazardousDeadlines($('hazardousDueBefore').value),ticket);
  hazardousBind('hazardousDuePrev',()=>hazardousDeadlines(dueBefore,Math.max(0,offset-100)),ticket);
  hazardousBind('hazardousDueNext',()=>hazardousDeadlines(dueBefore,offset+100),ticket);
  hazardousBindInstallations(ticket);
}
function hazardousMaterialValues(row) {
  const exact = value => typeof value === 'string' && /^(?:0|[1-9][0-9]{0,17})(?:\.[0-9]{1,6})?$/.test(value);
  const quantity = row.quantity, capacity = row.capacity??'';
  if (!row.name?.trim() || !row.quantity_unit?.trim()) throw new Error('品名・数量単位を入力してください。');
  if (!exact(quantity)) throw new Error('数量は0以上の十進数（整数18桁・小数6桁以内）で入力してください。01・00.1のような余分な先頭の0は使えません。');
  if ((capacity !== '') !== Boolean(row.capacity_unit?.trim())) throw new Error('容量と容量単位は両方入力するか、両方空欄にしてください。');
  if (capacity !== '' && !exact(capacity)) throw new Error('容量は0以上の十進数（整数18桁・小数6桁以内）で入力してください。01・00.1のような余分な先頭の0は使えません。');
  return {name:row.name.trim(),category_label:row.category_label?.trim()??'',quantity,quantity_unit:row.quantity_unit.trim(),capacity:capacity === '' ? null : capacity,capacity_unit:row.capacity_unit?.trim()||null};
}
async function hazardousSourceQuery(kind,q,offset,extra,picker,ticket) {
  const request = ++picker.request;
  try {
    const rows=await hazardousAPI('/hazardous/sources/'+kind+'?'+new URLSearchParams({q,limit:100,offset,...extra}),{},ticket,hazardousSourceRights[kind]);
    hazardousAssert(ticket);
    if (request !== picker.request) throw hazardousCancelled();
    return rows;
  } catch (error) {
    if (request !== picker.request) throw hazardousCancelled();
    throw error;
  }
}

function hazardousField(key, label, value='', type='text', required=false, options=[]) {
  const id = 'hazardousField_' + key;
  const control = type === 'textarea' ? `<textarea id="${id}" ${required?'required':''}>${esc(value??'')}</textarea>` :
    type === 'select' ? `<select id="${id}" ${required?'required':''}>${options.map(([v,l])=>`<option value="${esc(v)}" ${String(value)===v?'selected':''}>${esc(l)}</option>`).join('')}</select>` :
    type === 'checkbox' ? `<input id="${id}" type="checkbox" ${required?'required':''}>` :
    `<input id="${id}" type="${type}" value="${esc(value??'')}" ${required?'required':''}>`;
  return `<label class="field" for="${id}">${esc(label)}${control}</label>`;
}
function hazardousForm(title, body, ticket, submit, back, submitLabel='保存') {
  hazardousShell(ticket);
  $('hazardousContent').innerHTML=`<h2>${esc(title)}</h2><form id="hazardousForm">${body}<p id="hazardousFormStatus" role="status" aria-live="polite"></p><div class="toolbar"><button class="btn primary" id="hazardousSave" type="submit">${esc(submitLabel)}</button>${hazardousButton('hazardousBack','変更せず戻る')}</div></form>`;
  let submitting=false,busy=false;
  const refreshBusy=()=>{
    if(!hazardousOwns(ticket))return;
    $('hazardousSave').disabled=submitting||busy;
    $('hazardousForm').setAttribute('aria-busy',String(submitting||busy));
  };
  $('hazardousForm').onsubmit=event=>{
    event.preventDefault();
    if (submitting || busy) return;
    return hazardousAction(async()=>{
      hazardousAssert(ticket); submitting = true;
      const save = $('hazardousSave'); refreshBusy();
      try { await submit(); }
      finally { if (hazardousOwns(ticket) && save.isConnected) { submitting = false; refreshBusy(); } }
    },ticket);
  };
  hazardousBind('hazardousBack',back,ticket);
  return {isSubmitting:()=>submitting,setBusy(value,message=''){
    hazardousAssert(ticket);busy=value;
    $('hazardousFormStatus').textContent=message;refreshBusy();
  }};
}
function hazardousValue(key) { return $('hazardousField_'+key)?.value??''; }
async function hazardousInstallationForm(row=null) {
  const ticket = hazardousBegin();
  const permission = row ? 'hazardous.update' : 'hazardous.create';
  await hazardousAuthority(ticket,permission);
  let facilityPicker;
  const body = (row?`<p>対象物: ${esc(row.building_name??'登録済み対象物')}（変更不可）</p>`:'<div id="hazardousFacilityPicker"></div>')+
    hazardousField('name','施設・設備の名称',row?.name??'','text',true)+
    hazardousField('category_label','原本に記載された区分（職員入力）',row?.category_label??'','text',true)+
    hazardousField('location_detail','設置場所',row?.location_detail??'')+hazardousField('notes','備考',row?.notes??'','textarea')+
    '<h3>品名・数量・容量</h3><p class="muted">数量は整数18桁・小数6桁以内。01・00.1のような余分な先頭の0は入力できません。原本の単位をそのまま入力します。容量を入力する場合は容量単位も必要です。</p><div id="hazardousMaterials"></div>'+hazardousButton('hazardousMaterialAdd','品目を追加')+
    (row?hazardousField('reason','訂正理由','','textarea',true):'');
  const form=hazardousForm(row?'施設・設備・数量の訂正':'施設・設備を登録',body,ticket,async()=>{
    const materials=[...$('hazardousMaterials').querySelectorAll('[data-hazardous-material]')].map(element=>{
      const data={};element.querySelectorAll('[data-material-field]').forEach(input=>data[input.dataset.materialField]=input.value);
      return hazardousMaterialValues(data);
    });
    const data={name:hazardousValue('name').trim(),category_label:hazardousValue('category_label').trim(),location_detail:hazardousValue('location_detail'),notes:hazardousValue('notes'),materials};
    if (row) { data.expected_version=row.version;data.reason=hazardousValue('reason').trim(); }
    else { data.building_id=facilityPicker?.ids()[0];if(!data.building_id)throw new Error('対象物を検索して選択してください。'); }
    const saved=await hazardousAPI(row?hazardousPath(row.installation_id):'/hazardous/installations',hazardousJSON(row?'PATCH':'POST',data),ticket,permission);
    await hazardousAfterSave(()=>hazardousDetail(saved.installation_id));
  },row?()=>hazardousDetail(row.installation_id):()=>hazardousList());
  (row?.materials??[]).forEach(material=>hazardousMaterialRow(material,ticket));
  hazardousBind('hazardousMaterialAdd',()=>{
    if ($('hazardousMaterials').querySelectorAll('[data-hazardous-material]').length>=100)throw new Error('品目は100件以内で登録してください。');
    hazardousMaterialRow({},ticket);
  },ticket);
  if (!row) {
    form.setBusy(true,'対象物の候補を読込中です。');
    facilityPicker=await hazardousSourcePicker($('hazardousFacilityPicker'),'facilities','対象物を選択',[],{},ticket,false);
    hazardousAssert(ticket);form.setBusy(false);
  }
}
function hazardousMaterialRow(material,ticket) {
  hazardousAssert(ticket);
  const box=document.createElement('fieldset');box.dataset.hazardousMaterial='true';box.className='card';
  const fields=[['name','品名',true],['category_label','原本に記載された品目区分',false],['quantity','数量',true],['quantity_unit','数量単位',true],['capacity','容量（任意）',false],['capacity_unit','容量単位（任意）',false]];
  box.innerHTML='<legend>品目</legend><div class="grid3">'+fields.map(([key,label,required])=>`<label class="field">${esc(label)}<input data-material-field="${key}" type="text" ${['quantity','capacity'].includes(key)?'inputmode="decimal"':''} ${required?'required':''} value="${esc(material[key]??'')}"></label>`).join('')+'</div><button class="btn" type="button">この品目を除く</button>';
  box.querySelector('button').onclick=()=>hazardousAction(()=>{hazardousAssert(ticket);box.remove();},ticket);
  $('hazardousMaterials').append(box);
}
async function hazardousSourcePicker(container,kind,label,selected,extra,ticket,multiple=true) {
  hazardousAssert(ticket);
  const picker={request:0},chosen=new Map(selected.map(row=>[row.id,row]));
  const prefix='hazardousPicker_'+kind;
  container.innerHTML=`<fieldset class="card" id="${prefix}"><legend>${esc(label)}</legend><div class="toolbar"><input id="${prefix}_q" aria-label="${esc(label)}を検索" placeholder="名称で検索"><button class="btn" type="button" id="${prefix}_search">検索</button><button class="btn" type="button" id="${prefix}_prev">前へ</button><button class="btn" type="button" id="${prefix}_next">次へ</button><select id="${prefix}_choice" aria-label="${esc(label)}の候補"><option value="">候補を読込中</option></select><button class="btn" type="button" id="${prefix}_select">選択</button></div><div id="${prefix}_selected" aria-live="polite"></div></fieldset>`;
  let offset=0,rows=[];
  const paint=()=>{
    hazardousAssert(ticket);
    $(prefix+'_selected').innerHTML=chosen.size?[...chosen.values()].map((row,index)=>`<div class="row"><span>${esc(row.label)}</span><span class="muted" style="overflow-wrap:anywhere">${row.sha256?'SHA-256: '+esc(row.sha256):''}</span><button class="btn" type="button" data-hazardous-remove="${index}">選択解除</button></div>`).join(''):'<p class="muted">未選択</p>';
    $(prefix+'_selected').querySelectorAll('[data-hazardous-remove]').forEach(button=>{
      const id=[...chosen.keys()][Number(button.dataset.hazardousRemove)];
      button.onclick=()=>hazardousAction(async()=>{await hazardousAuthority(ticket,hazardousSourceRights[kind]);chosen.delete(id);paint();},ticket);
    });
  };
  const load=async()=>{
    const result=await hazardousSourceQuery(kind,$(prefix+'_q').value,offset,extra,picker,ticket);
    hazardousAssert(ticket);if(!container.isConnected)throw hazardousCancelled();rows=result;
    for(const row of rows)if(chosen.has(row.id))chosen.set(row.id,row);
    $(prefix+'_choice').innerHTML='<option value="">候補から選択</option>'+rows.map(row=>`<option value="${esc(row.id)}">${esc(row.label)}</option>`).join('');
    $(prefix+'_prev').disabled=!offset;$(prefix+'_next').disabled=rows.length<100;paint();
  };
  hazardousBind(prefix+'_search',async()=>{offset=0;await load();},ticket);
  hazardousBind(prefix+'_prev',async()=>{offset=Math.max(0,offset-100);await load();},ticket);
  hazardousBind(prefix+'_next',async()=>{offset+=100;await load();},ticket);
  hazardousBind(prefix+'_select',async()=>{
    const id=$(prefix+'_choice').value;const row=rows.find(r=>r.id===id);
    if(!row)throw new Error('候補を選択してください。');
    await hazardousAuthority(ticket,hazardousSourceRights[kind]);
    if(!multiple)chosen.clear();chosen.set(id,row);paint();
  },ticket);
  paint();await load();
  return {ids:()=>[...chosen.keys()],add:row=>{hazardousAssert(ticket);chosen.set(row.id,row);paint();},reload:load};
}
function hazardousSelected(record,kind,field) {
  const sources=record?.sources?.[kind]??[];
  return (record?.[field]??[]).map((id,index)=>sources.find(s=>s.id===id)??{id,label:'保存した関連記録 '+(index+1)});
}
async function hazardousRecordForm(installation,record=null) {
  const ticket=hazardousBegin(),permission=record?'hazardous.update':'hazardous.create';
  await hazardousAuthority(ticket,permission);
  if(record && record.status!=='draft')throw new Error('確認済み記録は「改訂草案を作成」から訂正してください。');
  const pickers={};
  const sources=[['documents','document_ids','証拠原本'],['legal','legal_source_version_ids','法令根拠の版'],['inspections','inspection_ids','同じ対象物の査察'],['violations','violation_case_ids','同じ対象物の違反・改善案件']];
  let body=`<p>${esc(installation.name)} / 施設版 ${esc(installation.version)}</p>`+
    hazardousField('kind','記録の種類',record?.kind??'permit','select',true,[['permit','許可の記録'],['notification','届出の記録'],['change','変更の記録']])+
    hazardousField('title','記録の名称',record?.title??'','text',true)+hazardousField('reference_no','原本の許可・届出番号（任意）',record?.reference_no??'')+
    hazardousField('recorded_on','原本の記録日',record?.recorded_on??new Date().toISOString().slice(0,10),'date',true)+hazardousField('due_on','原本に記録された期限（任意）',record?.due_on??'','date')+
    hazardousField('notes','備考',record?.notes??'','textarea');
  for(const [kind,,label] of sources)body+=hazardousSourceAvailable(kind)?`<div id="hazardousSource_${kind}"></div>`:`<p class="muted">${esc(label)}の参照権限がありません。</p>`;
  if(hazardousCan('document.create')&&hazardousCan('document.read'))body+='<fieldset class="card"><legend>新しい証拠原本を登録</legend><label class="field">原本ファイル<input id="hazardousUploadFile" type="file"></label>'+hazardousButton('hazardousUpload','原本をアップロードして選択')+'<p id="hazardousUploadStatus" aria-live="polite"></p></fieldset>';
  if(record)body+=hazardousField('reason','草案の訂正理由','','textarea',true);
  const form=hazardousForm(record?'許可・届出・変更の草案を訂正':'許可・届出・変更の証拠を記録',body,ticket,async()=>{
    const payload={expected_installation_version:installation.version,kind:hazardousValue('kind'),title:hazardousValue('title').trim(),reference_no:hazardousValue('reference_no').trim()||null,recorded_on:hazardousValue('recorded_on'),due_on:hazardousValue('due_on')||null,notes:hazardousValue('notes')};
    for(const [kind,field] of sources)payload[field]=pickers[kind]?.ids()??[];
    if(record){payload.expected_version=record.version;payload.reason=hazardousValue('reason').trim();}
    const saved=await hazardousAPI(hazardousPath(installation.installation_id)+'/records'+(record?'/'+encodeURIComponent(record.record_id):''),hazardousJSON(record?'PATCH':'POST',payload),ticket,permission);
    await hazardousAfterSave(()=>hazardousRecordDetail(installation.installation_id,saved.record_id));
  },()=>hazardousDetail(installation.installation_id));
  form.setBusy(true,'関連する根拠を読込中です。');
  if($('hazardousUpload'))$('hazardousUpload').disabled=true;
  await Promise.all(sources.filter(([kind])=>hazardousSourceAvailable(kind)).map(async([kind,field,label])=>{
    const picker=await hazardousSourcePicker($('hazardousSource_'+kind),kind,label,hazardousSelected(record,kind,field),['documents','inspections','violations'].includes(kind)?{building_id:installation.building_id}:{},ticket);
    hazardousAssert(ticket);pickers[kind]=picker;
  }));
  hazardousAssert(ticket);form.setBusy(false);
  if($('hazardousUpload'))$('hazardousUpload').disabled=false;
  let uploading=false;
  hazardousBind('hazardousUpload',async()=>{
    if(uploading)return;
    if(form.isSubmitting())throw new Error('草案の保存中です。原本の登録は保存完了後に行ってください。');
    const file=$('hazardousUploadFile').files?.[0];if(!file)throw new Error('登録する原本ファイルを選択してください。');
    uploading=true;form.setBusy(true,'原本を登録中です。完了するまで草案は保存できません。');$('hazardousUpload').disabled=true;
    try{
      const data=new FormData();data.append('file',file);data.append('building_id',installation.building_id);data.append('document_type','hazardous_evidence');
      const uploaded=await hazardousAPI('/documents/upload',{method:'POST',body:data},ticket,'document.create');
      pickers.documents.add({id:uploaded.document_id,label:uploaded.original_filename??file.name,sha256:uploaded.sha256});
      $('hazardousUploadStatus').textContent='原本を登録し、証拠として選択しました。草案を保存するとこの記録に関連付けられます。';
      $('hazardousUploadFile').value='';
    }finally{if(hazardousOwns(ticket)){$('hazardousUpload').disabled=false;uploading=false;form.setBusy(false);}}
  },ticket);
}
async function hazardousRecordDetail(installationId,recordId) {
  const ticket=hazardousBegin(()=>hazardousRecordDetail(installationId,recordId)),installation=await hazardousAPI(hazardousPath(installationId),{},ticket);
  const record=(installation.evidence_records??[]).find(row=>row.record_id===recordId);
  if(!record)throw new Error('記録が見つからないか、関連する根拠の参照権限がありません。');
  hazardousShell(ticket);
  const active=installation.status==='active',draft=record.status==='draft',confirmed=record.status==='confirmed';
  $('hazardousContent').innerHTML=`<h2>${esc(record.title)}</h2><p>${esc(installation.name)} / ${esc(hazardousLabels[record.kind])} / ${esc(hazardousRecordStatus(record))}</p><p>原本の番号: ${esc(record.reference_no??'未登録')} / 記録日: ${esc(record.recorded_on)} / 設定した期限: ${esc(record.due_on??'未設定')}</p><p>${esc(record.notes??'')}</p><div class="toolbar">${hazardousButton('hazardousRecordBack','施設・設備に戻る')}${hazardousButton('hazardousRecordReload','再読込')}${active&&draft?hazardousButton('hazardousRecordEdit','草案を訂正','hazardous.update')+hazardousButton('hazardousConfirm','原本・証拠をHuman確認','hazardous.review'):''}${active&&confirmed?hazardousButton('hazardousRevision','改訂草案を作成','hazardous.update'):''}${active&&(draft||confirmed)?hazardousButton('hazardousCancel','記録を取消','hazardous.update'):''}</div>`+
    hazardousSourcesMarkup(record)+`<h3>${draft?'草案保存時の原本・根拠':'Human確認時の原本・根拠'}</h3><p>確認者: ${esc(record.confirmed_by??'未確認')} / 確認日時: ${esc(record.confirmed_at??'未確認')}</p><p class="muted">現在の事実や原本が変更されると過去の確認になります。過去の確認情報は保持されます。</p><details><summary>${draft?'草案に関連付けた版・原本ハッシュ':'確認時の版・原本ハッシュ'}</summary><pre style="white-space:pre-wrap;overflow-wrap:anywhere">${esc(JSON.stringify(record.source_snapshot??{},null,2))}</pre></details>`;
  hazardousBind('hazardousRecordBack',()=>hazardousDetail(installationId),ticket);
  hazardousBind('hazardousRecordReload',()=>hazardousRecordDetail(installationId,recordId),ticket);
  hazardousBind('hazardousRecordEdit',()=>hazardousRecordForm(installation,record),ticket);
  for(const [id,verb] of [['hazardousConfirm','confirm'],['hazardousCancel','cancel'],['hazardousRevision','revisions']])hazardousBind(id,()=>hazardousDecision(installation,record,verb),ticket);
  hazardousBindSources(installation,record,ticket);
}
function hazardousSafeURL(raw) {
  try{const url=new URL(raw);return ['https:','http:'].includes(url.protocol)?url.href:null;}catch{return null;}
}
function hazardousSourcesMarkup(record) {
  let html='<h3>関連する原本・業務記録</h3>';
  const sources=record.sources??{};
  if(hazardousCan('document.read'))html+=(sources.documents??[]).map(row=>`<div class="card"><b>${esc(row.label)}</b><p style="overflow-wrap:anywhere">SHA-256: ${esc(row.sha256)}</p><button class="btn" type="button" data-hazardous-document="${esc(row.id)}">原本を保存</button></div>`).join('');
  if(hazardousCan('legal_source.read'))html+=(sources.legal??[]).map(row=>{
    const original=row.raw_document_id?{document_id:row.raw_document_id}:(record.source_snapshot?.legal_sources??[]).find(s=>s.legal_source_version_id===row.id)?.original;
    const url=hazardousSafeURL(row.source_url);
    return `<div class="card"><b>${esc(row.label)}</b><p style="overflow-wrap:anywhere">SHA-256: ${esc(row.sha256)}</p>${url?`<a class="btn" target="_blank" rel="noopener noreferrer" href="${esc(url)}">法令の出典を開く</a>`:''}${original&&hazardousCan('document.read')?`<button class="btn" type="button" data-hazardous-document="${esc(original.document_id)}">法令原本を保存</button>`:''}</div>`;
  }).join('');
  if(hazardousCan('inspection.read'))html+=(sources.inspections??[]).map(row=>`<p>${esc(row.label)} <button class="btn" type="button" data-hazardous-inspection="${esc(row.id)}">査察記録を開く</button></p>`).join('');
  if(hazardousCan('violation.read'))html+=(sources.violations??[]).map(row=>`<p>${esc(row.label)} <button class="btn" type="button" data-hazardous-violation="${esc(row.id)}">違反・改善案件を開く</button></p>`).join('');
  return html;
}
function hazardousBindSources(installation,record,ticket) {
  document.querySelectorAll('[data-hazardous-document]').forEach(button=>button.onclick=()=>hazardousAction(()=>hazardousDownload(button.dataset.hazardousDocument,ticket),ticket));
  document.querySelectorAll('[data-hazardous-inspection]').forEach(button=>button.onclick=()=>hazardousAction(()=>hazardousInspection(installation,record,button.dataset.hazardousInspection),ticket));
  document.querySelectorAll('[data-hazardous-violation]').forEach(button=>button.onclick=()=>hazardousAction(async()=>{
    await hazardousAuthority(ticket,'violation.read');
    const isCurrent=()=>hazardousOwns(ticket);
    await openViolations(isCurrent);hazardousAssert(ticket);
    const modal=$('violationModal');
    const targetCurrent=()=>isCurrent()&&$('violationModal')===modal&&modal?.isConnected&&!modal.classList.contains('hidden');
    if(!targetCurrent())throw hazardousCancelled();
    await violationDetail(button.dataset.hazardousViolation,targetCurrent);
    if(!targetCurrent())throw hazardousCancelled();
    closeHazardous();
  },ticket));
}
async function hazardousDownload(id,ticket=hazardousTicket()) {
  await hazardousAuthority(ticket,'document.read');
  const response=await fetch('/documents/'+encodeURIComponent(id)+'/download');
  if(!response.ok)throw Object.assign(new Error('原本を取得できません。権限・原本の保存状態を確認してください。'),{status:response.status});
  const blob=await response.blob();await hazardousAuthority(ticket,'document.read');hazardousAssert(ticket);
  const url=URL.createObjectURL(blob),link=document.createElement('a');link.href=url;
  link.download=response.headers.get('Content-Disposition')?.match(/filename="([^"]+)"/)?.[1]??'original';
  document.body.append(link);link.click();link.remove();URL.revokeObjectURL(url);
}
async function hazardousInspection(installation,record,id) {
  const ticket=hazardousBegin(()=>hazardousInspection(installation,record,id)),inspection=await hazardousAPI('/inspections/'+encodeURIComponent(id),{},ticket,'inspection.read');
  if(inspection.building_id!==installation.building_id)throw new Error('査察の対象物が一致しません。');
  hazardousShell(ticket);
  $('hazardousContent').innerHTML=`<h2>関連する査察記録</h2><p>${esc(inspection.inspected_at)} / ${esc(inspection.inspection_type)} / ${esc(inspection.status)}</p><p>${esc(inspection.notes??'')}</p>`+hazardousTable(['指摘事項','改善状態','期限'],(inspection.findings??[]).map(f=>[esc(f.finding_text),esc(f.corrective_status),esc(f.due_date??'未設定')]))+hazardousButton('hazardousInspectionBack','証拠記録に戻る');
  hazardousBind('hazardousInspectionBack',()=>hazardousRecordDetail(installation.installation_id,record.record_id),ticket);
}
function hazardousDecisionPayload(installation,record,verb,values) {
  const reason=values.reason?.trim();if(!reason)throw new Error('理由を入力してください。');
  const payload={expected_version:record?record.version:installation.version,reason};
  if(record)payload.expected_installation_version=installation.version;
  if(verb!=='revisions'){
    if(values.human_acknowledged!==true)throw new Error('職員による確認のチェックが必要です。');
    payload.human_acknowledged=true;
  }
  return payload;
}
async function hazardousDecision(installation,record,verb) {
  const ticket=hazardousBegin(),permission=verb==='confirm'?'hazardous.review':'hazardous.update';
  await hazardousAuthority(ticket,permission);
  const labels={confirm:'原本・証拠をHuman確認',cancel:'記録を取消',revisions:'改訂草案を作成',retire:'施設・設備の廃止を記録'};
  const explanation=verb==='confirm'?'施設・数量の現行版と証拠原本、選択した法令根拠の版を職員が照合した記録です。許可の発行や法令適合の判定にはなりません。':
    verb==='revisions'?'確認済みの記録を保持して改訂草案を作成します。草案を訂正し、Human確認が完了するまで旧記録は維持されます。':
    verb==='retire'?'施設・設備を廃止状態にします。証拠と変更履歴は残ります。':'この証拠記録を取消状態にします。以前の確認内容と履歴は残ります。';
  const body=`<p>${esc(record?.title??installation.name)}</p><p>${esc(explanation)}</p>`+hazardousField('reason',verb==='confirm'?'原本を照合した内容・確認理由':'変更理由','','textarea',true)+
    (verb!=='revisions'?hazardousField('human_acknowledged',verb==='confirm'?'現行の事実・原本・根拠を職員が確認しました':'内容と理由を職員が確認しました',false,'checkbox',true):'');
  hazardousForm(labels[verb],body,ticket,async()=>{
    const data=hazardousDecisionPayload(installation,record,verb,{reason:hazardousValue('reason'),human_acknowledged:$('hazardousField_human_acknowledged')?.checked===true});
    const path=hazardousPath(installation.installation_id)+(record?'/records/'+encodeURIComponent(record.record_id):'')+'/'+verb;
    const saved=await hazardousAPI(path,hazardousJSON('POST',data),ticket,permission);
    if(record)await hazardousAfterSave(()=>hazardousRecordDetail(installation.installation_id,saved.record_id));
    else await hazardousAfterSave(()=>hazardousDetail(installation.installation_id));
  },()=>record?hazardousRecordDetail(installation.installation_id,record.record_id):hazardousDetail(installation.installation_id),labels[verb]);
}
