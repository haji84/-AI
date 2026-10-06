from fastapi import APIRouter, Depends, Response, Query, HTTPException
from fastapi.routing import APIRoute
from sqlalchemy.exc import IntegrityError, DataError
from sqlalchemy import select
from sqlalchemy.orm import Session
from ..authz import require_permission
from ..db import get_db
from ..models import User
from ..finance_models import FinanceYear, BudgetAccount
from ..finance_schemas import YearInput, YearPatch, AccountInput, AccountPatch, Action
from .. import finance_service as svc

def no_store(response:Response): response.headers['Cache-Control']='no-store'
class FinanceRoute(APIRoute):
    def get_route_handler(self):
        original=super().get_route_handler()
        async def handler(request):
            try:return await original(request)
            except IntegrityError:raise HTTPException(409,'duplicate/conflicting financial record; no batch rows committed') from None
            except DataError:raise HTTPException(422,'financial value exceeds configured database precision') from None
        return handler
router=APIRouter(prefix='/finance',tags=['finance'],dependencies=[Depends(no_store)],route_class=FinanceRoute)
def result(db,row): svc.save(db);return svc.row_dict(row)
@router.get('/years')
def years(db:Session=Depends(get_db),user:User=Depends(require_permission('finance.read'))):
    return [svc.row_dict(r) for r in db.scalars(select(FinanceYear).order_by(FinanceYear.fiscal_year.desc()))]
@router.post('/years',status_code=201)
def create_year(payload:YearInput,db:Session=Depends(get_db),user:User=Depends(require_permission('finance.admin'))):
    svc.need(db,user,'finance.read');return result(db,svc.create_year(db,user,payload))
@router.patch('/years/{key}')
def patch_year(key:str,payload:YearPatch,db:Session=Depends(get_db),user:User=Depends(require_permission('finance.admin'))):
    svc.need(db,user,'finance.read');return result(db,svc.patch_year(db,user,key,payload))
@router.post('/years/{key}/approve')
def approve_year(key:str,payload:Action,db:Session=Depends(get_db),user:User=Depends(require_permission('finance.approve'))):
    svc.need(db,user,'finance.read','finance.admin');return result(db,svc.approve_year(db,user,key,payload))
@router.get('/accounts')
def accounts(year_id:str|None=None,leaf:bool=False,level:int|None=Query(None,ge=1,le=32),q:str=Query('',max_length=300),limit:int=Query(100,ge=1,le=200),offset:int=Query(0,ge=0),db:Session=Depends(get_db),user:User=Depends(require_permission('finance.read'))):
    stmt=select(BudgetAccount)
    if year_id:stmt=stmt.where(BudgetAccount.year_id==year_id)
    if q:stmt=stmt.where(BudgetAccount.code.contains(q)|BudgetAccount.name.contains(q))
    if level:stmt=stmt.where(BudgetAccount.level==level)
    if leaf:
        from sqlalchemy import or_,and_
        policies=list(db.scalars(select(FinanceYear)))
        stmt=stmt.where(or_(*[and_(BudgetAccount.year_id==y.year_id,BudgetAccount.level==len(y.account_levels)) for y in policies])) if policies else stmt.where(False)
    return [svc.account_dict(db,r) for r in db.scalars(stmt.order_by(BudgetAccount.code,BudgetAccount.account_id).offset(offset).limit(limit))]
@router.post('/accounts',status_code=201)
def create_account(payload:AccountInput,db:Session=Depends(get_db),user:User=Depends(require_permission('finance.create'))):
    svc.need(db,user,'finance.read');return result(db,svc.create_account(db,user,payload))
@router.patch('/accounts/{key}')
def patch_account(key:str,payload:AccountPatch,db:Session=Depends(get_db),user:User=Depends(require_permission('finance.update'))):
    svc.need(db,user,'finance.read');return result(db,svc.patch_account(db,user,key,payload))

from ..finance_models import FinanceProposal, FinanceJournal
from ..finance_schemas import ProposalInput, ProposalPatch
@router.get('/accounts/{key}/balance')
def balance(key:str,db:Session=Depends(get_db),user:User=Depends(require_permission('finance.read'))):
    svc.get_row(db,BudgetAccount,key);return svc.account_balance(db,key)
@router.get('/proposals')
def proposals(q:str=Query('',max_length=300),kind:str|None=None,status:str|None=None,year_id:str|None=None,limit:int=Query(100,ge=1,le=200),offset:int=Query(0,ge=0),db:Session=Depends(get_db),user:User=Depends(require_permission('finance.read'))):
    stmt=select(FinanceProposal).join(BudgetAccount,BudgetAccount.account_id==FinanceProposal.account_id)
    if q:stmt=stmt.where(FinanceProposal.reason.contains(q))
    if kind:stmt=stmt.where(FinanceProposal.kind==kind)
    if status:stmt=stmt.where(FinanceProposal.status==status)
    if year_id:stmt=stmt.where(BudgetAccount.year_id==year_id)
    return [svc.visible(db,user,r) for r in db.scalars(stmt.order_by(FinanceProposal.created_at.desc(),FinanceProposal.proposal_id).offset(offset).limit(limit))]
@router.post('/proposals',status_code=201)
def create_proposal(payload:ProposalInput,db:Session=Depends(get_db),user:User=Depends(require_permission('finance.create'))):
    svc.need(db,user,'finance.read');row=svc.create_proposal(db,user,payload);svc.save(db);return svc.visible(db,user,row)
@router.get('/proposals/{key}')
def proposal_detail(key:str,db:Session=Depends(get_db),user:User=Depends(require_permission('finance.read'))):return svc.visible(db,user,svc.get_row(db,FinanceProposal,key))
@router.patch('/proposals/{key}')
def patch_proposal(key:str,payload:ProposalPatch,db:Session=Depends(get_db),user:User=Depends(require_permission('finance.update'))):
    svc.need(db,user,'finance.read');row=svc.patch_proposal(db,user,key,payload);svc.save(db);return svc.visible(db,user,row)
@router.post('/proposals/{key}/review')
def review_proposal(key:str,payload:Action,db:Session=Depends(get_db),user:User=Depends(require_permission('finance.review'))):
    svc.need(db,user,'finance.read');row=svc.proposal_action(db,user,key,payload,'review');svc.save(db);return svc.visible(db,user,row)
@router.post('/proposals/{key}/approve')
def approve_proposal(key:str,payload:Action,db:Session=Depends(get_db),user:User=Depends(require_permission('finance.approve'))):
    svc.need(db,user,'finance.read');row=svc.proposal_action(db,user,key,payload,'approve');svc.save(db);return svc.visible(db,user,row)
@router.post('/proposals/{key}/cancel')
def cancel_proposal(key:str,payload:Action,db:Session=Depends(get_db),user:User=Depends(require_permission('finance.admin'))):
    svc.need(db,user,'finance.read');row=svc.proposal_action(db,user,key,payload,'cancel');svc.save(db);return svc.visible(db,user,row)
@router.get('/journal')
def journal(account_id:str|None=None,limit:int=Query(100,ge=1,le=200),offset:int=Query(0,ge=0),db:Session=Depends(get_db),user:User=Depends(require_permission('finance.read'))):
    stmt=select(FinanceJournal)
    if account_id:stmt=stmt.where(FinanceJournal.account_id==account_id)
    return [svc.row_dict(r) for r in db.scalars(stmt.order_by(FinanceJournal.created_at,FinanceJournal.journal_id).offset(offset).limit(limit))]

from ..models import ContractCase, ContractCounterparty, ContractDocument, ContractChange, Document
from ..finance_models import ProcurementProfile, FinanceCandidate, FinanceContractAmendment
from ..finance_schemas import CounterpartyInput, CounterpartyPatch, ContractInput, ProfileInput, DocumentLink, CandidateInput, AmendmentInput
@router.get('/counterparties')
def counterparties(q:str=Query('',max_length=300),limit:int=Query(100,ge=1,le=200),offset:int=Query(0,ge=0),db:Session=Depends(get_db),user:User=Depends(require_permission('contract.read'))):
    stmt=select(ContractCounterparty)
    if q:stmt=stmt.where(ContractCounterparty.name.contains(q)|ContractCounterparty.registration_no.contains(q))
    return [svc.row_dict(r) for r in db.scalars(stmt.order_by(ContractCounterparty.name,ContractCounterparty.counterparty_id).offset(offset).limit(limit))]
@router.post('/counterparties',status_code=201)
def create_party(payload:CounterpartyInput,db:Session=Depends(get_db),user:User=Depends(require_permission('contract.create'))):
    svc.need(db,user,'contract.read');row=ContractCounterparty(**payload.model_dump());db.add(row);db.flush();svc.audit(db,user,'counterparty.create',row);return result(db,row)
@router.patch('/counterparties/{key}')
def patch_party(key:str,payload:CounterpartyPatch,db:Session=Depends(get_db),user:User=Depends(require_permission('contract.update'))):
    svc.need(db,user,'contract.read');row=svc.get_row(db,ContractCounterparty,key,True);svc.check_version(row,payload.expected_version);before=svc.row_dict(row);svc.bump(db,row,row.version,payload.model_dump(exclude={'expected_version'},exclude_unset=True));svc.audit(db,user,'counterparty.update',row,before);return result(db,row)
@router.get('/documents')
def documents(q:str=Query('',max_length=300),limit:int=Query(100,ge=1,le=200),offset:int=Query(0,ge=0),db:Session=Depends(get_db),user:User=Depends(require_permission('document.read'))):
    stmt=select(Document)
    if q:stmt=stmt.where(Document.original_filename.contains(q)|Document.sha256.contains(q))
    return [{'document_id':r.document_id,'original_filename':r.original_filename,'sha256':r.sha256} for r in db.scalars(stmt.order_by(Document.created_at.desc(),Document.document_id).offset(offset).limit(limit))]
@router.get('/contracts')
def contracts(q:str=Query('',max_length=300),year_id:str|None=None,limit:int=Query(100,ge=1,le=200),offset:int=Query(0,ge=0),db:Session=Depends(get_db),user:User=Depends(require_permission('contract.read'))):
    stmt=select(ContractCase).outerjoin(ContractCounterparty,ContractCounterparty.counterparty_id==ContractCase.counterparty_id)
    if q:stmt=stmt.where(ContractCase.title.contains(q)|ContractCase.contract_no.contains(q)|ContractCounterparty.name.contains(q))
    if year_id:stmt=stmt.join(ProcurementProfile).where(ProcurementProfile.year_id==year_id)
    return [svc.contract_dict(db,user,r) for r in db.scalars(stmt.order_by(ContractCase.updated_at.desc(),ContractCase.contract_case_id).offset(offset).limit(limit))]
@router.post('/contracts',status_code=201)
def create_contract(payload:ContractInput,db:Session=Depends(get_db),user:User=Depends(require_permission('finance.create'))):
    svc.need(db,user,'finance.read');row=svc.create_contract(db,user,payload);svc.save(db);return svc.contract_dict(db,user,row)
@router.get('/contracts/{key}')
def contract_detail(key:str,db:Session=Depends(get_db),user:User=Depends(require_permission('contract.read'))):return svc.contract_dict(db,user,svc.get_row(db,ContractCase,key))
@router.post('/contracts/{key}/approve')
def approve_contract(key:str,payload:Action,db:Session=Depends(get_db),user:User=Depends(require_permission('contract.approve'))):
    svc.need(db,user,'finance.approve');row=svc.approve_contract(db,user,key,payload);svc.save(db);return svc.contract_dict(db,user,row)
@router.put('/contracts/{key}/profile')
def contract_profile(key:str,payload:ProfileInput,db:Session=Depends(get_db),user:User=Depends(require_permission('finance.update'))):
    svc.need(db,user,'finance.read','contract.read','contract.update');contract=svc.get_row(db,ContractCase,key,True);svc.get_row(db,FinanceYear,payload.year_id);row=db.scalar(select(ProcurementProfile).where(ProcurementProfile.contract_case_id==key))
    if row:
        svc.check_version(row,payload.expected_version)
        if row.year_id!=payload.year_id:raise __import__('fastapi').HTTPException(409,'contract fiscal year is immutable')
        svc.bump(db,row,row.version,{'renewal_on':payload.renewal_on})
    else:
        svc.check_version(contract,payload.expected_version);row=ProcurementProfile(contract_case_id=key,year_id=payload.year_id,renewal_on=payload.renewal_on);db.add(row);db.flush()
    svc.validate_contract_policy(db,contract,contract.amount)
    svc.audit(db,user,'contract.profile',row);return result(db,row)
@router.post('/contracts/{key}/documents',status_code=201)
def link_document(key:str,payload:DocumentLink,db:Session=Depends(get_db),user:User=Depends(require_permission('contract.update'))):
    svc.need(db,user,'contract.read');contract=svc.get_row(db,ContractCase,key,True)
    if contract.status=='approved':raise __import__('fastapi').HTTPException(409,'approved source attachments require reviewed amendment')
    svc.source_document(db,user,payload.document_id);row=ContractDocument(contract_case_id=key,**payload.model_dump());db.add(row);db.flush();svc.bump(db,contract,contract.version);svc.audit(db,user,'contract.document.link',row);return result(db,row)
@router.get('/contracts/{key}/history')
def contract_history(key:str,db:Session=Depends(get_db),user:User=Depends(require_permission('contract.read'))):
    svc.get_row(db,ContractCase,key);svc.need(db,user,'document.read')
    return {'changes':[svc.row_dict(r) for r in db.scalars(select(ContractChange).where(ContractChange.contract_case_id==key).order_by(ContractChange.sequence_no))],'amendments':[svc.visible(db,user,r) for r in db.scalars(select(FinanceContractAmendment).where(FinanceContractAmendment.contract_case_id==key))]}
@router.get('/candidates')
def candidates(kind:str|None=None,year_id:str|None=None,q:str=Query('',max_length=300),limit:int=Query(100,ge=1,le=200),offset:int=Query(0,ge=0),db:Session=Depends(get_db),user:User=Depends(require_permission('finance.read'))):
    stmt=select(FinanceCandidate)
    if q:stmt=stmt.where(FinanceCandidate.title.contains(q))
    if kind:stmt=stmt.where(FinanceCandidate.kind==kind)
    if year_id:stmt=stmt.where(FinanceCandidate.year_id==year_id)
    return [svc.visible(db,user,r) for r in db.scalars(stmt.order_by(FinanceCandidate.created_at.desc(),FinanceCandidate.candidate_id).offset(offset).limit(limit))]
@router.post('/candidates',status_code=201)
def create_candidate(payload:CandidateInput,db:Session=Depends(get_db),user:User=Depends(require_permission('finance.create'))):
    svc.need(db,user,'finance.read');row=svc.create_candidate(db,user,payload);svc.save(db);return svc.visible(db,user,row)
@router.post('/candidates/{key}/review')
def review_candidate(key:str,payload:Action,db:Session=Depends(get_db),user:User=Depends(require_permission('finance.review'))):
    svc.need(db,user,'finance.read');row=svc.candidate_action(db,user,key,payload,'review');svc.save(db);return svc.visible(db,user,row)
@router.post('/candidates/{key}/cancel')
def cancel_candidate(key:str,payload:Action,db:Session=Depends(get_db),user:User=Depends(require_permission('finance.admin'))):
    svc.need(db,user,'finance.read');row=svc.candidate_action(db,user,key,payload,'cancel');svc.save(db);return svc.visible(db,user,row)
@router.post('/contracts/{key}/amendments',status_code=201)
def create_amendment(key:str,payload:AmendmentInput,db:Session=Depends(get_db),user:User=Depends(require_permission('finance.create'))):
    row=svc.create_amendment(db,user,key,payload);svc.save(db);return svc.visible(db,user,row)
@router.get('/amendments')
def amendments(db:Session=Depends(get_db),user:User=Depends(require_permission('finance.read'))):
    svc.need(db,user,'contract.read');return [svc.visible(db,user,r) for r in db.scalars(select(FinanceContractAmendment).order_by(FinanceContractAmendment.created_at.desc()).limit(200))]
@router.post('/amendments/{key}/review')
def review_amendment(key:str,payload:Action,db:Session=Depends(get_db),user:User=Depends(require_permission('finance.review'))):
    row=svc.amendment_action(db,user,key,payload,'review');svc.save(db);return svc.visible(db,user,row)
@router.post('/amendments/{key}/approve')
def approve_amendment(key:str,payload:Action,db:Session=Depends(get_db),user:User=Depends(require_permission('finance.approve'))):
    row=svc.amendment_action(db,user,key,payload,'approve');svc.save(db);return svc.visible(db,user,row)

from fastapi import File, Form, UploadFile, HTTPException
from typing import Literal
from datetime import date,timedelta
from ..models import FormTemplate
from ..finance_models import FinanceImportPreview
from ..finance_schemas import ImportConfirm,RenderInput
@router.get('/import-template/{dataset}')
def import_template(dataset:str,format:Literal['csv','xlsx']='csv',db:Session=Depends(get_db),user:User=Depends(require_permission('finance.import'))):
    svc.import_need(db,user,dataset);raw,mime=svc.tabular(svc.headers(dataset),[],format);return Response(raw,media_type=mime,headers={'Content-Disposition':f'attachment; filename="finance-{dataset}-template.{format}"','Cache-Control':'no-store'})
@router.post('/import/{dataset}')
def import_preview(dataset:str,file:UploadFile=File(...),document_id:str|None=Form(None),db:Session=Depends(get_db),user:User=Depends(require_permission('finance.import'))):
    row,sample=svc.preview_import(db,user,dataset,file,document_id);svc.save(db);return {**svc.row_dict(row),'row_data':None,'sample':sample,'rows':len(row.row_data),'schema_version':svc.SCHEMA_VERSION}
@router.post('/import-previews/{key}/confirm')
def confirm_import(key:str,payload:ImportConfirm,db:Session=Depends(get_db),user:User=Depends(require_permission('finance.import'))):
    value=svc.confirm_import(db,user,key,payload);svc.save(db);return value
@router.get('/export/{dataset}')
def export(dataset:str,format:Literal['csv','xlsx']='csv',year_id:str|None=None,db:Session=Depends(get_db),user:User=Depends(require_permission('finance.export'))):
    values=svc.export_rows(db,user,dataset,year_id);columns=list(dict.fromkeys(k for r in values for k in r)) or ['schema_version'];raw,mime=svc.tabular(columns,values,format);svc.save(db);return Response(raw,media_type=mime,headers={'Content-Disposition':f'attachment; filename="finance-{dataset}.{format}"','Cache-Control':'no-store'})
@router.get('/summary')
def summary(year_id:str,db:Session=Depends(get_db),user:User=Depends(require_permission('finance.read'))):
    svc.get_row(db,FinanceYear,year_id);return svc.finance_summary(db,year_id)
@router.get('/alerts')
def alerts(as_of:date|None=None,days:int=Query(30,ge=0,le=365),db:Session=Depends(get_db),user:User=Depends(require_permission('finance.read'))):
    target=as_of or date.today();contracts=[]
    if 'contract.read' in __import__('app.authz',fromlist=['permission_codes']).permission_codes(db,user.user_id):
        for case,profile in db.execute(select(ContractCase,ProcurementProfile).join(ProcurementProfile,ProcurementProfile.contract_case_id==ContractCase.contract_case_id)):
            for kind,due in [('expiry',case.end_date),('renewal',profile.renewal_on)]:
                if due and due<=target+timedelta(days=days):contracts.append({'kind':kind,'contract_case_id':case.contract_case_id,'title':case.title,'due_on':due.isoformat(),'overdue':due<target,'source_version':case.version})
    reviews=[svc.visible(db,user,r) for r in db.scalars(select(FinanceProposal).where(FinanceProposal.status.in_(['draft','reviewed'])).order_by(FinanceProposal.created_at).limit(200))]
    return {'as_of':target.isoformat(),'contracts':contracts,'human_review':reviews}
@router.get('/templates')
def templates(db:Session=Depends(get_db),user:User=Depends(require_permission('template.read'))):
    svc.need(db,user,'document.read');return [{'form_template_id':r.form_template_id,'name':r.name,'version_label':r.version_label,'module_code':r.module_code,'document_id':r.document_id} for r in db.scalars(select(FormTemplate).where(FormTemplate.module_code.in_(['contracts','procurement','budget']),FormTemplate.status=='active'))]
@router.post('/proposals/{key}/render',status_code=201)
def render(key:str,payload:RenderInput,db:Session=Depends(get_db),user:User=Depends(require_permission('finance.export'))):return result(db,svc.render_proposal(db,user,key,payload))

from ..finance_schemas import ContractPatch
@router.patch('/contracts/{key}')
def patch_contract(key:str,payload:ContractPatch,db:Session=Depends(get_db),user:User=Depends(require_permission('finance.update'))):
    svc.need(db,user,'finance.read');row=svc.patch_contract(db,user,key,payload);svc.save(db);return svc.contract_dict(db,user,row)

from ..finance_schemas import CandidatePatch
@router.patch('/candidates/{key}')
def patch_candidate(key:str,payload:CandidatePatch,db:Session=Depends(get_db),user:User=Depends(require_permission('finance.update'))):
    svc.need(db,user,'finance.read');row=svc.patch_candidate(db,user,key,payload);svc.save(db);return svc.visible(db,user,row)

from ..finance_models import ProcurementEvent
from ..finance_schemas import EventInput,EventPatch
@router.get('/procurement-events')
def procurement_events(contract_case_id:str|None=None,kind:str|None=None,status:str|None=None,q:str=Query('',max_length=300),limit:int=Query(100,ge=1,le=200),offset:int=Query(0,ge=0),db:Session=Depends(get_db),user:User=Depends(require_permission('finance.read'))):
    svc.need(db,user,'contract.read');stmt=select(ProcurementEvent)
    if contract_case_id:stmt=stmt.where(ProcurementEvent.contract_case_id==contract_case_id)
    if kind:stmt=stmt.where(ProcurementEvent.kind==kind)
    if status:stmt=stmt.where(ProcurementEvent.status==status)
    if q:stmt=stmt.where(ProcurementEvent.description.contains(q))
    return [svc.visible(db,user,r) for r in db.scalars(stmt.order_by(ProcurementEvent.created_at.desc(),ProcurementEvent.event_id).offset(offset).limit(limit))]
@router.post('/procurement-events',status_code=201)
def create_event(payload:EventInput,db:Session=Depends(get_db),user:User=Depends(require_permission('finance.create'))):
    svc.need(db,user,'finance.read','contract.read');row=svc.create_event(db,user,payload);svc.save(db);return svc.visible(db,user,row)
@router.get('/procurement-events/{key}')
def event_detail(key:str,db:Session=Depends(get_db),user:User=Depends(require_permission('finance.read'))):
    svc.need(db,user,'contract.read');row=svc.get_row(db,ProcurementEvent,key);return {**svc.visible(db,user,row),'payments':[svc.visible(db,user,r) for r in db.scalars(select(FinanceProposal).where(FinanceProposal.invoice_id==key))]}
@router.patch('/procurement-events/{key}')
def patch_event(key:str,payload:EventPatch,db:Session=Depends(get_db),user:User=Depends(require_permission('finance.update'))):
    svc.need(db,user,'finance.read','contract.read');row=svc.patch_event(db,user,key,payload);svc.save(db);return svc.visible(db,user,row)
@router.post('/procurement-events/{key}/review')
def review_event(key:str,payload:Action,db:Session=Depends(get_db),user:User=Depends(require_permission('finance.review'))):
    svc.need(db,user,'finance.read','contract.read');row=svc.event_action(db,user,key,payload,'review');svc.save(db);return svc.visible(db,user,row)
@router.post('/procurement-events/{key}/approve')
def approve_event(key:str,payload:Action,db:Session=Depends(get_db),user:User=Depends(require_permission('finance.approve'))):
    svc.need(db,user,'finance.read','contract.read');row=svc.event_action(db,user,key,payload,'approve');svc.save(db);return svc.visible(db,user,row)
@router.post('/procurement-events/{key}/cancel')
def cancel_event(key:str,payload:Action,db:Session=Depends(get_db),user:User=Depends(require_permission('finance.admin'))):
    svc.need(db,user,'finance.read','contract.read');row=svc.event_action(db,user,key,payload,'cancel');svc.save(db);return svc.visible(db,user,row)

from ..finance_schemas import DocumentDiff,Calculation
@router.get('/contracts/{key}/support')
def support(key:str,db:Session=Depends(get_db),user:User=Depends(require_permission('finance.read'))):
    return svc.contract_support(db,user,key)
@router.get('/documents/{key}/extract')
def extract(key:str,db:Session=Depends(get_db),user:User=Depends(require_permission('finance.read'))):
    return svc.extract_finance_document(db,user,key)
@router.post('/document-diff')
def document_diff(payload:DocumentDiff,db:Session=Depends(get_db),user:User=Depends(require_permission('finance.read'))):
    from difflib import unified_diff
    before=svc.extract_finance_document(db,user,payload.before_document_id);after=svc.extract_finance_document(db,user,payload.after_document_id)
    return {'authority':'candidate','before_source':before['source'],'after_source':after['source'],'diff':'\n'.join(unified_diff(before['text'].splitlines(),after['text'].splitlines(),fromfile=before['source']['filename'],tofile=after['source']['filename'])),'truncated':before['truncated'] or after['truncated']}
@router.post('/calculate')
def calculate(payload:Calculation,user:User=Depends(require_permission('finance.read'))):
    from decimal import Decimal
    total=sum(payload.amounts,Decimal('0'))
    if abs(total)>=Decimal('10000000000000000'):raise HTTPException(422,'result exceeds NUMERIC(18,2) authority limits')
    return {'authority':'candidate','operands':[svc.money(v) for v in payload.amounts],'total':svc.money(total)}
