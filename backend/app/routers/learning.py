"""Human-reviewed local learning; candidates never mutate business originals."""
from typing import Literal
from uuid import UUID
from fastapi import APIRouter,Depends,HTTPException
from pydantic import BaseModel,Field,ConfigDict,field_validator
from sqlalchemy import select,update,text
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from ..db import get_db
from ..authz import require_permission,permission_codes,current_user,revalidate_session
from ..audit import write_audit
from ..models import Document,FeatureFlag,User
from ..personnel import account_change_lock,employee_available
from ..settings import settings
from ..learning_engine import TASKS,compile_corrections,apply_artifact,compare_artifacts,fingerprint,validate_cases
from ..learning_models import LearningCorrection as Correction,LearningEvaluationSet as EvaluationSet,LearningArtifact as Artifact,LearningEvaluation as Evaluation,LearningChampion as Champion,LearningTransition as Transition

router=APIRouter(prefix='/learning',tags=['learning'])
Task=Literal['ocr','proper_names','audio_correction','document_correction','document_classification','facility_linking','photo_classification','workflow_pattern']


class Input(BaseModel):
    model_config=ConfigDict(extra='forbid')


class Reason(Input):
    reason:str=Field(min_length=1,max_length=1000)
    @field_validator('reason')
    @classmethod
    def nonblank(cls,value):
        if not value.strip():raise ValueError('Human reason required')
        return value.strip()


class CorrectionCreate(Reason):
    task:Task
    source_document_id:UUID|None=None
    synthetic:bool=False
    input_text:str=Field(min_length=1,max_length=2000)
    output_text:str=Field(max_length=2000)


class Review(Reason):
    expected_version:int=Field(ge=1)
    decision:Literal['approved','rejected']


class SetCreate(Reason):
    task:Task
    name:str=Field(min_length=1,max_length=200)
    synthetic:bool=False
    cases:list[dict]=Field(min_length=1,max_length=100)
    source_document_ids:list[UUID]=Field(default_factory=list,max_length=100)


class ArtifactCreate(Reason):
    task:Task
    correction_ids:list[UUID]=Field(min_length=1,max_length=500)


class Evaluate(Input):
    evaluation_set_id:UUID


class Promote(Reason):
    evaluation_id:UUID
    expected_version:int=Field(ge=1)


class Rollback(Reason):
    transition_id:UUID
    expected_version:int=Field(ge=1)


class Suggest(Input):
    task:Task
    input_text:str=Field(max_length=8000)


def output(row):return {column.name:getattr(row,column.name) for column in row.__table__.columns}
def get(db,model,identity):
    row=db.get(model,str(identity))
    if not row:raise HTTPException(404,'learning record not found')
    return row


def authority(db,actor,task,synthetic=False):
    if task not in TASKS:raise HTTPException(422,'unsupported learning task')
    flag=db.scalar(select(FeatureFlag).where(FeatureFlag.key=='module.learning.enabled'))
    if (flag is None and settings.production_mode) or (flag is not None and not flag.enabled):raise HTTPException(503,'learning module disabled')
    codes=permission_codes(db,actor.user_id)
    needed={'document.read','fire_investigation.read' if task in {'audio_correction','photo_classification','document_correction'} else 'intake.read'}
    if not needed<=codes:raise HTTPException(403,'source task access required')
    if synthetic and (settings.production_mode or 'account.manage' not in codes):raise HTTPException(422,'synthetic examples require nonproduction administrator')


def human_lock(db,actor,permission):
    account_change_lock(db)
    revalidate_session(db,actor.user_id)
    current=db.scalar(select(User).where(User.user_id==actor.user_id).execution_options(populate_existing=True))
    if not current or not current.active or not employee_available(db,current) or permission not in permission_codes(db,actor.user_id):raise HTTPException(403,'Human authority no longer effective')
    current_user(current)


def audit(db,actor,action,row,reason=None):
    write_audit(db,user_id=actor.user_id,action='learning.'+action,entity_type=row.__tablename__,
        entity_id=str(getattr(row,next(iter(row.__table__.primary_key.columns)).name)),
        after={'task':row.task,'reason':reason,'human_review_required':True})


def commit(db):
    try:db.commit()
    except IntegrityError:db.rollback();raise HTTPException(409,'concurrent or invalid learning change') from None


def lock_champion(db,task):
    if db.bind.dialect.name=='postgresql':db.execute(text('SELECT pg_advisory_xact_lock(hashtext(:key))'),{'key':'fire-ai-learning:'+task})
    champion=db.scalar(select(Champion).where(Champion.task==task).with_for_update().execution_options(populate_existing=True))
    if champion is None:
        champion=Champion(task=task);db.add(champion);db.flush()
    return champion


def artifact_payload(db,identity,task):
    if identity is None:return compile_corrections(task,[])
    row=get(db,Artifact,identity)
    if row.task!=task or fingerprint(row.artifact)!=row.artifact_sha256:raise HTTPException(409,'artifact integrity mismatch')
    return row.artifact


def validate_sources(db,evidence):
    for source in evidence:
        if get(db,Document,source['document_id']).sha256!=source['sha256']:raise HTTPException(409,'learning original evidence changed')


def validate_evaluation_evidence(db,artifact,fixed):
    validate_sources(db,fixed.source_evidence)
    validate_sources(db,[{'document_id':source['source_document_id'],'sha256':source['source_sha256']} for source in artifact.training_evidence if source['source_document_id']])
    training_ids={source['source_document_id'] for source in artifact.training_evidence if source['source_document_id']}
    training_hashes={source['source_sha256'] for source in artifact.training_evidence if source['source_document_id']}
    if training_ids & {source['document_id'] for source in fixed.source_evidence} or training_hashes & {source['sha256'] for source in fixed.source_evidence}:raise HTTPException(409,'fixed evaluation must be separate from training originals')


@router.get('/context')
def context(actor=Depends(require_permission('learning.read')),db:Session=Depends(get_db)):
    codes=permission_codes(db,actor.user_id)
    tasks=[task for task in sorted(TASKS) if {'document.read','fire_investigation.read' if task in {'audio_correction','photo_classification','document_correction'} else 'intake.read'}<=codes]
    return {'user_id':actor.user_id,'username':actor.username,'permissions':sorted(codes),'tasks':tasks,'production_mode':settings.production_mode,'engine':'literal-correction-v1'}


@router.get('/sources')
def sources(task:Task='ocr',q:str='',offset:int=0,actor=Depends(require_permission('learning.read')),db:Session=Depends(get_db)):
    authority(db,actor,task)
    if len(q)>200 or offset<0:raise HTTPException(422,'invalid source search')
    query=select(Document)
    if q:query=query.where(Document.original_filename.ilike('%'+q.replace('\\','\\\\').replace('%','\\%').replace('_','\\_')+'%',escape='\\'))
    rows=db.scalars(query.order_by(Document.created_at.desc(),Document.document_id).offset(offset).limit(100)).all()
    return [{'document_id':row.document_id,'name':row.original_filename,'sha256':row.sha256} for row in rows]


@router.get('/corrections')
def corrections(task:Task='ocr',limit:int=50,offset:int=0,actor=Depends(require_permission('learning.read')),db:Session=Depends(get_db)):
    authority(db,actor,task)
    if not 1<=limit<=100 or offset<0:raise HTTPException(422,'invalid paging')
    rows=db.scalars(select(Correction).where(Correction.task==task).order_by(Correction.created_at.desc(),Correction.correction_id).offset(offset).limit(limit)).all()
    return [output(row) for row in rows]


@router.post('/corrections',status_code=201)
def create_correction(payload:CorrectionCreate,actor=Depends(require_permission('learning.record')),db:Session=Depends(get_db)):
    human_lock(db,actor,'learning.record')
    authority(db,actor,payload.task,payload.synthetic)
    if payload.synthetic!=(payload.source_document_id is None):raise HTTPException(422,'existing source document or explicit synthetic example required')
    source=get(db,Document,payload.source_document_id) if payload.source_document_id else None
    row=Correction(task=payload.task,input_text=payload.input_text,output_text=payload.output_text,
        source_document_id=source.document_id if source else None,source_sha256=source.sha256 if source else None,
        synthetic=payload.synthetic,reason=payload.reason,created_by=actor.user_id)
    db.add(row);db.flush();audit(db,actor,'correction.create',row,payload.reason);commit(db);return output(row)


@router.post('/corrections/{identity}/review')
def review_correction(identity:UUID,payload:Review,actor=Depends(require_permission('learning.review')),db:Session=Depends(get_db)):
    human_lock(db,actor,'learning.review')
    row=get(db,Correction,identity);authority(db,actor,row.task,row.synthetic)
    if row.source_document_id and get(db,Document,row.source_document_id).sha256!=row.source_sha256:raise HTTPException(409,'source changed')
    changed=db.execute(update(Correction).where(Correction.correction_id==str(identity),Correction.version==payload.expected_version,Correction.review_status=='pending')
        .values(review_status=payload.decision,reviewed_by=actor.user_id,reason=payload.reason,version=payload.expected_version+1)).rowcount
    if not changed:raise HTTPException(409,'correction changed or already reviewed')
    audit(db,actor,'correction.review',row,payload.reason);commit(db);db.refresh(row);return output(row)


@router.get('/evaluation-sets')
def evaluation_sets(task:Task='ocr',actor=Depends(require_permission('learning.read')),db:Session=Depends(get_db)):
    authority(db,actor,task)
    return [output(row) for row in db.scalars(select(EvaluationSet).where(EvaluationSet.task==task).order_by(EvaluationSet.created_at.desc()).limit(100))]


@router.post('/evaluation-sets',status_code=201)
def create_set(payload:SetCreate,actor=Depends(require_permission('learning.record')),db:Session=Depends(get_db)):
    human_lock(db,actor,'learning.record')
    authority(db,actor,payload.task,payload.synthetic)
    try:cases=validate_cases(payload.cases)
    except ValueError as exc:raise HTTPException(422,str(exc)) from None
    if payload.synthetic and payload.source_document_ids:raise HTTPException(422,'synthetic test cannot claim original evidence')
    if not payload.synthetic and not payload.source_document_ids:raise HTTPException(422,'real fixed evaluation requires original documents')
    sources=[get(db,Document,identity) for identity in dict.fromkeys(map(str,payload.source_document_ids))]
    evidence=[{'document_id':source.document_id,'sha256':source.sha256} for source in sources]
    row=EvaluationSet(task=payload.task,name=payload.name,cases=cases,cases_sha256=fingerprint(cases),source_evidence=evidence,synthetic=payload.synthetic,reason=payload.reason,created_by=actor.user_id)
    db.add(row);db.flush();audit(db,actor,'set.create',row,payload.reason);commit(db);return output(row)


@router.post('/evaluation-sets/{identity}/review')
def review_set(identity:UUID,payload:Review,actor=Depends(require_permission('learning.review')),db:Session=Depends(get_db)):
    human_lock(db,actor,'learning.review')
    row=get(db,EvaluationSet,identity);authority(db,actor,row.task,row.synthetic)
    validate_sources(db,row.source_evidence)
    if fingerprint(row.cases)!=row.cases_sha256:raise HTTPException(409,'evaluation integrity mismatch')
    changed=db.execute(update(EvaluationSet).where(EvaluationSet.evaluation_set_id==str(identity),EvaluationSet.version==payload.expected_version,EvaluationSet.review_status=='pending')
        .values(review_status=payload.decision,reviewed_by=actor.user_id,reason=payload.reason,version=payload.expected_version+1)).rowcount
    if not changed:raise HTTPException(409,'evaluation set changed or already reviewed')
    audit(db,actor,'set.review',row,payload.reason);commit(db);db.refresh(row);return output(row)


@router.get('/artifacts')
def artifacts(task:Task='ocr',actor=Depends(require_permission('learning.read')),db:Session=Depends(get_db)):
    authority(db,actor,task)
    return [output(row) for row in db.scalars(select(Artifact).where(Artifact.task==task).order_by(Artifact.created_at.desc()).limit(100))]


@router.post('/artifacts',status_code=201)
def create_artifact(payload:ArtifactCreate,actor=Depends(require_permission('learning.evaluate')),db:Session=Depends(get_db)):
    human_lock(db,actor,'learning.evaluate')
    authority(db,actor,payload.task)
    ids=list(dict.fromkeys(map(str,payload.correction_ids)))
    rows=[get(db,Correction,identity) for identity in ids]
    for row in rows:
        authority(db,actor,row.task,row.synthetic)
        if row.task!=payload.task or row.review_status!='approved':raise HTTPException(409,'only approved matching corrections can train')
        if row.source_document_id and get(db,Document,row.source_document_id).sha256!=row.source_sha256:raise HTTPException(409,'training source changed')
    try:compiled=compile_corrections(payload.task,[output(row) for row in rows])
    except ValueError as exc:raise HTTPException(422,str(exc)) from None
    evidence=[{'correction_id':row.correction_id,'version':row.version,'source_document_id':row.source_document_id,'source_sha256':row.source_sha256,'correction_sha256':fingerprint({'input':row.input_text,'output':row.output_text})} for row in rows]
    row=Artifact(task=payload.task,artifact=compiled,artifact_sha256=fingerprint(compiled),training_evidence=evidence,synthetic=any(row.synthetic for row in rows),created_by=actor.user_id)
    db.add(row);db.flush();audit(db,actor,'candidate.create',row,payload.reason);commit(db);return output(row)


@router.post('/artifacts/{identity}/evaluate',status_code=201)
def evaluate(identity:UUID,payload:Evaluate,actor=Depends(require_permission('learning.evaluate')),db:Session=Depends(get_db)):
    human_lock(db,actor,'learning.evaluate')
    artifact=get(db,Artifact,identity);authority(db,actor,artifact.task,artifact.synthetic)
    fixed=get(db,EvaluationSet,payload.evaluation_set_id);authority(db,actor,fixed.task,fixed.synthetic)
    if fixed.task!=artifact.task or fixed.review_status!='approved' or fingerprint(fixed.cases)!=fixed.cases_sha256:raise HTTPException(409,'approved matching fixed evaluation required')
    validate_evaluation_evidence(db,artifact,fixed)
    champion=lock_champion(db,artifact.task)
    try:result=compare_artifacts(artifact_payload(db,champion.artifact_id,artifact.task),artifact_payload(db,artifact.artifact_id,artifact.task),fixed.cases)
    except ValueError as exc:raise HTTPException(422,str(exc)) from None
    row=Evaluation(artifact_id=artifact.artifact_id,evaluation_set_id=fixed.evaluation_set_id,champion_artifact_id=champion.artifact_id,champion_version=champion.version,result=result,result_sha256=fingerprint(result),created_by=actor.user_id)
    db.add(row);db.flush()
    write_audit(db,user_id=actor.user_id,action='learning.evaluate',entity_type='learning_evaluation',entity_id=row.evaluation_id,after={'task':artifact.task,'result_sha256':row.result_sha256,'fixed_set_sha256':fixed.cases_sha256,'human_review_required':True})
    commit(db);return output(row)


@router.get('/evaluations')
def evaluations(task:Task='ocr',actor=Depends(require_permission('learning.read')),db:Session=Depends(get_db)):
    authority(db,actor,task)
    return [output(row) for row in db.scalars(select(Evaluation).join(Artifact,Artifact.artifact_id==Evaluation.artifact_id).where(Artifact.task==task).order_by(Evaluation.created_at.desc()).limit(100))]


@router.get('/champions/{task}')
def champion_info(task:Task,actor=Depends(require_permission('learning.read')),db:Session=Depends(get_db)):
    authority(db,actor,task);champion=db.get(Champion,task)
    return output(champion) if champion else {'task':task,'artifact_id':None,'version':1}


@router.get('/champions/{task}/history')
def champion_history(task:Task,actor=Depends(require_permission('learning.read')),db:Session=Depends(get_db)):
    authority(db,actor,task)
    return [output(row) for row in db.scalars(select(Transition).where(Transition.task==task).order_by(Transition.applied_version.desc()).limit(100))]


def transition(db,actor,champion,target,action,reason,evaluation_id=None,rollback_of=None):
    old=champion.artifact_id;version=champion.version
    changed=db.execute(update(Champion).where(Champion.task==champion.task,Champion.version==version).values(artifact_id=target,version=version+1)).rowcount
    if not changed:raise HTTPException(409,'champion changed')
    row=Transition(task=champion.task,action=action,previous_artifact_id=old,selected_artifact_id=target,evaluation_id=evaluation_id,rollback_of=rollback_of,applied_version=version+1,reason=reason,created_by=actor.user_id)
    db.add(row);db.flush();audit(db,actor,action,row,reason);commit(db);return {**output(champion),'transition_id':row.transition_id}


@router.post('/champions/{task}/promote')
def promote(task:Task,payload:Promote,actor=Depends(require_permission('learning.promote')),db:Session=Depends(get_db)):
    human_lock(db,actor,'learning.promote')
    authority(db,actor,task);champion=lock_champion(db,task)
    if champion.version!=payload.expected_version:raise HTTPException(409,'champion changed')
    result=get(db,Evaluation,payload.evaluation_id);artifact=get(db,Artifact,result.artifact_id);fixed=get(db,EvaluationSet,result.evaluation_set_id)
    authority(db,actor,artifact.task,artifact.synthetic);authority(db,actor,fixed.task,fixed.synthetic)
    if artifact.task!=task or fixed.task!=task or result.champion_version!=champion.version or result.champion_artifact_id!=champion.artifact_id:raise HTTPException(409,'evaluation baseline changed')
    if fixed.review_status!='approved' or fingerprint(fixed.cases)!=fixed.cases_sha256 or fingerprint(result.result)!=result.result_sha256:raise HTTPException(409,'evaluation evidence changed')
    validate_evaluation_evidence(db,artifact,fixed)
    # Recalculate from immutable evidence; caller cannot supply accuracy or override a gate.
    recalculated=compare_artifacts(artifact_payload(db,champion.artifact_id,task),artifact_payload(db,artifact.artifact_id,task),fixed.cases)
    if fingerprint(recalculated)!=result.result_sha256 or not recalculated['no_regression'] or not recalculated['strict_improvement']:raise HTTPException(409,'candidate must improve fixed benchmark without regression')
    return transition(db,actor,champion,artifact.artifact_id,'promote',payload.reason,result.evaluation_id)


@router.post('/champions/{task}/rollback')
def rollback(task:Task,payload:Rollback,actor=Depends(require_permission('learning.promote')),db:Session=Depends(get_db)):
    human_lock(db,actor,'learning.promote')
    authority(db,actor,task);champion=lock_champion(db,task);prior=get(db,Transition,payload.transition_id)
    if champion.version!=payload.expected_version or prior.task!=task or prior.applied_version!=champion.version or prior.selected_artifact_id!=champion.artifact_id:raise HTTPException(409,'rollback must reverse the current lineage tip')
    if prior.previous_artifact_id:
        target=get(db,Artifact,prior.previous_artifact_id);authority(db,actor,target.task,target.synthetic);artifact_payload(db,target.artifact_id,task)
    return transition(db,actor,champion,prior.previous_artifact_id,'rollback',payload.reason,rollback_of=prior.transition_id)


@router.post('/suggest')
def suggest(payload:Suggest,actor=Depends(require_permission('learning.read')),db:Session=Depends(get_db)):
    authority(db,actor,payload.task);champion=db.get(Champion,payload.task)
    identity=champion.artifact_id if champion else None
    if identity:
        artifact=get(db,Artifact,identity);authority(db,actor,artifact.task,artifact.synthetic)
    try:result=apply_artifact(artifact_payload(db,identity,payload.task),payload.input_text)
    except ValueError as exc:raise HTTPException(422,str(exc)) from None
    return {**result,'task':payload.task,'champion_artifact_id':identity,'champion_version':champion.version if champion else 1}
