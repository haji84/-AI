"""Synthetic-only dataset contracts; never workstation or model-quality evidence."""
import json
from uuid import uuid4

import pytest
from sqlalchemy import select

from test_emergency_audit_api import P, client, create_profile, login, pdf, upload
from app.db import SessionLocal
from app.models import AuditLog, Document, User

T = P + '/training'


def family(c, reports, identity=None):
    identity = identity or str(uuid4())
    r = c.post(T + '/families', json={'family_id': identity,
        'report_ids': [x['report_id'] for x in reports]})
    assert r.status_code in (200, 201), r.text
    return r.json()


def truth_input(report, **changes):
    value = {'request_id': str(uuid4()), 'expected_version': report['version'],
        'task': 'transcription', 'basis': 'as_written', 'form_as_of': '2026-11-22', 'as_of': '2026-11-22',
        'source_verified': True, 'whole_scope_checked': True,
        'annotations': [{'field_id': 'a', 'page': 1, 'bbox': [0, 0, 1, .2],
            'read_state': 'confirmed', 'truth': 'error', 'error_id': str(uuid4()),
            'observed_text': 'SYNTHETIC AS WRITTEN',
            'allowed_corrections': ['SYNTHETIC CORRECTED'],
            'evidence': 'SYNTHETIC INDEPENDENT SOURCE CHECK'}]}
    return {**value, **changes}


def save_truth(c, report, payload=None):
    r = c.post(P + '/revisions/' + report['current_revision_id'] + '/training-truth',
        json=payload or truth_input(report))
    assert r.status_code in (200, 201), r.text
    return r.json()


def prepared(c):
    profile = create_profile(c)
    reports = [upload(c, content=pdf('SYNTHETIC FAMILY '+str(i)), profile_id=profile['config_id']).json()
               for i in range(3)]
    families = [family(c, [report])['family_id'] for report in reports]
    login(c, 'reviewer')
    truths = [save_truth(c, report) for report in reports]
    return reports, families, truths


def dataset_input(families, truths, **changes):
    value = {'request_id': str(uuid4()), 'task': 'transcription',
        'preprocessing_sha256': '1'*64,
        'truth_ids': [x['truth_id'] for x in truths],
        'family_splits': [{'family_id': family_id, 'split': split}
                          for family_id, split in zip(families, ['train', 'validation', 'holdout'])]}
    return {**value, **changes}


def test_truth_requires_independent_employee_and_preserves_written_error_encrypted(client):
    profile = create_profile(client)
    report = upload(client, profile_id=profile['config_id']).json()
    path = P + '/revisions/' + report['current_revision_id'] + '/training-truth'
    payload = truth_input(report)
    assert client.post(path, json=payload).status_code == 403
    login(client, 'reviewer')
    saved = save_truth(client, report, payload)
    assert saved['annotations'][0]['observed_text'] == 'SYNTHETIC AS WRITTEN'
    assert saved['annotations'][0]['allowed_corrections'] == ['SYNTHETIC CORRECTED']
    assert saved['model_training_performed'] is False
    assert client.post(path, json=payload).status_code == 200
    changed = {**payload, 'whole_scope_checked': False}
    assert client.post(path, json=changed).status_code == 409
    from app.emergency_training_models import TrainingTruth
    with SessionLocal() as db:
        row = db.get(TrainingTruth, saved['truth_id'])
        assert b'SYNTHETIC AS WRITTEN' not in row.payload_cipher
        assert b'SYNTHETIC CORRECTED' not in row.payload_cipher
        assert b'SYNTHETIC INDEPENDENT' not in row.payload_cipher
        assert list(db.scalars(select(Document))) == []
        logs = db.scalars(select(AuditLog).where(AuditLog.action.like('emergency.audit.training%'))).all()
        assert logs
        assert 'SYNTHETIC AS WRITTEN' not in json.dumps([x.after_data for x in logs])
        owner = db.scalar(select(User).where(User.username == 'audit-owner'))
        reviewer = db.scalar(select(User).where(User.username == 'audit-reviewer'))
        # One active account per employee is enforced by the existing DB.
        # Reassignment must still respect the report's original employee snapshot.
        original_employee = owner.employee_id
        owner.employee_id = None
        db.flush()
        reviewer.employee_id = original_employee
        db.commit()
    login(client, 'reviewer')
    assert client.post(path, json={**payload, 'request_id': str(uuid4())}).status_code == 403


def test_family_rejects_reassignment_and_exact_duplicate_across_families(client):
    content = pdf('SYNTHETIC SAME SOURCE')
    first = upload(client, content=content).json()
    copied = upload(client, content=content).json()
    saved = family(client, [first])
    assert family(client, [first], saved['family_id'])['family_id'] == saved['family_id']
    for report in [first, copied]:
        r = client.post(T + '/families', json={'family_id': str(uuid4()), 'report_ids': [report['report_id']]})
        assert r.status_code == 409
    assert family(client, [copied], saved['family_id'])['report_count'] == 2
    login(client, 'outsider')
    r = client.get(T + '/families/' + saved['family_id'])
    assert r.status_code == 404


def test_dataset_freezes_partitions_and_never_substitutes_corrections_as_transcription(client):
    reports, families, truths = prepared(client)
    payload = dataset_input(families, truths)
    r = client.post(T + '/datasets', json=payload)
    assert r.status_code == 201, r.text
    saved = r.json()
    manifest = saved['manifest']
    assert saved['model_training_performed'] is False
    assert manifest['counts'] == {'train': 1, 'validation': 1, 'holdout': 1, 'quarantined': 0}
    assert {x['target'] for x in manifest['samples']} == {'observed_text'}
    assert 'SYNTHETIC AS WRITTEN' not in r.text
    assert 'SYNTHETIC CORRECTED' not in r.text
    assert len({x['source_sha256'] for x in manifest['samples']}) == 3
    assert client.post(T + '/datasets', json=payload).status_code == 200
    changed = {**payload, 'preprocessing_sha256': '2'*64}
    assert client.post(T + '/datasets', json=changed).status_code == 409
    assert client.get(T + '/datasets/' + saved['dataset_id']).json()['manifest_sha256'] == saved['manifest_sha256']
    login(client, 'outsider')
    assert client.get(T + '/datasets/' + saved['dataset_id']).status_code == 404
    from app.emergency_training_models import TrainingDataset
    from app import emergency_vault as vault
    with SessionLocal() as db:
        row = db.get(TrainingDataset, saved['dataset_id'])
        assert saved['manifest_sha256'].encode() not in row.manifest_cipher
        with pytest.raises(vault.VaultError):
            vault.open_json('training_dataset', str(uuid4()), row.manifest_cipher)


def test_dataset_rejects_family_overlap_incomplete_splits_and_inherited_split_changes(client):
    _, families, truths = prepared(client)
    payload = dataset_input(families, truths)
    duplicate = {**payload, 'family_splits': payload['family_splits'] + [
        {'family_id': families[0], 'split': 'holdout'}]}
    assert client.post(T + '/datasets', json=duplicate).status_code == 422
    incomplete = {**payload, 'family_splits': payload['family_splits'][:2]}
    assert client.post(T + '/datasets', json=incomplete).status_code == 422
    saved = client.post(T + '/datasets', json=payload)
    assert saved.status_code == 201, saved.text
    swapped = [dict(x) for x in payload['family_splits']]
    swapped[0]['split'], swapped[2]['split'] = 'holdout', 'train'
    r = client.post(T + '/datasets', json={**payload, 'request_id': str(uuid4()),
        'supersedes_id': saved.json()['dataset_id'], 'family_splits': swapped})
    assert r.status_code == 409


def test_unresolved_reading_and_unreviewed_negative_are_not_training_labels(client):
    reports, families, truths = prepared(client)
    original = truth_input(reports[0])
    annotations = [original['annotations'][0], {**original['annotations'][0],
        'field_id': 'unknown', 'read_state': 'unconfirmed', 'truth': 'unknown',
        'error_id': None, 'allowed_corrections': [], 'observed_text': None}]
    # An unknown field cannot be smuggled into a teacher record.
    r = client.post(P + '/revisions/' + reports[0]['current_revision_id'] + '/training-truth',
        json={**original, 'annotations': annotations})
    assert r.status_code == 422
    negative = {**original['annotations'][0], 'truth': 'correct', 'error_id': None,
                'allowed_corrections': []}
    revised = save_truth(client, reports[0], {**original, 'supersedes_id': truths[0]['truth_id'],
        'whole_scope_checked': False, 'annotations': [negative]})
    payload = dataset_input(families, [revised, *truths[1:]])
    assert client.post(T + '/datasets', json=payload).status_code == 409
    # The superseded truth is not reusable to bypass the new incomplete review.
    assert client.post(T + '/datasets', json=dataset_input(families, truths)).status_code == 409


def test_truth_rejects_stale_source_unknown_positions_and_private_input_echo(client):
    profile = create_profile(client)
    report = upload(client, profile_id=profile['config_id']).json()
    login(client, 'reviewer')
    path = P + '/revisions/' + report['current_revision_id'] + '/training-truth'
    payload = truth_input(report)
    assert client.post(path, json={**payload, 'expected_version': 99}).status_code == 409
    malformed = {**payload, 'patient_private_marker': 'SYNTHETIC_PRIVATE_DO_NOT_REFLECT'}
    r = client.post(path, json=malformed)
    assert r.status_code == 422 and 'SYNTHETIC_PRIVATE' not in r.text
    assert r.headers['cache-control'] == 'no-store'
    bad_annotation = {**payload['annotations'][0], 'page': 2}
    assert client.post(path, json={**payload, 'annotations': [bad_annotation]}).status_code == 422
    r = client.post(path, json=payload, headers={'Origin': 'https://external.invalid'})
    assert r.status_code == 403


def test_retired_profile_or_tampered_original_blocks_dataset_snapshot(client):
    reports, families, truths = prepared(client)
    from app.emergency_audit_models import AuditConfiguration, AuditRevision
    from app import emergency_vault as vault
    with SessionLocal() as db:
        revision = db.get(AuditRevision, reports[0]['current_revision_id'])
        profile = db.get(AuditConfiguration, revision.profile_id)
        profile.status = 'retired'
        db.commit()
    r = client.post(T + '/datasets', json=dataset_input(families, truths))
    assert r.status_code == 409
    with SessionLocal() as db:
        profile = db.get(AuditConfiguration, profile.config_id)
        profile.status = 'draft'
        db.commit()
    # Change only this generated encrypted fixture; no real originals are touched.
    revision_id = reports[0]['current_revision_id']
    path = vault._path('revision', revision_id)
    path.write_bytes(vault.seal('revision', revision_id, b'SYNTHETIC TAMPER'))
    assert client.post(T + '/datasets', json=dataset_input(families, truths)).status_code == 503


def test_exact_duplicate_annotations_do_not_inflate_training_or_evaluation_counts(client):
    reports, families, truths = prepared(client)
    from app import emergency_vault as vault
    original = vault.read_original('revision', reports[0]['current_revision_id'])
    login(client)
    copied = upload(client, content=original, profile_id=reports[0]['revision']['profile_id']).json()
    family(client, [copied], families[0])
    login(client, 'reviewer')
    duplicate = save_truth(client, copied)
    r = client.post(T + '/datasets', json=dataset_input(families, [*truths, duplicate]))
    assert r.status_code == 201, r.text
    manifest = r.json()['manifest']
    assert manifest['counts'] == {'train': 1, 'validation': 1, 'holdout': 1, 'quarantined': 1}
    assert manifest['quarantined'][0]['reason'] == 'duplicate_source'


def test_conflicting_transcriptions_of_the_same_source_cannot_be_selected_by_input_order(client):
    reports, families, truths = prepared(client)
    from app import emergency_vault as vault
    original = vault.read_original('revision', reports[0]['current_revision_id'])
    login(client)
    copied = upload(client, content=original, profile_id=reports[0]['revision']['profile_id']).json()
    family(client, [copied], families[0])
    login(client, 'reviewer')
    payload = truth_input(copied)
    payload['annotations'][0]['observed_text'] = 'SYNTHETIC CONFLICTING TRANSCRIPTION'
    conflicting = save_truth(client, copied, payload)
    for ordered in [[*truths, conflicting], [conflicting, *truths]]:
        assert client.post(T + '/datasets', json=dataset_input(families, ordered)).status_code == 409


def test_revised_report_automatically_inherits_its_family_partition(client):
    reports, families, truths = prepared(client)
    login(client)
    report = reports[0]
    r = client.post(P+'/reports/'+report['report_id']+'/revisions',
        data={'request_id': str(uuid4()), 'expected_version': report['version'],
              'profile_id': report['revision']['profile_id']},
        files={'file': ('synthetic-revision.pdf', pdf('SYNTHETIC REVISED ORIGINAL'), 'application/pdf')})
    assert r.status_code == 201, r.text
    revision = r.json()
    login(client, 'reviewer')
    truth = save_truth(client, revision)
    r = client.post(T+'/datasets', json=dataset_input(families, [*truths, truth]))
    assert r.status_code == 201, r.text
    samples = r.json()['manifest']['samples']
    inherited = [s for s in samples if s['report_id'] == report['report_id']]
    assert len(inherited) == 2
    assert {s['family_id'] for s in inherited} == {families[0]}
    assert {s['split'] for s in inherited} == {'train'}


def test_new_dataset_root_cannot_reset_a_previously_fixed_family_split(client):
    _, families, truths = prepared(client)
    payload = dataset_input(families, truths)
    assert client.post(T+'/datasets', json=payload).status_code == 201
    splits = [dict(f) for f in payload['family_splits']]
    splits[0]['split'], splits[2]['split'] = 'holdout', 'train'
    assert client.post(T+'/datasets', json={**payload, 'request_id': str(uuid4()),
        'family_splits': splits}).status_code == 409


@pytest.mark.parametrize('lost_permission', ['emergency.patient.read', 'emergency.audit.read_all'])
def test_publisher_cannot_reuse_labels_after_the_reviewer_loses_detail_access(client, lost_permission):
    _, families, truths = prepared(client)
    from app.models import Permission, RolePermission, UserRole
    with SessionLocal() as db:
        reviewer = db.scalar(select(User).where(User.username == 'audit-reviewer'))
        role_ids = db.scalars(select(UserRole.role_id).where(UserRole.user_id == reviewer.user_id)).all()
        permission = db.scalar(select(Permission).where(Permission.code == lost_permission))
        for link in db.scalars(select(RolePermission).where(RolePermission.role_id.in_(role_ids),
                RolePermission.permission_id == permission.permission_id)):
            db.delete(link)
        db.commit()
    login(client)
    assert client.post(T+'/datasets', json=dataset_input(families, truths)).status_code == 409


def test_revision_uploader_independence_uses_the_employee_at_upload_time(client):
    profile = create_profile(client)
    report = upload(client, profile_id=profile['config_id']).json()
    login(client, 'reviewer')
    response = client.post(P+'/reports/'+report['report_id']+'/revisions',
        data={'request_id': str(uuid4()), 'expected_version': report['version'], 'profile_id': profile['config_id']},
        files={'file': ('synthetic-second-author.pdf', pdf('SYNTHETIC SECOND AUTHOR'), 'application/pdf')})
    assert response.status_code == 201, response.text
    revision = response.json()
    from app.models import Permission, RolePermission, UserRole
    with SessionLocal() as db:
        uploader = db.scalar(select(User).where(User.username == 'audit-reviewer'))
        reviewer = db.scalar(select(User).where(User.username == 'audit-outsider'))
        original_employee, other_employee = uploader.employee_id, reviewer.employee_id
        uploader.employee_id = None
        db.flush()
        reviewer.employee_id = original_employee
        db.flush()
        uploader.employee_id = other_employee
        role_id = db.scalar(select(UserRole.role_id).where(UserRole.user_id == reviewer.user_id))
        for code in ['emergency.report.review', 'emergency.audit.read_all']:
            permission = db.scalar(select(Permission).where(Permission.code == code))
            db.add(RolePermission(role_id=role_id, permission_id=permission.permission_id))
        db.commit()
    login(client, 'outsider')
    assert client.post(P+'/revisions/'+revision['current_revision_id']+'/training-truth',
        json=truth_input(revision)).status_code == 403


def test_enrolled_report_cannot_append_an_original_owned_by_a_different_family(client):
    reports, _, _ = prepared(client)
    from app import emergency_vault as vault
    content = vault.read_original('revision', reports[1]['current_revision_id'])
    login(client)
    r = client.post(P+'/reports/'+reports[0]['report_id']+'/revisions',
        data={'request_id': str(uuid4()), 'expected_version': reports[0]['version'],
              'profile_id': reports[0]['revision']['profile_id']},
        files={'file': ('synthetic-cross-family.pdf', content, 'application/pdf')})
    assert r.status_code == 409


def test_fully_unreadable_family_remains_in_quarantine_without_becoming_a_negative(client):
    reports, families, truths = prepared(client)
    login(client)
    unreadable = upload(client, content=pdf('SYNTHETIC UNREADABLE CASE'),
        profile_id=reports[0]['revision']['profile_id']).json()
    quarantine_family = family(client, [unreadable])['family_id']
    login(client, 'reviewer')
    payload = truth_input(unreadable)
    payload['annotations'][0].update(read_state='unreadable', truth='unknown', error_id=None,
        observed_text=None, allowed_corrections=[])
    label = save_truth(client, unreadable, payload)
    request = dataset_input(families, [*truths, label])
    request['family_splits'].append({'family_id': quarantine_family, 'split': 'train'})
    r = client.post(T+'/datasets', json=request)
    assert r.status_code == 201, r.text
    manifest = r.json()['manifest']
    assert manifest['counts'] == {'train': 1, 'validation': 1, 'holdout': 1, 'quarantined': 1}
    assert manifest['quarantined'][0]['reason'] == 'reading_unreadable'
    assert manifest['quarantined'][0]['family_id'] == quarantine_family


def test_distinct_error_locations_in_one_narrative_field_are_preserved(client):
    profile = create_profile(client)
    report = upload(client, profile_id=profile['config_id']).json()
    login(client, 'reviewer')
    payload = truth_input(report)
    first = {**payload['annotations'][0], 'bbox': [0, 0, .4, .2]}
    second = {**payload['annotations'][0], 'bbox': [.5, 0, 1, .2], 'error_id': str(uuid4()),
              'observed_text': 'SYNTHETIC SECOND ERROR'}
    r = client.post(P+'/revisions/'+report['current_revision_id']+'/training-truth',
        json={**payload, 'annotations': [first, second]})
    assert r.status_code == 201, r.text
    assert len(r.json()['annotations']) == 2
    duplicate = {**payload, 'request_id': str(uuid4()),
                 'annotations': [first, {**second, 'bbox': first['bbox']}]}
    assert client.post(P+'/revisions/'+report['current_revision_id']+'/training-truth',
        json=duplicate).status_code == 422


def test_current_rules_can_review_a_historical_form_without_changing_its_applicability(client):
    definition = {'label': 'Synthetic historical form', 'form_key': 'synthetic-v1',
        'valid_from': '2020-01-01', 'valid_to': '2021-12-31',
        'fields': [{'field_id': 'a', 'label': 'Synthetic value', 'value_type': 'text',
                    'page': 1, 'bbox': [0, 0, 1, .2], 'extraction': 'region'}]}
    r = client.post(P+'/profiles', json={'request_id': str(uuid4()), 'definition': definition})
    assert r.status_code == 201, r.text
    report = upload(client, profile_id=r.json()['config_id']).json()
    r = client.post(P+'/rule-sets', json={'request_id': str(uuid4()), 'definition': {
        'label': 'Synthetic current rules', 'form_key': 'synthetic-v1', 'valid_from': '2026-01-01', 'rules': []}})
    assert r.status_code == 201, r.text
    login(client, 'reviewer')
    payload = truth_input(report, task='content_review', basis='current', form_as_of='2020-06-01',
        as_of='2026-11-22', rule_set_id=r.json()['config_id'])
    r = client.post(P+'/revisions/'+report['current_revision_id']+'/training-truth', json=payload)
    assert r.status_code == 201, r.text
    assert r.json()['form_as_of'] == '2020-06-01'
    assert r.json()['as_of'] == '2026-11-22'


def test_missing_or_changed_primary_manual_blocks_new_teacher_records(client):
    from app.emergency_audit_models import AuditConfiguration, AuditSource
    from app import emergency_vault as vault
    from hashlib import sha256
    source_id = str(uuid4())
    manual = pdf('SYNTHETIC PRIVATE MANUAL')
    with SessionLocal() as db:
        owner = db.scalar(select(User).where(User.username == 'audit-owner'))
        db.add(AuditSource(source_id=source_id, request_id=str(uuid4()), source_sha256=sha256(manual).hexdigest(),
            media_type='application/pdf', size_bytes=len(manual), page_count=1, created_by=owner.user_id))
        db.commit()
    vault.store_original('source', source_id, manual)
    base_profile = create_profile(client)
    from app.emergency_audit_config_service import _definition
    with SessionLocal() as db:
        definition = _definition(db.get(AuditConfiguration, base_profile['config_id'])).model_dump(mode='json')
    r = client.post(P+'/profiles', json={'request_id': str(uuid4()), 'definition': definition, 'source_id': source_id})
    assert r.status_code == 201, r.text
    profile = r.json()
    report = upload(client, profile_id=profile['config_id']).json()
    login(client, 'reviewer')
    teacher = save_truth(client, report)
    assert teacher['source']['profile'].get('source_sha256') == sha256(manual).hexdigest()
    vault._path('source', source_id).write_bytes(vault.seal('source', source_id, b'SYNTHETIC ALTERED MANUAL'))
    payload = truth_input(report, supersedes_id=teacher['truth_id'])
    assert client.post(P+'/revisions/'+report['current_revision_id']+'/training-truth', json=payload).status_code == 503


def test_secondary_rule_evidence_is_bound_and_reverified_when_freezing(client):
    reports, families, _ = prepared(client)
    from app import emergency_vault as vault
    sources = []
    for text in ['SYNTHETIC PRIMARY RULE MANUAL', 'SYNTHETIC SECONDARY RULE MANUAL']:
        r = client.post(P+'/sources', data={'request_id': str(uuid4())},
            files={'file': ('synthetic-policy.pdf', pdf(text), 'application/pdf')})
        assert r.status_code == 201, r.text
        sources.append(r.json())
    r = client.post(P+'/rule-sets', json={'request_id': str(uuid4()), 'source_id': sources[0]['source_id'],
        'definition': {'label': 'Synthetic secondary-source rules', 'form_key': 'synthetic-v1',
            'valid_from': '2026-01-01', 'rules': [{'rule_id': 'synthetic-rule', 'label': 'Synthetic rule',
                'message': 'Synthetic review', 'severity': 'review',
                'source': {'document_title': 'Synthetic secondary manual', 'version': '1', 'page': '1',
                           'sha256': sources[1]['sha256']},
                'assertion': {'kind': 'field', 'field': 'a', 'operator': 'eq', 'value': 'SYNTHETIC'}}]}})
    assert r.status_code == 201, r.text
    truths = [save_truth(client, report, truth_input(report, task='content_review',
        basis='contemporaneous', rule_set_id=r.json()['config_id'])) for report in reports]
    result = client.post(T+'/datasets', json=dataset_input(families, truths, task='content_review'))
    assert result.status_code == 201, result.text
    assert truths[0]['source']['rules']['evidence_sha256'] == {s['source_id']: s['sha256'] for s in sources}
    identity = sources[1]['source_id']
    vault._path('source', identity).write_bytes(vault.seal('source', identity, b'SYNTHETIC DAMAGED SECONDARY'))
    assert client.post(T+'/datasets', json=dataset_input(families, truths, task='content_review')).status_code == 503


def test_unselected_legacy_revision_collision_cannot_hide_from_a_new_manifest(client):
    reports, families, truths = prepared(client)
    from hashlib import sha256
    from app import emergency_vault as vault
    from app.emergency_audit_models import AuditReport, AuditRevision
    content = vault.read_original('revision', reports[1]['current_revision_id'])
    # Reproduce a historical collision from before the enrolled-upload guard.
    # Only this test's synthetic rows are constructed; the production guard remains enabled.
    identity = str(uuid4())
    with SessionLocal() as db:
        parent = db.get(AuditReport, reports[0]['report_id'])
        legacy = AuditRevision(revision_id=identity, report_id=parent.report_id, number=2,
            request_id=str(uuid4()), request_sha256='a'*64, source_sha256=sha256(content).hexdigest(),
            media_type='application/pdf', size_bytes=len(content), page_count=1,
            profile_id=reports[0]['revision']['profile_id'], version=1, created_by=parent.owner_id)
        db.add(legacy); parent.current_revision_id = identity; parent.revision_number = 2; parent.version += 1
        vault.store_original('revision', identity, content)
        db.commit()
    login(client)
    response = client.post(P+'/reports/'+reports[1]['report_id']+'/revisions',
        data={'request_id': str(uuid4()), 'expected_version': reports[1]['version'],
              'profile_id': reports[1]['revision']['profile_id']},
        files={'file': ('synthetic-new-source.pdf', pdf('SYNTHETIC NEW DISTINCT B'), 'application/pdf')})
    assert response.status_code == 201, response.text
    login(client, 'reviewer')
    fresh = save_truth(client, response.json())
    assert client.post(T+'/datasets', json=dataset_input(families, [truths[0], fresh, truths[2]])).status_code == 409


def test_shared_evidence_is_verified_once_and_not_repeated_per_annotation(client, monkeypatch):
    from app import emergency_vault as vault
    from app.emergency_audit_models import AuditConfiguration
    from app.emergency_audit_config_service import _definition
    from collections import Counter
    r = client.post(P+'/sources', data={'request_id': str(uuid4())},
        files={'file': ('synthetic-manual.pdf', pdf('SYNTHETIC SHARED MANUAL'), 'application/pdf')})
    assert r.status_code == 201, r.text
    source_id = r.json()['source_id']
    base = create_profile(client)
    with SessionLocal() as db:
        definition = _definition(db.get(AuditConfiguration, base['config_id'])).model_dump(mode='json')
    r = client.post(P+'/profiles', json={'request_id': str(uuid4()), 'definition': definition, 'source_id': source_id})
    assert r.status_code == 201, r.text
    profile_id = r.json()['config_id']
    reports = [upload(client, content=pdf('SYNTHETIC DISTINCT '+str(i)), profile_id=profile_id).json()
               for i in range(3)]
    families = [family(client, [report])['family_id'] for report in reports]
    login(client, 'reviewer')
    truths = []
    for report in reports:
        payload = truth_input(report)
        template = payload['annotations'][0]
        payload['annotations'] = [{**template, 'error_id': str(uuid4()),
            'bbox': [i/20, 0, (i+1)/20, .2]} for i in range(20)]
        truths.append(save_truth(client, report, payload))
    reads = Counter()
    original_read = vault.read_original
    def read(kind, identity):
        reads[(kind, identity)] += 1
        return original_read(kind, identity)
    monkeypatch.setattr(vault, 'read_original', read)
    # Same behavior as the production envelope ceiling, at a small test budget.
    monkeypatch.setattr(vault, 'MAX_ENVELOPE', 45_000)
    r = client.post(T+'/datasets', json=dataset_input(families, truths))
    assert r.status_code == 201, r.text
    manifest = r.json()['manifest']
    assert manifest['counts'] == {'train': 20, 'validation': 20, 'holdout': 20, 'quarantined': 0}
    assert reads[('source', source_id)] == 1
    assert len(manifest['configurations']) == 1
