"""Freeze independent labels and family partitions, without executing training.

All writes enter through the existing serializing session/permission guard.
The registry is department-private; no generic learning/Document path is used.
"""
from collections import Counter
from uuid import uuid4

from fastapi import HTTPException
from sqlalchemy import select

from . import emergency_audit_service as core, emergency_vault as vault
from .authz import permission_codes
from .emergency_audit_config_service import _definition
from .emergency_audit_models import AuditJob, AuditRevision, AuditSource
from .emergency_training_models import TrainingDataset, TrainingFamilyMember, TrainingFamilyPartition, TrainingTruth
from .emergency_training_schemas import RegisterTruth
from .models import User
from .personnel import employee_available

MAX_SOURCE_BYTES = 100 * 1024 * 1024


def _employee(user):
    if not user.employee_id:
        core.failure(403)
    return user.employee_id


def _members(db, user, identity, *, required=True):
    rows = list(db.scalars(select(TrainingFamilyMember)
        .where(TrainingFamilyMember.family_id == identity).order_by(TrainingFamilyMember.report_id).limit(101)))
    if not rows and required:
        core.failure(404)
    if len(rows) > 100:
        core.failure(413)
    for row in rows:
        core.report(db, user, row.report_id)
    return rows


def family_output(db, user, identity):
    members = _members(db, user, identity)
    return {'family_id': identity, 'report_count': len(members),
            'report_ids': [m.report_id for m in members], 'model_training_performed': False}


def _known_duplicates(db, family_id, checksums):
    collision = db.scalar(select(TrainingFamilyMember.report_id).join(AuditRevision,
        AuditRevision.report_id == TrainingFamilyMember.report_id).where(
        AuditRevision.source_sha256.in_(checksums), TrainingFamilyMember.family_id != family_id).limit(1))
    if collision:
        core.failure(409, '同じ原本または同一事案の所属を確認してください。')


def validate_family_original(db, report_id, checksum):
    """Called under the existing Human mutation lock before appending a source."""
    member = db.get(TrainingFamilyMember, report_id)
    if member:
        _known_duplicates(db, member.family_id, {checksum})


def register_family(db, user, payload):
    employee_id = _employee(user)
    identity = str(payload.family_id)
    members = _members(db, user, identity, required=False)
    reports = [core.report(db, user, str(r)) for r in payload.report_ids]
    if len({r.dataset_kind for r in reports} | {
            core.report(db, user, m.report_id).dataset_kind for m in members}) != 1:
        core.failure(422)
    added = []
    for report in reports:
        member = db.get(TrainingFamilyMember, report.report_id)
        if member:
            if member.family_id != identity:
                core.failure(409, '同一事案の所属は変更できません。')
            continue
        hashes = set(db.scalars(select(AuditRevision.source_sha256)
            .where(AuditRevision.report_id == report.report_id)))
        _known_duplicates(db, identity, hashes)
        added.append(TrainingFamilyMember(report_id=report.report_id, family_id=identity,
            created_by=user.user_id, created_employee_id=employee_id))
    if len(members) + len(added) > 100:
        core.failure(413)
    if added:
        db.add_all(added)
        core.audit(db, user, 'training_family', identity, count=len(added))
        db.commit()
    return family_output(db, user, identity), bool(added)


def _independent(db, user, parent, revision):
    employee_id = _employee(user)
    initial = db.scalar(select(AuditJob).where(AuditJob.revision_id == revision.revision_id,
        AuditJob.kind == 'read').order_by(AuditJob.created_at, AuditJob.job_id).limit(1))
    if (not parent.owner_employee_id or not initial or not initial.requested_employee_id or
        initial.requested_by != revision.created_by):
        core.failure(409, '原本の登録時の職員記録を確認してください。')
    if (
        user.user_id in {parent.owner_id, revision.created_by} or
        employee_id in {parent.owner_employee_id, initial.requested_employee_id}):
        core.failure(403, '原本の作成者と異なる職員による確認が必要です。')


def _configuration(db, identity, kind, dataset_kind, as_of):
    row = core.configuration(db, identity, kind)
    if row.status == 'retired' or (dataset_kind == 'internal_trial' and row.status != 'approved'):
        core.failure(409, '有効な様式・根拠の版を確認してください。')
    definition = _definition(row)
    if as_of < definition.valid_from or (definition.valid_to is not None and as_of > definition.valid_to):
        core.failure(422, '適用日と様式・根拠を確認してください。')
    return row, definition


def _verify_evidence(source, cache):
    identity = (source.source_id, source.source_sha256, source.size_bytes, source.media_type, source.page_count)
    if identity not in cache['sources']:
        core.verified_original(source, 'source')
        cache['sources'].add(identity)


def _proof(db, row, definition, cache):
    identity = (row.config_id, row.request_sha256, row.status)
    if identity in cache['configurations']:
        return cache['configurations'][identity]
    source = db.get(AuditSource, row.source_id) if row.source_id else None
    if row.source_id and source is None:
        core.failure(409, '設定の根拠原本を確認してください。')
    if row.status == 'approved' and source is None:
        core.failure(409, '承認済み設定の根拠原本が確認できません。')
    retained = {}
    if source:
        _verify_evidence(source, cache)
        retained[source.source_id] = source.source_sha256
    if row.kind == 'rules':
        for rule in definition.rules:
            checksum = rule.source.sha256
            if checksum is None:
                if row.status == 'approved':
                    core.failure(409, '各条件の根拠原本を確認してください。')
                continue
            checksum = checksum.lower()
            if checksum in retained.values():
                continue
            secondary = db.scalar(select(AuditSource).where(AuditSource.source_sha256 == checksum)
                .order_by(AuditSource.created_at, AuditSource.source_id).limit(1))
            if secondary is None:
                core.failure(409, '各条件の根拠原本を確認してください。')
            _verify_evidence(secondary, cache)
            retained[secondary.source_id] = checksum
    proof = {'config_id': row.config_id, 'definition_sha256': row.request_sha256,
            'source_id': row.source_id, 'source_sha256': source.source_sha256 if source else None,
            'evidence_sha256': retained, 'status': row.status}
    cache['configurations'][identity] = proof
    return proof


def _source_proof(db, parent, revision, payload, cache=None):
    if cache is None:
        cache = {'configurations': {}, 'sources': set()}
    profile, definition = _configuration(db, revision.profile_id, 'profile', parent.dataset_kind, payload.form_as_of)
    fields = {f.field_id: f for f in definition.fields}
    for annotation in payload.annotations:
        field = fields.get(annotation.field_id)
        if field is None or annotation.page > revision.page_count or annotation.page != field.page:
            core.failure(422, '原本と正式な欄の位置を確認してください。')
        if field.extraction == 'not_printed' and annotation.read_state != 'not_printed':
            core.failure(422, '非印字と確認済みの値は区別してください。')
        if annotation.bbox is not None and field.bbox is not None:
            a, b = annotation.bbox, field.bbox
            if a[0] < b[0] or a[1] < b[1] or a[2] > b[2] or a[3] > b[3]:
                core.failure(422, '正解の位置は対象欄の範囲内で指定してください。')
    rules = None
    if payload.rule_set_id:
        rule, rule_definition = _configuration(db, payload.rule_set_id, 'rules', parent.dataset_kind, payload.as_of)
        if rule.form_key != profile.form_key:
            core.failure(422)
        rules = _proof(db, rule, rule_definition, cache)
    return {'report_id': parent.report_id, 'revision_id': revision.revision_id,
        'revision_version': revision.version, 'source_sha256': revision.source_sha256,
        'size_bytes': revision.size_bytes, 'dataset_kind': parent.dataset_kind,
        'profile': _proof(db, profile, definition, cache), 'rules': rules}


def truth_record(db, user, identity):
    row = db.get(TrainingTruth, identity)
    if row is None:
        core.failure(404)
    core.revision(db, user, row.revision_id)
    return row


def _truth_content(row):
    value = vault.open_json('training_truth', row.truth_id, row.payload_cipher)
    try:
        payload = RegisterTruth.model_validate(value['request'])
        if (core.digest(value['request']) != row.request_sha256 or
            str(payload.request_id) != row.request_id or payload.task != row.task or
            (str(payload.supersedes_id) if payload.supersedes_id else None) != row.supersedes_id or
            value['source']['revision_id'] != row.revision_id):
            raise ValueError()
    except (KeyError, TypeError, ValueError):
        raise vault.VaultError('PRIVATE_CONTENT_INTEGRITY') from None
    return value, payload


def truth_output(db, user, row):
    core.revision(db, user, row.revision_id)
    value, _ = _truth_content(row)
    return {**value['request'], 'truth_id': row.truth_id, 'revision_id': row.revision_id,
            'source': value['source'], 'created_by': row.created_by,
            'created_at': row.created_at, 'model_training_performed': False}


def register_truth(db, user, identity, payload):
    parent, revision = core.revision(db, user, identity)
    _independent(db, user, parent, revision)
    request = payload.model_dump(mode='json')
    fingerprint = core.digest(request)
    existing = db.scalar(select(TrainingTruth).where(TrainingTruth.request_id == str(payload.request_id)))
    if existing:
        if (existing.request_sha256 != fingerprint or existing.revision_id != identity or
            existing.created_by != user.user_id or existing.created_employee_id != user.employee_id):
            core.failure(409)
        _truth_content(existing)
        return existing, False
    if parent.version != payload.expected_version:
        core.failure(409)
    proof = _source_proof(db, parent, revision, payload)
    previous = None
    if payload.supersedes_id:
        previous = truth_record(db, user, str(payload.supersedes_id))
        if previous.revision_id != identity or previous.task != payload.task:
            core.failure(422)
        if db.scalar(select(TrainingTruth.truth_id).where(TrainingTruth.supersedes_id == previous.truth_id)):
            core.failure(409)
    elif db.scalar(select(TrainingTruth.truth_id).where(
            TrainingTruth.revision_id == identity, TrainingTruth.task == payload.task)):
        core.failure(409, '正解の訂正は既存版を指定して新しい版にしてください。')
    core.verified_original(revision)
    row = TrainingTruth(truth_id=str(uuid4()), request_id=str(payload.request_id), request_sha256=fingerprint,
        supersedes_id=previous.truth_id if previous else None, revision_id=identity, task=payload.task,
        created_by=user.user_id, created_employee_id=user.employee_id)
    row.payload_cipher = vault.seal_json('training_truth', row.truth_id, {'request': request, 'source': proof})
    db.add(row)
    core.audit(db, user, 'training_truth', row.truth_id, count=len(payload.annotations))
    db.commit()
    return row, True


def dataset_record(db, identity):
    row = db.get(TrainingDataset, identity)
    if row is None:
        core.failure(404)
    return row


def _manifest(row):
    value = vault.open_json('training_dataset', row.dataset_id, row.manifest_cipher)
    if core.digest(value) != row.manifest_sha256:
        raise vault.VaultError('PRIVATE_CONTENT_INTEGRITY')
    return value


def dataset_output(db, user, row):
    manifest = _manifest(row)
    for identity in manifest['report_ids']:
        core.report(db, user, identity)
    return {'dataset_id': row.dataset_id, 'manifest_sha256': row.manifest_sha256,
        'supersedes_id': row.supersedes_id, 'manifest': manifest, 'created_at': row.created_at,
        'model_training_performed': False, 'training_ready': False}


def _usable_truth(db, user, identity, task, cache):
    row = truth_record(db, user, identity)
    if row.task != task or db.scalar(select(TrainingTruth.truth_id).where(TrainingTruth.supersedes_id == identity)):
        core.failure(409, '最新の独立正解を確認してください。')
    author = db.get(User, row.created_by)
    if (not author or not author.active or author.employee_id != row.created_employee_id or
        not employee_available(db, author) or 'emergency.report.review' not in permission_codes(db, author.user_id)):
        core.failure(409, '正解の独立確認者を確認してください。')
    try:
        core.revision(db, author, row.revision_id)
    except HTTPException as error:
        if error.status_code not in {403, 404}:
            raise
        core.failure(409, '正解の独立確認者の現在の参照権限を確認してください。')
    value, payload = _truth_content(row)
    parent, revision = core.revision(db, user, row.revision_id)
    _independent(db, author, parent, revision)
    proof = _source_proof(db, parent, revision, payload, cache)
    if proof != value['source']:
        core.failure(409, '原本・様式・正解の版を確認してください。')
    core.verified_original(revision)
    return row, payload, proof


def _quarantine(annotation, payload):
    if annotation.read_state != 'confirmed':
        return 'reading_' + annotation.read_state
    if annotation.truth in {'unknown', 'not_applicable'}:
        return 'truth_' + annotation.truth
    if annotation.truth == 'correct' and not payload.whole_scope_checked:
        return 'negative_scope_unreviewed'
    if payload.task == 'content_review' and annotation.truth == 'error' and not annotation.allowed_corrections:
        return 'correction_unconfirmed'
    return None


def register_dataset(db, user, payload):
    _employee(user)
    request = payload.model_dump(mode='json')
    fingerprint = core.digest(request)
    existing = db.scalar(select(TrainingDataset).where(TrainingDataset.request_id == str(payload.request_id)))
    if existing:
        if (existing.request_sha256 != fingerprint or existing.created_by != user.user_id or
            existing.created_employee_id != user.employee_id):
            core.failure(409)
        dataset_output(db, user, existing)
        return existing, False
    assignments = {str(f.family_id): f.split for f in payload.family_splits}
    report_ids = set()
    for family_id in assignments:
        members = _members(db, user, family_id)
        identities = [m.report_id for m in members]
        report_ids.update(identities)
        all_hashes = set(db.scalars(select(AuditRevision.source_sha256)
            .where(AuditRevision.report_id.in_(identities))))
        _known_duplicates(db, family_id, all_hashes)
        fixed = db.get(TrainingFamilyPartition, family_id)
        if fixed and fixed.split != assignments[family_id]:
            core.failure(409, '固定したfamilyの分割は別datasetでも移動できません。')
    if len(report_ids) > 100:
        core.failure(413)
    previous = None
    if payload.supersedes_id:
        previous = dataset_record(db, str(payload.supersedes_id))
        old = dataset_output(db, user, previous)['manifest']
        if previous.task != payload.task or any(assignments.get(f) != s for f, s in old['family_splits'].items()):
            core.failure(409, '固定したfamilyの分割は移動・削除できません。')
        if db.scalar(select(TrainingDataset.dataset_id).where(TrainingDataset.supersedes_id == previous.dataset_id)):
            core.failure(409)
    samples, quarantined, hashes, kinds, submitted_families = [], [], {}, set(), set()
    observed_inputs = {}
    evidence_cache = {'configurations': {}, 'sources': set()}
    configurations = {}
    for identity in payload.truth_ids:
        row, truth, proof = _usable_truth(db, user, str(identity), payload.task, evidence_cache)
        for config in (proof['profile'], proof['rules']):
            if config is not None:
                configurations[config['config_id']] = config
        member = db.get(TrainingFamilyMember, proof['report_id'])
        if not member or member.family_id not in assignments:
            core.failure(422, '原本familyと分割の対応を確認してください。')
        family_id = member.family_id
        submitted_families.add(family_id)
        _known_duplicates(db, family_id, {proof['source_sha256']})
        source_hash = proof['source_sha256']
        if source_hash in hashes and hashes[source_hash][0] != family_id:
            core.failure(409, '同一原本を別のfamilyへ分けることはできません。')
        hashes[source_hash] = (family_id, proof['size_bytes'])
        if sum(v[1] for v in hashes.values()) > MAX_SOURCE_BYTES:
            core.failure(413, '固定する原本集合の容量上限を超えています。')
        kinds.add(proof['dataset_kind'])
        for index, annotation in enumerate(truth.annotations):
            reference = {'truth_id': row.truth_id, 'truth_sha256': row.request_sha256,
                'annotation_index': index, 'revision_id': row.revision_id,
                'report_id': proof['report_id'], 'source_sha256': source_hash, 'revision_version': proof['revision_version'],
                'family_id': family_id, 'split': assignments[family_id],
                'profile_id': proof['profile']['config_id'],
                'rule_set_id': proof['rules']['config_id'] if proof['rules'] else None}
            reason = _quarantine(annotation, truth)
            if reason is None:
                input_scope = (source_hash, proof['profile']['definition_sha256'],
                               annotation.field_id, annotation.page, tuple(annotation.bbox))
                target = annotation.observed_text if payload.task == 'transcription' else {
                    'truth': annotation.truth, 'allowed_corrections': annotation.allowed_corrections,
                    'basis': truth.basis, 'as_of': truth.as_of.isoformat(), 'rules': proof['rules']}
                target_sha256 = core.digest(target)
                if input_scope in observed_inputs:
                    if observed_inputs[input_scope] != target_sha256:
                        core.failure(409, '同一原本の独立正解が一致していません。再確認してください。')
                    reason = 'duplicate_source'
                else:
                    observed_inputs[input_scope] = target_sha256
            if reason:
                quarantined.append({**reference, 'reason': reason})
            else:
                samples.append({**reference, 'target': 'observed_text' if payload.task == 'transcription' else 'content_truth'})
    if len(kinds) != 1:
        core.failure(422)
    counts = Counter(s['split'] for s in samples)
    if submitted_families != set(assignments) or any(counts[s] == 0 for s in ('train', 'validation', 'holdout')):
        core.failure(409, '未確定を正解にせず、各familyの利用できる正解を確認してください。')
    manifest = {'schema_version': 1, 'task': payload.task, 'dataset_kind': next(iter(kinds)),
        'preprocessing_sha256': payload.preprocessing_sha256, 'family_splits': assignments,
        'configurations': configurations,
        'report_ids': sorted(report_ids), 'samples': samples, 'quarantined': quarantined,
        'counts': {**{s: counts[s] for s in ('train', 'validation', 'holdout')}, 'quarantined': len(quarantined)}}
    row = TrainingDataset(dataset_id=str(uuid4()), request_id=str(payload.request_id), request_sha256=fingerprint,
        supersedes_id=previous.dataset_id if previous else None, task=payload.task,
        manifest_sha256=core.digest(manifest), created_by=user.user_id, created_employee_id=user.employee_id)
    row.manifest_cipher = vault.seal_json('training_dataset', row.dataset_id, manifest)
    for family_id, split in assignments.items():
        if db.get(TrainingFamilyPartition, family_id) is None:
            db.add(TrainingFamilyPartition(family_id=family_id, split=split,
                created_by=user.user_id, created_employee_id=user.employee_id))
    db.add(row)
    core.audit(db, user, 'training_dataset', row.dataset_id, count=len(samples))
    db.commit()
    return row, True
