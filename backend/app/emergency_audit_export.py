"""Authorize and freeze one current inspection for a private review-copy export."""
from dataclasses import dataclass
from hashlib import sha256

from sqlalchemy import select

from . import emergency_audit_service as svc, emergency_vault as vault
from .authz import require_mutation_permission
from .emergency_audit_models import AuditConfiguration, AuditEvent, AuditRevision, AuditRun
from .emergency_audit_pdf import PDFExportError, validate_plan
from .models import User


@dataclass(frozen=True)
class ExportSnapshot:
    user_id: str
    employee_id: str
    guard: str
    plan: dict


def _configuration_guard(db, identity, kind, mode):
    if not identity:
        if mode == 'approved':
            svc.failure(409)
        return None
    config = db.get(AuditConfiguration, identity, populate_existing=True)
    if (config is None or config.kind != kind or config.status == 'retired'
            or (mode == 'approved' and config.status != 'approved')):
        svc.failure(409, '様式・チェック条件の状態が変わっています。最新の条件で再検査してください。')
    return [config.config_id, config.version, config.status, sha256(config.definition_cipher).hexdigest()]


def _active_dispositions(db, report_id, run_id):
    replaced = select(AuditEvent.supersedes_id).where(AuditEvent.report_id == report_id,
                                                     AuditEvent.supersedes_id.is_not(None))
    events = db.scalars(select(AuditEvent).where(AuditEvent.report_id == report_id,
        AuditEvent.kind == 'dispositions', AuditEvent.payload['run_id'].as_string() == run_id,
        AuditEvent.event_id.not_in(replaced)).order_by(AuditEvent.created_at, AuditEvent.event_id))
    result = {}
    for event in events:
        for item in event.payload['decisions']:
            result[item['rule_id']] = {'decision': item['decision'], 'reason_code': item.get('reason_code', 'unknown')}
    return result


def _plan(parent, revision, run, body, decisions):
    """Explicit projection only: raw input values and suggested_text are excluded."""
    fields = body['input_fields']; findings = []
    used = {key for item in body['findings'] for key in item['fields']}
    for item in body['findings']:
        is_ai = run.mode in {'ai', 'vision'} or item.get('origin') == 'ai'
        evidence = item.get('evidence', {}) if is_ai else {}
        locations = []
        if is_ai:
            # Text quotes do not provide coordinates. Never search a newer
            # reading or a current profile to invent a box for this old quote.
            if evidence.get('bbox') is not None:
                locations.append({'page': evidence['page'], 'bbox': evidence['bbox']})
        else:
            for key in item['fields']:
                for word in fields.get(key, {}).get('evidence', []):
                    location = {'page': word['page'], 'bbox': word['bbox']}
                    if location not in locations:
                        locations.append(location)
        decision = decisions.get(item['rule_id'], {})
        findings.append({'rule_id': item['rule_id'], 'status': item['status'], 'message': item['message'],
            'source_reference': item.get('source_reference', ''), 'fields': list(item['fields']), 'is_ai': is_ai,
            'decision': decision.get('decision'), 'decision_reason': decision.get('reason_code'),
            'quote': evidence.get('quote', evidence.get('text')) if is_ai else None, 'locations': locations})
    return validate_plan({'schema_version': 1, 'run_id': run.run_id, 'report_version': parent.version,
        'revision_number': revision.number, 'page_count': revision.page_count, 'mode': run.mode,
        'reading_complete': body.get('reading_complete', False), 'as_of': body.get('as_of'),
        'fields': [{'field_id': key, 'label': fields.get(key, {}).get('label', key),
                    'state': fields.get(key, {}).get('state', 'unmapped'), 'used': key in used}
                   for key in sorted(set(fields) | used)], 'findings': findings}).model_dump(mode='json')


def capture_export(db, user_id, report_id, payload, *, expected_employee_id=None):
    """Short serialized authorization transaction, used before and after rendering."""
    user = db.get(User, user_id, populate_existing=True)
    if user is None:
        svc.failure(403)
    user = require_mutation_permission('emergency.report.export')(user=user, db=db)
    if not user.employee_id or (expected_employee_id is not None and user.employee_id != expected_employee_id):
        svc.failure(403)
    parent = svc.report(db, user, report_id)
    if parent.version != payload.expected_version:
        svc.failure(409, '別の操作で更新されています。再読込して確認してください。')
    revision = db.get(AuditRevision, parent.current_revision_id, populate_existing=True)
    run = db.get(AuditRun, str(payload.run_id), populate_existing=True)
    latest = svc.latest_run(db, parent.report_id, parent.current_revision_id)
    if (revision is None or run is None or run.report_id != parent.report_id
            or run.revision_id != parent.current_revision_id or run.revision_version != revision.version
            or latest is None or latest.run_id != run.run_id):
        svc.failure(409, '最新の原本と検査結果を開いてください。')
    body = vault.open_json('run', run.run_id, run.payload_cipher)
    if body.get('source_sha256') != revision.source_sha256:
        svc.failure(409, '検査時点の原本を確認できません。最新の原本で再検査してください。')
    profile_id = body.get('profile_id', revision.profile_id)
    if profile_id != revision.profile_id:
        svc.failure(409)
    configs = [_configuration_guard(db, profile_id, 'profile', run.mode),
               _configuration_guard(db, run.rule_set_id, 'rules', run.mode)]
    try:
        plan = _plan(parent, revision, run, body, _active_dispositions(db, parent.report_id, run.run_id))
    except (PDFExportError, ValueError, TypeError, KeyError, AttributeError):
        svc.failure(409, 'この検査の記録を安全に出力できません。最新の原本で再検査してください。')
    guard = svc.digest({'plan': plan, 'configurations': configs, 'revision_id': revision.revision_id,
        'revision_version': revision.version, 'source_sha256': revision.source_sha256, 'source_size': revision.size_bytes,
        'mode': run.mode, 'run_payload': sha256(run.payload_cipher).hexdigest()})
    return ExportSnapshot(user.user_id, user.employee_id, guard, plan), parent, revision, user
