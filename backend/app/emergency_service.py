from collections import Counter
from datetime import date, datetime, time
from hashlib import sha256
import json
import re
from sqlalchemy import select
from .models import EmergencyCase, EmergencyPatient, EmergencyCrewAssignment, EmergencyClinicalFlag
from .emergency_models import EmergencyTreatment

RULE_VERSION = 'emergency-clinical-candidate/1'


def row_dict(row):
    data = {}
    for c in row.__table__.columns:
        value = getattr(row, c.name)
        data[c.name] = value.isoformat() if isinstance(value, (date, datetime, time)) else value
    return data


def patient_evidence(db, patient):
    treatments = db.scalars(select(EmergencyTreatment).where(EmergencyTreatment.emergency_patient_id == patient.emergency_patient_id).order_by(EmergencyTreatment.treatment_id)).all()
    evidence = {'patient_id': patient.emergency_patient_id, 'patient_version': patient.version,
                'patient_fields': {k: getattr(patient,k) for k in ['diagnosis_text','condition_text','symptoms_text']},
                'treatments': [row_dict(t) for t in treatments], 'rule_version': RULE_VERSION}
    evidence['source_sha256'] = sha256(json.dumps(evidence,ensure_ascii=False,sort_keys=True).encode()).hexdigest()
    return evidence


def suggested_flags(evidence):
    # Rule-based review aids only; free-text negation/uncertainty is deliberately conservative.
    result = []
    texts = list(evidence['patient_fields'].values())
    for flag, pattern, negation in [
        ('cpa', r'CPA|心肺停止|心停止', r'(CPA|心肺停止|心停止)\s*(なし|無し|否定)|非CPA'),
        ('allergy', r'アレルギー|アナフィラキシー', r'(アレルギー|アナフィラキシー)\s*(なし|無し|否定|禁忌)')]:
        matched = [text for text in texts if text and re.search(pattern,text,re.I) and not re.search(negation,text,re.I)]
        cpr = flag == 'cpa' and any(t['code'] in ('cpr','chest_compressions') for t in evidence['treatments'])
        if matched or cpr:
            result.append((flag, {'basis': 'treatment_assisted' if cpr else 'text_candidate', 'matched_fields': matched, **evidence}))
    return result


def check_case(db, case):
    issues = []
    def issue(code, field, message, severity='warning'):
        issues.append({'code':code,'field':field,'message':message,'severity':severity})
    for field in ['call_date','station_code','dispatch_number','call_time','dispatch_time','scene_arrival_time','leave_scene_time','return_station_time']:
        if getattr(case,field) in (None,''):
            issue('missing_input',field,'入力がありません')
    previous = None
    for field in ['call_time','dispatch_time','scene_arrival_time','leave_scene_time','return_station_time']:
        value = getattr(case,field)
        if value is not None:
            if previous is not None and value < previous:
                issue('time_day_offset_unresolved',field,'時刻が前に戻っています。日跨ぎか入力誤りかを確認してください')
            previous = value
    patients = db.scalars(select(EmergencyPatient).where(EmergencyPatient.emergency_case_id==case.emergency_case_id)).all()
    if not patients:
        issue('missing_patient','patients','傷病者が登録されていません')
    for p in patients:
        for field in ['hospital_code','severity_code']:
            if not getattr(p,field): issue('missing_input',f'{p.emergency_patient_id}.{field}','入力がありません')
    crew = db.scalars(select(EmergencyCrewAssignment).where(EmergencyCrewAssignment.emergency_case_id==case.emergency_case_id)).all()
    if any(c.employee_id is None for c in crew):
        issue('unresolved_employee','crew','共通職員IDが未確認の隊員があります')
    return {'emergency_case_id':case.emergency_case_id,'case_version':case.version,'issues':issues,'auto_corrected':False}


def statistics(db, year, month=None):
    start = date(year,month or 1,1)
    end = date(year+1,1,1) if month is None or month==12 else date(year,month+1,1)
    if month==12: end=date(year+1,1,1)
    cases = db.scalars(select(EmergencyCase).where(EmergencyCase.call_date>=start,EmergencyCase.call_date<end)).all()
    case_ids = [c.emergency_case_id for c in cases]
    patients = db.scalars(select(EmergencyPatient).where(EmergencyPatient.emergency_case_id.in_(case_ids))).all() if case_ids else []
    ids = [p.emergency_patient_id for p in patients]
    clinical = Counter()
    evidence_by_patient = {p.emergency_patient_id: patient_evidence(db,p)['source_sha256'] for p in patients}
    flags = db.scalars(select(EmergencyClinicalFlag).where(EmergencyClinicalFlag.emergency_patient_id.in_(ids),EmergencyClinicalFlag.review_status=='confirmed')).all() if ids else []
    seen=set()
    stale=0
    for f in flags:
        if f.evidence.get('source_sha256') != evidence_by_patient[f.emergency_patient_id]:
            stale+=1; continue
        key=(f.emergency_patient_id,f.flag_type)
        if key not in seen:
            clinical[f.flag_type]+=1; seen.add(key)
    return {'year':year,'month':month,'verified_clinical_counts':dict(clinical),
            'stale_confirmed_flags':stale,
            'definition':'Only Human-confirmed candidates with unchanged source evidence; no automatic diagnosis or source mutation.'}
