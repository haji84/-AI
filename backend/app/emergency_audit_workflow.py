"""Reproducible check snapshots and original-free acceptance observations."""
from collections import Counter
from dataclasses import asdict
from datetime import datetime, timezone
from uuid import UUID, uuid4, uuid5

from pydantic import ValidationError
from sqlalchemy import select

from .authz import permission_codes
from .emergency_acceptance_schemas import ReportMeasurement
from .emergency_audit_models import AuditConfiguration, AuditEvent, AuditJob, AuditReport, AuditRevision, AuditRun
from .emergency_audit_schemas import FollowupEvent, StudyEvent, SubmittedEvent, TruthEvent, WorkEvent
from . import emergency_audit_service as svc
from . import emergency_vault as vault
from .emergency_review_core import Observation, evaluate_confirmed_fields
from .emergency_rule_engine import evaluate_rules
from .emergency_rule_schemas import RuleSetDefinition
from .models import now_utc


def aware(value):
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


def active_events(db, row):
    recorded = svc.events(db, row)
    replaced = {item.supersedes_id for item in recorded if item.supersedes_id}
    return [item for item in recorded if item.event_id not in replaced]


def state(db, row):
    result = {'study': {'cohort': 'assisted', 'activity_kind': 'unknown'}, 'submitted': None,
              'followup': None, 'truth_review': None}
    followup_at = None
    for event in active_events(db, row):
        if event.kind in result:
            result[event.kind] = event.payload
        if event.kind == 'submitted':
            result['followup'] = None; followup_at = None
        elif event.kind == 'followup':
            followup_at = aware(event.created_at)
        elif event.kind == 'work_interval' and result['followup']:
            result['followup'] = {**result['followup'], 'work_complete': False}
    latest = db.get(AuditRevision, row.current_revision_id)
    if result['followup'] and latest and followup_at and aware(latest.created_at) > followup_at:
        result['followup'] = {'complete': False, 'corrected_after_submission': None, 'work_complete': False}
    return result


def permit_assistance(db, parent):
    if state(db, parent)['study']['cohort'] == 'baseline':
        svc.failure(409, '導入前の比較対象には自動チェックを実行できません。')


def rule_observations(fields):
    result = {}
    for key, item in fields.items():
        value = item.get('value') if item.get('state') == 'confirmed' else None
        if value is not None and item.get('value_type') in {'date', 'datetime', 'time'}:
            value = {'type': item['value_type'], 'value': value}
        result[key] = {'state': item['state'], 'value': value, 'unit': item.get('unit')}
    return result


def read_state_for_rule(item, fields):
    values = [fields.get(key, {}).get('state', 'unmapped') for key in item['fields']]
    for possible in ('unreadable', 'unmapped', 'not_printed', 'unconfirmed'):
        if possible in values:
            return possible
    return 'confirmed' if values else 'unmapped'


def differences(previous, current):
    old = {item['rule_id'] for item in previous if item['status'] == 'REVIEW_REQUIRED'}
    now = {item['rule_id'] for item in current if item['status'] == 'REVIEW_REQUIRED'}
    tested = {item['rule_id'] for item in current if item['status'] in {'NO_ISSUE_DETECTED', 'NOT_APPLICABLE'}}
    unknown = {item['rule_id'] for item in current if item['status'] == 'NOT_TESTED'}
    return {'resolved': sorted((old - now) & tested), 'persistent': sorted(old & now),
            'new': sorted(now - old), 'untested': sorted(unknown | (old - now - tested))}


def check(db, user, identity, payload):
    parent, revision = svc.revision(db, user, identity, current=True)
    permit_assistance(db, parent)
    if revision.processing_status not in {'ready', 'partial'}:
        svc.failure(409, '読取処理が終わってからチェックしてください。')
    fields = svc.read_fields(revision)
    selected = None
    approval = 'PROVISIONAL_NOT_APPROVED'
    if payload.rule_set_id:
        selected = svc.configuration(db, payload.rule_set_id, 'rules')
        if selected.status == 'retired':
            svc.failure(409, '使用を終了した条件では新しいチェックを作成できません。')
        definition = RuleSetDefinition.model_validate(vault.open_json('config', selected.config_id, selected.definition_cipher))
        mapping_row, mapping = svc.profile(db, revision.profile_id)
        if payload.mode == 'approved':
            if selected.status != 'approved' or mapping_row.status != 'approved':
                svc.failure(409, '承認済みの様式とチェック条件を選んでください。')
            if (mapping.form_key != definition.form_key or payload.as_of < mapping.valid_from or
                (mapping.valid_to is not None and payload.as_of > mapping.valid_to) or
                payload.as_of < definition.valid_from or
                (definition.valid_to is not None and payload.as_of > definition.valid_to)):
                svc.failure(409, '適用日と様式の版に対応する承認済み条件がありません。')
            approval = 'APPROVED_RULE'
        findings = evaluate_rules(definition, rule_observations(fields),
            approval='approved' if approval == 'APPROVED_RULE' else 'draft', as_of=payload.as_of, form_key=mapping.form_key)
    else:
        if payload.mode != 'candidate':
            svc.failure(409, '正式なチェック条件を選択してください。')
        observations = {key: Observation(item['state'], item.get('value') if item['state'] == 'confirmed' else None)
                        for key, item in fields.items()}
        findings = [asdict(item) for item in evaluate_confirmed_fields(observations)]
    previous = svc.latest_run(db, parent.report_id)
    previous_findings = vault.open_json('run', previous.run_id, previous.payload_cipher)['findings'] if previous else []
    svc.claim_report(db, parent, payload.expected_version)
    run_id = str(uuid4())
    counts = {status: 0 for status in ('REVIEW_REQUIRED', 'NO_ISSUE_DETECTED', 'NOT_TESTED', 'NOT_APPLICABLE')}
    counts.update(Counter(item['status'] for item in findings))
    reading = vault.open_json('reading', revision.revision_id, revision.reading_cipher, {})
    body = {'approval': approval, 'as_of': payload.as_of.isoformat(), 'findings': findings,
        'counts': counts, 'changes': differences(previous_findings, findings),
        'submission_decision': 'NOT_PROVIDED', 'reading_complete': reading.get('complete', False),
        'checked_scope_only': True, 'field_states': {key: item['state'] for key, item in fields.items()},
        'rule_read_states': {item['rule_id']: read_state_for_rule(item, fields) for item in findings},
        'input_fields': fields, 'source_sha256': revision.source_sha256, 'profile_id': revision.profile_id}
    run = AuditRun(run_id=run_id, report_id=parent.report_id, revision_id=revision.revision_id,
        revision_version=revision.version, report_version=parent.version,
        rule_set_id=selected.config_id if selected else None, mode=payload.mode,
        payload_cipher=vault.seal_json('run', run_id, body), created_by=user.user_id)
    db.add(run); svc.audit(db, user, 'check', parent.report_id, version=parent.version, count=len(findings))
    db.commit(); return parent


def save_dispositions(db, user, identity, payload):
    run = db.get(AuditRun, str(identity))
    if not run:
        svc.failure(404)
    parent, revision = svc.revision(db, user, run.revision_id, current=True)
    if run.revision_version != revision.version or svc.latest_run(db, parent.report_id, revision.revision_id).run_id != run.run_id:
        svc.failure(409, '最新のチェック結果を開いてください。')
    findings = vault.open_json('run', run.run_id, run.payload_cipher)['findings']
    known = {item['rule_id'] for item in findings}
    if len({item.rule_id for item in payload.decisions}) != len(payload.decisions) or any(item.rule_id not in known for item in payload.decisions):
        svc.failure(422)
    svc.claim_report(db, parent, payload.expected_version)
    body = {'run_id': run.run_id, 'decisions': [item.model_dump() for item in payload.decisions]}
    db.add(AuditEvent(event_id=str(uuid4()), report_id=parent.report_id, kind='dispositions',
        request_sha256=svc.digest(body), payload=body, actor_id=user.user_id, actor_employee_id=user.employee_id))
    svc.audit(db, user, 'dispositions', parent.report_id, version=parent.version, count=len(payload.decisions))
    db.commit(); return parent


EVENT_SCHEMAS = {'study': StudyEvent, 'submitted': SubmittedEvent, 'followup': FollowupEvent,
                 'work_interval': WorkEvent, 'truth_review': TruthEvent}


def initial_run(db, parent):
    return db.scalar(select(AuditRun).where(AuditRun.report_id == parent.report_id)
                     .order_by(AuditRun.created_at, AuditRun.run_id).limit(1))


def all_runs(db, parent):
    return list(db.scalars(select(AuditRun).where(AuditRun.report_id == parent.report_id)
                           .order_by(AuditRun.created_at, AuditRun.run_id)))


def metric_scope(db, parent, runs=None, current=None):
    runs = all_runs(db, parent) if runs is None else runs
    current = state(db, parent) if current is None else current
    submitted = datetime.fromisoformat(current['submitted']['occurred_at']) if current['submitted'] else None
    if submitted is None:
        return runs, {'status': 'SUBMISSION_NOT_RECORDED', 'eligible_run_count': None,
                      'post_submission_revision_runs': None, 'all_run_count': len(runs)}
    eligible = [run for run in runs if aware(db.get(AuditRevision, run.revision_id).created_at) <= aware(submitted)]
    return eligible, {'status': 'PRE_SUBMISSION_SOURCE_REVISIONS', 'eligible_run_count': len(eligible),
                     'post_submission_revision_runs': len(runs) - len(eligible), 'all_run_count': len(runs)}


def _checked_instant(value):
    if value.utcoffset() is None or aware(value) > now_utc():
        svc.failure(422, '日時には時差を含め、実際に作業した過去の日時を指定してください。')
    return aware(value)


def save_event(db, user, identity, payload):
    parent = svc.report(db, user, identity)
    try:
        typed = EVENT_SCHEMAS[payload.kind].model_validate(payload.payload)
    except (ValueError, TypeError, ValidationError):
        svc.failure(422, '測定記録の形式を確認してください。')
    body = typed.model_dump(mode='json')
    fingerprint = svc.digest({'kind': payload.kind, 'payload': body, 'report_id': parent.report_id,
                              'supersedes_event_id': str(payload.supersedes_event_id) if payload.supersedes_event_id else None})
    prior = db.get(AuditEvent, str(payload.event_id))
    if prior:
        if prior.report_id != parent.report_id or prior.actor_id != user.user_id or prior.request_sha256 != fingerprint:
            svc.failure(409, '同じ記録番号で別の内容は保存できません。')
        return parent
    current = state(db, parent)
    first = initial_run(db, parent)
    replaced = None
    if payload.supersedes_event_id:
        replaced = db.get(AuditEvent, str(payload.supersedes_event_id))
        if not replaced or replaced.report_id != parent.report_id or replaced.kind != payload.kind:
            svc.failure(422, '訂正元の測定記録を確認してください。')
        if not user.employee_id or replaced.actor_employee_id != user.employee_id:
            svc.failure(403, '記録した本人が測定内容を訂正してください。')
        if db.scalar(select(AuditEvent.event_id).where(AuditEvent.supersedes_id == replaced.event_id)):
            svc.failure(409, 'この記録には既に訂正版があります。')
    if payload.kind == 'study':
        ai_used = db.scalar(select(AuditJob.job_id).join(AuditRevision,
            AuditRevision.revision_id == AuditJob.revision_id).where(AuditRevision.report_id == parent.report_id,
            AuditJob.kind.in_(['ai', 'vision'])).limit(1))
        if (first or current['submitted'] or ai_used) and typed.cohort != current['study']['cohort']:
            svc.failure(409, 'チェック・提出後には比較対象の区分を変更できません。')
    elif payload.kind == 'submitted':
        instant = _checked_instant(typed.occurred_at)
        if current['submitted'] and replaced is None:
            svc.failure(409, '提出日時は既に記録されています。')
        if instant < aware(parent.created_at):
            # Historical baseline imports may be explicitly measured, but a
            # submission predating import cannot establish before/after timing.
            svc.failure(422, 'この取込より前の提出は、この評価の提出前検査として記録できません。')
    elif payload.kind == 'followup':
        if not current['submitted']:
            svc.failure(409, '実際の提出を確認してから追跡結果を記録してください。')
        if typed.complete and typed.corrected_after_submission is None:
            svc.failure(422, '追跡完了には訂正の有無を確認してください。')
        if typed.work_complete and not any(event.kind == 'work_interval' for event in active_events(db, parent)):
            svc.failure(422, '作業時間が未記録です。未記録をゼロ分として確定できません。')
    elif payload.kind == 'work_interval':
        start, end = _checked_instant(typed.started_at), _checked_instant(typed.ended_at)
        if end < start or (end - start).total_seconds() > 31 * 86400 or not user.employee_id:
            svc.failure(422, '作業区間を確認してください。')
        intervals = list(db.scalars(select(AuditEvent).where(AuditEvent.kind == 'work_interval',
            AuditEvent.actor_employee_id == user.employee_id,
            AuditEvent.event_id.not_in(select(AuditEvent.supersedes_id).where(AuditEvent.supersedes_id.is_not(None))))))
        if replaced:
            intervals = [event for event in intervals if event.event_id != replaced.event_id]
        if sum(event.report_id == parent.report_id for event in intervals) >= 1000:
            svc.failure(422, '作業記録の上限に達しています。')
        for event in intervals:
            if event.actor_employee_id == user.employee_id:
                a = datetime.fromisoformat(event.payload['started_at']); b = datetime.fromisoformat(event.payload['ended_at'])
                if start < aware(b) and end > aware(a):
                    svc.failure(409, '同じ担当者の作業時間が重なっています。')
    elif payload.kind == 'truth_review':
        if 'emergency.report.review' not in permission_codes(db, user.user_id):
            svc.failure(403)
        if not user.employee_id or user.user_id == parent.owner_id or user.employee_id == parent.owner_employee_id:
            svc.failure(403, '作成者とは別の職員が原本全体を確認してください。')
        reviewed_run = db.get(AuditRun, str(typed.run_id))
        if not reviewed_run or reviewed_run.report_id != parent.report_id:
            svc.failure(422, '対象の検査履歴と、その時点の原本を確認してください。')
        reference = vault.open_json('run', reviewed_run.run_id, reviewed_run.payload_cipher)
        known = {item['rule_id'] for item in reference['findings']}
        keys = {item.rule_id for item in typed.items}
        if len(keys) != len(typed.items) or not keys <= known:
            svc.failure(422)
        if typed.complete and (not typed.whole_report_checked or keys != known or
                              any(item.truth == 'unknown' or item.verified_read_state is None for item in typed.items)):
            svc.failure(422, '全項目・原本全体の独立確認が終わるまで完了にできません。')
        if len({item.opportunity_id for item in typed.missed_errors}) != len(typed.missed_errors):
            svc.failure(422)
        known_opps = {str(uuid5(UUID(run.run_id), item['rule_id'])) for run in all_runs(db, parent)
                      for item in vault.open_json('run', run.run_id, run.payload_cipher)['findings']}
        if any(str(item.opportunity_id) in known_opps for item in typed.missed_errors):
            svc.failure(422)
        other_truths = {event.payload['run_id']: event.payload for event in active_events(db, parent)
                       if event.kind == 'truth_review' and event.payload['run_id'] != reviewed_run.run_id}
        other_opps = {item['opportunity_id'] for record in other_truths.values() for item in record.get('missed_errors', [])}
        if any(str(item.opportunity_id) in other_opps for item in typed.missed_errors):
            svc.failure(422, '別の検査と同じ評価項目番号は使用できません。')
        # Linking a later warning to the SAME actual error requires explicit
        # independent attestation; a disposition never silently does this.
        for item in typed.items:
            if item.detected_in_run_ids and item.truth != 'error':
                svc.failure(422)
            for detected in item.detected_in_run_ids:
                linked = db.get(AuditRun, str(detected))
                if not linked or linked.report_id != parent.report_id:
                    svc.failure(422)
                linked_body = vault.open_json('run', linked.run_id, linked.payload_cipher)
                if not any(f['rule_id'] == item.rule_id and f['status'] == 'REVIEW_REQUIRED' for f in linked_body['findings']):
                    svc.failure(422)
    svc.claim_report(db, parent, payload.expected_version)
    event = AuditEvent(event_id=str(payload.event_id), report_id=parent.report_id, kind=payload.kind,
        supersedes_id=replaced.event_id if replaced else None, request_sha256=fingerprint,
        payload=body, actor_id=user.user_id, actor_employee_id=user.employee_id)
    db.add(event); svc.audit(db, user, 'event', parent.report_id, version=parent.version, kind=payload.kind)
    db.commit(); return parent


def measurement(db, parent):
    current = state(db, parent)
    runs, _ = metric_scope(db, parent, current=current)
    first = runs[0] if runs else None
    opportunities = []
    truths = {event.payload['run_id']: event.payload for event in active_events(db, parent) if event.kind == 'truth_review'}
    submitted = datetime.fromisoformat(current['submitted']['occurred_at']) if current['submitted'] else None
    revision = db.get(AuditRevision, first.revision_id if first else parent.current_revision_id)
    for run in runs:
        snapshot = vault.open_json('run', run.run_id, run.payload_cipher)
        truth = truths.get(run.run_id, {})
        adjudicated = {item['rule_id']: item for item in truth.get('items', [])}
        if submitted is None and any(item['status'] == 'REVIEW_REQUIRED' for item in snapshot['findings']):
            # The existing evaluator deliberately requires known timing. Do not
            # encode unknown timing as either timely or late to satisfy a schema.
            return None
        for item in snapshot['findings']:
            known = adjudicated.get(item['rule_id'], {})
            # An independently linked later warning labels that later actual
            # opportunity; it never manufactures an earlier warning event.
            if not known:
                linked_labels = [label for record in truths.values() for label in record.get('items', [])
                    if label['rule_id'] == item['rule_id'] and run.run_id in label.get('detected_in_run_ids', [])]
                if len({label.get('error_id') for label in linked_labels}) == 1 and linked_labels:
                    known = linked_labels[-1]
            status = item['status']
            decision = ('warning' if status == 'REVIEW_REQUIRED' else 'clear' if status == 'NO_ISSUE_DETECTED'
                        else 'not_applicable' if status == 'NOT_APPLICABLE' else 'unchecked')
            timing = aware(run.created_at) < aware(submitted) if submitted else False
            opportunities.append({'opportunity_id': str(uuid5(UUID(run.run_id), item['rule_id'])),
                'truth': known.get('truth', 'unknown'), 'error_id': known.get('error_id'), 'decision': decision,
                'before_submission': timing if decision == 'warning' else None,
                'read_state': snapshot['rule_read_states'][item['rule_id']],
                'verified_read_state': known.get('verified_read_state')})
        for missed in truth.get('missed_errors', []):
            opportunities.append({**missed, 'truth': 'error', 'decision': 'unchecked', 'before_submission': None})
    work = []
    for event in active_events(db, parent):
        if event.kind == 'work_interval':
            work.append({'worker_id': event.actor_employee_id, 'stage': event.payload['stage'],
                'start_seconds': int(datetime.fromisoformat(event.payload['started_at']).timestamp()),
                'end_seconds': int(datetime.fromisoformat(event.payload['ended_at']).timestamp())})
    followup = current['followup'] or {}
    reading = vault.open_json('reading', revision.revision_id, revision.reading_cipher, {}) if revision else {}
    statuses = {page['status'] for page in reading.get('pages', [])}
    document_kind = ('photo' if revision and revision.media_type != 'application/pdf' else
        'text_pdf' if statuses == {'TEXT_EXTRACTED'} else 'mixed' if 'TEXT_EXTRACTED' in statuses else
        'image_pdf' if statuses else 'unknown')
    result = {'report_id': parent.report_id, 'report_version': revision.number if revision else 1,
        **current['study'], 'document_kind': document_kind,
        'followup_complete': followup.get('complete', False),
        'corrected_after_submission': followup.get('corrected_after_submission'),
        'independent_review_complete': bool(runs) and all(truths.get(run.run_id, {}).get('complete') and
            truths.get(run.run_id, {}).get('whole_report_checked') for run in runs),
        'work_complete': followup.get('work_complete', False), 'opportunities': opportunities, 'work': work}
    if len(opportunities) > 1000:
        # Full immutable history remains available. No truncation to improve
        # measured performance when the bounded measurement API cannot fit it.
        return None
    return ReportMeasurement.model_validate(result).model_dump(mode='json')


def record_ai_run(db, report, revision, job, ai_result):
    """Called in the fenced worker publication transaction; never commits."""
    if ai_result.get('status') not in {'REVIEW_REQUIRED', 'NO_CANDIDATE'}:
        return
    run_id = str(uuid4())
    findings = []
    fields = svc.read_fields(revision)
    seen = set()
    for index, candidate in enumerate(ai_result.get('candidates', []), 1):
        page = candidate['page']
        evidence_key = svc.digest(candidate)[:16]
        if evidence_key in seen:
            continue
        seen.add(evidence_key)
        findings.append({'rule_id': f'AI-{job.kind.upper()}-{evidence_key}', 'status': 'REVIEW_REQUIRED',
            'message': candidate.get('reason') or '画像の読取候補です。手書き・訂正線・本文を原本と照合してください。',
            'fields': [], 'source_reference': f'原本 {page} ページ／AIによる未確認候補',
            'rule_approval': 'AI_CANDIDATE_NOT_APPROVED', 'reason_code': 'HUMAN_CONFIRMATION_REQUIRED',
            'origin': 'ai', 'evidence': candidate})
    # Absence of a model candidate is not a demonstrated inspection pass.
    if not findings:
        findings.append({'rule_id': f'AI-{job.kind.upper()}-SCOPE', 'status': 'NOT_TESTED',
            'message': 'AIの候補はありません。記載の正しさは確定していません。', 'fields': [],
            'source_reference': '原本／AIによる補助確認', 'rule_approval': 'AI_CANDIDATE_NOT_APPROVED',
            'reason_code': 'NO_CANDIDATE_NOT_A_CLEAR', 'origin': 'ai'})
    counts = {key: 0 for key in ('REVIEW_REQUIRED', 'NO_ISSUE_DETECTED', 'NOT_TESTED', 'NOT_APPLICABLE')}
    counts.update(Counter(item['status'] for item in findings))
    previous = svc.latest_run(db, report.report_id)
    old = vault.open_json('run', previous.run_id, previous.payload_cipher)['findings'] if previous else []
    body = {'approval': 'AI_CANDIDATE_NOT_APPROVED', 'findings': findings, 'counts': counts,
        'changes': differences(old, findings), 'submission_decision': 'NOT_PROVIDED',
        'checked_scope_only': True, 'reading_complete': False,
        'field_states': {key: value['state'] for key, value in fields.items()},
        'rule_read_states': {item['rule_id']: 'unconfirmed' for item in findings},
        'input_fields': fields, 'source_sha256': revision.source_sha256}
    db.add(AuditRun(run_id=run_id, report_id=report.report_id, revision_id=revision.revision_id,
        revision_version=revision.version, report_version=report.version, rule_set_id=None, mode=job.kind,
        payload_cipher=vault.seal_json('run', run_id, body), created_by=job.requested_by))


def export_measurement(db, user, payload):
    if len(set(payload.report_ids)) != len(payload.report_ids):
        svc.failure(422)
    rows = [svc.report(db, user, identity) for identity in payload.report_ids]
    kinds = {row.dataset_kind for row in rows}
    if len(kinds) != 1:
        svc.failure(422, '合成データと本部内実測は別に評価してください。')
    values = [measurement(db, row) for row in rows]
    if any(value is None for value in values):
        svc.failure(409, '測定に未確定の日時、または項目数の上限超過があります。対象の報告書を確認してください。')
    if sum(len(item['opportunities']) for item in values) > 20_000:
        svc.failure(422, '一度に評価する項目数を減らしてください。')
    return {'dataset_kind': kinds.pop(), 'comparison_confirmed': False, 'held_out_confirmed': False,
            'followup_days': None, 'targets': {}, 'reports': values}
