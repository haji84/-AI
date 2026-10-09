'use strict';

// The queue holds only source pointers. Existing module screens and the server
// remain authoritative for each record and every operation on it.
const workQueueState={generation:0,navigation:0,visible:false,scope:'all',offset:0,limit:50,data:null,loading:false,error:'',opening:false};
const workQueueRelations={created_by_me:'自分が作成',borrowed_by_me:'自分が借用',available_to_my_role:'権限に応じた業務',shared_deadline:'共通の期限'};
const workQueueModules={operational_assets:'資機材・在庫',fleet:'車両',violations:'違反・改善措置',inquiries:'議会・照会',budget:'財務・予算',hazardous_materials:'危険物'};
const workQueueKinds={pressure_test:'耐圧試験',use:'使用期限',calibration:'校正',service:'点検・整備',expiry:'ロット期限',loan_return:'返却予定',inspection:'車両点検',service_mileage:'走行距離による整備',unresolved_fault:'未解消の故障',corrective_action:'改善措置',draft:'下書き・未正式承認',review:'Human根拠確認',approval:'Human正式承認',evidence_review:'原本・根拠確認',hazardous_deadline:'記録の期限',evaluation_review:'評価候補のHuman確認',evaluation_refresh:'評価候補の再作成'};

function hideWorkQueue(){
  workQueueState.generation++;workQueueState.navigation++;
  Object.assign(workQueueState,{visible:false,data:null,loading:false,error:'',opening:false});
  const panel=$('workQueuePanel');
  if(panel){panel.innerHTML='';panel.classList.add('hidden');panel.setAttribute('aria-busy','false');}
}
function clearWorkQueue(){
  hideWorkQueue();Object.assign(workQueueState,{scope:'all',offset:0});
  $('workQueueBtn')?.classList.add('hidden');
}
async function initWorkQueue(){
  const ticket=workQueueState.generation;
  await window.FireAISession.check();
  if(ticket!==workQueueState.generation)return;
  const button=$('workQueueBtn');
  if(button){button.onclick=()=>openWorkQueue();button.classList.remove('hidden');}
}
function workQueueEnsureCurrent(owned){if(!owned())throw Object.assign(new Error('画面が変更されました'),{cancelled:true});}
function workQueueNavigation(item){
  const nav=item?.navigation;
  if(!nav||typeof nav.id!=='string'||!/^[A-Za-z0-9_-]{1,128}$/.test(nav.id))return null;
  // Never accept a URL, function name, or executable handler from the response.
  switch(nav.surface){
    case 'hazardous_installation':return {open:owned=>hazardousAction(()=>openHazardous(owned)),detail:owned=>hazardousAction(()=>item.source_type==='hazardous_record'&&typeof item.source_id==='string'&&/^[A-Za-z0-9_-]{1,128}$/.test(item.source_id)?hazardousRecordDetail(nav.id,item.source_id,owned):hazardousDetail(nav.id,owned)),modal:'hazardousModal'};
    case 'hazardous_evaluation':return {open:owned=>hazardousAction(()=>openHazardous(owned)),detail:owned=>hazardousAction(()=>hazardousEvaluationDetail(nav.id,owned)),modal:'hazardousModal'};
    case 'asset':return {open:owned=>openAssets(owned),detail:owned=>assetsAction(()=>assetsDetail(nav.id,'',owned)),modal:'assetsModal'};
    case 'vehicle':return {open:owned=>openOperations(owned),detail:owned=>operationsAction(()=>operationsVehicleDetail(nav.id,owned)),modal:'operationsModal'};
    case 'violation':return {open:owned=>violationAction(async()=>{await openViolations(owned);workQueueEnsureCurrent(owned);}),detail:owned=>violationAction(async()=>{await violationDetail(nav.id,owned);workQueueEnsureCurrent(owned);}),modal:'violationModal'};
    case 'inquiry':return {open:owned=>openInquiries(owned),detail:owned=>inquiryAction(()=>inquiryDetail(nav.id,owned)),modal:'inquiryModal'};
    case 'finance_proposal':return {open:owned=>openFinance(owned),detail:owned=>financeAction(()=>financeProposalDetail(nav.id,owned)),modal:'financeModal'};
    default:return null;
  }
}
function workQueueCard(item,index){
  const due=item.due_on?(item.overdue?'期限超過':item.due_on===workQueueState.data.as_of?'本日期限':'期限')+' '+item.due_on:'日付の期限なし';
  const relations=(item.relationships??[]).filter(key=>Object.hasOwn(workQueueRelations,key));
  return `<article class="card" style="margin:12px 0;padding:16px"><div class="muted">${esc(workQueueModules[item.module]??item.module)} / ${esc(workQueueKinds[item.kind]??item.kind)}</div><h3>${esc(item.title)}</h3><p${item.overdue?' class="dangerText"':''}>${esc(due)} / 状態: ${esc(item.status)}</p><p>${relations.map(key=>`<span class="pill">${esc(workQueueRelations[key])}</span>`).join(' ')}</p><div class="toolbar"><button type="button" class="btn" data-work-queue-open="${index}"${!workQueueNavigation(item)||workQueueState.opening?' disabled':''}>元記録を開く</button><span class="muted">元記録 Version ${esc(item.source_version)}</span></div></article>`;
}
function renderWorkQueue(){
  const panel=$('workQueuePanel');if(!panel||!workQueueState.visible)return;
  const {data,scope,loading,error,opening}=workQueueState;
  panel.classList.remove('hidden');panel.setAttribute('aria-busy',String(loading||opening));
  panel.innerHTML='<div class="toolbar"><h2>今日の業務</h2><span class="grow"></span><label>表示範囲 <select id="workQueueScope"><option value="all">権限内のすべて</option><option value="related">自分が作成・借用したもの</option></select></label><button type="button" class="btn" id="workQueueRefresh">再読込</button></div>'+
    '<p class="muted">資機材・車両・危険物の期限、改善措置、照会・財務・危険物の確認待ちを表示します。作成者・借用者との関係を示し、元記録で詳細を確認できます。</p>'+
    (loading?'<p role="status">読み込み中…</p>':error?`<p class="dangerText" role="alert">業務一覧を取得できません。再読込してください。 ${esc(error)}</p>`:data?`<p>基準日 ${esc(data.as_of)} / 期限の表示範囲 ～ ${esc(data.through)} (${esc(data.business_timezone)})</p><p id="workQueueCount">${data.total}件${data.items.length?' / '+(data.offset+1)+'～'+(data.offset+data.items.length)+'件を表示':''}</p>${data.items.length?data.items.map(workQueueCard).join(''):data.total?'<p role="status">このページの業務はありません。前のページへ戻るか、再読込してください。</p>':'<p role="status">対象の業務はありません。</p>'}<div class="toolbar"><button type="button" class="btn" id="workQueuePrev"${data.offset===0||opening?' disabled':''}>前へ</button><button type="button" class="btn" id="workQueueNext"${data.offset+data.items.length>=data.total||opening?' disabled':''}>次へ</button></div>`:'')+
    (opening?'<p role="status">元記録を開いています…</p>':'');
  $('workQueueScope').value=scope;
  $('workQueueScope').onchange=()=>{workQueueState.scope=$('workQueueScope').value==='related'?'related':'all';return loadWorkQueue(0);};
  $('workQueueRefresh').onclick=()=>loadWorkQueue(0);
  if($('workQueuePrev'))$('workQueuePrev').onclick=()=>loadWorkQueue(Math.max(0,data.offset-data.limit));
  if($('workQueueNext'))$('workQueueNext').onclick=()=>loadWorkQueue(data.offset+data.limit);
  const ticket=workQueueState.generation;
  panel.querySelectorAll('[data-work-queue-open]').forEach(button=>{
    const item=data.items[Number(button.dataset.workQueueOpen)];
    button.onclick=()=>openWorkQueueSource(item,ticket);
  });
}
async function loadWorkQueue(offset=0){
  const ticket=++workQueueState.generation;
  workQueueState.navigation++;
  Object.assign(workQueueState,{offset,data:null,loading:true,error:'',opening:false});
  renderWorkQueue();
  const current=()=>ticket===workQueueState.generation&&workQueueState.visible;
  try{
    const data=await api('/work-queue?'+new URLSearchParams({scope:workQueueState.scope,limit:String(workQueueState.limit),offset:String(offset)}));
    if(!current())return;
    if(data?.schema_version!=='work-queue-v1'||!Array.isArray(data.items)||!Number.isInteger(data.total)||data.total<0||data.offset!==offset||data.limit!==workQueueState.limit||data.scope!==workQueueState.scope)throw new Error('業務一覧の応答を確認できません。');
    workQueueState.data=data;
  }catch(error){
    if(!current()||error.cancelled)return;
    workQueueState.error=error.status===404?'この業務一覧は現在利用できません。':String(error.message);
  }finally{
    if(current()){workQueueState.loading=false;renderWorkQueue();}
  }
}
async function openWorkQueue(){
  window.beginMainNavigation?.();
  $('detailView')?.classList.add('hidden');$('noSelection')?.classList.add('hidden');
  workQueueState.visible=true;
  await loadWorkQueue(0);
}
async function openWorkQueueSource(item,ticket){
  const navigation=workQueueNavigation(item);
  if(!navigation||ticket!==workQueueState.generation||!workQueueState.visible||workQueueState.opening)return;
  const operation=++workQueueState.navigation;
  const owned=()=>ticket===workQueueState.generation&&operation===workQueueState.navigation&&workQueueState.visible;
  let interrupted=false;
  const current=()=>owned()&&!interrupted;
  // User intent must supersede the queued detail before the shared-session
  // document guard awaits authority and redispatches the newer interaction.
  const interrupt=event=>{if(event.target?.closest?.('button, a, input, select, textarea, form, summary, [onclick]'))interrupted=true;};
  const events=['click','change','submit'];
  for(const event of events)window.addEventListener(event,interrupt,true);
  workQueueState.opening=true;renderWorkQueue();
  try{
    await window.FireAISession.check();if(!current())return;
    await navigation.open(current);if(!current())return;
    const modal=$(navigation.modal);
    const liveModal=()=>modal?.isConnected&&$(navigation.modal)===modal&&!modal.classList.contains('hidden');
    if(!liveModal())return;
    await window.FireAISession.check();if(!current()||!liveModal())return;
    await navigation.detail(()=>current()&&liveModal());
  }catch(error){
    if(current()&&!error.cancelled){workQueueState.data=null;workQueueState.error='元記録を開けません。 '+String(error.message);}
  }finally{
    for(const event of events)window.removeEventListener(event,interrupt,true);
    if(owned()){workQueueState.opening=false;renderWorkQueue();}
  }
}
