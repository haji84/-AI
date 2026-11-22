"""Private, immutable audit definitions with bounded impact and human approval.

Impact is a reproducible configuration test, not proof of clinical correctness
or an operational improvement measurement. No configuration becomes approved
through extraction, a rule result, or an AI response.
"""
from __future__ import annotations

from collections import Counter
from datetime import date
from hashlib import sha256
from uuid import UUID, uuid4

from pydantic import ValidationError
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError

from . import emergency_audit_service as core
from . import emergency_vault as vault
from .authz import permission_codes
from .emergency_audit_models import AuditConfiguration, AuditReport, AuditRevision, AuditSource
from .emergency_mapping import ProfileDefinition, confirm_value
from .emergency_rule_engine import evaluate_rules
from .emergency_rule_schemas import RuleObservation, RuleSetDefinition, TemporalValue
from .models import User, now_utc
from .personnel import account_change_lock, employee_available


_SOURCE_MEDIA = {'application/pdf', 'image/png', 'image/jpeg'}
_TESTED = {'NO_ISSUE_DETECTED', 'REVIEW_REQUIRED'}
_INVALID_REGION = {'UNKNOWN_CODE', 'VALUE_FORMAT_INVALID', 'REGION_BOUNDARY_AMBIGUOUS',
                   'PAGE_UNAVAILABLE', 'EMPTY_REGION', 'SOURCE_UNREADABLE'}


def _identity(value):
    try:
        return str(UUID(str(value)))
    except (ValueError, TypeError, AttributeError):
        core.failure(422)


def _authorize(db, user, permission):
    identity = user.user_id
    account_change_lock(db)
    fresh = db.get(User, identity, populate_existing=True)
    if not fresh or not fresh.active or not fresh.employee_id or not employee_available(db, fresh):
        core.failure(403, '職員と結び付いた有効なアカウントで操作してください。')
    core.require_details(db, fresh)
    if permission not in permission_codes(db, identity):
        core.failure(403)
    if not vault.ready():
        core.failure(503, '原本を保護する鍵が利用できません。')
    return fresh


def _parse(kind, value):
    try:
        if kind == 'profile':
            return ProfileDefinition.model_validate(value)
        if kind == 'rules':
            return RuleSetDefinition.model_validate(value)
    except (ValidationError, ValueError, TypeError, RecursionError):
        core.failure(422, '様式・チェック条件の定義を確認してください。')
    core.failure(422)


def _fingerprint(kind, definition, source_id, supersedes_id):
    return core.digest({'kind': kind, 'definition': definition.model_dump(mode='json'),
                        'source_id': source_id, 'supersedes_id': supersedes_id})


def _definition(row):
    definition = _parse(row.kind, vault.open_json('config', row.config_id, row.definition_cipher))
    if (definition.label != row.label or definition.form_key != row.form_key or
        _fingerprint(row.kind, definition, row.source_id, row.supersedes_id) != row.request_sha256):
        raise vault.VaultError('PRIVATE_CONTENT_INTEGRITY')
    return definition


def _locked_config(db, identity):
    row = db.scalar(select(AuditConfiguration).where(AuditConfiguration.config_id == _identity(identity))
                    .with_for_update().execution_options(populate_existing=True))
    if row is None:
        core.failure(422, '様式・チェック条件を確認してください。')
    return row


def _claim(db, row, expected_version, expected_status, **changes):
    if row.version != expected_version or row.status != expected_status:
        core.failure(409, '別の操作で更新されています。再読込して確認してください。')
    affected = db.execute(update(AuditConfiguration).where(
        AuditConfiguration.config_id == row.config_id,
        AuditConfiguration.version == expected_version,
        AuditConfiguration.status == expected_status,
    ).values(version=expected_version + 1, **changes).execution_options(synchronize_session=False)).rowcount
    if affected != 1:
        db.rollback()
        core.failure(409, '別の操作で更新されています。再読込して確認してください。')
    db.refresh(row)
    return row


def config_output(db, row):
    definition = _definition(row).model_dump(mode='json')
    impact = row.impact
    return {'config_id': row.config_id, 'kind': row.kind, 'label': row.label,
            'form_key': row.form_key, 'status': row.status, 'version': row.version,
            'definition': definition, 'source_id': row.source_id, 'supersedes_id': row.supersedes_id,
            'created_by': row.created_by, 'created_employee_id': row.created_employee_id,
            'approved_by': row.approved_by, 'approved_employee_id': row.approved_employee_id,
            'approval_version': impact.get('approval_version') if impact else None,
            'created_at': row.created_at, 'approved_at': row.approved_at, 'impact': impact}


def create_source(db, user, data, metadata, request_id):
    """Persist an already reader-validated source; originals never become Documents."""
    user = _authorize(db, user, 'emergency.audit.configure')
    request_id = _identity(request_id)
    if (type(data) is not bytes or not 1 <= len(data) <= 25 * 1024 * 1024 or
        not isinstance(metadata, dict) or metadata.get('media_type') not in _SOURCE_MEDIA or
        type(metadata.get('page_count')) is not int or not 1 <= metadata['page_count'] <= 50):
        core.failure(422)
    checksum = sha256(data).hexdigest()
    existing = db.scalar(select(AuditSource).where(AuditSource.request_id == request_id))
    if existing:
        if (existing.created_by != user.user_id or existing.source_sha256 != checksum or
            existing.size_bytes != len(data) or existing.media_type != metadata['media_type'] or
            existing.page_count != metadata['page_count']):
            core.failure(409, '同じ受付番号で別の内容は登録できません。')
        core.verified_original(existing, 'source')
        return existing, False
    row = AuditSource(source_id=str(uuid4()), request_id=request_id, source_sha256=checksum,
        media_type=metadata['media_type'], size_bytes=len(data), page_count=metadata['page_count'],
        created_by=user.user_id)
    db.add(row)
    stored = False
    try:
        db.flush()
        vault.store_original('source', row.source_id, data); stored = True
        core.audit(db, user, 'source_create', row.source_id, count=row.page_count)
        db.commit()
    except Exception:
        db.rollback()
        if stored:
            vault.discard_uncommitted('source', row.source_id)
        raise
    return row, True


def create_config(db, user, kind, payload):
    user = _authorize(db, user, 'emergency.audit.configure')
    definition = _parse(kind, payload.definition)
    request_id = _identity(payload.request_id)
    source_id = _identity(payload.source_id) if payload.source_id else None
    supersedes_id = _identity(payload.supersedes_id) if payload.supersedes_id else None
    fingerprint = _fingerprint(kind, definition, source_id, supersedes_id)
    existing = db.scalar(select(AuditConfiguration).where(AuditConfiguration.request_id == request_id))
    if existing:
        if (existing.request_sha256 != fingerprint or existing.created_by != user.user_id or
            existing.created_employee_id != user.employee_id):
            core.failure(409, '同じ受付番号で別の内容は登録できません。')
        _definition(existing)
        return existing, False
    if source_id and db.get(AuditSource, source_id) is None:
        core.failure(422, '根拠資料を確認してください。')
    if supersedes_id:
        parent = _locked_config(db, supersedes_id)
        if parent.kind != kind or parent.form_key != definition.form_key:
            core.failure(422, '改訂元と種類・様式が一致していません。')
        if db.scalar(select(AuditConfiguration.config_id).where(AuditConfiguration.supersedes_id == supersedes_id)):
            core.failure(409, 'この設定には既に新しい版があります。')
    identity = str(uuid4())
    row = AuditConfiguration(config_id=identity, request_id=request_id, request_sha256=fingerprint,
        supersedes_id=supersedes_id, kind=kind, label=definition.label, form_key=definition.form_key,
        definition_cipher=vault.seal_json('config', identity, definition.model_dump(mode='json')),
        source_id=source_id, status='draft', version=1, created_by=user.user_id,
        created_employee_id=user.employee_id)
    db.add(row)
    try:
        db.flush()
        core.audit(db, user, 'config_create', row.config_id, kind=kind, version=1)
        db.commit()
    except IntegrityError:
        db.rollback()
        core.failure(409, '同じ受付番号または改訂元の設定が既に登録されています。')
    return row, True


def _cipher_hash(value):
    return sha256(value).hexdigest() if value is not None else None


def _input_snapshot(parent, revision):
    return {'report_id': parent.report_id, 'report_version': parent.version,
            'revision_id': revision.revision_id, 'revision_version': revision.version,
            'revision_number': revision.number, 'source_sha256': revision.source_sha256,
            'profile_id': revision.profile_id, 'processing_status': revision.processing_status,
            'reading_cipher_sha256': _cipher_hash(revision.reading_cipher),
            'fields_cipher_sha256': _cipher_hash(revision.fields_cipher)}


def _fixed_report(db, user, identity):
    visible = core.report(db, user, identity)
    parent = db.scalar(select(AuditReport).where(AuditReport.report_id == visible.report_id)
                       .with_for_update().execution_options(populate_existing=True))
    revision = db.scalar(select(AuditRevision).where(AuditRevision.revision_id == parent.current_revision_id,
        AuditRevision.report_id == parent.report_id).with_for_update().execution_options(populate_existing=True))
    if revision is None:
        core.failure(409, '検証対象の版を読み込めません。')
    return parent, revision


def _observations(fields, definition):
    """Use schema types and explicit confirmation; no OCR candidate is a fact."""
    result = {}
    for mapping in definition.fields:
        item = fields.get(mapping.field_id)
        if not isinstance(item, dict) or item.get('state') != 'confirmed' or 'value' not in item:
            continue
        if item.get('unit') != mapping.unit or item.get('value_type', mapping.value_type) != mapping.value_type:
            continue
        try:
            value = confirm_value(mapping, item['value'])
            if value is not None and mapping.value_type in {'date', 'datetime', 'time'}:
                value = TemporalValue(type=mapping.value_type, value=value)
            result[mapping.field_id] = RuleObservation(state='confirmed', value=value, unit=mapping.unit)
        except (ValidationError, ValueError, TypeError):
            continue
    return result


def _profile_case(revision, definition):
    reading = vault.open_json('reading', revision.revision_id, revision.reading_cipher)
    current = core.read_fields(revision)
    mapped = core.mapped_fields(reading, definition)
    counts = Counter(item['state'] for item in mapped.values())
    invalid = 0
    tested = 0
    nonautomatic = 0
    changed = 0
    for field in definition.fields:
        item = mapped[field.field_id]
        if field.extraction != 'region':
            nonautomatic += 1
            continue
        valid = (item['state'] == 'unconfirmed' and item.get('candidate') is not None and
                 bool(item.get('evidence')) and not _INVALID_REGION.intersection(item.get('issues', [])))
        tested += int(valid)
        invalid += int(not valid)
    # Comparing extraction outputs describes changes only, never correctness.
    for key in mapped.keys() | current.keys():
        new, previous = mapped.get(key), current.get(key)
        if new is None or previous is None:
            changed += 1
        else:
            before = previous.get('value') if previous.get('state') == 'confirmed' else previous.get('candidate')
            if new.get('state') != previous.get('state') or new.get('candidate') != before:
                changed += 1
    return {'candidate_counts': dict(counts), 'prior_counts': dict(Counter(item.get('state', 'unmapped') for item in current.values())),
            'tested_opportunities': tested, 'invalid_opportunities': invalid,
            'nonautomatic_fields': nonautomatic, 'changed_count': changed,
            'comparison_available': True, 'reason_code': 'REGIONS_INCOMPLETE' if invalid else 'REGIONS_TESTED'}


def _rule_case(db, parent, revision, definition):
    if revision.profile_id is None:
        return {'candidate_counts': {}, 'prior_counts': {}, 'tested_opportunities': 0,
                'invalid_opportunities': len(definition.rules) or 1, 'changed_count': 0,
                'comparison_available': False, 'reason_code': 'PROFILE_REQUIRED', 'tested_rule_ids': []}
    profile_row = core.configuration(db, revision.profile_id, 'profile')
    mapping = _definition(profile_row)
    if mapping.form_key != definition.form_key:
        return {'candidate_counts': {}, 'prior_counts': {}, 'tested_opportunities': 0,
                'invalid_opportunities': len(definition.rules) or 1, 'changed_count': 0,
                'comparison_available': False, 'reason_code': 'FORM_NOT_MATCHED', 'tested_rule_ids': []}
    fields = core.read_fields(revision)
    findings = evaluate_rules(definition, _observations(fields, mapping), approval='draft',
                              as_of=definition.valid_from, form_key=mapping.form_key)
    counts = Counter(item['status'] for item in findings)
    tested_ids = [item['rule_id'] for item in findings if item['status'] in _TESTED]
    candidate = {item['rule_id']: item['status'] for item in findings}
    old, previous, comparable, comparison_reason = None, {}, False, 'NO_PRIOR_RUN'
    old = core.latest_run(db, parent.report_id, revision.revision_id)
    if old and old.revision_version == revision.version:
        previous_payload = vault.open_json('run', old.run_id, old.payload_cipher)
        if previous_payload.get('as_of') == definition.valid_from.isoformat():
            previous = {item['rule_id']: item['status'] for item in previous_payload.get('findings', [])}
            comparable, comparison_reason = True, 'SAME_REVISION_AND_SCENARIO'
        else:
            comparison_reason = 'DIFFERENT_EVALUATION_DATE'
    elif old:
        comparison_reason = 'PRIOR_RUN_STALE'
    changes = sum(previous.get(key) != candidate.get(key) for key in previous.keys() | candidate.keys()) if comparable else 0
    return {'candidate_counts': dict(counts), 'prior_counts': dict(Counter(previous.values())),
            'tested_opportunities': len(tested_ids), 'invalid_opportunities': counts['NOT_TESTED'],
            'changed_count': changes, 'comparison_available': comparable,
            'comparison_reason': comparison_reason, 'prior_run_id': old.run_id if old else None,
            'reason_code': 'RULE_INPUTS_INCOMPLETE' if counts['NOT_TESTED'] else 'RULES_TESTED',
            'tested_rule_ids': tested_ids}


def impact_config(db, user, identity, payload):
    user = _authorize(db, user, 'emergency.audit.configure')
    row = _locked_config(db, identity)
    if row.status != 'draft':
        core.failure(409, '影響検証は変更案に対して実施してください。')
    ids = [_identity(value) for value in payload.report_ids]
    if not 1 <= len(ids) <= 100 or len(set(ids)) != len(ids):
        core.failure(422, '重複しない検証対象を1件から100件まで指定してください。')
    definition = _definition(row)
    cases = []
    tested_ids = set()
    for report_id in sorted(ids):
        parent, revision = _fixed_report(db, user, report_id)
        snapshot = _input_snapshot(parent, revision)
        core.verified_original(revision)
        if revision.processing_status not in {'ready', 'partial'} or revision.reading_cipher is None:
            case = {'candidate_counts': {}, 'prior_counts': {}, 'tested_opportunities': 0,
                    'invalid_opportunities': 1, 'changed_count': 0, 'comparison_available': False,
                    'reason_code': 'READING_NOT_READY'}
        else:
            try:
                case = _profile_case(revision, definition) if row.kind == 'profile' else _rule_case(db, parent, revision, definition)
            except (ValueError, TypeError, KeyError):
                case = {'candidate_counts': {}, 'prior_counts': {}, 'tested_opportunities': 0,
                        'invalid_opportunities': 1, 'changed_count': 0, 'comparison_available': False,
                        'reason_code': 'INPUT_STRUCTURE_INVALID'}
        tested_ids.update(case.pop('tested_rule_ids', []))
        cases.append({**snapshot, **case})
    tested = sum(item['tested_opportunities'] for item in cases)
    incomplete = sum(bool(item['invalid_opportunities']) for item in cases)
    untested_rules = len(definition.rules) - len(tested_ids) if row.kind == 'rules' else 0
    result = {'schema_version': 1, 'kind': row.kind, 'definition_sha256': core.digest(definition.model_dump(mode='json')),
              'config_version': row.version + 1, 'evaluated_as_of': definition.valid_from.isoformat(),
              'report_count': len(cases), 'tested_opportunities': tested, 'incomplete_count': incomplete,
              'untested_rule_count': untested_rules, 'changed_count': sum(item['changed_count'] for item in cases),
              'can_approve': incomplete == 0 and tested > 0 and untested_rules == 0,
              'truth_verified': False, 'operational_effect_measured': False,
              'reports': cases, 'created_by': user.user_id, 'created_at': now_utc().isoformat()}
    _claim(db, row, row.version, 'draft', impact=result)
    core.audit(db, user, 'config_impact', row.config_id, kind=row.kind, version=row.version, count=len(cases))
    db.commit()
    return row


def _overlap(left, right):
    return left.valid_from <= (right.valid_to or date.max) and right.valid_from <= (left.valid_to or date.max)


def approve_config(db, user, identity, payload):
    user = _authorize(db, user, 'emergency.audit.approve')
    row = _locked_config(db, identity)
    if row.status != 'draft' or row.version != payload.expected_version:
        core.failure(409, '最新の変更案と検証結果を確認してください。')
    if (not row.created_employee_id or row.created_by == user.user_id or row.created_employee_id == user.employee_id):
        core.failure(403, '変更案の作成者とは別の職員が承認してください。')
    if payload.source_verified is not True or payload.mapping_verified is not True:
        core.failure(422)
    definition = _definition(row)
    impact = row.impact
    if (not isinstance(impact, dict) or impact.get('can_approve') is not True or
        impact.get('config_version') != row.version or impact.get('report_count', 0) < 1 or
        impact.get('tested_opportunities', 0) < 1 or impact.get('incomplete_count') != 0 or
        impact.get('untested_rule_count') != 0 or
        impact.get('definition_sha256') != core.digest(definition.model_dump(mode='json'))):
        core.failure(409, '変更案の影響検証を完了してください。')
    cases = impact.get('reports')
    if not isinstance(cases, list) or not 1 <= len(cases) <= 100 or len(cases) != impact['report_count']:
        core.failure(409, '検証対象を再確認してください。')
    if not row.source_id:
        core.failure(409, '確認に用いた根拠資料を登録してください。')
    source = db.get(AuditSource, row.source_id)
    if source is None:
        core.failure(409, '根拠資料を確認できません。')
    core.verified_original(source, 'source')
    approved_source_hashes = {source.source_sha256}
    if row.kind == 'rules':
        if any(rule.source.sha256 is None for rule in definition.rules):
            core.failure(409, '各チェック条件の根拠資料と版を指定してください。')
        # A set may combine national and local manuals. Each immutable hash
        # must identify a retained private original, independently of which
        # manual is selected as the primary reference for this configuration.
        required = {rule.source.sha256.lower() for rule in definition.rules}
        for checksum in sorted(required - approved_source_hashes):
            retained = db.scalar(select(AuditSource).where(AuditSource.source_sha256 == checksum)
                .order_by(AuditSource.created_at, AuditSource.source_id).limit(1))
            if retained is None:
                core.failure(409, 'チェック条件が参照する根拠資料の版を登録してください。')
            core.verified_original(retained, 'source')
            approved_source_hashes.add(checksum)
    for case in sorted(cases, key=lambda item: item['report_id']):
        parent, revision = _fixed_report(db, user, case['report_id'])
        snapshot = _input_snapshot(parent, revision)
        if any(case.get(key) != value for key, value in snapshot.items()):
            core.failure(409, '検証後に報告書が変わっています。影響検証をやり直してください。')
        core.verified_original(revision)
    for other in db.scalars(select(AuditConfiguration).where(
            AuditConfiguration.kind == row.kind, AuditConfiguration.form_key == row.form_key,
            AuditConfiguration.status == 'approved', AuditConfiguration.config_id != row.config_id)
            .with_for_update()):
        if _overlap(definition, _definition(other)):
            core.failure(409, '施行期間が重なる承認済み設定があります。使用終了または期間を確認してください。')
    result = {**impact, 'approval_version': row.version + 1, 'source_verified': True, 'mapping_verified': True,
              'approved_source_hashes': sorted(approved_source_hashes)}
    _claim(db, row, payload.expected_version, 'draft', status='approved', impact=result,
           approved_by=user.user_id, approved_employee_id=user.employee_id, approved_at=now_utc())
    core.audit(db, user, 'config_approve', row.config_id, kind=row.kind, version=row.version, count=len(cases))
    db.commit()
    return row


def retire_config(db, user, identity, payload):
    user = _authorize(db, user, 'emergency.audit.approve')
    row = _locked_config(db, identity)
    _definition(row)
    _claim(db, row, payload.expected_version, 'approved', status='retired')
    core.audit(db, user, 'config_retire', row.config_id, kind=row.kind, version=row.version)
    db.commit()
    return row
