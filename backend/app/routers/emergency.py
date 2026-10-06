from pathlib import Path
from uuid import uuid4
from hashlib import sha256
from fastapi import APIRouter, Depends, HTTPException, Query, Response, UploadFile, File
from sqlalchemy import select, update, or_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from ..audit import write_audit
from ..authz import require_permission, permission_codes, current_user
from ..db import get_db
from ..models import EmergencyCase, EmergencyPatient, EmergencyCrewAssignment, EmergencyClinicalFlag, Employee, Document, User, now_utc
from ..emergency_models import EmergencyTreatment, EmergencyReportDraft
from ..emergency_schemas import CaseInput, CasePatch, PatientInput, PatientPatch, TreatmentInput, Version, Review, CrewInput, ReportInput
from ..emergency_service import row_dict, patient_evidence, suggested_flags, check_case, statistics

def no_store(response: Response):
    response.headers['Cache-Control']='no-store'


router = APIRouter(dependencies=[Depends(no_store)],prefix='/emergency',tags=['emergency'])


def get_row(db, model, key):
    row=db.get(model,key)
    if row is None: raise HTTPException(404,'record not found')
    return row


def lock_case(db, case_id):
    row = db.scalar(select(EmergencyCase).where(EmergencyCase.emergency_case_id == case_id).with_for_update())
    if row is None: raise HTTPException(404, 'record not found')
    return row


def lock_patient(db, patient_id):
    patient = get_row(db, EmergencyPatient, patient_id)
    lock_case(db, patient.emergency_case_id)
    return db.scalar(select(EmergencyPatient).where(EmergencyPatient.emergency_patient_id == patient_id).with_for_update().execution_options(populate_existing=True))


def need(db,user,*codes):
    if not set(codes).issubset(permission_codes(db,user.user_id)):
        raise HTTPException(403,'missing emergency detail permission')


def commit(db):
    try: db.commit()
    except IntegrityError:
        db.rollback(); raise HTTPException(409,'duplicate identity or invalid relationship')


def audit(db,user,action,row,before=None):
    write_audit(db,user_id=user.user_id,action=action,entity_type=row.__tablename__,entity_id=str(getattr(row,list(row.__table__.primary_key.columns)[0].name)),before=before,after={'version':getattr(row,'version',None)})


def patch(db,user,row,payload):
    before=row_dict(row)
    values=payload.model_dump(exclude={'expected_version'},exclude_unset=True)
    if 'call_date' in values and values['call_date'] is None:
        raise HTTPException(422,'call_date must not be null')
    pk=list(row.__table__.primary_key.columns)[0]
    result=db.execute(update(type(row)).where(pk==getattr(row,pk.name),type(row).version==payload.expected_version).values(**values,version=payload.expected_version+1,updated_at=now_utc()))
    if result.rowcount!=1:
        db.rollback(); raise HTTPException(409,'record version conflict')
    audit(db,user,'emergency.record.update',row,before)
    commit(db); db.refresh(row)
    return row_dict(row)


@router.get('/cases')
def cases(q:str='',limit:int=Query(50,ge=1,le=200),offset:int=Query(0,ge=0),db:Session=Depends(get_db),user:User=Depends(require_permission('emergency.case.read'))):
    query=select(EmergencyCase)
    if q: query=query.where(or_(EmergencyCase.dispatch_number.contains(q),EmergencyCase.incident_address.contains(q),EmergencyCase.command_text.contains(q)))
    return [row_dict(c) for c in db.scalars(query.order_by(EmergencyCase.call_date.desc(),EmergencyCase.emergency_case_id).offset(offset).limit(limit))]


@router.post('/cases',status_code=201)
def create_case(payload:CaseInput,db:Session=Depends(get_db),user:User=Depends(require_permission('emergency.case.create'))):
    row=EmergencyCase(source_case_key=f'manual:{uuid4()}',call_month=payload.call_date.strftime('%Y-%m'),**payload.model_dump())
    db.add(row); db.flush(); audit(db,user,'emergency.case.create',row); commit(db)
    return row_dict(row)


@router.get('/cases/{case_id}')
def case_detail(case_id:str,db:Session=Depends(get_db),user:User=Depends(require_permission('emergency.case.read'))):
    return row_dict(get_row(db,EmergencyCase,case_id))


@router.patch('/cases/{case_id}')
def patch_case(case_id:str,payload:CasePatch,db:Session=Depends(get_db),user:User=Depends(require_permission('emergency.case.update'))):
    need(db,user,'emergency.case.read')
    result=patch(db,user,get_row(db,EmergencyCase,case_id),payload)
    # call_month remains source/import provenance; operational statistics use call_date.
    return result


@router.get('/cases/{case_id}/patients')
def patients(case_id:str,db:Session=Depends(get_db),user:User=Depends(require_permission('emergency.patient.read'))):
    need(db,user,'emergency.case.read'); get_row(db,EmergencyCase,case_id)
    return [row_dict(p) for p in db.scalars(select(EmergencyPatient).where(EmergencyPatient.emergency_case_id==case_id).order_by(EmergencyPatient.patient_number))]


@router.post('/cases/{case_id}/patients',status_code=201)
def create_patient(case_id:str,payload:PatientInput,db:Session=Depends(get_db),user:User=Depends(require_permission('emergency.patient.create'))):
    need(db,user,'emergency.case.read','emergency.patient.read'); lock_case(db,case_id)
    row=EmergencyPatient(emergency_case_id=case_id,**payload.model_dump()); db.add(row)
    try: db.flush()
    except IntegrityError: db.rollback(); raise HTTPException(409,'patient number already exists')
    audit(db,user,'emergency.patient.create',row); commit(db); return row_dict(row)


@router.patch('/patients/{patient_id}')
def patch_patient(patient_id:str,payload:PatientPatch,db:Session=Depends(get_db),user:User=Depends(require_permission('emergency.patient.update'))):
    need(db,user,'emergency.patient.read')
    return patch(db,user,lock_patient(db,patient_id),payload)


@router.get('/cases/{case_id}/crew')
def crew(case_id:str,db:Session=Depends(get_db),user:User=Depends(require_permission('emergency.crew.read'))):
    get_row(db,EmergencyCase,case_id)
    return [row_dict(c) for c in db.scalars(select(EmergencyCrewAssignment).where(EmergencyCrewAssignment.emergency_case_id==case_id))]


@router.post('/cases/{case_id}/crew',status_code=201)
def add_crew(case_id:str,payload:CrewInput,db:Session=Depends(get_db),user:User=Depends(require_permission('emergency.crew.manage'))):
    need(db,user,'emergency.crew.read','emergency.case.read'); lock_case(db,case_id)
    employee=get_row(db,Employee,payload.employee_id)
    if not employee.active: raise HTTPException(422,'employee is inactive')
    key=f'manual:{case_id}:{payload.employee_id}:{payload.crew_role}'
    if db.scalar(select(EmergencyCrewAssignment).where(EmergencyCrewAssignment.source_record_key==key)):
        raise HTTPException(409,'crew already assigned')
    row=EmergencyCrewAssignment(emergency_case_id=case_id,source_record_key=key,source_crew_code=employee.employee_code,**payload.model_dump())
    db.add(row); db.flush(); audit(db,user,'emergency.crew.create',row); commit(db); return row_dict(row)


@router.get('/patients/{patient_id}/treatments')
def treatments(patient_id:str,db:Session=Depends(get_db),user:User=Depends(require_permission('emergency.patient.read'))):
    get_row(db,EmergencyPatient,patient_id)
    return [row_dict(t) for t in db.scalars(select(EmergencyTreatment).where(EmergencyTreatment.emergency_patient_id==patient_id))]


@router.post('/patients/{patient_id}/treatments',status_code=201)
def add_treatment(patient_id:str,payload:TreatmentInput,db:Session=Depends(get_db),user:User=Depends(require_permission('emergency.patient.update'))):
    need(db,user,'emergency.patient.read'); lock_patient(db,patient_id)
    if payload.source_document_id:
        need(db,user,'document.read'); get_row(db,Document,payload.source_document_id)
    if payload.performed_at and payload.performed_at.tzinfo is None:
        raise HTTPException(422,'performed_at requires timezone')
    row=EmergencyTreatment(emergency_patient_id=patient_id,created_by=user.user_id,**payload.model_dump())
    db.add(row); db.flush(); audit(db,user,'emergency.treatment.create',row); commit(db); return row_dict(row)


@router.get('/patients/{patient_id}/clinical-flags')
def clinical_flags(patient_id:str,db:Session=Depends(get_db),user:User=Depends(require_permission('emergency.patient.read'))):
    patient=get_row(db,EmergencyPatient,patient_id)
    current=patient_evidence(db,patient)['source_sha256']
    return [{**row_dict(f),'stale':f.evidence.get('source_sha256')!=current} for f in db.scalars(select(EmergencyClinicalFlag).where(EmergencyClinicalFlag.emergency_patient_id==patient_id))]


@router.post('/patients/{patient_id}/clinical-candidates')
def candidates(patient_id:str,payload:Version,db:Session=Depends(get_db),user:User=Depends(require_permission('emergency.clinical.generate'))):
    need(db,user,'emergency.patient.read')
    patient=lock_patient(db,patient_id)
    if patient.version!=payload.expected_version: raise HTTPException(409,'patient version conflict')
    evidence=patient_evidence(db,patient)
    output=[]
    for flag_type,source in suggested_flags(evidence):
        existing=db.scalars(select(EmergencyClinicalFlag).where(EmergencyClinicalFlag.emergency_patient_id==patient_id,EmergencyClinicalFlag.flag_type==flag_type,EmergencyClinicalFlag.derivation_method=='rule')).all()
        row=next((f for f in existing if f.evidence.get('source_sha256')==source['source_sha256']),None)
        if row is None:
            row=EmergencyClinicalFlag(candidate_fingerprint=sha256(f'{patient_id}:{flag_type}:{source["source_sha256"]}'.encode()).hexdigest(),emergency_patient_id=patient_id,flag_type=flag_type,flag_value='candidate',derivation_method='rule',evidence=source,confidence=None)
            db.add(row); db.flush(); audit(db,user,'emergency.clinical.generate',row)
        output.append(row_dict(row))
    commit(db); return output


@router.post('/clinical-flags/{flag_id}/review')
def review_flag(flag_id:str,payload:Review,db:Session=Depends(get_db),user:User=Depends(require_permission('emergency.clinical.review'))):
    need(db,user,'emergency.patient.read')
    row=get_row(db,EmergencyClinicalFlag,flag_id)
    patient=lock_patient(db,row.emergency_patient_id)
    if row.evidence.get('source_sha256')!=patient_evidence(db,patient)['source_sha256']:
        raise HTTPException(409,'candidate evidence changed; generate a new candidate')
    before=row_dict(row)
    result=db.execute(update(EmergencyClinicalFlag).where(EmergencyClinicalFlag.flag_id==flag_id,EmergencyClinicalFlag.version==payload.expected_version,EmergencyClinicalFlag.review_status=='unreviewed').values(review_status=payload.decision,version=payload.expected_version+1,confirmed_by=user.user_id,confirmed_at=now_utc()))
    if result.rowcount!=1: db.rollback(); raise HTTPException(409,'candidate review conflict')
    write_audit(db,user_id=user.user_id,action='emergency.clinical.review',entity_type='emergency_clinical_flags',entity_id=flag_id,before=before,after={'decision':payload.decision,'note':payload.note})
    commit(db); db.refresh(row); return row_dict(row)


@router.get('/cases/{case_id}/checks')
def checks(case_id:str,db:Session=Depends(get_db),user:User=Depends(require_permission('emergency.case.read'))):
    need(db,user,'emergency.patient.read','emergency.crew.read')
    return check_case(db,get_row(db,EmergencyCase,case_id))


def report_snapshot(db,case_id):
    lock_case(db,case_id)
    return {'case':row_dict(get_row(db,EmergencyCase,case_id)),
            'patients':[row_dict(p) for p in db.scalars(select(EmergencyPatient).where(EmergencyPatient.emergency_case_id==case_id).order_by(EmergencyPatient.emergency_patient_id))],
            'treatments':[row_dict(t) for t in db.scalars(select(EmergencyTreatment).join(EmergencyPatient, EmergencyPatient.emergency_patient_id==EmergencyTreatment.emergency_patient_id).where(EmergencyPatient.emergency_case_id==case_id).order_by(EmergencyTreatment.treatment_id))],
            'crew':[row_dict(c) for c in db.scalars(select(EmergencyCrewAssignment).where(EmergencyCrewAssignment.emergency_case_id==case_id).order_by(EmergencyCrewAssignment.crew_assignment_id))]}


@router.post('/cases/{case_id}/reports',status_code=201)
def create_report(case_id:str,payload:ReportInput,db:Session=Depends(get_db),user:User=Depends(require_permission('emergency.report.create'))):
    need(db,user,'emergency.case.read','emergency.patient.read','emergency.crew.read')
    row=EmergencyReportDraft(emergency_case_id=case_id,created_by=user.user_id,source_snapshot=report_snapshot(db,case_id),**payload.model_dump())
    db.add(row); db.flush(); audit(db,user,'emergency.report.create',row); commit(db); return row_dict(row)


@router.get('/cases/{case_id}/reports')
def reports(case_id:str,db:Session=Depends(get_db),user:User=Depends(require_permission('emergency.report.read'))):
    need(db,user,'emergency.patient.read','emergency.crew.read','emergency.case.read')
    get_row(db,EmergencyCase,case_id)
    return [row_dict(r) for r in db.scalars(select(EmergencyReportDraft).where(EmergencyReportDraft.emergency_case_id==case_id))]


@router.post('/reports/{report_id}/review')
def review_report(report_id:str,payload:Review,db:Session=Depends(get_db),user:User=Depends(require_permission('emergency.report.review'))):
    need(db,user,'emergency.case.read','emergency.patient.read','emergency.crew.read')
    row=get_row(db,EmergencyReportDraft,report_id)
    if row.source_snapshot!=report_snapshot(db,row.emergency_case_id):
        raise HTTPException(409,'report sources changed; create a new draft')
    result=db.execute(update(EmergencyReportDraft).where(EmergencyReportDraft.report_id==report_id,EmergencyReportDraft.version==payload.expected_version,EmergencyReportDraft.status=='draft').values(status=payload.decision,version=payload.expected_version+1,reviewed_by=user.user_id,reviewed_at=now_utc(),review_note=payload.note))
    if result.rowcount!=1: db.rollback(); raise HTTPException(409,'report review conflict')
    audit(db,user,'emergency.report.review',row); commit(db); db.refresh(row); return row_dict(row)


@router.get('/clinical-statistics')
def summary(year:int=Query(...,ge=1900,le=9998),month:int|None=Query(None,ge=1,le=12),db:Session=Depends(get_db),user:User=Depends(require_permission('emergency.report.read'))):
    result=statistics(db,year,month)
    write_audit(db,user_id=user.user_id,action='emergency.statistics.read',entity_type='emergency_statistics',after={'year':year,'month':month,'verified_clinical_counts':result['verified_clinical_counts'],'stale_confirmed_flags':result['stale_confirmed_flags']})
    commit(db); return result



@router.post('/import/workbook')
def import_workbook(file:UploadFile=File(...),db:Session=Depends(get_db),user:User=Depends(require_permission('emergency.import'))):
    from ..storage import store_upload, _root
    from ..importers.emergency import import_emergency_workbook
    if Path(file.filename or '').suffix.lower() not in ['.xlsm','.xlsx']:
        raise HTTPException(422,'audited workbook format requires xlsx or xlsm')
    path,_,_=store_upload(file)
    try: return import_emergency_workbook(db,_root()/path,started_by=user.user_id).safe_dict()
    except (ValueError,KeyError):
        db.rollback(); raise HTTPException(422,'workbook content does not match the audited mapping')
