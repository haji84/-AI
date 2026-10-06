"""Aggregate reporting only: no diagnosis, names, raw payload or clinical inference."""
from datetime import date
from sqlalchemy import distinct, func, select
from sqlalchemy.orm import Session
from .models import EmergencyCase as C, EmergencyPatient as P


def summary(db: Session, *, start_date: date | None, end_date: date | None, group_by: str) -> dict:
    conditions = []
    if start_date is not None:
        conditions.append(C.call_date >= start_date)
    if end_date is not None:
        conditions.append(C.call_date <= end_date)
    bounded = start_date is not None or end_date is not None
    if bounded:
        conditions.append(C.call_date.is_not(None))
    case_count = db.scalar(select(func.count()).select_from(C).where(*conditions)) or 0
    patient_count, hospital_count = db.execute(select(
        func.count(P.emergency_patient_id),
        func.count(P.emergency_patient_id).filter(P.hospital_code.is_not(None), func.trim(P.hospital_code) != '')
    ).select_from(C).join(P, P.emergency_case_id == C.emergency_case_id).where(*conditions)).one()
    # CASE-side grouping uses outer join, so incidents with no patient remain visible.
    # Patient-side grouping is a separate query, preventing multiplied case totals.
    if group_by == 'region':
        code = C.incident_area_code
        query = select(code, func.count(P.emergency_patient_id), func.count(distinct(C.emergency_case_id))).select_from(C).outerjoin(P, P.emergency_case_id == C.emergency_case_id)
    else:
        code = P.hospital_code if group_by == 'hospital' else P.severity_code
        query = select(code, func.count(P.emergency_patient_id), func.count(distinct(C.emergency_case_id))).select_from(C).join(P, P.emergency_case_id == C.emergency_case_id)
    rows = db.execute(query.where(*conditions).group_by(code).order_by(code)).all()
    undated = db.scalar(select(func.count()).select_from(C).where(C.call_date.is_(None))) or 0
    return {
        'period': {'start_date': start_date.isoformat() if start_date else None, 'end_date': end_date.isoformat() if end_date else None},
        'group_by': group_by,
        'totals': {'cases': case_count, 'patients': patient_count, 'patients_with_hospital': hospital_count},
        'undated_cases_excluded': undated if bounded else 0,
        'definitions': {
            'cases': '事案台帳の件数。患者との結合で重複計上しない。',
            'patients': '救護者台帳の人数。',
            'patients_with_hospital': '搬送先コードが入力された人数。コードの意味や搬送完了は推測しない。',
            'patient_share': '内訳人数 / 期間内の全救護者人数。0人の場合は0。',
            'group_cases': '区分内の事案実数。複数区分に同じ事案があるため内訳の合計は全事案数と一致しない場合がある。',
        },
        'groups': [{'code': code, 'patients': patients, 'cases': cases,
                    'patient_share': patients / patient_count if patient_count else 0.0}
                   for code, patients, cases in rows],
    }
