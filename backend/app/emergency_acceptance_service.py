"""Authenticated callers persist measurements; this service does not approve releases."""
from hashlib import sha256
import json

from fastapi import HTTPException
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError

from .audit import write_audit
from .authz import permission_codes
from .emergency_acceptance import evaluate_acceptance
from .emergency_acceptance_api_schemas import EVIDENCE_GATES
from .emergency_acceptance_models import EmergencyAcceptanceEvaluation
from .models import Document, now_utc
from .settings import settings


READ_CODES = {'emergency.case.read', 'emergency.patient.read', 'emergency.report.read'}


def require_details(db, user):
    if not READ_CODES.issubset(permission_codes(db, user.user_id)):
        raise HTTPException(403, '救急の個票・評価記録を扱う権限がありません。')


def allow_dataset(kind):
    if kind == 'internal_trial' and not settings.emergency_acceptance_internal_enabled:
        raise HTTPException(403, '本部内実測は、この環境では有効になっていません。')


def get_evaluation(db, identity, *, lock=False):
    query = select(EmergencyAcceptanceEvaluation).where(
        EmergencyAcceptanceEvaluation.evaluation_id == str(identity))
    if lock:
        query = query.with_for_update().execution_options(populate_existing=True)
    row = db.scalar(query)
    if row is None:
        raise HTTPException(404, '評価記録が見つかりません。')
    allow_dataset(row.dataset_kind)
    return row


def successor(db, identity):
    return db.scalar(select(EmergencyAcceptanceEvaluation.evaluation_id).where(
        EmergencyAcceptanceEvaluation.supersedes_id == identity))


def output(db, row, user, *, include_measurement=False):
    evidence = [{key: item[key] for key in ('gate', 'document_id', 'result')} for item in row.evidence]
    by_gate = {item['gate']: item['result'] for item in evidence}
    superseded_by = successor(db, row.evaluation_id)
    result = {
        'evaluation_id': row.evaluation_id, 'version': row.version, 'dataset_kind': row.dataset_kind,
        'status': row.status, 'created_at': row.created_at, 'reviewed_at': row.reviewed_at,
        'review_decision': row.review_decision, 'summary': row.summary, 'supersedes_id': row.supersedes_id,
        'superseded_by': superseded_by,
        'evidence': evidence, 'production_complete': False,
        'release_status': 'NOT_RELEASE_APPROVAL',
        'can_review': bool(not superseded_by and row.status == 'recorded' and row.created_by != user.user_id
                           and user.employee_id and row.created_employee_id
                           and user.employee_id != row.created_employee_id),
        'release_gates': [{'gate': gate, 'status': (
            'MISSING' if gate not in by_gate else 'RECORDED_PASS' if by_gate[gate] == 'passed' else 'RECORDED_FAIL')}
                         for gate in EVIDENCE_GATES],
    }
    if include_measurement:
        result['measurement'] = row.measurement
    return result


def audit(db, user, action, row):
    # Explicit allowlist. No measurement JSON, original hashes, field values or document names.
    write_audit(db, user_id=user.user_id, action='emergency.acceptance.' + action,
                entity_type='emergency_acceptance_evaluations', entity_id=row.evaluation_id,
                after={'version': row.version, 'dataset_kind': row.dataset_kind,
                       'status': row.status, 'report_count': len(row.measurement['reports']),
                       'review_decision': row.review_decision, 'evidence_count': len(row.evidence)})


def save(db, user, payload):
    allow_dataset(payload.measurement.dataset_kind)
    normalized = payload.model_dump(mode='json', exclude={'request_id'})
    digest = sha256(json.dumps(normalized, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()).hexdigest()
    previous = db.scalar(select(EmergencyAcceptanceEvaluation).where(
        EmergencyAcceptanceEvaluation.request_id == str(payload.request_id)))
    if previous is not None:
        if previous.request_sha256 != digest or previous.created_by != user.user_id:
            raise HTTPException(409, '同じ要求番号に異なる内容が登録されています。')
        return previous, False
    if payload.supersedes_id is not None:
        parent = get_evaluation(db, payload.supersedes_id, lock=True)
        if parent.version != payload.expected_previous_version or parent.dataset_kind != payload.measurement.dataset_kind:
            raise HTTPException(409, '前の評価版が変わっています。再読込してください。')
        if db.scalar(select(EmergencyAcceptanceEvaluation.evaluation_id).where(
                EmergencyAcceptanceEvaluation.supersedes_id == parent.evaluation_id)):
            raise HTTPException(409, 'この評価には既に新版があります。')
    row = EmergencyAcceptanceEvaluation(
        request_id=str(payload.request_id), request_sha256=digest,
        supersedes_id=str(payload.supersedes_id) if payload.supersedes_id else None,
        dataset_kind=payload.measurement.dataset_kind,
        measurement=payload.measurement.model_dump(mode='json'), summary=evaluate_acceptance(payload.measurement),
        created_by=user.user_id, created_employee_id=user.employee_id)
    try:
        db.add(row); db.flush(); audit(db, user, 'create', row); db.commit()
    except IntegrityError:
        db.rollback()
        # A retry after a concurrent identical request must not create a second record.
        prior = db.scalar(select(EmergencyAcceptanceEvaluation).where(
            EmergencyAcceptanceEvaluation.request_id == str(payload.request_id)))
        if prior and prior.request_sha256 == digest and prior.created_by == user.user_id:
            return prior, False
        raise HTTPException(409, '評価が同時に更新されました。再読込してください。') from None
    db.refresh(row)
    return row, True


def review(db, user, identity, payload):
    row = get_evaluation(db, identity, lock=True)
    if (row.version != payload.expected_version or row.status != 'recorded'
            or successor(db, row.evaluation_id)):
        raise HTTPException(409, '評価版が変わっています。再読込してください。')
    if (row.created_by == user.user_id or not user.employee_id or not row.created_employee_id
            or row.created_employee_id == user.employee_id):
        raise HTTPException(403, '登録者とは別の職員による確認が必要です。')
    if payload.evidence and 'document.read' not in permission_codes(db, user.user_id):
        raise HTTPException(403, '根拠資料を確認する権限がありません。')
    evidence = []
    for item in payload.evidence:
        document = db.get(Document, str(item.document_id))
        if document is None or document.document_type != 'emergency_acceptance_evidence':
            raise HTTPException(422, '内部登録済みの完成評価用証拠資料を指定してください。')
        evidence.append({**item.model_dump(mode='json'), 'document_sha256': document.sha256})
    changed = db.execute(update(EmergencyAcceptanceEvaluation).where(
        EmergencyAcceptanceEvaluation.evaluation_id == row.evaluation_id,
        EmergencyAcceptanceEvaluation.version == payload.expected_version,
        EmergencyAcceptanceEvaluation.status == 'recorded').values(
            version=payload.expected_version + 1, status='reviewed', review_decision=payload.decision,
            reviewed_by=user.user_id, reviewed_employee_id=user.employee_id, reviewed_at=now_utc(), evidence=evidence))
    if changed.rowcount != 1:
        db.rollback()
        raise HTTPException(409, '評価が同時に確認されました。再読込してください。')
    db.flush(); db.refresh(row); audit(db, user, 'review', row)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, '確認結果を保存できません。再読込してください。') from None
    db.refresh(row)
    return row
