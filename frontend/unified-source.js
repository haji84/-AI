// Closed workforce source handoff. Read-only source UI owns its own fresh rights.
let unifiedWorkforceSourceGeneration=0;
async function openUnifiedWorkforceSource(id){
  if(typeof id!=='string'||!/^[A-Za-z0-9_-]{1,128}$/.test(id))return;
  const ticket=++unifiedWorkforceSourceGeneration;
  const session=window.FireAISession.currentGeneration();
  const owned=()=>ticket===unifiedWorkforceSourceGeneration&&session===window.FireAISession.currentGeneration();
  closeUnifiedSearch();
  const events=['click','popstate','pagehide'];
  const interrupt=event=>{
    if(event.type!=='click'){unifiedWorkforceSourceGeneration++;return;}
    const target=event.target?.closest?.('button, a, [onclick]');
    if(target?.closest?.('header'))unifiedWorkforceSourceGeneration++;
  };
  for(const event of events)window.addEventListener(event,interrupt,true);
  try{
    await openWorkforceSource(owned);if(!owned())return;
    const modal=$('workforceModal');
    const live=()=>owned()&&modal?.isConnected&&$('workforceModal')===modal&&!modal.classList.contains('hidden');
    if(!live())return;
    await workforceSourceDetail('roster',id,live);
  }catch(error){
    if(!error.cancelled&&owned()){
      if($('unifiedSearchResults'))$('unifiedSearchResults').innerHTML='';
      if($('unifiedSearchSummary'))$('unifiedSearchSummary').textContent='元記録を開けません。再検索してください。';
      $('unifiedSearchModal')?.classList.remove('hidden');
    }
  }
  finally{for(const event of events)window.removeEventListener(event,interrupt,true);}
}
