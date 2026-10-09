'use strict';
// Notice candidates have their own lifetime; no Role or assignment mutation here.
(()=>{
  const base='/personnel-intake/proposals';
  window.createPersonnelIntakeController=function({send,paint,notify,clear}){
    let owner=0,binding=null,proposal=null,rows=[],busy=false,permissions=[];
    const cancelled=()=>Object.assign(new Error('セッションまたは権限が変わりました。再読込してください。'),{cancelled:true});
    const current=ticket=>ticket===owner;
    const display=()=>paint({proposal,rows,busy,permissions});
    function reset(){owner++;binding=null;proposal=null;rows=[];busy=false;permissions=[];clear();}
    async function authorize(ticket,required){
      let context;
      try{context=await send('/auth/context','GET');}
      catch(error){if(current(ticket))reset();throw error;}
      if(!current(ticket))throw cancelled();
      if(typeof context?.user_id!=='string'||typeof context?.session_id!=='string'||!Array.isArray(context?.permissions)||context.permissions.some(code=>typeof code!=='string')||!(context.tenant_id===null||typeof context.tenant_id==='string')){
        reset();throw new Error('認証情報を確認できません。');
      }
      const key=JSON.stringify([context.user_id,context.session_id,context.tenant_id,[...context.permissions].sort()]);
      if(binding!==null&&binding!==key){reset();throw cancelled();}
      if(!required.every(code=>context.permissions.includes(code))){reset();throw Object.assign(new Error('人事原本を操作する権限がありません。'),{status:403});}
      binding=key;permissions=context.permissions;
    }
    async function api(ticket,path,method='GET',payload,extra=[]){
      const needed=['personnel.read','document.read',...extra];
      await authorize(ticket,needed);
      if(!current(ticket))throw cancelled();
      const result=await send(path,method,payload);
      if(!current(ticket))throw cancelled();
      await authorize(ticket,needed);
      if(!current(ticket))throw cancelled();
      return result;
    }
    async function run(action,mutating=false){
      if(busy){notify('処理中です。結果を待ってください。');return;}
      const ticket=++owner;
      if(mutating){busy=true;display();}
      try{await action(ticket);}
      catch(error){
        if(error.cancelled||!current(ticket))return;
        if(error.status===401||error.status===403)reset();
        else if(error.status===409){proposal=null;rows=[];display();}
        notify(error.status===409?'元データまたは候補が変わりました。再読込して確認してください。':error.message);
      }finally{if(current(ticket)){busy=false;display();}}
    }
    return {
      clear:reset,
      check:async()=>{
        const ticket=owner;
        try{await authorize(ticket,['personnel.read','document.read']);}
        catch(error){if(!current(ticket)||error.cancelled)return;reset();notify(error.message);}
      },
      load:()=>run(async ticket=>{rows=await api(ticket,base);proposal=null;notify('候補を読み込みました。');}),
      detail:id=>run(async ticket=>{proposal=null;display();proposal=await api(ticket,base+'/'+encodeURIComponent(id));notify('原本と変更内容を確認してください。');}),
      create:file=>run(async ticket=>{
        if(!file)throw new Error('原本ファイルを選択してください。');
        const form=new FormData();form.append('file',file);form.append('document_type','personnel_notice');
        const document=await api(ticket,'/documents/upload','POST',form,['personnel.manage','document.create']);
        proposal=await api(ticket,base,'POST',{document_id:document.document_id},['personnel.manage']);rows=[];
        notify('候補を作成しました。人事履歴はまだ変更していません。');
      },true),
      revise:(fields,quote,reason)=>run(async ticket=>{
        if(!proposal||proposal.status!=='candidate')throw new Error('未確認の候補を選択してください。');
        proposal=await api(ticket,base+'/'+proposal.proposal_id,'PATCH',{expected_version:proposal.version,proposed:fields,source_quote:quote,reason},['personnel.manage']);
        notify('候補を更新しました。人事履歴はまだ変更していません。');
      },true),
      decision:(action,reason,acknowledged)=>run(async ticket=>{
        if(!proposal||!['review','apply','reject'].includes(action))throw new Error('最新の候補を選択してください。');
        if(acknowledged!==true||!reason?.trim())throw new Error('原本・対象・期間を確認し、理由と確認チェックを入力してください。');
        proposal=await api(ticket,base+'/'+proposal.proposal_id+'/'+action,'POST',{expected_version:proposal.version,reason,acknowledged:true},['personnel.manage']);
        notify(action==='apply'?'人事履歴へ反映しました。将来日付はその日から有効です。':action==='review'?'Human確認済みです。正式反映には別の適用操作が必要です。':'候補を却下しました。');
      },true)
    };
  };

  const root=document.getElementById('personnelIntake');if(!root)return;
  const el=id=>document.getElementById(id);
  const names={candidate:'候補・未正式',reviewed:'Human確認済・適用待ち',applied:'適用済',rejected:'却下'};
  const errorNames=value=>value.includes('employee_code')?'職員コードが未登録または無効です。':value.includes('organization_code')?'所属コードが未登録または無効です。':value.includes('title')?'役職が既存の正式名称と一致しません。':'抽出項目を解決できません。原本を確認して候補を補正してください。';
  let displayed=null;
  async function send(path,method,payload){
    const form=payload instanceof FormData;
    const response=await fetch(path,{method,credentials:'same-origin',cache:'no-store',headers:payload&&!form?{'Content-Type':'application/json'}:{},body:payload?(form?payload:JSON.stringify(payload)):undefined});
    const value=await response.json();
    if(!response.ok)throw Object.assign(new Error(response.status===422?'入力または原本の条件を確認してください。':response.status===409?'元データが変わりました。':response.status===401||response.status===403?'セッションまたは権限を確認してください。':'処理できませんでした。'),{status:response.status});
    return value;
  }
  function empty(){displayed=null;root.hidden=true;el('noticeDetail').hidden=true;el('noticeList').replaceChildren();for(const id of ['noticeSource','noticeBefore','noticeAfter','noticeErrors','noticeIdentity'])el(id).textContent='';for(const id of ['noticeUpload','noticeEdit','noticeDecision'])el(id).reset();}
  function paint(state){
    root.hidden=!state.permissions.includes('personnel.read')||!state.permissions.includes('document.read');
    const manage=state.permissions.includes('personnel.manage');
    el('noticeUpload').hidden=!manage||!state.permissions.includes('document.create');
    el('noticeEdit').hidden=!manage;el('noticeDecision').hidden=!manage;
    el('noticeList').replaceChildren();
    for(const item of state.rows){const button=document.createElement('button');button.type='button';button.textContent=(item.proposed?.employee_code||'未解決')+' / '+(names[item.status]||'要確認')+' / '+(item.proposed?.valid_from||'日付未解決');button.disabled=state.busy;button.addEventListener('click',()=>window.PersonnelIntake.detail(item.proposal_id));el('noticeList').appendChild(button);}
    const row=state.proposal;el('noticeDetail').hidden=!row;
    if(row){
      el('noticeIdentity').textContent='状態: '+(names[row.status]||'要確認')+' / 版: '+row.version+' / 原本: '+row.source_document_id+' / SHA-256: '+row.source_sha256;
      el('noticeSource').textContent=row.source_text;
      const before=row.before_snapshot||{},after=row.after_snapshot||{};
      el('noticeBefore').textContent=(before.display_name||'職員未解決')+' / 元版: '+(before.employee_version??'未解決')+'\n'+(before.assignments||[]).map(item=>(item.kind==='secondary'?'兼務':'本務')+' / '+item.title+' / '+item.valid_from+'〜'+(item.valid_to||'終了未指定')).join('\n');
      el('noticeAfter').textContent='職員コード: '+(after.employee_code||'未解決')+'\n所属: '+(after.organization_code||'未解決')+' '+(after.organization_name||'')+'\n役職: '+(after.title||'未解決')+'\n本務・兼務: '+(after.kind==='secondary'?'兼務':'本務')+'\n処理: '+(after.mode==='transfer'?'本務異動':'辞令追加')+'\n開始日: '+(after.valid_from||'未解決')+'\n終了日: '+(after.valid_to||'指定なし');
      el('noticeErrors').textContent=(row.errors||[]).map(errorNames).join('\n');
      if(displayed!==row.proposal_id+':'+row.version){
        displayed=row.proposal_id+':'+row.version;
        for(const name of ['employee_code','organization_code','title','kind','valid_from','valid_to','mode'])el('noticeEdit').elements[name].value=row.proposed?.[name]??(name==='kind'?'primary':name==='mode'?'transfer':'');
        el('noticeEdit').elements.source_quote.value=row.source_quote||row.source_text;el('noticeEdit').elements.reason.value='';el('noticeDecision').reset();
      }
      el('noticeEdit').hidden=!manage||row.status!=='candidate';
    }else{displayed=null;for(const id of ['noticeSource','noticeBefore','noticeAfter','noticeErrors','noticeIdentity'])el(id).textContent='';el('noticeEdit').reset();el('noticeDecision').reset();}
    for(const field of root.querySelectorAll('button,input,select,textarea'))field.disabled=state.busy;
    el('noticeReview').disabled=state.busy||!manage||!row||row.status!=='candidate'||!!row.errors?.length;
    el('noticeApply').disabled=state.busy||!manage||!row||row.status!=='reviewed';
    el('noticeReject').disabled=state.busy||!manage||!row||!['candidate','reviewed'].includes(row.status);
  }
  window.PersonnelIntake=window.createPersonnelIntakeController({send,paint,clear:empty,notify:text=>el('noticeMessage').textContent=text});
  el('noticeReload').addEventListener('click',()=>window.PersonnelIntake.load());
  el('noticeUpload').addEventListener('submit',event=>{event.preventDefault();window.PersonnelIntake.create(event.currentTarget.elements.file.files[0]);});
  el('noticeEdit').addEventListener('submit',event=>{event.preventDefault();const values=Object.fromEntries(new FormData(event.currentTarget));const {source_quote,reason,...fields}=values;fields.valid_to=fields.valid_to||null;window.PersonnelIntake.revise(fields,source_quote,reason);});
  el('noticeDecision').addEventListener('submit',event=>{
    event.preventDefault();const form=event.currentTarget;const action=event.submitter?.value;
    if(action==='apply'&&!confirm('原本・職員・所属・役職・期間を確認し、人事履歴へ正式反映します。既存のHuman権限ルールが発令日から適用されます。よろしいですか？'))return;
    window.PersonnelIntake.decision(action,form.elements.reason.value,form.elements.acknowledged.checked);
  });
  for(const id of ['logoutButton','passwordForm','loginForm'])el(id)?.addEventListener(id==='logoutButton'?'click':'submit',()=>window.PersonnelIntake.clear(),true);
  window.addEventListener('focus',()=>{if(!root.hidden)window.PersonnelIntake.check();});
  document.addEventListener('visibilitychange',()=>{if(document.visibilityState==='visible'&&!root.hidden)window.PersonnelIntake.check();});
})();
