// Human team grouping reuses workforce session and canonical personnel history.
async function workforceTeamAPI(url,options={}){
  const generation=workforceState.generation,view=workforceState.viewGeneration;
  try{return await workforceAPI(url,options);}
  catch(error){
    if(error.status===503&&generation===workforceState.generation&&view===workforceState.viewGeneration)clearWorkforce();
    throw error;
  }
}
function workforceTeamBind(id,fn){
  const generation=workforceState.generation,view=workforceState.viewGeneration;
  workforceBind(id,()=>{
    if(generation!==workforceState.generation||view!==workforceState.viewGeneration)return;
    return fn();
  });
}
async function workforceTeamMutation(button,action,refresh){
  const generation=workforceState.generation,view=workforceState.viewGeneration;
  if(workforcePendingHuman||button.disabled||button.isConnected===false||!workforceCan('workforce.admin')||!workforceCan('personnel.read'))return;
  const operation={generation,view,controls:new Map()};workforcePendingHuman=operation;
  button.disabled=true;workforceLockHumanControls();
  if($('workforceHumanStatus'))$('workforceHumanStatus').textContent='班のHuman登録を処理中です。完了までお待ちください。';
  let accepted=false;
  try{
    await action();accepted=true;
    const pending=refresh();operation.view=workforceState.viewGeneration;await pending;
  }catch(error){
    if(accepted&&!error.cancelled&&workforcePendingHuman===operation&&generation===workforceState.generation&&operation.view===workforceState.viewGeneration)throw new Error('班の登録は完了しましたが、最新表示を取得できません。班メニューから再読込してください。');
    throw error;
  }finally{
    if(workforcePendingHuman===operation){
      workforcePendingHuman=null;
      for(const [control,state] of operation.controls)if(control.isConnected!==false&&generation===workforceState.generation&&state.view===workforceState.viewGeneration)control.disabled=state.disabled||!workforceHumanAllowed(control);
      if(generation===workforceState.generation&&view===workforceState.viewGeneration&&button.isConnected!==false)button.disabled=!workforceCan('workforce.admin')||!workforceCan('personnel.read');
      if($('workforceHumanStatus'))$('workforceHumanStatus').textContent='';
    }
  }
}
async function workforceTeams(){
  const view=++workforceState.viewGeneration;
  const items=[];let offset=0;
  while(true){const page=await workforceTeamAPI('/workforce/teams?'+new URLSearchParams({offset,limit:100}));items.push(...page.items);if(page.items.length<100)break;offset+=100;}
  workforceAssertView(view);
  $('workforceContent').innerHTML=`<h2>班管理</h2><p>組織・職員の人事履歴を参照するHuman登録です。勤務表・出動配置は別に確認してください。</p><div class="toolbar">${workforceCan('personnel.read')?workforceButton('workforceTeamNew','班を追加','workforce.admin'):''}</div><table><thead><tr><th>コード</th><th>班名</th><th>組織</th><th>有効</th><th>操作</th></tr></thead><tbody>${items.map(team=>`<tr><td>${esc(team.code)}</td><td>${esc(team.name)}</td><td>${esc(workforceState.organizations.find(row=>row.organization_id===team.organization_id)?.name??team.organization_id)}</td><td>${team.active?'有効':'無効'}</td><td><button class="btn" id="workforceTeamMembers_${esc(team.team_id)}" type="button">所属履歴</button><button class="btn" id="workforceTeamHistory_${esc(team.team_id)}" type="button">変更履歴</button>${workforceCan('workforce.admin')&&workforceCan('personnel.read')?`<button class="btn" id="workforceTeamEdit_${esc(team.team_id)}" type="button">班を変更</button>`:''}</td></tr>`).join('')}</tbody></table>`;
  workforceTeamBind('workforceTeamNew',()=>workforceTeamForm());
  for(const team of items){
    workforceTeamBind('workforceTeamMembers_'+team.team_id,()=>workforceTeamMembers(team.team_id));
    workforceTeamBind('workforceTeamHistory_'+team.team_id,()=>workforceTeamHistory(team.team_id));
    workforceTeamBind('workforceTeamEdit_'+team.team_id,()=>workforceTeamForm(team));
  }
}
async function workforceTeamHistory(key){
  const view=++workforceState.viewGeneration,items=[];let offset=0;
  while(true){const page=await workforceTeamAPI('/workforce/teams/'+key+'/history?'+new URLSearchParams({offset,limit:100}));items.push(...page.items);if(page.items.length<100)break;offset+=100;}
  workforceAssertView(view);
  $('workforceContent').innerHTML=`<h2>班の保護された変更履歴</h2><p>登録時点の班名・所属根拠・Human理由を保持しています。</p><button class="btn" id="workforceTeamBack" type="button">班一覧</button>${items.map(change=>`<article><h3>${esc(change.action)}</h3><p>${esc(change.created_at)} / Human ${esc(change.actor_id)}</p><p>${esc(change.reason)}</p><details><summary>変更前</summary><pre>${esc(JSON.stringify(change.before_data,null,2))}</pre></details><details><summary>変更後</summary><pre>${esc(JSON.stringify(change.after_data,null,2))}</pre></details><p>SHA256 ${esc(change.evidence_sha256)}</p></article>`).join('')}`;
  workforceTeamBind('workforceTeamBack',workforceTeams);
}
function workforceTeamForm(team){
  if(workforcePendingHuman||!workforceCan('workforce.admin')||!workforceCan('personnel.read'))return;
  workforceState.viewGeneration++;
  const fields=team?[['name','班名','text'],['reason','Human変更理由','textarea']]:[
    ['organization_id','所属組織','select',workforceOptions(workforceState.organizations,'organization_id',row=>row.code+' / '+row.name)],
    ['code','班コード','text'],['name','班名','text'],['reason','Human登録理由','textarea']];
  $('workforceContent').innerHTML=`<h2>${team?'班の変更':'班の追加'}</h2><div class="grid2">${fields.map(field=>workforceField(field,team??{})).join('')}</div>${team?`<label><input id="workforceTeamActive" type="checkbox" ${team.active?'checked':''}>有効</label><p>Version ${esc(team.version)}。無効化後も所属履歴は保持します。</p>`:''}<div class="toolbar"><button class="btn primary" id="workforceTeamSave" type="button" data-workforce-team-edit="true">Human登録</button><button class="btn" id="workforceTeamBack" type="button">戻る</button></div>`;
  workforceTeamBind('workforceTeamSave',()=>{
    const data=workforceValues(fields);
    if(!data.reason||!data.name||(!team&&(!data.organization_id||!data.code)))throw new Error('班名・組織・コードとHuman理由を入力してください。');
    if(team)Object.assign(data,{expected_version:team.version,active:$('workforceTeamActive').checked});
    return workforceTeamMutation($('workforceTeamSave'),()=>workforceTeamAPI('/workforce/teams'+(team?'/'+team.team_id:''),workforceJSON(team?'PATCH':'POST',data)),workforceTeams);
  });
  workforceTeamBind('workforceTeamBack',workforceTeams);
}
async function workforceTeamMembers(key){
  const view=++workforceState.viewGeneration;const items=[];let offset=0,team;
  while(true){const page=await workforceTeamAPI('/workforce/teams/'+key+'/members?'+new URLSearchParams({offset,limit:100}));
    if(team&&team.version!==page.team.version)throw new Error('班の更新があります。所属履歴を再読込してください。');
    team=page.team;items.push(...page.items);if(page.items.length<100)break;offset+=100;
  }
  workforceAssertView(view);
  $('workforceContent').innerHTML=`<h2>${esc(team.name)} — 所属履歴</h2><p>班 Version ${esc(team.version)}。利用可否は現在の人事履歴と登録時点の根拠を照合します。出動配置を確定する画面ではありません。</p><div class="toolbar">${team.active&&workforceCan('personnel.read')?workforceButton('workforceTeamMemberNew','所属を追加','workforce.admin'):''}<button class="btn" id="workforceTeamBack" type="button">班一覧</button></div><table><thead><tr><th>職員</th><th>開始</th><th>終了</th><th>根拠履歴Version</th><th>現根拠</th><th>登録状態</th><th>操作</th></tr></thead><tbody>${items.map(member=>`<tr><td>${esc(member.employee_name??member.employee_id)}</td><td>${esc(member.valid_from)}</td><td>${esc(member.valid_to??'未指定')}</td><td>${esc(member.assignment_version)}</td><td>${member.operational_status==='current'?'一致':'利用不可（無効または根拠変更）'}</td><td>${member.active?'有効':'無効'}</td><td>${workforceCan('workforce.admin')&&workforceCan('personnel.read')?`<button class="btn" id="workforceTeamMemberToggle_${esc(member.membership_id)}" type="button" data-workforce-team-edit="true">${member.active?'無効化':'再有効化'}</button>`:''}</td></tr>`).join('')}</tbody></table>`;
  workforceTeamBind('workforceTeamMemberNew',()=>workforceTeamMemberForm(team));
  workforceTeamBind('workforceTeamBack',workforceTeams);
  for(const member of items)workforceTeamBind('workforceTeamMemberToggle_'+member.membership_id,()=>{
    if(workforcePendingHuman||!workforceCan('workforce.admin')||!workforceCan('personnel.read'))return;
    const reason=prompt('班所属のHuman変更理由','');if(!reason)return;
    return workforceTeamMutation($('workforceTeamMemberToggle_'+member.membership_id),()=>workforceTeamAPI('/workforce/teams/'+key+'/members/'+member.membership_id,workforceJSON('PATCH',{expected_version:member.version,expected_team_version:team.version,active:!member.active,reason})),()=>workforceTeamMembers(key));
  });
  workforceLockHumanControls();
}
function workforceTeamMemberForm(team){
  if(workforcePendingHuman||!workforceCan('workforce.admin')||!workforceCan('personnel.read'))return;
  const view=++workforceState.viewGeneration,generation=workforceState.generation;
  const fields=[['employee_id','職員','select',workforceOptions(workforceState.employees,'employee_id',row=>row.display_name)],
    ['assignment_id','班組織の主所属履歴','select',[]],['valid_from','所属開始','date'],['valid_to','所属終了（未指定可）','date'],['reason','Human登録理由','textarea']];
  $('workforceContent').innerHTML=`<h2>${esc(team.name)} — 所属追加</h2><p>人事履歴の期間内で登録してください。所属履歴は変更せず参照します。</p><div class="grid2">${fields.map(field=>workforceField(field,{valid_from:workforceState.date})).join('')}</div><div class="toolbar"><button class="btn primary" id="workforceTeamMemberSave" type="button" data-workforce-team-edit="true">Human登録</button><button class="btn" id="workforceTeamBack" type="button">戻る</button></div>`;
  let selection=0,assignmentRows=[];
  $('workforceField_employee_id').onchange=()=>workforceAction(async()=>{
    const ticket=++selection,employee=$('workforceField_employee_id').value;
    assignmentRows=[];$('workforceField_assignment_id').value='';$('workforceField_assignment_id').innerHTML='';
    if(!employee)return;
    const assignments=await workforceTeamAPI('/administration/staff/'+employee+'/assignments');
    if(ticket!==selection||generation!==workforceState.generation||view!==workforceState.viewGeneration)return;
    const rows=assignments.filter(row=>row.organization_id===team.organization_id&&row.kind==='primary');
    assignmentRows=rows;
    $('workforceField_assignment_id').innerHTML='<option value="">選択してください</option>'+rows.map(row=>`<option value="${esc(row.assignment_id)}">${esc(row.valid_from)}〜${esc(row.valid_to??'未指定')} / Version ${esc(row.version)}</option>`).join('');
  });
  workforceTeamBind('workforceTeamMemberSave',()=>{
    const data=workforceValues(fields);
    if(!data.employee_id||!data.assignment_id||!data.valid_from||!data.reason)throw new Error('職員・主所属履歴・開始日とHuman理由を入力してください。');
    const assignment=assignmentRows.find(row=>row.assignment_id===data.assignment_id);
    if(!assignment)throw new Error('主所属履歴を再選択してください。');
    data.expected_assignment_version=assignment.version;
    data.expected_team_version=team.version;
    return workforceTeamMutation($('workforceTeamMemberSave'),()=>workforceTeamAPI('/workforce/teams/'+team.team_id+'/members',workforceJSON('POST',data)),()=>workforceTeamMembers(team.team_id));
  });
  workforceTeamBind('workforceTeamBack',()=>workforceTeamMembers(team.team_id));
}
