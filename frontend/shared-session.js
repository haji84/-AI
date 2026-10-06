'use strict';
// The server remains the authority. No cookie, token or token digest is read here.
(()=>{
  const originalFetch=window.fetch.bind(window);
  let generation=0,binding=null,reset=()=>{},installed=false;
  const wrapped=new WeakSet(),redispatch=new WeakSet();
  const cancelled=()=>Object.assign(new Error('セッションまたは権限が変わりました。再ログインしてください。'),{cancelled:true});
  function invalidate(){generation++;binding=null;reset();}
  function privatePath(input){
    try{const url=new URL(typeof input==='string'?input:(input.url??input.href),window.location.origin);
      if(!['http:','https:'].includes(url.protocol)||url.origin!==window.location.origin||url.pathname.startsWith('/ui/')||url.pathname==='/health')return null;
      return url.pathname;
    }catch{return null;}
  }
  async function observe(ticket){
    try{
      const response=await originalFetch('/auth/context',{cache:'no-store'});
      if(ticket!==generation)throw cancelled();
      if(!response.ok){const error=Object.assign(new Error('authority unavailable'),{status:response.status});throw error;}
      const data=await response.json();
      if(ticket!==generation)throw cancelled();
      if(!data||typeof data.user_id!=='string'||typeof data.session_id!=='string'||!Array.isArray(data.permissions)||data.permissions.some(x=>typeof x!=='string')||!(data.tenant_id===null||typeof data.tenant_id==='string'))throw new Error('invalid authority context');
      const key=JSON.stringify([data.user_id,data.session_id,data.tenant_id,[...data.permissions].sort()]);
      if(binding!==null&&binding!==key){invalidate();throw cancelled();}
      binding=key;return key;
    }catch(error){
      if(ticket!==generation)throw cancelled();
      if(binding!==null){invalidate();throw cancelled();}
      throw error;
    }
  }
  function guardResponse(response,ticket,key){
    if(wrapped.has(response))return response;
    wrapped.add(response);
    for(const method of ['json','text','blob','arrayBuffer','formData']){
      if(typeof response[method]!=='function')continue;
      const read=response[method].bind(response);
      response[method]=async(...args)=>{
        let value,failed=null;
        try{value=await read(...args);}catch(error){failed=error;}
        if(ticket!==generation)throw cancelled();
        if(key!==null&&(await observe(ticket)!==key||ticket!==generation))throw cancelled();
        if(failed)throw failed;
        return value;
      };
    }
    if(typeof response.clone==='function'){
      const clone=response.clone.bind(response);
      response.clone=()=>guardResponse(clone(),ticket,key);
    }
    return response;
  }
  window.fetch=async(input,options={})=>{
    const path=privatePath(input);
    if(!path||path==='/auth/context')return originalFetch(input,options);
    if(path==='/auth/login'||path==='/auth/logout'){
      invalidate();const ticket=generation;const response=await originalFetch(input,options);if(ticket!==generation)throw cancelled();return guardResponse(response,ticket,null);
    }
    const ticket=generation;
    const key=await observe(ticket);
    try{
      const response=await originalFetch(input,{...options,cache:'no-store'});
      if(ticket!==generation)throw cancelled();
      if(await observe(ticket)!==key)throw cancelled();
      return guardResponse(response,ticket,key);
    }catch(error){if(ticket!==generation)throw cancelled();throw error;}
  };
  async function cachedAction(event){
    const target=event.target?.closest?.('button, a, input, select, textarea, form, summary, [onclick]');
    if(!target||redispatch.has(target)){if(target)redispatch.delete(target);return;}
    if(target.closest?.('#loginView')||target.id==='logoutBtn'||target.disabled)return;
    if(event.type==='click'&&['INPUT','SELECT','TEXTAREA'].includes(target.tagName))return;
    // Ordinary navigation between UI pages has its own entry-point guards.
    if(target.tagName==='A'&&!privatePath(target.href))return;
    event.preventDefault();event.stopImmediatePropagation();
    const ticket=generation;
    const releasePreflight=window.financeSessionPreflight?.(target)??(()=>{});
    try{
      await observe(ticket);
      if(ticket!==generation||target.isConnected===false)return;
      releasePreflight();
      if(target.tagName==='A'&&privatePath(target.href)){
        const response=await window.fetch(target.href);if(!response.ok)throw new Error('原本の取得が許可されません');
        const blob=await response.blob();if(ticket!==generation)return;
        const url=URL.createObjectURL(blob),link=document.createElement('a');link.href=url;
        link.download=response.headers.get('Content-Disposition')?.match(/filename="([^"]+)"/)?.[1]??'original';
        link.click();URL.revokeObjectURL(url);return;
      }
      redispatch.add(target);
      if(event.type==='click'&&typeof target.click==='function')target.click();
      else target.dispatchEvent(event.type==='click'?new MouseEvent('click',{bubbles:true,cancelable:true,clientX:event.clientX,clientY:event.clientY,screenX:event.screenX,screenY:event.screenY,button:event.button,buttons:event.buttons,ctrlKey:event.ctrlKey,shiftKey:event.shiftKey,altKey:event.altKey,metaKey:event.metaKey,detail:event.detail}):new Event(event.type,{bubbles:true,cancelable:true}));
    }catch(error){if(!error.cancelled&&ticket===generation&&binding!==null)invalidate();}
    finally{releasePreflight();}
  }
  window.FireAISession={install(options={}){
    reset=options.reset??reset;
    if(installed)return;
    installed=true;
    for(const name of ['click','change','submit'])document.addEventListener(name,cachedAction,true);
    const refresh=()=>{if(binding!==null)observe(generation).catch(()=>{});};
    window.addEventListener('focus',refresh);
    window.addEventListener('unhandledrejection',event=>{if(event.reason?.cancelled)event.preventDefault();});
    document.addEventListener('visibilitychange',()=>{if(document.visibilityState==='visible')refresh();});
  },check:()=>observe(generation),currentGeneration:()=>generation,invalidate};
})();
