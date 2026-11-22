"""Private report lifecycle, scope, immutable originals and optimistic writes."""
from __future__ import annotations

from collections import Counter
from hashlib import sha256
import json
from uuid import UUID, uuid4

from fastapi import HTTPException
from sqlalchemy import or_, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .audit import write_audit
from .authz import permission_codes
from .emergency_audit_models import AuditConfiguration, AuditEvent, AuditJob, AuditReport, AuditRevision, AuditRun, AuditSource
from .emergency_mapping import ProfileDefinition, confirm_value, map_fields
from . import emergency_vault as vault
from .models import User, now_utc
from .personnel import employee_available
from .settings import settings

DETAIL_RIGHTS = {'emergency.case.read', 'emergency.patient.read', 'emergency.report.read'}


def failure(status, message='操作できません。権限・現在の版・設定を確認してください。'):
    raise HTTPException(status, message)


def digest(value):
    return sha256(json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False, allow_nan=False).encode()).hexdigest()


def require_details(db, user):
    if not DETAIL_RIGHTS <= permission_codes(db, user.user_id):
        failure(403)
    if not settings.emergency_audit_enabled:
        failure(503, '報告書監査はサーバーで有効化されていません。')


def allow_dataset(kind):
    if kind not in {'synthetic', 'internal_trial'}:
        failure(422)
    if kind == 'internal_trial' and not (
        settings.emergency_audit_internal_enabled and settings.production_mode and
        settings.tenant_id and settings.cookie_secure and settings.database_url.startswith('postgresql')
    ):
        failure(403, '実帳票の取込は、本部内の利用環境を設定してから有効にしてください。')
    if not vault.ready():
        failure(503, '原本を保護する鍵が利用できません。管理担当者に確認してください。')


def scope_clause(db, user):
    if 'emergency.audit.read_all' in permission_codes(db, user.user_id):
        return None
    # An account reassigned to another employee must not inherit private reports.
    return or_(
        (AuditReport.owner_id == user.user_id) & (AuditReport.owner_employee_id == user.employee_id),
        (AuditReport.reviewer_id == user.user_id) & (AuditReport.reviewer_employee_id == user.employee_id),
    ) if user.employee_id else AuditReport.owner_id == '00000000-0000-0000-0000-000000000000'


def reports_query(db, user):
    require_details(db, user)
    query = select(AuditReport)
    scope = scope_clause(db, user)
    if scope is not None:
        query = query.where(scope)
    if not settings.emergency_audit_internal_enabled or not settings.production_mode:
        query = query.where(AuditReport.dataset_kind == 'synthetic')
    return query


def report(db, user, identity):
    row = db.scalar(reports_query(db, user).where(AuditReport.report_id == str(identity)))
    if row is None:
        failure(404, '対象の報告書を参照できません。')
    allow_dataset(row.dataset_kind)
    return row


def revision(db, user, identity, *, current=False):
    row = db.get(AuditRevision, str(identity))
    if row is None:
        failure(404, '対象の報告書を参照できません。')
    owner = report(db, user, row.report_id)
    if current and owner.current_revision_id != row.revision_id:
        failure(409, '新しい版があります。最新の報告書を開いてください。')
    return owner, row


def audit(db, user, action, identity, **counts):
    # Intentionally no before/after row dump, text, values, path or original filename.
    safe = {key: value for key, value in counts.items() if key in {'version', 'count', 'number', 'kind', 'status'}}
    write_audit(db, user_id=user.user_id if user else None, action='emergency.audit.' + action,
                entity_type='emergency_audit', entity_id=str(identity), after=safe)


def claim_report(db, row, expected_version):
    if row.version != expected_version:
        failure(409, '別の操作で更新されています。再読込して確認してください。')
    claimed = db.execute(update(AuditReport).where(AuditReport.report_id == row.report_id,
        AuditReport.version == expected_version).values(version=expected_version + 1)
        .execution_options(synchronize_session=False)).rowcount
    if claimed != 1:
        db.rollback(); failure(409, '別の操作で更新されています。再読込して確認してください。')
    db.refresh(row)
    return row


def configuration(db, identity, kind=None):
    row = db.get(AuditConfiguration, str(identity)) if identity else None
    if row is None or (kind is not None and row.kind != kind):
        failure(422, '様式・チェック条件を確認してください。')
    return row


def profile(db, identity):
    row = configuration(db, identity, 'profile')
    return row, ProfileDefinition.model_validate(vault.open_json('config', row.config_id, row.definition_cipher))


def read_fields(row):
    return vault.open_json('fields', row.revision_id, row.fields_cipher, {})


def mapped_fields(reading, definition):
    fields = map_fields(reading, definition)
    for item in definition.fields:
        fields[item.field_id].update(label=item.label, value_type=item.value_type,
                                     unit=item.unit, phase=item.phase)
    return fields


def queue(db, row, user, kind='read', page=None):
    active = db.scalar(select(AuditJob).where(AuditJob.revision_id == row.revision_id,
        AuditJob.kind == kind, AuditJob.status.in_(['queued', 'processing'])))
    if active:
        return active
    job = AuditJob(revision_id=row.revision_id, kind=kind, source_sha256=row.source_sha256,
                   revision_version=row.version, requested_by=user.user_id,
                   requested_employee_id=user.employee_id, page_number=page)
    db.add(job)
    if kind == 'read':
        row.processing_status = 'queued'; row.error_code = None
    return job


def verified_original(row, kind='revision'):
    identity = row.revision_id if kind == 'revision' else row.source_id
    value = vault.read_original(kind, identity)
    if len(value) != row.size_bytes or sha256(value).hexdigest() != row.source_sha256:
        raise vault.VaultError('PRIVATE_CONTENT_INTEGRITY')
    return value


def create_report(db, user, data, metadata, request_id, dataset_kind, profile_id=None,
                  *, report_id=None, expected_version=None):
    require_details(db, user); allow_dataset(dataset_kind)
    if not user.employee_id:
        failure(403, '職員と結び付いたアカウントで操作してください。')
    source_hash = sha256(data).hexdigest()
    fingerprint = digest({'sha256': source_hash, 'dataset_kind': dataset_kind,
                          'profile_id': str(profile_id) if profile_id else None,
                          'report_id': str(report_id) if report_id else None})
    existing = db.scalar(select(AuditRevision).where(AuditRevision.request_id == str(request_id)))
    if existing:
        parent = report(db, user, existing.report_id)
        if existing.request_sha256 != fingerprint or existing.created_by != user.user_id:
            failure(409, '同じ受付番号で別の内容は登録できません。')
        return parent, False
    if profile_id:
        selected, _ = profile(db, profile_id)
        if selected.status == 'retired':
            failure(409, 'この様式設定は使用を終了しています。')
    if report_id:
        parent = report(db, user, report_id)
        if parent.dataset_kind != dataset_kind:
            failure(422)
        from .emergency_training_service import validate_family_original
        validate_family_original(db, parent.report_id, source_hash)
        claim_report(db, parent, expected_version)
        parent.revision_number += 1
        # Existing active jobs cannot overwrite a replacement revision.
        db.execute(update(AuditJob).where(AuditJob.revision_id == parent.current_revision_id,
            AuditJob.status.in_(['queued', 'processing'])).values(status='cancelled', error_code='SUPERSEDED', finished_at=now_utc()))
    else:
        parent = AuditReport(report_id=str(uuid4()), request_id=str(request_id), request_sha256=fingerprint,
            owner_id=user.user_id, owner_employee_id=user.employee_id, dataset_kind=dataset_kind,
            version=1, revision_number=1)
        db.add(parent); db.flush()
    row = AuditRevision(revision_id=str(uuid4()), report_id=parent.report_id, number=parent.revision_number,
        request_id=str(request_id), request_sha256=fingerprint, source_sha256=source_hash,
        media_type=metadata['media_type'], size_bytes=len(data), page_count=metadata['page_count'],
        profile_id=str(profile_id) if profile_id else None, version=1, created_by=user.user_id)
    db.add(row); parent.current_revision_id = row.revision_id
    stored = False
    try:
        db.flush()
        vault.store_original('revision', row.revision_id, data); stored = True
        queue(db, row, user)
        audit(db, user, 'revision_create', parent.report_id, version=parent.version, number=row.number)
        db.commit()
    except Exception:
        db.rollback()
        if stored:
            vault.discard_uncommitted('revision', row.revision_id)
        raise
    return parent, True


def remap(db, user, identity, payload):
    parent, row = revision(db, user, identity, current=True)
    if row.processing_status not in {'ready', 'partial'} or not row.reading_cipher:
        failure(409, '読取処理が終わってから様式を設定してください。')
    selected, definition = profile(db, payload.profile_id)
    if selected.status == 'retired':
        failure(409)
    fields = mapped_fields(vault.open_json('reading', row.revision_id, row.reading_cipher), definition)
    claim_report(db, parent, payload.expected_version)
    row.profile_id = selected.config_id; row.version += 1
    row.fields_cipher = vault.seal_json('fields', row.revision_id, fields)
    row.ai_cipher = None
    audit(db, user, 'mapping', parent.report_id, version=parent.version, count=len(fields))
    db.commit(); return parent


def confirm_fields(db, user, identity, payload):
    parent, row = revision(db, user, identity, current=True)
    if not row.profile_id or row.processing_status not in {'ready', 'partial'}:
        failure(409, '読取結果と様式を確認してください。')
    _, definition = profile(db, row.profile_id)
    definitions = {item.field_id: item for item in definition.fields}
    fields = read_fields(row)
    for item in payload.fields:
        if item.field_id not in definitions or item.field_id not in fields:
            failure(422, '様式に登録されていない項目です。')
        mapping = definitions[item.field_id]
        # A printed absence is distinct from a confirmed blank; don't allow a
        # source-not-printed field to become a made-up observation.
        if mapping.extraction == 'not_printed' and item.state != 'not_printed':
            failure(422, '印刷されない項目は原本から確認済みにできません。')
        try:
            value = confirm_value(mapping, item.value) if item.state == 'confirmed' else None
        except (ValueError, TypeError):
            failure(422, '値の種類・日付・単位を確認してください。')
        fields[item.field_id].update(state=item.state, value=value, confirmed_by=user.user_id,
            confirmed_employee_id=user.employee_id, confirmed_at=now_utc().isoformat())
    claim_report(db, parent, payload.expected_version)
    row.version += 1; row.fields_cipher = vault.seal_json('fields', row.revision_id, fields)
    row.ai_cipher = None
    audit(db, user, 'fields_confirm', parent.report_id, version=parent.version, count=len(payload.fields))
    db.commit(); return parent


def retry(db, user, identity, payload, kind='read'):
    parent, row = revision(db, user, identity, current=True)
    if kind == 'read' and row.processing_status not in {'failed', 'partial'}:
        failure(409, '失敗・一部未読の読取処理だけ再実行できます。')
    if kind == 'ai' and not row.reading_cipher:
        failure(409, '読取結果がまだありません。')
    if kind == 'vision' and (payload.page > row.page_count or row.processing_status == 'processing'):
        failure(409, '読取処理が終わってから対象ページを指定してください。')
    if db.scalar(select(AuditJob).where(AuditJob.revision_id == row.revision_id,
        AuditJob.kind == kind, AuditJob.status.in_(['queued', 'processing']))):
        failure(409, '処理中です。完了を待ってください。')
    claim_report(db, parent, payload.expected_version)
    # A reading retry invalidates old confirmations/results before publication.
    if kind == 'read':
        row.version += 1
        row.fields_cipher = None; row.ai_cipher = None
    queue(db, row, user, kind, getattr(payload, 'page', None))
    audit(db, user, 'retry' if kind == 'read' else 'ai_queue', parent.report_id, version=parent.version)
    db.commit(); return parent


def assign_reviewer(db, user, identity, payload):
    parent = report(db, user, identity)
    if parent.owner_id != user.user_id and 'emergency.audit.read_all' not in permission_codes(db, user.user_id):
        failure(403)
    person = db.get(User, str(payload.reviewer_id))
    if not person or not person.active or not person.employee_id or not employee_available(db, person):
        failure(422, '確認担当者を指定できません。')
    if person.employee_id == parent.owner_employee_id or person.user_id == parent.owner_id:
        failure(422, '作成者とは別の職員を指定してください。')
    if not DETAIL_RIGHTS | {'emergency.report.review'} <= permission_codes(db, person.user_id):
        failure(422, '確認担当者に必要な閲覧・確認権限がありません。')
    claim_report(db, parent, payload.expected_version)
    parent.reviewer_id = person.user_id; parent.reviewer_employee_id = person.employee_id
    audit(db, user, 'reviewer_assign', parent.report_id, version=parent.version)
    db.commit(); return parent


def events(db, row):
    return list(db.scalars(select(AuditEvent).where(AuditEvent.report_id == row.report_id)
                          .order_by(AuditEvent.created_at, AuditEvent.event_id)))


def summary(db, row, user):
    current = db.get(AuditRevision, row.current_revision_id)
    active = db.scalar(select(AuditJob).where(AuditJob.revision_id == row.current_revision_id)
                       .order_by(AuditJob.created_at.desc(), AuditJob.job_id).limit(1))
    submitted = next((event.payload['occurred_at'] for event in reversed(events(db, row)) if event.kind == 'submitted'), None)
    return {'report_id': row.report_id, 'version': row.version, 'current_revision_id': row.current_revision_id,
        'revision_number': row.revision_number, 'dataset_kind': row.dataset_kind, 'created_at': row.created_at,
        'status': current.processing_status if current else 'queued', 'job_status': active.status if active else None,
        'owner': row.owner_id == user.user_id, 'reviewer_id': row.reviewer_id, 'submitted_at': submitted}


def revision_output(db, row):
    return {'revision_id': row.revision_id, 'number': row.number, 'media_type': row.media_type,
        'page_count': row.page_count, 'profile_id': row.profile_id, 'processing_status': row.processing_status,
        'error_code': row.error_code, 'reading': vault.open_json('reading', row.revision_id, row.reading_cipher),
        'fields': read_fields(row), 'ai_result': vault.open_json('ai', row.revision_id, row.ai_cipher)}


def latest_run(db, report_id, revision_id=None):
    query = select(AuditRun).where(AuditRun.report_id == report_id)
    if revision_id:
        query = query.where(AuditRun.revision_id == revision_id)
    return db.scalar(query.order_by(AuditRun.created_at.desc(), AuditRun.run_id.desc()).limit(1))


def run_output(db, row, parent, revision_row):
    if row is None:
        return None
    result = vault.open_json('run', row.run_id, row.payload_cipher)
    result.pop('input_fields', None)
    result.pop('source_sha256', None)
    dispositions = {}
    decision_reasons = {}
    for event in events(db, parent):
        if event.kind == 'dispositions' and event.payload['run_id'] == row.run_id:
            dispositions.update({item['rule_id']: item['decision'] for item in event.payload['decisions']})
            decision_reasons.update({item['rule_id']: item.get('reason_code', 'unknown') for item in event.payload['decisions']})
    config = db.get(AuditConfiguration, row.rule_set_id) if row.rule_set_id else None
    stale = row.revision_id != parent.current_revision_id or row.revision_version != revision_row.version
    if row.mode == 'approved' and (not config or config.status != 'approved'):
        stale = True
    if row.mode == 'approved':
        mapping_id = result.get('profile_id') or revision_row.profile_id
        mapping = db.get(AuditConfiguration, mapping_id) if mapping_id else None
        if not mapping or mapping.status != 'approved':
            stale = True
    return {**result, 'run_id': row.run_id, 'revision_id': row.revision_id,
        'report_version': row.report_version, 'created_at': row.created_at,
        'mode': row.mode, 'rule_set_id': row.rule_set_id, 'stale': stale, 'decisions': dispositions,
        'decision_reasons': decision_reasons}


def output(db, row, user, selected_revision=None):
    from .emergency_audit_workflow import all_runs, initial_run, measurement, metric_scope
    current = db.get(AuditRevision, selected_revision or row.current_revision_id)
    result = summary(db, row, user)
    result['revisions'] = [{'revision_id': item.revision_id, 'number': item.number, 'created_at': item.created_at,
        'processing_status': item.processing_status} for item in db.scalars(select(AuditRevision)
        .where(AuditRevision.report_id == row.report_id).order_by(AuditRevision.number.desc()))]
    result['revision'] = revision_output(db, current)
    result['last_run'] = run_output(db, latest_run(db, row.report_id, current.revision_id), row, current)
    first = initial_run(db, row)
    result['initial_run'] = run_output(db, first, row, db.get(AuditRevision, first.revision_id)) if first else None
    result['runs'] = [{'run_id': item.run_id, 'revision_id': item.revision_id,
                      'created_at': item.created_at, 'mode': item.mode} for item in all_runs(db, row)]
    recorded = events(db, row)
    replaced = {item.supersedes_id for item in recorded if item.supersedes_id}
    rights = permission_codes(db, user.user_id)
    result['events'] = [{'event_id': item.event_id, 'kind': item.kind, 'payload': item.payload,
                         'supersedes_event_id': item.supersedes_id,
                         'can_correct': bool(user.employee_id and user.employee_id == item.actor_employee_id and
                             item.event_id not in replaced and item.kind in {'work_interval', 'submitted'} and
                             ('emergency.report.create' in rights or
                              (item.kind == 'work_interval' and 'emergency.report.review' in rights))),
                         'created_at': item.created_at} for item in recorded]
    result['measurement'] = measurement(db, row)
    result['measurement_scope'] = metric_scope(db, row)[1]
    result['measurement_pending'] = (['SUBMISSION_NOT_RECORDED'] if not result['submitted_at'] else
                                     ['MEASUREMENT_LIMIT_EXCEEDED']) if result['measurement'] is None else []
    return result
