"""Human measures and append-only corrective evidence; no automated legal decisions."""
from fastapi import HTTPException
from sqlalchemy import select
from . import violation_service as svc
from .models import now_utc
from .authz import permission_codes
from .violation_models import ViolationCase,ViolationMeasure,CorrectiveAction,CorrectionEvent

ACTIVE_CASES=('candidate','reviewed','confirmed')

def parent(db,case_id,expected=None,allow_completed=False):
    case=svc.get(db,ViolationCase,case_id,True)
    if case.status not in ACTIVE_CASES and not (allow_completed and case.status in ('completed','resolved_candidate')):raise HTTPException(409,'case is closed or superseded')
    if expected is not None and case.version!=expected:raise HTTPException(409,'case version changed')
    return case

def child(db,model,identity,case_id):
    row=svc.get(db,model,identity,True)
    if row.case_id!=case_id:raise HTTPException(409,'record belongs to another case')
    return row

def visible(db,user,row):
    data=svc.redact_sources(svc.serial(row),permission_codes(db,user.user_id))
    if 'document.read' not in permission_codes(db,user.user_id):
        for key in ('document_ids','procedure_document_ids'):data.pop(key,None)
        for key in ('review_snapshot','withdrawal_snapshot','completion_snapshot','source_snapshot','verification_snapshot'):data.pop(key,None)
    return data

def documents(db,user,identities):return [svc.document_snapshot(db,user,x) for x in sorted(set(identities))]

def measure_snapshot(db,user,case,row):
    formal=row.kind in ('order','disposition')
    if formal and case.status!='confirmed':raise HTTPException(409,'formal violation required before order/disposition')
    if not row.document_ids or (formal and not row.procedure_document_ids):raise HTTPException(409,'measure/procedure originals required')
    return {'case_id':case.case_id,'case_version':case.version,'case_status':case.status,'formal_violation_confirmed':bool(case.confirmed_by),'basis':svc.source_snapshot(db,user,case,formal),'documents':documents(db,user,row.document_ids),'procedure_documents':documents(db,user,row.procedure_document_ids),'instruction':row.instruction,'due_on':svc.serial(row)['due_on'],'official_reference':row.official_reference}

def create_measure(db,user,case_id,payload):
    case=parent(db,case_id,payload.expected_case_version)
    if payload.kind!='guidance' and case.status!='confirmed':raise HTTPException(409,'formal violation required')
    documents(db,user,payload.document_ids);documents(db,user,payload.procedure_document_ids)
    row=ViolationMeasure(case_id=case_id,created_by=user.user_id,**payload.model_dump(exclude={'expected_case_version'}));db.add(row);db.flush();svc.bump(db,case,case.version,{});svc.audit(db,user,'measure.create',row);return row

def patch_measure(db,user,case_id,key,payload):
    parent(db,case_id);row=child(db,ViolationMeasure,key,case_id)
    if row.status!='draft':raise HTTPException(409,'only draft measure can be edited')
    values=payload.model_dump(exclude={'expected_version'},exclude_unset=True)
    if any(values.get(k) is None for k in ('instruction','document_ids','procedure_document_ids') if k in values):raise HTTPException(422,'required measure fields cannot be null')
    before=svc.serial(row);svc.bump(db,row,payload.expected_version,values);documents(db,user,row.document_ids);documents(db,user,row.procedure_document_ids);svc.audit(db,user,'measure.update',row,before);return row

def measure_action(db,user,case_id,key,payload,verb):
    case=parent(db,case_id,allow_completed=verb=='withdraw');row=child(db,ViolationMeasure,key,case_id)
    if row.version!=payload.expected_version:raise HTTPException(409,'measure version changed')
    before=svc.serial(row);values={'last_human_reason':payload.reason}
    if verb=='review':
        if row.status not in ('draft','reviewed'):raise HTTPException(409,'draft/reviewed measure required')
        values.update(status='reviewed',review_snapshot=measure_snapshot(db,user,case,row),reviewed_by=user.user_id,reviewed_at=now_utc())
    elif verb=='confirm':
        if row.status!='reviewed':raise HTTPException(409,'separate Human measure review required')
        if row.review_snapshot!=measure_snapshot(db,user,case,row):raise HTTPException(409,'measure review evidence changed')
        values.update(status='confirmed',confirmed_by=user.user_id,confirmed_at=now_utc())
    elif verb=='cancel':
        if row.status not in ('draft','reviewed'):raise HTTPException(409,'formal measure requires withdrawal evidence')
        values.update(status='cancelled')
    elif verb=='withdraw':
        if row.status!='confirmed':raise HTTPException(409,'confirmed measure required')
        values.update(status='withdrawn',withdrawal_snapshot={'documents':documents(db,user,payload.proof_document_ids),'human_by':user.user_id,'reason':payload.reason})
    elif verb=='reopen':
        if row.status!='reviewed':raise HTTPException(409,'only unconfirmed review can be reopened')
        values.update(status='draft',review_snapshot={},reviewed_by=None,reviewed_at=None)
    else:raise HTTPException(422,'unknown measure action')
    svc.bump(db,row,payload.expected_version,values);svc.audit(db,user,'measure.'+verb,row,before);return row

def append_event(db,user,row,kind,text,reason,source_snapshot,passed=None):
    event=CorrectionEvent(action_id=row.action_id,sequence_no=row.version,kind=kind,text=text,human_reason=reason,source_snapshot=source_snapshot,verification_passed=passed,created_by=user.user_id);db.add(event);db.flush();svc.audit(db,user,'correction.event.'+kind,event);return event

def create_correction(db,user,case_id,payload):
    case=parent(db,case_id,payload.expected_case_version)
    measure=child(db,ViolationMeasure,payload.measure_id,case_id) if payload.measure_id else None
    if measure and measure.status!='confirmed':raise HTTPException(409,'confirmed Human measure required')
    if case.status!='confirmed' and (not measure or measure.kind!='guidance'):raise HTTPException(409,'candidate correction requires confirmed advisory guidance')
    row=CorrectiveAction(case_id=case_id,created_by=user.user_id,**payload.model_dump(exclude={'expected_case_version'}));db.add(row);db.flush();svc.bump(db,case,case.version,{})
    append_event(db,user,row,'instruction',row.description,'Human correction instruction',{'case_id':case_id,'case_version':case.version,'measure_id':row.measure_id});svc.audit(db,user,'correction.create',row);return row

def patch_correction(db,user,case_id,key,payload):
    parent(db,case_id);row=child(db,CorrectiveAction,key,case_id)
    if row.status in ('completed','cancelled'):raise HTTPException(409,'closed correction immutable')
    values=payload.model_dump(exclude={'expected_version','reason'},exclude_unset=True)
    if 'description' in values and values['description'] is None:raise HTTPException(422,'instruction cannot be null')
    before=svc.serial(row)
    if values:values.update(status='open',verification_passed=None,verification_snapshot={},verified_by=None,verified_at=None)
    svc.bump(db,row,payload.expected_version,values)
    append_event(db,user,row,'instruction',row.description,payload.reason,{'before':before,'after':svc.serial(row)});svc.audit(db,user,'correction.update',row,before);return row

def correction_event(db,user,case_id,key,payload,verb):
    case=parent(db,case_id);row=child(db,CorrectiveAction,key,case_id)
    if row.version!=payload.expected_version:raise HTTPException(409,'correction version changed')
    if row.status=='cancelled' or (row.status=='completed' and verb!='reopen'):raise HTTPException(409,'closed correction immutable')
    proof=documents(db,user,payload.evidence_document_ids);snapshot={'case_id':case_id,'case_version':case.version,'documents':proof};before=svc.serial(row);values={};text=payload.reason;passed=None
    if verb=='respond':
        values.update(status='responded',verification_passed=None,verification_snapshot={},verified_by=None,verified_at=None);text=payload.response_text
    elif verb=='verify':
        if row.status not in ('responded','verified'):raise HTTPException(409,'response required before Human verification')
        response=db.scalar(select(CorrectionEvent).where(CorrectionEvent.action_id==row.action_id,CorrectionEvent.kind=='response').order_by(CorrectionEvent.sequence_no.desc()))
        if not response:raise HTTPException(409,'response evidence required')
        response_proof=response.source_snapshot.get('documents',[])
        for original in response_proof:
            if svc.document_snapshot(db,user,original['document_id'])!=original:raise HTTPException(409,'response original changed')
        combined={p['document_id']:p for p in response_proof+proof};snapshot['documents']=[combined[k] for k in sorted(combined)]
        snapshot.update(response_event_id=response.event_id,instruction=row.description,due_on=svc.serial(row)['due_on'])
        passed=payload.passed;values.update(verification_snapshot=snapshot,status='verified' if passed else 'responded',verification_passed=passed,verified_by=user.user_id,verified_at=now_utc())
    elif verb=='complete':
        if row.status!='verified' or not row.verification_passed:raise HTTPException(409,'positive Human verification required')
        verification=row.verification_snapshot
        if verification.get('instruction')!=row.description or verification.get('due_on')!=svc.serial(row)['due_on']:raise HTTPException(409,'verified instruction changed')
        for original in verification.get('documents',[]):
            if svc.document_snapshot(db,user,original['document_id'])!=original:raise HTTPException(409,'verified evidence changed')
        combined={p['document_id']:p for p in verification.get('documents',[])+proof};snapshot['documents']=[combined[k] for k in sorted(combined)];snapshot['verification']=verification
        values.update(status='completed',completed_by=user.user_id,completed_at=now_utc(),completion_snapshot=snapshot)
    elif verb=='cancel':values.update(status='cancelled')
    elif verb=='reopen':
        if row.status!='completed':raise HTTPException(409,'completed correction required')
        values.update(status='open',verification_passed=None,verification_snapshot={},verified_by=None,verified_at=None,completed_by=None,completed_at=None,completion_snapshot={})
    else:raise HTTPException(422,'unknown correction event')
    svc.bump(db,row,payload.expected_version,values);append_event(db,user,row,{'respond':'response','verify':'verification','complete':'completion','cancel':'cancel','reopen':'reopen'}[verb],text,payload.reason,snapshot,passed);svc.audit(db,user,'correction.'+verb,row,before);return row

def blocks_withdrawal(db,case):
    active_tasks=db.scalar(select(CorrectiveAction).where(CorrectiveAction.case_id==case.case_id,CorrectiveAction.status.not_in(('completed','cancelled'))))
    if active_tasks:raise HTTPException(409,'open correction tasks must be explicitly resolved before case withdrawal/replacement')
    active_orders=db.scalar(select(ViolationMeasure).where(ViolationMeasure.case_id==case.case_id,ViolationMeasure.kind.in_(('order','disposition')),ViolationMeasure.status=='confirmed'))
    if active_orders:raise HTTPException(409,'formal order/disposition must be separately withdrawn before case withdrawal/replacement')

def complete_case(db,user,row):
    if row.status not in ACTIVE_CASES:raise HTTPException(409,'active case required')
    actions=list(db.scalars(select(CorrectiveAction).where(CorrectiveAction.case_id==row.case_id,CorrectiveAction.status!='cancelled').with_for_update()))
    if not actions or any(a.status!='completed' for a in actions):raise HTTPException(409,'all active correction tasks must be completed')
    pending=db.scalar(select(ViolationMeasure).where(ViolationMeasure.case_id==row.case_id,ViolationMeasure.status.in_(('draft','reviewed'))))
    if pending:raise HTTPException(409,'pending measure review must be resolved')
    for action in actions:
        if not action.completed_by or not action.verified_by or not action.verification_passed or not action.completion_snapshot.get('documents'):raise HTTPException(409,'Human verification/completion evidence missing')
        for proof in action.completion_snapshot.get('documents',[]):
            if svc.document_snapshot(db,user,proof['document_id'])!=proof:raise HTTPException(409,'completion original changed')
    return {'status':'completed' if row.confirmed_by else 'resolved_candidate','completed_by':user.user_id,'completed_at':now_utc()}
