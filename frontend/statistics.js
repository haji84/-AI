'use strict';

// Statistics stores observations only. Domain records and live server rights
// remain authoritative. No source identities or evidence enter aggregate state.
const statisticsState={generation:0,intent:0,preflightRelease:null,visible:false,busy:false,permissions:[],catalog:null,view:'query',draft:{start_date:'',end_date:'',metric_keys:[]},preview:null,report:null,reportID:null,list:null,history:null,drilldown:null,error:'',notice:'',conflict:false,reviewNote:'',acknowledged:false,replacementReason:''};
const statisticsTitle='汎用統計出力（正式様式ではありません）';
const statisticsCoverage='網羅性: unknown（不明）。観測値0も、未登録・欠測がないことを意味しません。';
const statisticsJSON=data=>({method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(data)});
const statisticsCan=permission=>statisticsState.permissions.includes(permission);
const statisticsID=id=>typeof id==='string'&&/^[A-Za-z0-9_-]{1,128}$/.test(id);
const statisticsCancelled=()=>Object.assign(new Error('画面が変更されました'),{cancelled:true});

function statisticsRememberInputs(){
  if(statisticsState.view==='query'&&$('statisticsStart')){
    statisticsState.draft={start_date:$('statisticsStart').value,end_date:$('statisticsEnd').value,metric_keys:Array.from($('statisticsContent').querySelectorAll('[data-statistics-metric]')).filter(node=>node.checked&&statisticsState.catalog?.metrics.some(metric=>metric.key===node.dataset.statisticsMetric&&metric.available)).map(node=>node.dataset.statisticsMetric)};
  }
  if($('statisticsReviewNote'))statisticsState.reviewNote=$('statisticsReviewNote').value;
  if($('statisticsAcknowledge'))statisticsState.acknowledged=$('statisticsAcknowledge').checked;
  if($('statisticsReplacementReason'))statisticsState.replacementReason=$('statisticsReplacementReason').value;
}
function closeStatistics(){
  statisticsRememberInputs();statisticsState.preflightRelease?.();statisticsState.generation++;statisticsState.intent++;
  Object.assign(statisticsState,{visible:false,busy:false,preview:null,report:null,reportID:null,list:null,history:null,drilldown:null,error:'',notice:''});
  $('statisticsModal')?.remove();
}
function clearStatistics(){
  closeStatistics();Object.assign(statisticsState,{permissions:[],catalog:null,draft:{start_date:'',end_date:'',metric_keys:[]},reviewNote:'',acknowledged:false,replacementReason:'',conflict:false});
  $('statisticsBtn')?.classList.add('hidden');
}
async function initStatistics(isCurrent=()=>true){
  const ticket=statisticsState.generation;
  try{
    const result=await api('/auth/permissions');
    if(ticket!==statisticsState.generation||!isCurrent())return;
    statisticsState.permissions=result.permissions;
    const button=$('statisticsBtn');if(button){button.statisticsIntent=statisticsState.intent;button.onclick=()=>{if(button.statisticsIntent===statisticsState.intent)return openStatistics();};button.classList.toggle('hidden',!statisticsCan('statistics.read'));}
  }catch(error){if(error.cancelled)throw error;}
}
function statisticsEnsureModal(){
  if($('statisticsModal'))return;
  const modal=document.createElement('div');modal.id='statisticsModal';modal.className='modalWrap';modal.style.zIndex='74';
  modal.innerHTML='<div class="modal" style="width:min(1220px,98vw)"><div class="modalHead"><b>横断統計・保存観測</b><span class="grow"></span><button type="button" class="btn" id="statisticsClose">閉じる</button></div><div class="modalBody"><div id="statisticsContent"></div></div></div>';
  document.body.append(modal);$('statisticsClose').onclick=closeStatistics;
}
function statisticsBegin(view=statisticsState.view){
  statisticsState.preflightRelease?.();const ticket=++statisticsState.generation,intent=statisticsState.intent;statisticsState.view=view;statisticsState.busy=true;statisticsState.error='';statisticsState.notice='';
  renderStatistics();const modal=$('statisticsModal');
  return ()=>ticket===statisticsState.generation&&intent===statisticsState.intent&&statisticsState.visible&&modal=== $('statisticsModal')&&modal?.isConnected;
}
function statisticsError(error,current){
  if(!current()||error.cancelled)return;
  if(error.status===401||error.status===403){clearStatistics();return;}
  statisticsState.error=error.status===409?'記録または元データに変更があります。保存記録を再読込して確認し、新しい保存版が必要か判断してください。':Array.isArray(error.body?.detail)?error.body.detail.map(item=>item.msg).join(' / '):String(error.message);
  if(error.status===409)statisticsState.conflict=true;
}
async function statisticsAction(action){
  if(statisticsState.busy||!statisticsState.visible)return;
  statisticsRememberInputs();const current=statisticsBegin();
  try{await action(current);}catch(error){statisticsError(error,current);}
  finally{if(current()){statisticsState.busy=false;renderStatistics();}}
}
function statisticsBind(id,action){
  const node=$(id),ticket=statisticsState.generation;if(!node)return;node.statisticsIntent=statisticsState.intent;
  node.onclick=()=>{if(node.statisticsIntent!==statisticsState.intent||ticket!==statisticsState.generation||!node.isConnected||node.disabled)return;return action();};
}
function statisticsButton(id,label,permission='',disabled=false,allowBusy=false){
  return permission&&!statisticsCan(permission)?'':`<button type="button" class="btn" id="${id}"${disabled||(statisticsState.busy&&!allowBusy)?' disabled':''}>${esc(label)}</button>`;
}
function statisticsText(value){return typeof value==='string'?value:value===null||value===undefined?'該当なし':JSON.stringify(value);}
function statisticsDefinition(metric){
  return `<p>出典: ${esc(metric.source_module)} / 単位: ${esc(metric.unit)} / 粒度: ${esc(metric.grain??'定義を参照')} / 分母: ${esc(statisticsText(metric.denominator))}</p><p>定義: ${esc(metric.definition??metric.label)} / 定義版: ${esc(metric.definition_version)}</p><p>日付基準: ${esc(statisticsText(metric.date_basis))}</p>`;
}
function statisticsSnapshot(snapshot,saved=false){
  const period=snapshot.period;
  return `<section id="statisticsSnapshot"><h3>${saved?'保存された観測':'プレビュー観測'}</h3><p>${esc(statisticsCoverage)}</p><p>選択期間（両端を含む）: ${esc(period.start_date)} ～ ${esc(period.end_date)}</p><p>保存された業務タイムゾーン: ${esc(period.business_timezone)} / 日付基準版: ${esc(period.date_basis_version)}</p><p>日時資料のUTC範囲: ${esc(period.start_at_utc)} 以上 ～ ${esc(period.end_before_utc)} 未満。DATE資料は選択日付で判定します。</p><p>観測取得日時: ${esc(snapshot.captured_at)} / 問合せ版: ${esc(snapshot.query_version)}</p><p>${saved?'保存値は不変です。現在の元データとの一致を常時保証するものではありません。':'保存時は選択条件で元データを再取得します。プレビューの値と異なる場合があります。'}</p>${snapshot.metrics.map((metric,index)=>`<article class="card" style="margin:12px 0;padding:14px"><h4>${esc(metric.label)}</h4><p class="statisticsValue">${metric.status==='observed'&&typeof metric.value==='string'?'観測値: '+esc(metric.value)+' '+esc(metric.unit):'利用不可（値なし）'}</p><p>網羅性: ${esc(metric.coverage_status)}（不明）</p>${statisticsDefinition(metric)}<p>除外・不明項目（選択期間内の欠測数とは限りません）:</p>${metric.exclusions.length?'<ul>'+metric.exclusions.map(item=>`<li>${esc(item.reason)}: ${esc(item.count)} / 粒度 ${esc(item.grain)} / 範囲 ${esc(item.scope)}（本部の全日付）</li>`).join('')+'</ul>':'<p>報告された除外項目なし。歴史的な網羅性は不明です。</p>'}<ul>${metric.limitations.map(text=>`<li>${esc(text)}</li>`).join('')}</ul>${saved&&metric.status==='observed'?`<button type="button" class="btn" data-statistics-drill="${index}"${statisticsState.busy?' disabled':''}>元記録の参照権限を確認</button>`:''}</article>`).join('')}</section>`;
}
function statisticsQueryMarkup(){
  const {catalog,draft,preview,busy}=statisticsState;
  if(!catalog)return busy?'<p role="status">定義と権限を読み込み中…</p>':statisticsButton('statisticsRetryCatalog','定義を再読込');
  return `<h3>観測する期間と指標</h3><p>業務タイムゾーン（サーバー設定）: ${esc(catalog.business_timezone)}。ブラウザーのタイムゾーンでは変更しません。</p><p>${esc(statisticsCoverage)}</p><div class="grid2"><label class="field">開始日（含む）<input type="date" id="statisticsStart" value="${esc(draft.start_date)}"${busy?' disabled':''}></label><label class="field">終了日（含む）<input type="date" id="statisticsEnd" value="${esc(draft.end_date)}"${busy?' disabled':''}></label></div>${catalog.metrics.map(metric=>`<article class="card" style="margin:10px 0;padding:12px"><label><input type="checkbox" data-statistics-metric="${esc(metric.key)}"${draft.metric_keys.includes(metric.key)?' checked':''}${busy||!metric.available?' disabled':''}> ${esc(metric.label)}${!metric.available?'（現在利用不可）':''}</label>${statisticsDefinition(metric)}</article>`).join('')}<div class="toolbar">${statisticsButton('statisticsQuery','観測プレビュー','statistics.read')}${statisticsButton('statisticsSave','元データを再取得して保存','statistics.record')}</div><p>保存値は変更できません。訂正時は同じ期間・指標から新しい保存版を作成します。</p>${preview?statisticsSnapshot(preview):''}`;
}
function statisticsReportMarkup(){
  const {report,history,drilldown,conflict,reviewNote,acknowledged,replacementReason,busy}=statisticsState;if(!report)return busy?'<p role="status">保存記録を読み込み中…</p>':statisticsButton('statisticsReload','保存記録を再読込');
  return `<h3>${report.state==='confirmed'?'Human確認済み':'保存済み'} / 報告 ${esc(report.report_id)} / Version ${esc(report.version)}</h3><p>保存日時: ${esc(report.created_at)} / Human確認日時: ${esc(report.confirmed_at??'未確認')}</p><p>Human確認は観測値の確認記録です。歴史的な網羅性や正式承認を意味しません。確認時点以降の元データ更新も停止しません。</p>${report.predecessor_id?`<p>前の保存版: ${esc(report.predecessor_id)} <button type="button" class="btn" data-statistics-report="${esc(report.predecessor_id)}">前の保存版を開く</button></p>`:''}${report.successor_id?`<p>後続の保存版: ${esc(report.successor_id)} <button type="button" class="btn" data-statistics-report="${esc(report.successor_id)}">後続の保存版を開く</button></p>`:''}<div class="toolbar">${statisticsButton('statisticsReload','保存記録を再読込')}${statisticsButton('statisticsHistory','操作履歴を読む')}${statisticsButton('statisticsCSV','汎用CSVを取得','statistics.export')}${statisticsButton('statisticsXLSX','汎用XLSXを取得','statistics.export')}</div>${statisticsSnapshot(report.snapshot,true)}${statisticsCan('statistics.record')&&!report.successor_id?`<section><h3>Human確認・新しい保存版</h3>${report.state==='saved'?`<label class="field">確認記録<textarea id="statisticsReviewNote"${busy?' disabled':''}>${esc(reviewNote)}</textarea></label><label><input type="checkbox" id="statisticsAcknowledge"${acknowledged?' checked':''}${busy?' disabled':''}> 観測値・定義・除外と制限を確認しました。網羅性は不明のままです。</label>${statisticsButton('statisticsConfirm','観測値をHuman確認','statistics.record',conflict)}`:''}<label class="field">新しい保存版を作成する理由<textarea id="statisticsReplacementReason"${busy?' disabled':''}>${esc(replacementReason)}</textarea></label>${statisticsButton('statisticsReplace','同じ条件で新しい保存版を作成','statistics.record',conflict)}<p>前の保存値と確認履歴は残ります。期間・指標・保存された日付基準で元データを再取得します。</p></section>`:''}${history?`<section><h3>操作履歴</h3><ul>${history.items.map(item=>`<li>${esc(item.action)} / Version ${esc(item.version)} / ${esc(item.occurred_at)}</li>`).join('')}</ul><p>${esc(history.total)}件</p>${statisticsButton('statisticsHistoryPrev','履歴の前のページ','',history.offset===0)}${statisticsButton('statisticsHistoryNext','履歴の次のページ','',history.offset+history.items.length>=history.total)}</section>`:''}${drilldown?`<section id="statisticsDrilldown"><h3>権限を確認した元記録への参照</h3><p>保存された指標の対象を、現在の元記録画面で開きます。元記録は保存後に更新されている場合があります。</p>${drilldown.error?`<p role="status">${esc(drilldown.error)}</p>`:`<p>${esc(drilldown.total)}件 / ${esc(drilldown.metric_key)}</p><ul>${drilldown.items.map((item,index)=>`<li>${esc(item.source_module)} / ${esc(item.record_type)} <button type="button" class="btn" data-statistics-source="${index}"${busy||!statisticsNavigation(item)?' disabled':''}>元記録を開く</button></li>`).join('')}</ul>${statisticsButton('statisticsDrillPrev','元記録の前のページ','',drilldown.offset===0)}${statisticsButton('statisticsDrillNext','元記録の次のページ','',drilldown.offset+drilldown.items.length>=drilldown.total)}`}</section>`:''}`;
}
function renderStatistics(){
  if(!statisticsState.visible)return;statisticsEnsureModal();
  const {view,list,error,notice,busy}=statisticsState;$('statisticsModal').setAttribute('aria-busy',String(busy));
  $('statisticsContent').innerHTML=`<h2>${statisticsTitle}</h2><p class="notice">財務・通貨の集計、過去時点の職員数・車両数、会計年度・前年比較、網羅性の宣言、正式原本様式の出力は未対応です。</p><div class="toolbar">${statisticsButton('statisticsBack','期間・指標に戻る','',false,true)}${statisticsButton('statisticsSaved','保存記録一覧','',false,true)}</div><p id="statisticsStatus" role="status">${busy?'処理中…':''}</p>${error?`<p class="dangerText" role="alert">${esc(error)}</p>`:''}${notice?`<p role="status">${esc(notice)}</p>`:''}${view==='query'?statisticsQueryMarkup():view==='report'?statisticsReportMarkup():`<h3>保存記録一覧</h3>${list?`<p>${esc(list.total)}件</p>${list.items.map(item=>`<article class="card"><p>${esc(item.state==='confirmed'?'Human確認済み':'保存済み')} / ${esc(item.snapshot.period.start_date)} ～ ${esc(item.snapshot.period.end_date)} / ${esc(item.snapshot.period.business_timezone)} / 取得 ${esc(item.snapshot.captured_at)} / 網羅性 unknown</p><button type="button" class="btn" data-statistics-report="${esc(item.report_id)}"${busy?' disabled':''}>保存記録を開く</button></article>`).join('')}${statisticsButton('statisticsListPrev','一覧の前のページ','',list.offset===0)}${statisticsButton('statisticsListNext','一覧の次のページ','',list.offset+list.items.length>=list.total)}`:busy?'<p>保存記録を読み込み中…</p>':'<p>保存記録を取得できません。一覧を再読込してください。</p>'}`}`;
  // Values assigned as DOM properties preserve exact input text after errors.
  if($('statisticsReviewNote'))$('statisticsReviewNote').value=statisticsState.reviewNote;
  if($('statisticsReplacementReason'))$('statisticsReplacementReason').value=statisticsState.replacementReason;
  for(const id of ['statisticsStart','statisticsEnd','statisticsReviewNote','statisticsAcknowledge','statisticsReplacementReason'])if($(id)){$(id).oninput=statisticsRememberInputs;$(id).onchange=statisticsRememberInputs;}
  $('statisticsContent').querySelectorAll('[data-statistics-metric]').forEach(node=>node.onchange=statisticsRememberInputs);
  statisticsBind('statisticsRetryCatalog',openStatistics);statisticsBind('statisticsBack',statisticsShowQuery);statisticsBind('statisticsSaved',()=>statisticsLoadList(0));
  statisticsBind('statisticsQuery',()=>statisticsQuery(false));statisticsBind('statisticsSave',()=>statisticsQuery(true));
  statisticsBind('statisticsConfirm',statisticsConfirm);statisticsBind('statisticsReplace',statisticsReplace);
  statisticsBind('statisticsReload',()=>statisticsLoadReport(statisticsState.report?.report_id??statisticsState.reportID));
  statisticsBind('statisticsHistory',()=>statisticsHistory(0));
  statisticsBind('statisticsCSV',()=>statisticsDownload('csv'));statisticsBind('statisticsXLSX',()=>statisticsDownload('xlsx'));
  statisticsBind('statisticsListPrev',()=>statisticsLoadList(Math.max(0,list.offset-list.limit)));statisticsBind('statisticsListNext',()=>statisticsLoadList(list.offset+list.limit));
  const history=statisticsState.history;statisticsBind('statisticsHistoryPrev',()=>statisticsHistory(Math.max(0,history.offset-history.limit)));statisticsBind('statisticsHistoryNext',()=>statisticsHistory(history.offset+history.limit));
  const drill=statisticsState.drilldown;statisticsBind('statisticsDrillPrev',()=>statisticsDrill(drill.metric_key,Math.max(0,drill.offset-drill.limit)));statisticsBind('statisticsDrillNext',()=>statisticsDrill(drill.metric_key,drill.offset+drill.limit));
  const ticket=statisticsState.generation;
  for(const [attribute,action] of [['statisticsReport',node=>statisticsLoadReport(node.dataset.statisticsReport)],['statisticsDrill',node=>statisticsDrill(statisticsState.report.snapshot.metrics[Number(node.dataset.statisticsDrill)].key,0)],['statisticsSource',node=>statisticsOpenSource(statisticsState.drilldown.items[Number(node.dataset.statisticsSource)])]]){
    const selector='[data-'+attribute.replace(/[A-Z]/g,c=>'-'+c.toLowerCase())+']';
    $('statisticsContent').querySelectorAll(selector).forEach(node=>{node.statisticsIntent=statisticsState.intent;node.onclick=()=>{if(node.statisticsIntent!==statisticsState.intent||ticket!==statisticsState.generation||node.disabled||!node.isConnected)return;return action(node);};});
  }
}
async function openStatistics(){
  statisticsRememberInputs();statisticsState.visible=true;statisticsState.catalog=null;statisticsState.preview=null;statisticsState.report=null;statisticsState.list=null;const current=statisticsBegin('query');
  try{
    const [rights,catalog]=await Promise.all([api('/auth/permissions'),api('/statistics/metrics')]);if(!current())return;
    statisticsState.permissions=rights.permissions;if(!statisticsCan('statistics.read')){clearStatistics();return;}
    if(!Array.isArray(catalog?.metrics)||typeof catalog.business_timezone!=='string')throw new Error('統計定義を確認できません。');
    statisticsState.catalog=catalog;
  }catch(error){statisticsError(error,current);}finally{if(current()){statisticsState.busy=false;renderStatistics();}}
}
function statisticsShowQuery(){
  statisticsRememberInputs();statisticsState.preflightRelease?.();statisticsState.generation++;statisticsState.intent++;Object.assign(statisticsState,{view:'query',busy:false,preview:null,report:null,history:null,drilldown:null,error:'',notice:'',conflict:false});renderStatistics();
}
function statisticsValidDate(value){
  if(!/^\d{4}-\d{2}-\d{2}$/.test(value))return false;
  const [year,month,day]=value.split('-').map(Number);const leap=year%4===0&&(year%100!==0||year%400===0);
  return year>0&&month>=1&&month<=12&&day>=1&&day<=[31,leap?29:28,31,30,31,30,31,31,30,31,30,31][month-1];
}
function statisticsQueryPayload(){
  const {start_date,end_date,metric_keys}=statisticsState.draft;
  if(!statisticsValidDate(start_date)||!statisticsValidDate(end_date))throw new Error('有効な開始日と終了日を入力してください。');
  if(start_date>end_date)throw new Error('終了日は開始日以降にしてください。');
  if(!metric_keys.length)throw new Error('利用可能な指標を選択してください。');
  return {start_date,end_date,metric_keys:[...metric_keys]};
}
function statisticsCheckSnapshot(snapshot){
  if(!snapshot?.period||!Array.isArray(snapshot.metrics)||snapshot.coverage_status!=='unknown'||snapshot.metrics.some(metric=>!['observed','unavailable'].includes(metric.status)||(metric.status==='observed'?typeof metric.value!=='string':metric.value!==null)||!Array.isArray(metric.exclusions)||!Array.isArray(metric.limitations)))throw new Error('観測値の応答を確認できません。');
  return snapshot;
}
function statisticsAcceptReport(report){
  if(!statisticsID(report?.report_id)||!Number.isInteger(report.version)||!['saved','confirmed'].includes(report.state))throw new Error('保存記録の応答を確認できません。');
  statisticsCheckSnapshot(report.snapshot);Object.assign(statisticsState,{report,reportID:report.report_id,view:'report',preview:null,history:null,drilldown:null,conflict:false,acknowledged:false,reviewNote:'',replacementReason:''});
}
async function statisticsQuery(save){
  if(!statisticsCan(save?'statistics.record':'statistics.read'))return;
  return statisticsAction(async current=>{
    const payload=statisticsQueryPayload();const result=await api(save?'/statistics/reports':'/statistics/query',statisticsJSON(payload));if(!current())return;
    if(save){statisticsAcceptReport(result);statisticsState.notice='元データを再取得して保存しました。保存された観測値を確認してください。';}
    else statisticsState.preview=statisticsCheckSnapshot(result);
  });
}
async function statisticsLoadList(offset=0){
  statisticsRememberInputs();statisticsState.list=null;statisticsState.report=null;const current=statisticsBegin('list');
  try{const result=await api('/statistics/reports?'+new URLSearchParams({limit:'20',offset:String(offset)}));if(current())statisticsState.list=result;}
  catch(error){statisticsError(error,current);}finally{if(current()){statisticsState.busy=false;renderStatistics();}}
}
async function statisticsLoadReport(id){
  if(!statisticsID(id))return;statisticsRememberInputs();statisticsState.reportID=id;statisticsState.report=null;statisticsState.history=null;statisticsState.drilldown=null;const current=statisticsBegin('report');
  try{const report=await api('/statistics/reports/'+encodeURIComponent(id));if(current())statisticsAcceptReport(report);}
  catch(error){statisticsError(error,current);}finally{if(current()){statisticsState.busy=false;renderStatistics();}}
}
async function statisticsConfirm(){
  if(!statisticsCan('statistics.record')||statisticsState.conflict)return;
  return statisticsAction(async current=>{
    if(!statisticsState.acknowledged)throw new Error('観測値・定義・制限を確認し、確認欄にチェックしてください。');
    const report=statisticsState.report;const result=await api('/statistics/reports/'+encodeURIComponent(report.report_id)+'/confirm',statisticsJSON({expected_version:report.version,acknowledged:true,review_note:statisticsState.reviewNote.trim()}));
    if(current()){statisticsAcceptReport(result);statisticsState.notice='観測値をHuman確認しました。網羅性はunknownのままです。';}
  });
}
async function statisticsReplace(){
  if(!statisticsCan('statistics.record')||statisticsState.conflict)return;
  return statisticsAction(async current=>{
    const reason=statisticsState.replacementReason.trim();if(!reason)throw new Error('新しい保存版を作成する理由を入力してください。');
    const report=statisticsState.report;const result=await api('/statistics/reports/'+encodeURIComponent(report.report_id)+'/replacements',statisticsJSON({expected_version:report.version,reason}));
    if(current()){statisticsAcceptReport(result);statisticsState.notice='新しい保存版を作成しました。前の保存値は変更されません。';}
  });
}
async function statisticsHistory(offset=0){
  return statisticsAction(async current=>{const result=await api('/statistics/reports/'+encodeURIComponent(statisticsState.report.report_id)+'/history?'+new URLSearchParams({limit:'20',offset:String(offset)}));if(current())statisticsState.history=result;});
}
async function statisticsDrill(metric_key,offset=0){
  return statisticsAction(async current=>{
    statisticsState.drilldown=null;
    try{
      const result=await api('/statistics/reports/'+encodeURIComponent(statisticsState.report.report_id)+'/drilldown?'+new URLSearchParams({metric_key,limit:'20',offset:String(offset)}));
      if(current())statisticsState.drilldown={...result,metric_key};
    }catch(error){
      if(!current()||error.cancelled)return;
      if(error.status===403){statisticsState.drilldown={error:'元記録の参照には別の権限が必要です。観測値は引き続き確認できます。',metric_key};return;}
      throw error;
    }
  });
}
async function statisticsDownload(format){
  if(!statisticsCan('statistics.export')||!['csv','xlsx'].includes(format))return;
  return statisticsAction(async current=>{
    const response=await fetch('/statistics/reports/'+encodeURIComponent(statisticsState.report.report_id)+'/export?format='+format);
    if(!response.ok){const body=await response.json();throw Object.assign(new Error(statisticsText(body.detail??'出力できません。')),{status:response.status});}
    const blob=await response.blob();if(!current())return;
    await window.FireAISession.check();if(!current())return;
    const filename=response.headers.get('Content-Disposition')?.match(/filename="([A-Za-z0-9._-]+)"/)?.[1];
    if(!filename||!filename.endsWith('.'+format))throw new Error('出力ファイル名を確認できません。');
    const url=URL.createObjectURL(blob),link=document.createElement('a');link.href=url;link.download=filename;document.body.append(link);
    try{link.click();}finally{link.remove();URL.revokeObjectURL(url);}
    statisticsState.notice='保存された観測値の汎用'+format.toUpperCase()+'を取得しました。';
  });
}
function statisticsNavigation(item){
  const nav=item?.navigation;if(!nav||!statisticsID(nav.id))return null;
  switch(nav.surface){
    case 'vehicle':return {open:current=>openOperations(current),detail:current=>operationsAction(()=>operationsVehicleDetail(nav.id,current)),modal:'operationsModal'};
    case 'incident':return {open:current=>openOperations(current),detail:current=>operationsAction(()=>operationsIncidentDetail(nav.id,current)),modal:'operationsModal'};
    case 'dispatch':return {open:current=>openOperations(current),detail:current=>operationsAction(()=>operationsDispatchDetail(nav.id,current)),modal:'operationsModal'};
    case 'emergency_case':return {open:current=>openEmergency(current),detail:current=>emergencyAction(()=>emergencyDetail(nav.id,current)),modal:'emergencyModal'};
    default:return null;
  }
}
async function statisticsOpenSource(item){
  const navigation=statisticsNavigation(item);if(!navigation)return;
  return statisticsAction(async current=>{
    let interrupted=false;const owned=()=>current()&&!interrupted;
    const interrupt=event=>{if(event.target?.closest?.('button, a, input, select, textarea, form, summary, [onclick]'))interrupted=true;};
    const events=['click','change','submit'];for(const event of events)window.addEventListener(event,interrupt,true);
    try{
      await window.FireAISession.check();if(!owned())return;
      // Keep the existing original-record screen above this statistics dialog.
      await navigation.open(owned);if(!owned())return;
      const modal=$(navigation.modal);const live=()=>owned()&&modal?.isConnected&&$(navigation.modal)===modal&&!modal.classList.contains('hidden');
      if(!live())return;modal.style.zIndex='75';await window.FireAISession.check();if(!live())return;
      await navigation.detail(live);
    }finally{for(const event of events)window.removeEventListener(event,interrupt,true);}
  });
}
// Dismiss at the user's navigation intent, before SharedSession awaits its
// authority check. A late response cannot repaint during that preflight gap.
window.addEventListener('click',event=>{
  if(!statisticsState.visible)return;const target=event.target?.closest?.('button, a, [onclick]');if(!target)return;
  if(target.id==='statisticsBack'){statisticsShowQuery();return;}
  if(target.id==='statisticsClose'||(target.closest?.('header')&&target.id!=='statisticsBtn'))closeStatistics();
},true);
window.addEventListener('popstate',()=>{if(statisticsState.visible)closeStatistics();});

// The shared guard calls this synchronously after accepting the original click,
// then releases it before redispatch. Keep that exact node connected throughout.
function statisticsSessionPreflight(target,eventType){
  const entry=target?.id==='statisticsBtn';
  if(eventType!=='click'||target?.tagName!=='BUTTON'||(!entry&&(!statisticsState.visible||!target.closest?.('#statisticsModal')))||target.id==='statisticsClose')return ()=>{};
  statisticsRememberInputs();statisticsState.preflightRelease?.();
  const intent=++statisticsState.intent,ticket=statisticsState.generation;
  target.statisticsIntent=intent;statisticsState.busy=true;
  if(entry){Object.assign(statisticsState,{visible:true,view:'query',catalog:null,preview:null,report:null,list:null,error:'',notice:''});renderStatistics();}
  const modal=$('statisticsModal');
  const disabled=Array.from($('statisticsContent').querySelectorAll('button, input, select, textarea')).map(node=>[node,node.disabled]);
  if(entry)disabled.push([target,target.disabled]);
  for(const [node] of disabled)if(!['statisticsBack','statisticsSaved'].includes(node.id)&&!node.dataset.statisticsReport)node.disabled=true;
  modal.setAttribute('aria-busy','true');if($('statisticsStatus'))$('statisticsStatus').textContent='権限を確認中…';
  let released=false;const release=()=>{
    if(released)return;released=true;
    if(statisticsState.preflightRelease!==release||ticket!==statisticsState.generation||intent!==statisticsState.intent||$('statisticsModal')!==modal)return;
    statisticsState.preflightRelease=null;statisticsState.busy=false;
    for(const [node,value] of disabled)if(node.isConnected)node.disabled=value;
    modal.setAttribute('aria-busy','false');if($('statisticsStatus'))$('statisticsStatus').textContent='';
  };
  statisticsState.preflightRelease=release;return release;
}
window.statisticsSessionPreflight=statisticsSessionPreflight;
