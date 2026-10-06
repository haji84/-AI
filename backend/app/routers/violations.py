from datetime import date
from fastapi import APIRouter,Depends,Query,Response
from sqlalchemy import select
from sqlalchemy.orm import Session
from ..authz import require_permission,require_mutation_permission
from ..db import get_db
from ..models import User
from ..violation_models import ViolationCase,ViolationMeasure,CorrectiveAction,CorrectionEvent
from .. import violation_corrections as corrections
from ..violation_schemas import MeasureInput,MeasurePatch,MeasureWithdrawal,CorrectionInput,CorrectionPatch,CorrectionEvidence,CorrectionResponse,CorrectionVerification
from ..violation_schemas import CaseInput,CasePatch,HumanAction,Revision
from .. import violation_service as svc

def no_store(response:Response):response.headers['Cache-Control']='no-store'
router=APIRouter(prefix='/violations',tags=['violations'],dependencies=[Depends(no_store)])
def result(db,user,row):db.commit();return svc.case_dict(db,user,row)

@router.get('')
def cases(building_id:str|None=None,status:str|None=None,q:str=Query('',max_length=300),limit:int=Query(100,ge=1,le=1000),offset:int=Query(0,ge=0),db:Session=Depends(get_db),user:User=Depends(require_permission('violation.read'))):
    statement=select(ViolationCase)
    if building_id:statement=statement.where(ViolationCase.building_id==building_id)
    if status:statement=statement.where(ViolationCase.status==status)
    if q:statement=statement.where(ViolationCase.possible_issue.contains(q))
    return [svc.case_dict(db,user,r) for r in db.scalars(statement.order_by(ViolationCase.created_at.desc(),ViolationCase.case_id).offset(offset).limit(limit))]

@router.post('',status_code=201)
def create(payload:CaseInput,db:Session=Depends(get_db),user:User=Depends(require_mutation_permission('violation.create'))):
    svc.need(db,user,'violation.read');return result(db,user,svc.create_case(db,user,payload))

@router.get('/corrections')
def correction_queue(overdue_on:date|None=None,include_closed:bool=False,limit:int=Query(100,ge=1,le=1000),offset:int=Query(0,ge=0),db:Session=Depends(get_db),user:User=Depends(require_permission('violation.read'))):
    statement=select(CorrectiveAction).join(ViolationCase,CorrectiveAction.case_id==ViolationCase.case_id)
    if not include_closed:statement=statement.where(ViolationCase.status.in_(corrections.ACTIVE_CASES),CorrectiveAction.status.not_in(('completed','cancelled')))
    if overdue_on:statement=statement.where(CorrectiveAction.due_on<overdue_on,CorrectiveAction.status.not_in(('completed','cancelled')))
    return [corrections.visible(db,user,r) for r in db.scalars(statement.order_by(CorrectiveAction.due_on,CorrectiveAction.action_id).offset(offset).limit(limit))]

@router.get('/export/{dataset}')
def export_records(dataset:str,db:Session=Depends(get_db),user:User=Depends(require_mutation_permission('violation.export'))):
    import json
    from fastapi import HTTPException
    from ..finance_service import tabular
    from ..audit import write_audit
    svc.need(db,user,'violation.read')
    models={'cases':ViolationCase,'measures':ViolationMeasure,'corrections':CorrectiveAction,'events':CorrectionEvent}
    if dataset not in models:raise HTTPException(404,'unknown export dataset')
    model=models[dataset];key=list(model.__table__.primary_key.columns)[0]
    records=[svc.case_dict(db,user,r) if dataset=='cases' else corrections.visible(db,user,r) for r in db.scalars(select(model).order_by(key))]
    columns=list(dict.fromkeys(k for r in records for k in r)) or ['schema_version']
    values=[{k:json.dumps(v,ensure_ascii=False,sort_keys=True) if isinstance(v,(dict,list)) else v for k,v in r.items()} for r in records]
    raw,mime=tabular(columns,values,'csv')
    write_audit(db,user_id=user.user_id,action='violation.export',entity_type=model.__tablename__,entity_id=None,after={'dataset':dataset,'count':len(records),'schema_version':'violation-v1'})
    db.commit();return Response(raw,media_type=mime,headers={'Content-Disposition':f'attachment; filename="violation-{dataset}.csv"','Cache-Control':'no-store'})

@router.get('/sources/{kind}')
def source_choices(kind:str,building_id:str|None=None,q:str=Query('',max_length=300),limit:int=Query(100,ge=1,le=200),offset:int=Query(0,ge=0),db:Session=Depends(get_db),user:User=Depends(require_permission('violation.read'))):
    from fastapi import HTTPException
    from ..models import Facility,Document,LegalRule,LegalRuleVersion,Inspection,InspectionFinding
    if kind=='facilities':
        svc.need(db,user,'facility.read');stmt=select(Facility).where(Facility.deleted_at.is_(None),Facility.status=='active',Facility.name.contains(q)).order_by(Facility.name,Facility.building_id)
        return [{'id':r.building_id,'label':r.name} for r in db.scalars(stmt.offset(offset).limit(limit))]
    if kind=='documents':
        svc.need(db,user,'document.read');stmt=select(Document).where(Document.original_filename.contains(q)).order_by(Document.created_at.desc(),Document.document_id)
        return [{'id':r.document_id,'label':r.original_filename,'sha256':r.sha256} for r in db.scalars(stmt.offset(offset).limit(limit))]
    if kind=='rules':
        svc.need(db,user,'legal_rule.read','legal_source.read');stmt=select(LegalRuleVersion,LegalRule).join(LegalRule,LegalRuleVersion.rule_id==LegalRule.rule_id).where(LegalRuleVersion.status=='approved',LegalRule.name.contains(q)).order_by(LegalRule.rule_code,LegalRuleVersion.version_no,LegalRuleVersion.legal_rule_version_id)
        return [{'id':v.legal_rule_version_id,'label':f'{r.rule_code} / {r.name} / v{v.version_no}','effective_from':str(v.effective_from),'effective_to':str(v.effective_to) if v.effective_to else None} for v,r in db.execute(stmt.offset(offset).limit(limit))]
    if kind=='findings':
        svc.need(db,user,'inspection.read');svc.need(db,user,'facility.read')
        if not building_id:raise HTTPException(422,'building_id required')
        facility=svc.get(db,Facility,building_id);stmt=select(InspectionFinding).join(Inspection,InspectionFinding.inspection_id==Inspection.inspection_id).where(Inspection.building_id==facility.building_id,InspectionFinding.finding_text.contains(q)).order_by(InspectionFinding.finding_id)
        return [{'id':r.finding_id,'label':r.finding_text} for r in db.scalars(stmt.offset(offset).limit(limit))]
    raise HTTPException(404,'unknown source kind')

@router.get('/{key}')
def detail(key:str,db:Session=Depends(get_db),user:User=Depends(require_permission('violation.read'))):
    data=svc.case_dict(db,user,svc.get(db,ViolationCase,key));data['measures']=[corrections.visible(db,user,r) for r in db.scalars(select(ViolationMeasure).where(ViolationMeasure.case_id==key).order_by(ViolationMeasure.created_at,ViolationMeasure.measure_id))];data['corrections']=[corrections.visible(db,user,r) for r in db.scalars(select(CorrectiveAction).where(CorrectiveAction.case_id==key).order_by(CorrectiveAction.created_at,CorrectiveAction.action_id))];return data

@router.patch('/{key}')
def patch(key:str,payload:CasePatch,db:Session=Depends(get_db),user:User=Depends(require_mutation_permission('violation.update'))):
    svc.need(db,user,'violation.read');return result(db,user,svc.patch_case(db,user,key,payload))

@router.post('/{key}/review')
def review(key:str,payload:HumanAction,db:Session=Depends(get_db),user:User=Depends(require_mutation_permission('violation.review'))):
    svc.need(db,user,'violation.read');return result(db,user,svc.case_action(db,user,key,payload,'review'))

@router.post('/{key}/confirm')
def confirm(key:str,payload:HumanAction,db:Session=Depends(get_db),user:User=Depends(require_mutation_permission('violation.approve'))):
    svc.need(db,user,'violation.read');return result(db,user,svc.case_action(db,user,key,payload,'confirm'))

@router.post('/{key}/withdraw')
def withdraw(key:str,payload:HumanAction,db:Session=Depends(get_db),user:User=Depends(require_mutation_permission('violation.approve'))):
    svc.need(db,user,'violation.read');return result(db,user,svc.case_action(db,user,key,payload,'withdraw'))

@router.post('/{key}/revisions',status_code=201)
def revision(key:str,payload:Revision,db:Session=Depends(get_db),user:User=Depends(require_mutation_permission('violation.update'))):
    svc.need(db,user,'violation.read');return result(db,user,svc.revision(db,user,key,payload))

@router.post('/{key}/complete')
def complete(key:str,payload:HumanAction,db:Session=Depends(get_db),user:User=Depends(require_mutation_permission('violation.approve'))):
    svc.need(db,user,'violation.read');return result(db,user,svc.case_action(db,user,key,payload,'complete'))

def entity_result(db,user,row):db.commit();return corrections.visible(db,user,row)
@router.post('/{key}/measures',status_code=201)
def create_measure(key:str,payload:MeasureInput,db:Session=Depends(get_db),user:User=Depends(require_mutation_permission('violation.create'))):
    svc.need(db,user,'violation.read');return entity_result(db,user,corrections.create_measure(db,user,key,payload))
@router.patch('/{key}/measures/{identity}')
def patch_measure(key:str,identity:str,payload:MeasurePatch,db:Session=Depends(get_db),user:User=Depends(require_mutation_permission('violation.update'))):
    svc.need(db,user,'violation.read');return entity_result(db,user,corrections.patch_measure(db,user,key,identity,payload))
@router.post('/{key}/measures/{identity}/review')
def review_measure(key:str,identity:str,payload:HumanAction,db:Session=Depends(get_db),user:User=Depends(require_mutation_permission('violation.review'))):
    svc.need(db,user,'violation.read');return entity_result(db,user,corrections.measure_action(db,user,key,identity,payload,'review'))
@router.post('/{key}/measures/{identity}/confirm')
def confirm_measure(key:str,identity:str,payload:HumanAction,db:Session=Depends(get_db),user:User=Depends(require_mutation_permission('violation.approve'))):
    svc.need(db,user,'violation.read');return entity_result(db,user,corrections.measure_action(db,user,key,identity,payload,'confirm'))
@router.post('/{key}/measures/{identity}/cancel')
def cancel_measure(key:str,identity:str,payload:HumanAction,db:Session=Depends(get_db),user:User=Depends(require_mutation_permission('violation.update'))):
    svc.need(db,user,'violation.read');return entity_result(db,user,corrections.measure_action(db,user,key,identity,payload,'cancel'))
@router.post('/{key}/measures/{identity}/reopen')
def reopen_measure(key:str,identity:str,payload:HumanAction,db:Session=Depends(get_db),user:User=Depends(require_mutation_permission('violation.update'))):
    svc.need(db,user,'violation.read');return entity_result(db,user,corrections.measure_action(db,user,key,identity,payload,'reopen'))
@router.post('/{key}/measures/{identity}/withdraw')
def withdraw_measure(key:str,identity:str,payload:MeasureWithdrawal,db:Session=Depends(get_db),user:User=Depends(require_mutation_permission('violation.approve'))):
    svc.need(db,user,'violation.read');return entity_result(db,user,corrections.measure_action(db,user,key,identity,payload,'withdraw'))
@router.post('/{key}/corrections',status_code=201)
def create_correction(key:str,payload:CorrectionInput,db:Session=Depends(get_db),user:User=Depends(require_mutation_permission('violation.create'))):
    svc.need(db,user,'violation.read');return entity_result(db,user,corrections.create_correction(db,user,key,payload))
@router.patch('/{key}/corrections/{identity}')
def patch_correction(key:str,identity:str,payload:CorrectionPatch,db:Session=Depends(get_db),user:User=Depends(require_mutation_permission('violation.update'))):
    svc.need(db,user,'violation.read');return entity_result(db,user,corrections.patch_correction(db,user,key,identity,payload))
@router.get('/{key}/corrections/{identity}/events')
def correction_history(key:str,identity:str,limit:int=Query(100,ge=1,le=1000),offset:int=Query(0,ge=0),db:Session=Depends(get_db),user:User=Depends(require_permission('violation.read'))):
    corrections.child(db,CorrectiveAction,identity,key)
    return [corrections.visible(db,user,r) for r in db.scalars(select(CorrectionEvent).where(CorrectionEvent.action_id==identity).order_by(CorrectionEvent.sequence_no).offset(offset).limit(limit))]
@router.post('/{key}/corrections/{identity}/respond')
def respond(key:str,identity:str,payload:CorrectionResponse,db:Session=Depends(get_db),user:User=Depends(require_mutation_permission('violation.update'))):
    svc.need(db,user,'violation.read');return entity_result(db,user,corrections.correction_event(db,user,key,identity,payload,'respond'))
@router.post('/{key}/corrections/{identity}/verify')
def verify(key:str,identity:str,payload:CorrectionVerification,db:Session=Depends(get_db),user:User=Depends(require_mutation_permission('violation.review'))):
    svc.need(db,user,'violation.read');return entity_result(db,user,corrections.correction_event(db,user,key,identity,payload,'verify'))
@router.post('/{key}/corrections/{identity}/complete')
def complete_correction(key:str,identity:str,payload:CorrectionEvidence,db:Session=Depends(get_db),user:User=Depends(require_mutation_permission('violation.approve'))):
    svc.need(db,user,'violation.read');return entity_result(db,user,corrections.correction_event(db,user,key,identity,payload,'complete'))
@router.post('/{key}/corrections/{identity}/cancel')
def cancel_correction(key:str,identity:str,payload:CorrectionEvidence,db:Session=Depends(get_db),user:User=Depends(require_mutation_permission('violation.approve'))):
    svc.need(db,user,'violation.read');return entity_result(db,user,corrections.correction_event(db,user,key,identity,payload,'cancel'))
@router.post('/{key}/corrections/{identity}/reopen')
def reopen_correction(key:str,identity:str,payload:CorrectionEvidence,db:Session=Depends(get_db),user:User=Depends(require_mutation_permission('violation.approve'))):
    svc.need(db,user,'violation.read');return entity_result(db,user,corrections.correction_event(db,user,key,identity,payload,'reopen'))
