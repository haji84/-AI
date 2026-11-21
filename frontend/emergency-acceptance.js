'use strict';
(()=>{
  const $=id=>document.getElementById(id), base='/emergency/acceptance';
  const required=['emergency.case.read','emergency.patient.read','emergency.report.read'];
  const targetFields=[['targetCorrection','correction_reduction_percent',1,100],['targetRecall','recall',100,100],['targetFalseAlerts','false_alerts_per_report',1,null],['targetTime','time_reduction_percent',1,100],['targetReadAccuracy','read_state_accuracy',100,100],['minimumReports','minimum_reports_per_cohort',1,null],['minimumErrors','minimum_true_errors',1,null]];
  const gates={protocol:'評価計画・比較条件',current_rules:'現行正式ルール',form_mapping:'帳票と入力欄の対応',real_reading:'実帳票の読取評価',correction_loop:'訂正から再チェックの実操作',network_egress:'外部通信の確認',access_control:'権限と本部分離',protected_storage:'保存・暗号化・原本分離',logs_and_cache:'ログ・一時ファイル・キャッシュ',restore:'バックアップと復元'};
  const statuses={NOT_MEASURED:'未測定',INSUFFICIENT_DATA:'データ不足',TARGET_UNSET:'目標未設定',PENDING:'判定保留',NOT_MET:'目標未達',MET:'数値目標を達成'};
  const blockerLabels={
    DEVELOPMENT_ONLY:'合成データのため実運用の成果は未測定です。',
    NO_MEASUREMENTS:'測定記録がまだありません。',
    TARGETS_UNSET:'数値目標が未設定です。',
    SAMPLE_MINIMUMS_UNSET:'最低件数が未設定です。',
    COMPARISON_NOT_CONFIRMED:'導入前後の比較条件が未確認です。',
    HOLDOUT_NOT_CONFIRMED:'学習に使用していない評価データか未確認です。',
    FOLLOWUP_WINDOW_UNSET:'提出後の追跡期間が未設定です。',
    PENDING_FOLLOWUP:'提出後の追跡が終わっていない、または訂正の有無が未確定の報告書があります。',
    INCOMPLETE_INDEPENDENT_REVIEW:'別担当者による正解確認が未完了の報告書、または検査項目のない報告書があります。',
    UNKNOWN_TRUTH:'正しい記載か実際の誤りか、確定していない検査項目があります。',
    READ_STATES_UNVERIFIED:'読取状態の独立確認が終わっていません。',
    UNSAFE_CLEAR:'読取不能・未確認などの項目を、誤って「問題なし」と表示した記録があります。',
    WORK_TIME_MISSING:'合計作業時間の計測または追跡が未完了です。',
    CORRECTION_REDUCTION_UNDEFINED:'導入前の訂正率が0、または比較データが不足しているため、相対削減率は算出できません。',
    TIME_REDUCTION_UNDEFINED:'導入前の作業時間が0、または比較データが不足しているため、時間の相対削減率は算出できません。',
    INSUFFICIENT_SAMPLE:'設定した最低件数に達していない指標があります。',
    NUMERIC_TARGETS_NOT_MET:'設定した数値目標に達していない指標があります。',
    PRIVACY_EVIDENCE_REQUIRED:'個人情報保護の実環境での証拠が必要です。',
    RULE_APPROVAL_REQUIRED:'現行正式ルールの承認が必要です。',
    FORM_APPROVAL_REQUIRED:'帳票と入力欄の対応確認が必要です。',
    ENVIRONMENT_APPROVAL_REQUIRED:'利用環境の検証と承認が必要です。'
  };
  const state={generation:0,intent:0,historyIntent:0,permissions:new Set(),payload:null,summary:null,selected:null,requestId:null,supersedes:null,evidence:[],busy:false,offset:0,history:[]};
  const canRead=()=>required.every(x=>state.permissions.has(x));
  const canSave=()=>canRead()&&state.permissions.has('emergency.report.create');
  const canReview=()=>canRead()&&state.permissions.has('emergency.report.review')&&state.selected?.status==='recorded'&&state.selected?.can_review===true&&!state.selected?.superseded_by;
  const snapshot=()=>({generation:state.generation,intent:state.intent});
  const current=t=>t.generation===state.generation&&t.intent===state.intent;
  const num=v=>typeof v==='number'&&Number.isFinite(v)?v.toLocaleString('ja-JP',{maximumFractionDigits:2}):'未測定';
  const percent=v=>typeof v==='number'&&Number.isFinite(v)?num(v*100)+'%':'未測定';
  const absolutePercent=v=>typeof v==='number'&&Number.isFinite(v)?num(v)+'%':'算出できません';
  function message(id,text,error=false){$(id).textContent=text;$(id).classList.toggle('error',error);}
  function controls(){
    const ready=canRead()&&!state.busy;
    for(const id of ['sampleButton','newButton','measurementFile','refreshHistory'])$(id).disabled=!ready;
    for(const [id]of targetFields)$(id).disabled=!ready||!state.payload||!!state.selected;
    $('recalculateButton').disabled=!ready||!state.payload||!!state.selected;
    $('saveButton').disabled=!ready||!canSave()||!state.summary||!!state.selected;
    $('reviseButton').hidden=!state.selected;$('reviseButton').disabled=!ready||!canSave()||!state.selected?.measurement||!!state.selected?.superseded_by;
    $('previousHistory').disabled=!ready||state.offset===0;$('nextHistory').disabled=!ready||state.history.length<30;
    for(const id of ['reviewAcknowledgement','evidenceGate','evidenceResult'])$(id).disabled=!ready||!canReview();
    const documents=ready&&canReview()&&state.permissions.has('document.read');
    for(const id of ['evidenceDocument','addEvidence','clearEvidence'])$(id).disabled=!documents;
    for(const id of ['confirmReview','rejectReview'])$(id).disabled=!ready||!canReview()||!$('reviewAcknowledgement').checked;
  }
  function clearResults(){
    state.payload=null;state.summary=null;state.selected=null;state.requestId=null;state.supersedes=null;state.evidence=[];
    $('resultsPanel').hidden=true;$('savedPanel').hidden=true;$('metricCards').replaceChildren();$('blockerList').replaceChildren();$('releaseGates').replaceChildren();$('evidenceDrafts').replaceChildren();
    $('measurementFile').value='';$('evidenceDocument').value='';$('reviewAcknowledgement').checked=false;
    for(const[id]of targetFields)$(id).value='';
    for(const id of ['inputMessage','selectionStatus','reviewMessage','summaryState','cohortCounts'])message(id,'');
    $('syntheticBanner').hidden=true;controls();
  }
  function reset(){
    state.generation++;state.intent++;state.historyIntent++;state.permissions=new Set();state.busy=false;state.history=[];state.offset=0;
    clearResults();$('historyList').replaceChildren();message('historyMessage','');message('pageMessage','セッションまたは権限が変わりました。ホームから再ログインしてください。',true);controls();
  }
  window.FireAISession.install({reset});
  function newIntent(){state.intent++;state.busy=false;clearResults();return snapshot();}
  async function request(path,method='GET',body){
    let response;
    try{response=await fetch(path,{method,cache:'no-store',...(body===undefined?{}:{headers:{'Content-Type':'application/json'},body:JSON.stringify(body)})});}
    catch(error){if(error.cancelled)throw error;throw Object.assign(new Error('通信できませんでした。接続を確認して、もう一度操作してください。'),{safe:true});}
    if(!response.ok){
      if(response.status===401||response.status===403){reset();throw Object.assign(new Error('セッションまたは権限を確認できません。ホームから再ログインしてください。'),{safe:true});}
      const texts={409:'記録の版・確認者・再送内容が一致しません。履歴を再読込して確認してください。',413:'測定記録が大きすぎます。2 MB以下の所定の記録を使用してください。',422:'測定記録の形式や数値を確認してください。患者情報や任意の項目は取り込めません。',503:'現在は処理できません。時間を置いてもう一度操作してください。'};
      throw Object.assign(new Error(texts[response.status]||'処理を完了できませんでした。権限と利用環境を確認してください。'),{safe:true});
    }
    try{return await response.json();}catch(error){if(error.cancelled)throw error;throw Object.assign(new Error('応答を確認できませんでした。もう一度操作してください。'),{safe:true});}
  }
  function fail(id,error,t){if(current(t)&&!error.cancelled)message(id,error.safe?error.message:'処理を完了できませんでした。測定記録を確認してやり直してください。',true);}
  function fillTargets(payload){for(const[id,key,scale]of targetFields){const v=payload.targets?.[key];$(id).value=typeof v==='number'&&Number.isFinite(v)?String(v*scale):'';}}
  function readTargets(){const result={};for(const[id,key,scale,max]of targetFields){const value=$(id).value.trim();if(!value){result[key]=null;continue;}const n=Number(value),integer=key.startsWith('minimum_');if(!Number.isFinite(n)||n<0||(max!==null&&n>max)||(integer&&(!Number.isInteger(n)||n<1)))throw Object.assign(new Error('目標は有効な数値、最低件数は1以上の整数で入力してください。'),{safe:true});result[key]=n/scale;}return result;}
  function line(list,label,value){const dt=document.createElement('dt'),dd=document.createElement('dd');dt.textContent=label;dd.textContent=value;list.append(dt,dd);}
  function card(title,value,status,rows,note=''){const article=document.createElement('article');article.className='metric';const heading=document.createElement('h3');heading.className='metric-title';heading.textContent=title;const badge=document.createElement('span');badge.className='badge'+(status==='MET'?' met':status==='NOT_MET'?' warn':'');badge.textContent=statuses[status]||'判定保留';const number=document.createElement('p');number.className='metric-value';number.textContent=value;const dl=document.createElement('dl');for(const[label,v]of rows)line(dl,label,v);article.append(heading,badge,number);if(note){const warning=document.createElement('p');warning.className='small muted';warning.textContent=note;article.append(warning);}article.append(dl);$('metricCards').append(article);}
  function renderSummary(summary){
    const m=summary.metrics||{},c=m.corrections||{},r=m.recall||{},f=m.false_alerts||{},t=m.time||{},s=m.read_states||{};
    $('resultsPanel').hidden=false;$('syntheticBanner').hidden=summary.dataset_kind!=='synthetic';
    $('syntheticBanner').textContent='合成データの操作確認です。実測値ではありません。';
    $('summaryState').textContent=summary.status==='DEVELOPMENT_ONLY'?'開発検証のみ・実運用の成果は未測定':summary.status==='NUMERIC_TARGETS_MET'?'数値目標の範囲で達成・受入の証拠確認が必要':'評価未完了・不足している条件を確認してください';
    $('metricCards').replaceChildren();
    card('1. 提出後の訂正率',percent(c.assisted?.rate),c.status,[['導入前',percent(c.baseline?.rate)],['導入後の訂正／観察完了',num(c.assisted?.numerator)+' / '+num(c.assisted?.denominator)+' 件'],['導入前の訂正／観察完了',num(c.baseline?.numerator)+' / '+num(c.baseline?.denominator)+' 件'],['相対削減率',absolutePercent(c.reduction_percent)],['差（導入前−導入後）',typeof c.percentage_points==='number'?num(c.percentage_points)+' ポイント':'未測定'],['追跡中・未確定（前／後）',num(c.baseline?.pending)+' / '+num(c.assisted?.pending)+' 件']]);
    card('2. 提出前の誤り発見率'+(r.unresolved>0?'（正解確認済みの範囲）':''),percent(r.rate),r.status,[['発見／実際の誤り',num(r.detected_errors)+' / '+num(r.actual_errors)+' 件'],['正解や独立確認が未確定',num(r.unresolved)+' 件'],['提出後に出た警告',num(r.late_warnings)+' 件']],r.unresolved>0?'未確定分を含む全体の発見率は未測定です。':'');
    card('3. 正しい記載への誤警告',typeof f.per_report==='number'?num(f.per_report)+' 件／報告書':'未測定',f.status,[['誤警告数',num(f.count)+' 件'],['独立評価した報告書',num(f.reviewed_reports)+' 件'],['警告中の誤警告割合',percent(f.false_fraction)],['警告等の評価が未確定',num(f.unresolved)+' 件']],f.unresolved>0?'確認できた誤警告の暫定値です。未確定分により増える可能性があります。':'');
    card('4. 合計作業時間',typeof t.assisted?.mean_minutes==='number'?num(t.assisted.mean_minutes)+' 人・分／報告書':'未測定',t.status,[['導入前の平均',num(t.baseline?.mean_minutes)+' 人・分'],['中央値（前／後）',num(t.baseline?.median_minutes)+' / '+num(t.assisted?.median_minutes)+' 人・分'],['計測済み（前／後）',num(t.baseline?.reports)+' / '+num(t.assisted?.reports)+' 件'],['欠測（前／後）',num(t.baseline?.missing)+' / '+num(t.assisted?.missing)+' 件'],['相対削減率',absolutePercent(t.reduction_percent)]]);
    card('5. 読取・未検査の区別と保護',percent(s.accuracy),s.status,[['読取状態の一致／確認済み',num(s.matched)+' / '+num(s.verified)+' 件'],['読取不能',num(s.unreadable)+' 件'],['未検査',num(s.unchecked)+' 件'],['誤って「問題なし」とした項目',num(s.unsafe_clear)+' 件'],['状態の独立確認が未確定',num(s.unresolved)+' 件'],['個人情報の保護', '実環境の証拠を別途確認']]);
    $('blockerList').replaceChildren();const labels=new Set((summary.blockers||[]).map(code=>blockerLabels[code]||'測定または受入の条件が未確認です。詳細は評価担当者が確認してください。'));
    labels.add('現行正式ルール・帳票対応・実帳票の読取・訂正操作・情報保護・復元の証拠は、下記で別に確認します。');
    for(const text of labels){const li=document.createElement('li');li.textContent=text;$('blockerList').append(li);}
    const counts=summary.counts||{};
    $('cohortCounts').replaceChildren();const countText=document.createElement('p');
    countText.textContent='測定記録：導入前 '+num(counts.baseline_reports)+' 件／導入後 '+num(counts.assisted_reports)+' 件。事案・帳票の構成が異なる場合は単純に比較できません。';$('cohortCounts').append(countText);
    const categories={activity_kind:{transport:'搬送',nontransport:'不搬送',transfer:'転院',unknown:'事案区分不明'},document_kind:{text_pdf:'文字を取り出せるPDF',image_pdf:'画像PDF',photo:'写真',mixed:'混在',unknown:'帳票区分不明'}};
    for(const [kind,names]of Object.entries(categories)){
      const table=document.createElement('table');table.className='strata';const caption=document.createElement('caption');caption.textContent=kind==='activity_kind'?'事案の構成':'帳票の構成';table.append(caption);
      const head=document.createElement('tr');for(const label of ['区分','導入前','導入後']){const th=document.createElement('th');th.textContent=label;head.append(th);}table.append(head);
      for(const[key,label]of Object.entries(names)){const row=document.createElement('tr');for(const value of [label,num(counts.strata?.baseline?.[kind]?.[key]),num(counts.strata?.assisted?.[kind]?.[key])]){const cell=document.createElement('td');cell.textContent=value;row.append(cell);}table.append(row);}$('cohortCounts').append(table);
    }
  }
  function renderEvidence(record){
    $('savedPanel').hidden=false;$('releaseGates').replaceChildren();
    for(const[gate,label]of Object.entries(gates)){const found=record.release_gates?.find(x=>x.gate===gate);const li=document.createElement('li'),name=document.createElement('div'),status=document.createElement('span');name.textContent=label;status.textContent=found?.status==='RECORDED_PASS'?'合格の証拠を登録':found?.status==='RECORDED_FAIL'?'未達の証拠を登録':'未登録';li.append(name,status);$('releaseGates').append(li);}
    state.evidence=[];$('evidenceDrafts').replaceChildren();$('reviewAcknowledgement').checked=false;$('evidenceDocument').value='';
    message('reviewMessage',record.superseded_by?'新しい評価版があるため、この版は確認できません。履歴から最新の評価版を選択してください。':record.status==='reviewed'?(record.review_decision==='confirmed'?'評価記録の確認済みです。本番導入の承認ではありません。':'評価記録は差し戻されています。訂正用の新しい版を作成してください。'):canReview()?'作成者とは別の担当者が内容を確認できます。':'作成者とは別の確認権限を持つ担当者による確認が必要です。');
  }
  async function preview(payload,t){
    const summary=await request(base+'/preview','POST',payload);if(!current(t))return;
    state.payload=payload;state.summary=summary;state.requestId=crypto.randomUUID();fillTargets(payload);renderSummary(summary);message('inputMessage','測定内容を検証しました。数値と不足している条件を確認してください。');controls();
  }
  async function sample(){
    const t=newIntent();state.busy=true;controls();message('inputMessage','合成データを読み込んでいます。');
    try{const payload=await request(base+'/sample');if(current(t))await preview(payload,t);}catch(e){fail('inputMessage',e,t);}finally{if(current(t)){state.busy=false;controls();}}
  }
  async function importFile(){
    const file=$('measurementFile').files?.[0],supersedes=state.supersedes,t=newIntent();state.supersedes=supersedes;if(!file)return;state.busy=true;controls();message('inputMessage','測定記録の形式を確認しています。');
    try{if(file.size>2*1024*1024||!file.name.toLowerCase().endsWith('.json'))throw Object.assign(new Error('2 MB以下の所定のJSON測定記録を選択してください。'),{safe:true});const text=await file.text();if(!current(t))return;let payload;try{payload=JSON.parse(text);}catch{throw Object.assign(new Error('JSON形式の測定記録を読み取れませんでした。作成元で形式を確認してください。'),{safe:true});}await preview(payload,t);}catch(e){fail('inputMessage',e,t);}finally{if(current(t)){state.busy=false;$('measurementFile').value='';controls();}}
  }
  async function recalculate(){
    if(state.busy||!state.payload||state.selected)return;const t=snapshot();state.busy=true;controls();
    try{const payload={...state.payload,targets:readTargets()};state.summary=null;state.requestId=null;$('resultsPanel').hidden=true;await preview(payload,t);}catch(e){fail('inputMessage',e,t);}finally{if(current(t)){state.busy=false;controls();}}
  }
  async function history(){
    if(!canRead())return;const generation=state.generation,ticket=++state.historyIntent,offset=state.offset;
    try{const rows=await request(base+'/evaluations?limit=30&offset='+offset);if(generation!==state.generation||ticket!==state.historyIntent)return;state.history=rows;$('historyList').replaceChildren();
      for(const record of rows){const button=document.createElement('button');button.type='button';button.className='history-item'+(state.selected?.evaluation_id===record.evaluation_id?' selected':'');button.dataset.evaluationId=record.evaluation_id;const title=document.createElement('strong'),info=document.createElement('span');const date=new Date(record.created_at);title.textContent=Number.isNaN(date.getTime())?'評価記録':date.toLocaleString('ja-JP',{timeZone:'Asia/Tokyo',month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit'});info.textContent=(record.dataset_kind==='synthetic'?'合成データ':'本部内実測')+' / '+(record.status==='reviewed'?(record.review_decision==='confirmed'?'記録確認済み':'差し戻し'):'確認待ち');button.append(title,info);button.onclick=()=>selectRecord(record.evaluation_id);$('historyList').append(button);}
      message('historyMessage',rows.length?'新しい記録から表示しています。':'保存済みの評価記録はありません。');controls();
    }catch(e){if(generation===state.generation&&ticket===state.historyIntent&&!e.cancelled)message('historyMessage','履歴を取得できませんでした。権限と接続を確認してください。',true);}
  }
  async function selectRecord(id){
    if(state.busy)return;const t=newIntent();state.busy=true;controls();message('inputMessage','保存した評価記録を読み込んでいます。');
    try{const record=await request(base+'/evaluations/'+encodeURIComponent(id));if(!current(t))return;state.selected=record;state.payload=record.measurement||null;state.summary=record.summary;fillTargets(state.payload||{});renderSummary(record.summary);renderEvidence(record);message('selectionStatus','保存済みの評価記録・版 '+num(record.version));message('inputMessage','保存した時点の測定です。訂正するときは新しい版を作成します。');}catch(e){fail('inputMessage',e,t);}finally{if(current(t)){state.busy=false;controls();}}
  }
  async function save(){
    if(state.busy||!canSave()||!state.summary||!state.payload||state.selected)return;const t=snapshot();state.busy=true;controls();message('selectionStatus','評価記録を保存しています。');
    try{state.requestId??=crypto.randomUUID();const record=await request(base+'/evaluations','POST',{request_id:state.requestId,measurement:state.payload,supersedes_id:state.supersedes?.evaluation_id??null,expected_previous_version:state.supersedes?.version??null});if(!current(t))return;state.selected={...record,measurement:state.payload};state.summary=record.summary;renderSummary(record.summary);renderEvidence(record);message('selectionStatus','評価記録を保存しました。提出許可・本番完成の判定ではありません。');state.offset=0;await history();}catch(e){fail('selectionStatus',e,t);}finally{if(current(t)){state.busy=false;controls();}}
  }
  function revise(){
    if(state.busy||!canSave()||!state.selected?.measurement||state.selected.superseded_by)return;const previous=state.selected,payload=structuredClone(previous.measurement);newIntent();state.payload=payload;state.supersedes={evaluation_id:previous.evaluation_id,version:previous.version};fillTargets(payload);message('inputMessage','訂正用の新しい版です。訂正した測定記録を取り込むか、目標を変更して再計算してください。以前の評価は残ります。');controls();
  }
  function addEvidence(){
    if(!canReview()||!state.permissions.has('document.read'))return;const documentId=$('evidenceDocument').value.trim(),gate=$('evidenceGate').value,result=$('evidenceResult').value;
    if(!Object.hasOwn(gates,gate)||!['passed','failed'].includes(result)||!/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(documentId)){message('reviewMessage','登録済み文書のUUIDと確認項目を指定してください。',true);return;}
    state.evidence=state.evidence.filter(x=>x.gate!==gate);state.evidence.push({gate,document_id:documentId,result});$('evidenceDrafts').replaceChildren();for(const item of state.evidence){const li=document.createElement('li');li.textContent=gates[item.gate]+'：'+(item.result==='passed'?'合格として記録予定':'未達として記録予定');$('evidenceDrafts').append(li);}$('evidenceDocument').value='';message('reviewMessage','確認時に添付する証拠を追加しました。まだ保存されていません。');
  }
  async function review(decision){
    if(state.busy||!canReview()||!$('reviewAcknowledgement').checked)return;const t=snapshot(),record=state.selected;state.busy=true;controls();
    try{const updated=await request(base+'/evaluations/'+encodeURIComponent(record.evaluation_id)+'/review','POST',{expected_version:record.version,decision,evidence:state.evidence});if(!current(t))return;state.selected={...updated,measurement:record.measurement};renderEvidence(updated);message('selectionStatus',decision==='confirmed'?'評価記録の確認を保存しました。':'評価記録を差し戻しました。');await history();}catch(e){fail('reviewMessage',e,t);}finally{if(current(t)){state.busy=false;controls();}}
  }
  $('sampleButton').onclick=sample;$('measurementFile').addEventListener('change',importFile);$('newButton').onclick=()=>{newIntent();controls();};$('recalculateButton').onclick=recalculate;$('saveButton').onclick=save;$('reviseButton').onclick=revise;
  $('refreshHistory').onclick=history;$('previousHistory').onclick=()=>{state.offset=Math.max(0,state.offset-30);return history();};$('nextHistory').onclick=()=>{state.offset+=30;return history();};
  $('addEvidence').onclick=addEvidence;$('clearEvidence').onclick=()=>{state.evidence=[];$('evidenceDrafts').replaceChildren();$('evidenceDocument').value='';};$('reviewAcknowledgement').addEventListener('change',controls);$('confirmReview').onclick=()=>review('confirmed');$('rejectReview').onclick=()=>review('rejected');
  for(const[id]of targetFields)$(id).addEventListener('input',()=>{if(state.selected)return;state.intent++;state.summary=null;state.requestId=null;state.busy=false;$('resultsPanel').hidden=true;message('inputMessage','目標を変更しました。再計算すると新しい結果を確認できます。');controls();});
  (async()=>{const generation=state.generation;try{const data=await request('/auth/context');if(generation!==state.generation)return;state.permissions=new Set(data.permissions||[]);if(!canRead()){reset();message('pageMessage','この評価画面を表示する権限がありません。管理者に確認してください。',true);return;}message('pageMessage','本部内の測定記録を扱います。未測定の性能は達成扱いにしません。');controls();await history();}catch(e){if(generation===state.generation&&!e.cancelled){reset();message('pageMessage','ログインと権限を確認できません。ホームからログインしてください。',true);}}})();
})();
