'use strict';
const adminState={staff:[],organizations:[],roles:[],accounts:[],history:[],permissions:new Set()};
const byId=id=>document.getElementById(id);
const message=text=>{byId('message').textContent=text;};
async function request(path,method='GET',body){
  const response=await fetch(path,{method,credentials:'same-origin',headers:body?{'Content-Type':'application/json'}:{},body:body?JSON.stringify(body):undefined});
  const data=await response.json();
  if(!response.ok){if(response.status===401){byId('workspace').hidden=true;byId('loginSection').hidden=false;}
    throw new Error(response.status===409?'競合または管理上の制約です。入力を確認し、最新状態を再読込してください。 '+String(data.detail):typeof data.detail==='string'?data.detail:JSON.stringify(data.detail));}
  return data;
}
function data(form){return Object.fromEntries(new FormData(form));}
function row(table,values){const element=document.createElement('tr');for(const value of values){const cell=document.createElement('td');cell.textContent=value??'－';element.appendChild(cell);}table.appendChild(element);}
function options(selector,items,id,label){for(const select of document.querySelectorAll(selector)){const previous=select.value;select.replaceChildren();if(select.dataset.empty){select.appendChild(new Option(select.dataset.empty,''));}
  for(const item of items)select.appendChild(new Option(label(item),item[id]));if([...select.options].some(x=>x.value===previous))select.value=previous;}}
function rolesText(ids){return ids.map(id=>adminState.roles.find(role=>role.role_id===id)?.name||id).join('、')||'なし';}
function roleChoices(id,excludeAdmin=false){const box=byId(id);const legend=box.querySelector('legend');box.replaceChildren(legend);for(const role of adminState.roles){if(excludeAdmin&&role.code==='system_admin')continue;const label=document.createElement('label');const input=document.createElement('input');input.type='checkbox';input.value=role.role_id;input.name='role';input.disabled=!role.active;label.append(input,document.createTextNode(role.name));box.appendChild(label);}}
function selectedRoles(id){return [...byId(id).querySelectorAll('input:checked')].map(input=>input.value);}
function staffRecord(id){const record=adminState.staff.find(item=>item.employee_id===id);if(!record)throw new Error('職員を選択してください');return record;}
function accountRecord(id){const record=adminState.accounts.find(item=>item.user_id===id);if(!record)throw new Error('アカウントを選択してください');return record;}
async function refresh(){
  const context=await request('/administration/context');adminState.permissions=new Set(context.permissions);byId('department').textContent=context.department+' / '+context.username+' / '+context.business_date;byId('workspace').hidden=false;byId('loginSection').hidden=true;
  const policy=context.password_max_age_days;const configured=Number.isInteger(policy);byId('passwordPolicy').textContent=configured?'本部の有効日数: '+policy+'日（最終パスワード変更日から算定）':'本部の有効日数は未設定です。日時指定または解除を選択してください。';byId('expiryPolicyOption').disabled=!configured;if(!configured&&byId('expiryForm').elements.mode.value==='policy')byId('expiryForm').elements.mode.value='explicit';
  for(const element of document.querySelectorAll('[data-permission]'))element.hidden=!adminState.permissions.has(element.dataset.permission);
  if(adminState.permissions.has('personnel.read'))[adminState.staff,adminState.organizations]=await Promise.all([request('/administration/staff'),request('/administration/organizations')]);
  if(!adminState.permissions.has('personnel.read')&&adminState.permissions.has('account.manage'))adminState.staff=await request('/administration/account-staff');
  if(adminState.permissions.has('account.manage'))adminState.accounts=await request('/administration/accounts');
  if(adminState.permissions.has('personnel.read')||adminState.permissions.has('account.manage'))adminState.roles=await request('/administration/roles');
  for(const id of ['staff','organizations','accounts'])byId(id).replaceChildren();
  for(const item of adminState.staff)row(byId('staff'),[item.employee_code,item.display_name,item.active?'有効':'無効']);
  for(const item of adminState.organizations)row(byId('organizations'),[item.code,item.name,adminState.organizations.find(x=>x.organization_id===item.parent_id)?.name,item.active?'有効':'無効']);
  for(const item of adminState.accounts)row(byId('accounts'),[item.username,adminState.staff.find(x=>x.employee_id===item.employee_id)?.display_name,item.active?'有効':'無効',rolesText(item.permanent_role_ids)+' / '+rolesText(item.effective_role_ids),new Date(item.password_changed_at).toLocaleString('ja-JP')+' / '+(item.password_expires_at?new Date(item.password_expires_at).toLocaleString('ja-JP')+(item.password_change_required?'（更新が必要）':''):'設定なし')]);
  options('.staffSelect',adminState.staff,'employee_id',item=>(item.employee_code||'旧職員')+' '+item.display_name);options('.orgSelect',adminState.organizations,'organization_id',item=>item.code+' '+item.name);options('.accountSelect',adminState.accounts,'user_id',item=>item.username);
  roleChoices('assignmentRoles',true);roleChoices('accountRoles');syncAccountRoles();syncStaffEdit();syncOrgEdit();const start=byId('assignmentForm').elements.valid_from;if(!start.value)start.value=context.business_date;
}
function syncStaffEdit(){const form=byId('staffEditForm');const record=adminState.staff.find(item=>item.employee_id===form.elements.employee_id.value);if(record){form.elements.active.value=String(record.active);form.elements.display_name.value=record.display_name;}}
function syncOrgEdit(){const form=byId('orgEditForm');const record=adminState.organizations.find(item=>item.organization_id===form.elements.organization_id.value);if(record){form.elements.active.value=String(record.active);form.elements.name.value=record.name;}}
function syncAccountRoles(){const account=adminState.accounts.find(item=>item.user_id===byId('accountEditForm').elements.user_id.value);for(const input of byId('accountRoles').querySelectorAll('input'))input.checked=!input.disabled&&!!account?.permanent_role_ids.includes(input.value);if(account)byId('accountEditForm').elements.active.value=String(account.active);}
async function submit(form,action,confirmText){try{if(confirmText&&!confirm(confirmText))return;await action(data(form));for(const input of form.querySelectorAll('input[type=password]'))input.value='';await refresh();message('保存しました。');}catch(error){message(error.message);}}
function bind(id,action,confirmText){byId(id).addEventListener('submit',event=>{event.preventDefault();submit(event.currentTarget,action,confirmText);});}
bind('loginForm',values=>request('/auth/login','POST',values));
bind('orgForm',values=>request('/administration/organizations','POST',{...values,parent_id:values.parent_id||null}));
bind('staffForm',values=>request('/administration/staff','POST',values));
bind('orgEditForm',values=>{const record=adminState.organizations.find(x=>x.organization_id===values.organization_id);const body={expected_version:record.version,active:values.active==='true',reason:values.reason};if(values.name)body.name=values.name;return request('/administration/organizations/'+record.organization_id,'PATCH',body);},'組織の正式名称・状態を変更します。無効化した組織の辞令権限は利用できなくなります。確認しましたか？');
bind('staffEditForm',values=>{const record=staffRecord(values.employee_id);const body={expected_version:record.version,active:values.active==='true',reason:values.reason};if(values.display_name)body.display_name=values.display_name;return request('/administration/staff/'+record.employee_id,'PATCH',body);},'職員の正式情報を変更します。無効化するとログインと既存セッションが停止します。確認しましたか？');
bind('assignmentForm',values=>{const record=staffRecord(values.employee_id);const operation=values.operation;return request('/administration/staff/'+record.employee_id+'/'+(operation==='transfer'?'transfer':'assignments'),'POST',{expected_version:record.version,organization_id:values.organization_id,title:values.title,kind:operation==='secondary'?'secondary':'primary',valid_from:values.valid_from,valid_to:values.valid_to||null,role_ids:selectedRoles('assignmentRoles'),reason:values.reason});},'辞令原本・期間・対象職員・付与するロールを確認して正式登録します。よろしいですか？');
bind('accountForm',values=>request('/administration/accounts','POST',values),'職員とログインIDを確認してアカウントを作成します。よろしいですか？');
bind('accountEditForm',values=>request('/administration/accounts/'+values.user_id,'PATCH',{expected_version:accountRecord(values.user_id).version,active:values.active==='true',role_ids:selectedRoles('accountRoles'),reason:values.reason}),'選択した永続ロールと状態を正式反映し、対象者のセッションを失効します。確認しましたか？');
bind('resetForm',values=>request('/administration/accounts/'+values.user_id+'/password-reset','POST',{expected_version:accountRecord(values.user_id).version,new_password:values.new_password,reason:values.reason}),'Human管理者としてパスワードを再設定し、対象者のセッションを失効します。確認しましたか？');
bind('expiryForm',values=>{const body={expected_version:accountRecord(values.user_id).version,mode:values.mode,reason:values.reason};if(values.mode==='explicit'){if(!values.expires_at)throw new Error('期限の日時を指定してください。');body.expires_at=new Date(values.expires_at).toISOString();}return request('/administration/accounts/'+values.user_id+'/password-expiry','POST',body);},'本部方針・対象者・日時を確認しましたか？対象者の全セッションが失効します。');
byId('passwordForm').addEventListener('submit',async event=>{event.preventDefault();try{await request('/administration/password','POST',data(event.currentTarget));event.currentTarget.reset();byId('workspace').hidden=true;byId('loginSection').hidden=false;message('変更しました。新しいパスワードで再ログインしてください。');}catch(error){message(error.message);}});
byId('historyForm').addEventListener('submit',async event=>{event.preventDefault();try{const id=data(event.currentTarget).employee_id;adminState.history=await request('/administration/staff/'+id+'/assignments');byId('history').replaceChildren();byId('historySelect').replaceChildren();for(const item of adminState.history){const name=(adminState.organizations.find(x=>x.organization_id===item.organization_id)?.name||item.organization_id)+' '+item.title;row(byId('history'),[name,item.kind==='secondary'?'兼務':'本務',item.valid_from,item.valid_to,rolesText(item.role_ids)]);byId('historySelect').appendChild(new Option(name+' '+item.valid_from,item.assignment_id));}}catch(error){message(error.message);}});
bind('endAssignmentForm',values=>{const record=adminState.history.find(x=>x.assignment_id===values.assignment_id);if(!record)throw new Error('先に人事履歴を表示してください');return request('/administration/assignments/'+record.assignment_id,'PATCH',{expected_version:record.version,expected_employee_version:staffRecord(record.employee_id).version,valid_to:values.valid_to,reason:values.reason});},'指定した終了日までを有効として人事履歴を変更します。理由と辞令を確認しましたか？');
byId('accountEditForm').elements.user_id.addEventListener('change',syncAccountRoles);
byId('staffEditForm').elements.employee_id.addEventListener('change',syncStaffEdit);
byId('orgEditForm').elements.organization_id.addEventListener('change',syncOrgEdit);
let auditRows=[];
async function loadAudit(older=false){try{const params=new URLSearchParams({limit:'100'});if(older&&auditRows.length)params.set('before_id',String(auditRows.at(-1).audit_id));const action=byId('auditAction').value.trim();if(action)params.set('action',action);const rows=await request('/administration/audit?'+params);auditRows=older?[...auditRows,...rows]:rows;byId('audit').textContent=JSON.stringify(auditRows,null,2);byId('auditOlder').disabled=rows.length<100;}catch(error){message(error.message);}}
byId('auditButton').addEventListener('click',()=>loadAudit());
byId('auditOlder').addEventListener('click',()=>loadAudit(true));
byId('auditAction').addEventListener('change',()=>loadAudit());
byId('refreshButton').addEventListener('click',()=>refresh().then(()=>message('最新状態を読み込みました。')).catch(error=>message(error.message)));
byId('logoutButton').addEventListener('click',async()=>{try{await request('/auth/logout','POST');location.reload();}catch(error){message(error.message);}});
refresh().catch(error=>message(error.message));
