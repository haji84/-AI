// Synthetic DOM and controlled HTTP authority; execute both actual product scripts.
const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict'),path=require('node:path');
const root=process.argv[2],scenario=process.argv[3],handlers={},gates=[],nodes={};let submitted;
const authority={user_id:'synthetic-user',session_id:'synthetic-session',tenant_id:null,permissions:['violation.read','document.read']};
const window={location:{origin:'http://synthetic.local'},addEventListener(){},fetch:()=>new Promise(resolve=>gates.push({released:false,resolve(data=authority){this.released=true;resolve(new Response(JSON.stringify(data)));}}))};
const controls=[];
function element(tagName,id){return {tagName,id,value:'',dataset:{},isConnected:true,disabled:false,
 closest(selector){
  if(selector==='#loginView')return null;
  if(selector==='#violationForm'||selector==='form')return controls.includes(this)||this.id==='violationForm'?nodes.violationForm:null;
  if(selector==='#violationModal')return nodes.violationModal;
  return this;
 },
 dispatchEvent(event){const ev={type:event.type,target:this,preventDefault(){this.prevented=true},stopImmediatePropagation(){this.stopped=true}};handlers[ev.type]?.(ev);if(!ev.stopped)this['on'+ev.type]?.(ev);return true;},
 click(){if(!this.disabled)this.dispatchEvent(new Event('click'));},setAttribute(name,value){this[name]=value;},querySelectorAll(){return controls;},contains(target){return controls.includes(target);}};}
for(const name of ['violationContent','violationForm','violationBack','violationField_rule_version_ids','violationField_evidence_document_ids','violationField_procedure_document_ids','violationModal'])nodes[name]=element(name==='violationForm'?'FORM':'INPUT',name);
nodes.violationField_rule_version_ids.value='synthetic-rule';nodes.violationField_evidence_document_ids.value='synthetic-evidence';
const buttons=Array.from({length:4},()=>element('BUTTON')),input=element('INPUT'),select=element('SELECT'),summary=element('DIV');select.options=[{text:'synthetic procedure'}];select.selectedIndex=0;
const save=element('BUTTON','synthetic-save'),unavailable=element('BUTTON','already-disabled');unavailable.disabled=true;
controls.push(...buttons,input,select,save,unavailable,nodes.violationBack,...Object.values(nodes).filter(x=>x.id?.startsWith('violationField_')));
const box={querySelector:tag=>({input,select,div:summary}[tag]),querySelectorAll:()=>buttons};nodes.violationField_procedure_document_ids.parentNode={append(){}};
const document={addEventListener:(type,fn)=>handlers[type]=fn,createElement:()=>box,querySelectorAll:()=>controls};
const ctx={window,document,$:id=>nodes[id],URL,URLSearchParams,Response,WeakSet,WeakMap,Event,console,esc:x=>String(x),capture:data=>submitted=JSON.parse(JSON.stringify(data))};vm.createContext(ctx);
for(const name of ['shared-session.js','violations.js'])vm.runInContext(fs.readFileSync(path.join(root,'frontend',name),'utf8'),ctx);
ctx.violationAPI=async()=>[{id:'synthetic-procedure',label:'synthetic procedure'}];
window.FireAISession.install({reset:()=>ctx.clearViolations()});
const flush=()=>new Promise(resolve=>setImmediate(resolve));
async function drain(){for(let turn=0;turn<8;turn++){for(const gate of gates)if(!gate.released)gate.resolve();await flush();}}
function form(){vm.runInContext("violationForm('synthetic',[['rule_version_ids','Rule'],['evidence_document_ids','Evidence'],['procedure_document_ids','Procedure']],{},data=>{for(const key of ['rule_version_ids','evidence_document_ids','procedure_document_ids'])data[key]=$('violationField_'+key).value;capture(violationIds(data))},()=>{})",ctx);}
(async()=>{
 form();await ctx.violationPicker('procedure_document_ids','documents',true);select.value='synthetic-procedure';
 // Establish binding so a changed identity/rights is rejected, not first-login accepted.
 const bound=window.FireAISession.check();gates[0].resolve();await bound;
 buttons[3].click();assert.equal(gates.length,2);assert.equal(nodes.violationField_procedure_document_ids.value,'');
 if(scenario==='pending-save'){
  // Submit events/Enter can bypass a disabled save button. Resolve save before selection.
  nodes.violationForm.dispatchEvent(new Event('submit'));
  for(const gate of gates.slice(2))gate.resolve();await flush();await flush();
  assert.equal(submitted,undefined,'save accepted incomplete references while picker authority pending');
  assert.equal(save.disabled,true,'save control not locked during picker authority');
  gates[1].resolve();await drain();
  assert.equal(nodes.violationField_procedure_document_ids.value,'synthetic-procedure');
  assert.equal(save.disabled,false);assert.equal(unavailable.disabled,true,'previous disabled state lost');
  nodes.violationForm.dispatchEvent(new Event('submit'));await drain();
  assert.deepEqual(submitted,{rule_version_ids:['synthetic-rule'],evidence_document_ids:['synthetic-evidence'],procedure_document_ids:['synthetic-procedure']});
 }else if(scenario==='view-switch'){
  vm.runInContext('violationState.viewGeneration++',ctx);gates[1].resolve();await drain();
  assert.equal(nodes.violationField_procedure_document_ids.value,'','old picker painted after view switch');
  nodes.violationForm.onsubmit({preventDefault(){}});await drain();assert.equal(submitted,undefined,'old form submitted after view switch');
 }else if(scenario==='replacement'){
  const oldForm=nodes.violationForm;nodes.violationForm=element('FORM','violationForm');form();
  gates[1].resolve();await drain();assert.equal(nodes.violationField_procedure_document_ids.value,'','old picker wrote new form');
  oldForm.onsubmit({preventDefault(){}});await drain();assert.equal(submitted,undefined,'replaced form submitted');
 }else if(scenario==='revoked'){
  gates[1].resolve({...authority,permissions:[]});await drain();
  assert.equal(nodes.violationField_procedure_document_ids.value,'','revoked picker replayed');
  assert.equal(nodes.violationContent.innerHTML,'','private draft survived authority change');
  nodes.violationForm.onsubmit({preventDefault(){}});await drain();assert.equal(submitted,undefined,'revoked old form submitted');
 }else if(scenario==='double-click'){
  assert.equal(buttons[3].disabled,true,'pending picker accepts repeated toggle');
  buttons[3].click();assert.equal(gates.length,2,'duplicate picker authorization issued');
  gates[1].resolve();await drain();assert.equal(nodes.violationField_procedure_document_ids.value,'synthetic-procedure');
 }else throw Error('unknown scenario');
 console.log('PASS '+scenario);
})().catch(error=>{console.error(error);process.exitCode=1;});
