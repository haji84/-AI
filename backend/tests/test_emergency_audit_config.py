"""Synthetic evidence only: immutable configurations and independent approval."""
import copy
import json
import os
from hashlib import sha256
from uuid import uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.db import Base
from app.models import AuditLog, Employee, Permission, Role, RolePermission, User, UserRole
from app.emergency_audit_models import AuditConfiguration, AuditReport, AuditRevision, AuditRun, AuditSource
from app.emergency_audit_schemas import ApproveConfiguration, ImpactInput, SaveConfiguration, VersionInput
from app import emergency_audit_config_service as service
from app import emergency_vault as vault
from app.settings import settings


DETAIL = {'emergency.case.read', 'emergency.patient.read', 'emergency.report.read'}
SOURCE_BYTES = b'SYNTHETIC POLICY SOURCE ONLY'
SOURCE_HASH = sha256(SOURCE_BYTES).hexdigest()


@pytest.fixture
def context(tmp_path, monkeypatch):
    key = tmp_path / 'external-key'
    key.write_bytes(os.urandom(32)); key.chmod(0o600)
    monkeypatch.setattr(settings, 'emergency_audit_key_file', str(key))
    monkeypatch.setattr(settings, 'storage_root', str(tmp_path / 'storage'))
    monkeypatch.setattr(settings, 'tenant_id', None)
    monkeypatch.setattr(settings, 'emergency_audit_enabled', True)
    monkeypatch.setattr(settings, 'emergency_audit_internal_enabled', False)
    engine = create_engine('sqlite+pysqlite:///:memory:')
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        permissions = {code: Permission(code=code) for code in DETAIL | {
            'emergency.audit.configure', 'emergency.audit.approve', 'emergency.audit.read_all'}}
        db.add_all(permissions.values()); db.flush()
        users = {}
        for name, rights in {
            'author': DETAIL | {'emergency.audit.configure', 'emergency.audit.approve'},
            'reviewer': DETAIL | {'emergency.audit.configure', 'emergency.audit.approve', 'emergency.audit.read_all'},
            'outsider': DETAIL | {'emergency.audit.configure', 'emergency.audit.approve'},
            'denied': DETAIL,
        }.items():
            employee = Employee(display_name='Synthetic ' + name)
            role = Role(code='config-' + name, name='Synthetic config ' + name)
            db.add_all([employee, role]); db.flush()
            user = User(username='config-' + name, password_hash='unused-synthetic', employee_id=employee.employee_id)
            db.add(user); db.flush()
            db.add(UserRole(user_id=user.user_id, role_id=role.role_id))
            db.add_all(RolePermission(role_id=role.role_id, permission_id=permissions[code].permission_id) for code in rights)
            users[name] = user
        db.commit()
        yield db, users, tmp_path
    engine.dispose()


def profile_definition(**changes):
    value = {'label': 'Synthetic profile', 'form_key': 'synthetic', 'valid_from': '2026-01-01',
             'fields': [{'field_id': 'amount', 'label': 'Synthetic amount', 'value_type': 'number',
                         'page': 1, 'bbox': [0.0, 0.0, 0.8, 0.8], 'extraction': 'region'}]}
    value.update(changes)
    return value


def rules_definition(**changes):
    value = {'label': 'Synthetic rules', 'form_key': 'synthetic', 'valid_from': '2026-01-01',
        'rules': [{'rule_id': 'synthetic-only', 'label': 'Synthetic comparison',
                   'message': 'Synthetic review required', 'severity': 'review',
                   'source': {'document_title': 'Synthetic source', 'version': '1', 'page': '1', 'sha256': SOURCE_HASH},
                   'assertion': {'kind': 'field', 'field': 'amount', 'operator': 'ge', 'value': 10}}]}
    value.update(changes)
    return value


def source(context, *, data=SOURCE_BYTES, request_id=None, user='author'):
    db, users, _ = context
    return service.create_source(db, users[user], data, {'media_type': 'application/pdf', 'page_count': 1}, request_id or uuid4())


def config(context, *, kind='rules', definition=None, evidence=True, supersedes=None, request_id=None, user='author'):
    db, users, _ = context
    source_id = source(context)[0].source_id if evidence else None
    definition = definition or (rules_definition() if kind == 'rules' else profile_definition())
    request = SaveConfiguration(request_id=request_id or uuid4(), definition=definition,
                                source_id=source_id, supersedes_id=supersedes)
    row, created = service.create_config(db, users[user], kind, request)
    return row, request


def report(context, *, fields=None, reading=None, owner='author', profile_row=None, processing='ready'):
    db, users, _ = context
    if profile_row is None:
        profile_row, _ = config(context, kind='profile')
    parent = AuditReport(report_id=str(uuid4()), request_id=str(uuid4()), request_sha256='a' * 64,
        owner_id=users[owner].user_id, owner_employee_id=users[owner].employee_id,
        dataset_kind='synthetic', version=1, revision_number=1)
    db.add(parent); db.flush()
    identity = str(uuid4()); data = b'SYNTHETIC REPORT ORIGINAL'
    reading = reading or {'schema_version': 1, 'page_count': 1, 'pages': [{
        'page': 1, 'width': 600, 'height': 800, 'status': 'TEXT_EXTRACTED', 'method': 'pdf_text',
        'issues': [], 'words': [{'text': '12', 'bbox': [0.1, 0.1, 0.2, 0.2], 'confidence': None}]}]}
    if fields is None:
        fields = {'amount': {'state': 'confirmed', 'value': 12, 'value_type': 'number', 'unit': None}}
    revision = AuditRevision(revision_id=identity, report_id=parent.report_id, number=1,
        request_id=str(uuid4()), request_sha256='b' * 64, source_sha256=sha256(data).hexdigest(),
        media_type='application/pdf', size_bytes=len(data), page_count=1, profile_id=profile_row.config_id,
        version=1, processing_status=processing, created_by=users[owner].user_id,
        reading_cipher=vault.seal_json('reading', identity, reading),
        fields_cipher=vault.seal_json('fields', identity, fields))
    db.add(revision); parent.current_revision_id = identity
    vault.store_original('revision', identity, data)
    db.commit()
    return parent, revision


def impact(context, row, parent, user='author'):
    return service.impact_config(context[0], context[1][user], row.config_id,
                                 ImpactInput(report_ids=[parent.report_id]))


def approve(context, row, user='reviewer', version=None):
    return service.approve_config(context[0], context[1][user], row.config_id,
        ApproveConfiguration(expected_version=version or row.version, source_verified=True, mapping_verified=True))


def rejected(code, function, *args, **kwargs):
    with pytest.raises(HTTPException) as error:
        function(*args, **kwargs)
    assert error.value.status_code == code


def test_source_original_is_encrypted_and_idempotent_without_names(context):
    db, _, root = context
    identity = uuid4()
    first, created = source(context, request_id=identity)
    again, duplicate = source(context, request_id=identity)
    assert created and not duplicate and first.source_id == again.source_id
    assert vault.read_original('source', first.source_id) == SOURCE_BYTES
    assert SOURCE_BYTES not in next((root / 'storage').rglob('*.bin')).read_bytes()
    rejected(409, source, context, request_id=identity, data=b'SYNTHETIC DIFFERENT')
    rejected(409, source, context, request_id=identity, user='reviewer')
    assert len(db.scalars(select(AuditSource)).all()) == 1


def test_new_definition_is_encrypted_draft_and_request_retries_are_exact(context):
    db, users, _ = context
    row, request = config(context)
    assert row.status == 'draft' and row.version == 1
    assert b'Synthetic comparison' not in row.definition_cipher
    assert service.create_config(db, users['author'], 'rules', request) == (row, False)
    changed = request.model_copy(update={'definition': rules_definition(label='Other synthetic')})
    rejected(409, service.create_config, db, users['author'], 'rules', changed)
    output = service.config_output(db, row)
    assert output['definition']['rules'][0]['source']['sha256'] == SOURCE_HASH
    assert output['approval_version'] is None and output['impact'] is None


def test_new_revision_does_not_mutate_parent_and_only_one_successor(context):
    db, users, _ = context
    parent, _ = config(context)
    successor, _ = config(context, supersedes=parent.config_id, definition=rules_definition(label='New synthetic'))
    assert successor.supersedes_id == parent.config_id and successor.status == 'draft'
    assert service.config_output(db, parent)['definition']['label'] == 'Synthetic rules'
    rejected(409, config, context, supersedes=parent.config_id)
    other, _ = config(context, kind='profile')
    rejected(422, config, context, supersedes=other.config_id)
    rejected(422, config, context, supersedes=successor.config_id, definition=rules_definition(form_key='another'))


def test_config_write_rights_and_linked_active_employee_are_rechecked(context):
    db, users, _ = context
    rejected(403, config, context, user='denied')
    users['author'].employee_id = None; db.commit()
    rejected(403, config, context)


def test_rule_impact_uses_confirmed_values_counts_only_and_fixes_input_versions(context):
    row, _ = config(context); parent, revision = report(context)
    updated = impact(context, row, parent)
    result = updated.impact
    assert updated.version == 2 and result['can_approve'] is True
    assert result['tested_opportunities'] == 1 and result['incomplete_count'] == 0
    assert result['evaluated_as_of'] == '2026-01-01'
    fixed = result['reports'][0]
    assert fixed['report_version'] == parent.version and fixed['revision_version'] == revision.version
    assert fixed['source_sha256'] == revision.source_sha256
    assert fixed['candidate_counts']['NO_ISSUE_DETECTED'] == 1
    assert 'value' not in json.dumps(result) and result['truth_verified'] is False
    assert parent.version == 1 and revision.version == 1


@pytest.mark.parametrize('field_state', ['unconfirmed', 'unreadable', 'unmapped', 'not_printed'])
def test_unknown_rule_inputs_never_become_approvable(context, field_state):
    row, _ = config(context)
    parent, _ = report(context, fields={'amount': {'state': field_state, 'value': 12, 'candidate': 12, 'value_type': 'number'}})
    updated = impact(context, row, parent)
    assert updated.impact['can_approve'] is False
    assert updated.impact['tested_opportunities'] == 0
    assert updated.impact['incomplete_count'] == 1
    rejected(409, approve, context, updated)


def test_empty_rule_set_and_all_not_applicable_have_no_tested_opportunities(context):
    parent, _ = report(context)
    empty, _ = config(context, definition=rules_definition(rules=[]))
    assert impact(context, empty, parent).impact['can_approve'] is False
    definition = rules_definition()
    definition['rules'][0]['applies_when'] = {'kind': 'field', 'field': 'amount', 'operator': 'eq', 'value': 99}
    row, _ = config(context, definition=definition)
    result = impact(context, row, parent).impact
    assert result['tested_opportunities'] == 0 and result['can_approve'] is False


def test_profile_impact_accepts_unconfirmed_candidates_but_not_missing_regions(context):
    parent, revision = report(context)
    row, _ = config(context, kind='profile')
    result = impact(context, row, parent).impact
    assert result['can_approve'] is True and result['tested_opportunities'] == 1
    assert result['reports'][0]['candidate_counts']['unconfirmed'] == 1
    assert vault.open_json('fields', revision.revision_id, revision.fields_cipher)['amount']['state'] == 'confirmed'
    bad_definition = profile_definition()
    bad_definition['fields'][0]['page'] = 2
    bad, _ = config(context, kind='profile', definition=bad_definition)
    result = impact(context, bad, parent).impact
    assert result['can_approve'] is False and result['incomplete_count'] == 1


def test_profile_empty_or_boundary_ambiguous_region_blocks_approval(context):
    parent, _ = report(context)
    for bounds in ([0.6, 0.6, 0.8, 0.8], [0.15, 0.1, 0.3, 0.3]):
        definition = profile_definition(); definition['fields'][0]['bbox'] = bounds
        row, _ = config(context, kind='profile', definition=definition)
        assert impact(context, row, parent).impact['can_approve'] is False


def test_impact_rejects_duplicates_and_inaccessible_reports(context):
    db, users, _ = context
    row, _ = config(context); parent, _ = report(context)
    rejected(422, service.impact_config, db, users['author'], row.config_id,
             ImpactInput(report_ids=[parent.report_id, parent.report_id]))
    rejected(404, impact, context, row, parent, user='outsider')


def test_pending_report_is_reported_incomplete_not_silently_omitted(context):
    row, _ = config(context); parent, _ = report(context, processing='queued')
    result = impact(context, row, parent).impact
    assert result['report_count'] == 1 and result['incomplete_count'] == 1
    assert result['can_approve'] is False and result['tested_opportunities'] == 0


def test_form_mismatch_is_incomplete_even_when_values_exist(context):
    row, _ = config(context, definition=rules_definition(form_key='wrong-form'))
    parent, _ = report(context)
    result = impact(context, row, parent).impact
    assert result['can_approve'] is False and result['incomplete_count'] == 1


def test_explicit_temporal_field_type_is_used_without_guessing(context):
    definition = rules_definition()
    definition['rules'][0]['assertion'] = {'kind': 'field', 'field': 'when', 'operator': 'ge',
                                        'value': {'type': 'date', 'value': '2026-01-01'}}
    row, _ = config(context, definition=definition)
    form = profile_definition()
    form['fields'][0].update(field_id='when', value_type='date')
    form_row, _ = config(context, kind='profile', definition=form)
    parent, _ = report(context, profile_row=form_row, fields={
        'when': {'state': 'confirmed', 'value': '2026-02-01', 'value_type': 'date', 'unit': None}})
    assert impact(context, row, parent).impact['tested_opportunities'] == 1


def test_source_and_impact_required_for_independent_approval(context):
    no_source, _ = config(context, evidence=False); parent, _ = report(context)
    impact(context, no_source, parent)
    rejected(409, approve, context, no_source)
    row, _ = config(context)
    rejected(409, approve, context, row)
    row = impact(context, row, parent)
    rejected(403, approve, context, row, user='author')
    approved = approve(context, row)
    assert approved.status == 'approved' and approved.version == 3
    assert approved.approved_by == context[1]['reviewer'].user_id
    assert service.config_output(context[0], approved)['approval_version'] == 3


@pytest.mark.parametrize('rule_hash', [None, 'f' * 64])
def test_every_rule_requires_matching_retained_source_hash(context, rule_hash):
    definition = rules_definition(); definition['rules'][0]['source']['sha256'] = rule_hash
    row, _ = config(context, definition=definition); parent, _ = report(context)
    impact(context, row, parent)
    rejected(409, approve, context, row)


def test_retained_source_tampering_cannot_approve(context):
    row, _ = config(context); parent, _ = report(context); impact(context, row, parent)
    source_row = context[0].get(AuditSource, row.source_id)
    source_row.source_sha256 = 'f' * 64; context[0].commit()
    with pytest.raises(vault.VaultError):
        approve(context, row)


def _two_source_definition(context):
    second, _ = source(context, data=b'SYNTHETIC SECOND PRIVATE POLICY')
    definition = rules_definition()
    additional = copy.deepcopy(definition['rules'][0])
    additional['rule_id'] = 'synthetic-second-source'
    additional['source'].update(document_title='Synthetic second policy', sha256=second.source_sha256)
    additional['assertion'] = {'kind': 'field', 'field': 'amount', 'operator': 'le', 'value': 20}
    definition['rules'].append(additional)
    return definition, second


def test_one_ruleset_can_approve_distinct_retained_private_sources(context):
    definition, second = _two_source_definition(context)
    row, _ = config(context, definition=definition)
    parent, _ = report(context)
    impact(context, row, parent)
    assert row.impact['tested_opportunities'] == 2 and row.impact['can_approve'] is True
    approved = approve(context, row)
    assert approved.status == 'approved'
    assert approved.impact['approved_source_hashes'] == sorted([SOURCE_HASH, second.source_sha256])
    retained = service.config_output(context[0], approved)['definition']['rules']
    assert {item['source']['sha256'] for item in retained} == {SOURCE_HASH, second.source_sha256}


def test_every_distinct_rule_source_is_verified_not_only_the_primary(context):
    definition, second = _two_source_definition(context)
    row, _ = config(context, definition=definition)
    parent, _ = report(context)
    impact(context, row, parent)
    path = context[2] / 'storage' / 'emergency-audit' / 'source' / (second.source_id + '.bin')
    damaged = bytearray(path.read_bytes()); damaged[-1] ^= 1; path.write_bytes(damaged)
    with pytest.raises(vault.VaultError):
        approve(context, row)
    context[0].refresh(row)
    assert row.status == 'draft' and row.version == 2


def test_old_author_employee_cannot_approve_after_account_reassignment(context):
    db, users, _ = context
    row, _ = config(context); parent, _ = report(context); impact(context, row, parent)
    original_employee = users['author'].employee_id
    users['author'].employee_id = None; db.commit()
    users['reviewer'].employee_id = original_employee; db.commit()
    rejected(403, approve, context, row)


@pytest.mark.parametrize('change', ['report_version', 'revision_version', 'fields_without_version', 'reading_without_version', 'source_hash'])
def test_stale_impact_cannot_approve(context, change):
    db, _, _ = context
    row, _ = config(context); parent, revision = report(context); impact(context, row, parent)
    if change == 'report_version': parent.version += 1
    elif change == 'revision_version': revision.version += 1
    elif change == 'fields_without_version': revision.fields_cipher = vault.seal_json('fields', revision.revision_id, {})
    elif change == 'reading_without_version': revision.reading_cipher = vault.seal_json('reading', revision.revision_id, {})
    else: revision.source_sha256 = 'f' * 64
    db.commit()
    rejected(409, approve, context, row)


def test_approver_must_still_have_access_to_each_impact_report(context):
    row, _ = config(context); parent, _ = report(context); impact(context, row, parent)
    rejected(404, approve, context, row, user='outsider')


def test_compare_and_swap_blocks_stale_approval_and_impact_cannot_edit_approved(context):
    row, _ = config(context); parent, _ = report(context); impact(context, row, parent)
    rejected(409, approve, context, row, version=1)
    approved = approve(context, row)
    rejected(409, impact, context, approved, parent)
    rejected(409, approve, context, approved)


def test_overlap_requires_explicit_retirement_and_keeps_approval_history(context):
    db, users, _ = context
    parent, _ = report(context)
    first, _ = config(context); impact(context, first, parent); approve(context, first)
    successor, _ = config(context, supersedes=first.config_id)
    impact(context, successor, parent)
    rejected(409, approve, context, successor)
    rejected(409, service.retire_config, db, users['reviewer'], first.config_id, VersionInput(expected_version=1))
    retired = service.retire_config(db, users['reviewer'], first.config_id, VersionInput(expected_version=first.version))
    assert retired.status == 'retired' and retired.version == 4
    assert service.config_output(db, retired)['approval_version'] == 3
    assert approve(context, successor).status == 'approved'


def test_nonoverlapping_effective_periods_can_both_be_approved(context):
    parent, _ = report(context)
    first, _ = config(context, definition=rules_definition(valid_to='2026-01-31'))
    impact(context, first, parent); approve(context, first)
    second, _ = config(context, definition=rules_definition(valid_from='2026-02-01'))
    impact(context, second, parent)
    assert approve(context, second).status == 'approved' and first.status == 'approved'


def test_change_counts_do_not_claim_actual_error_truth(context):
    db, users, _ = context
    row, _ = config(context); parent, revision = report(context)
    identity = str(uuid4())
    run = AuditRun(run_id=identity, report_id=parent.report_id, revision_id=revision.revision_id,
        revision_version=revision.version, report_version=parent.version, mode='candidate', created_by=users['author'].user_id,
        payload_cipher=vault.seal_json('run', identity, {'findings': [
            {'rule_id': 'synthetic-only', 'status': 'REVIEW_REQUIRED'}], 'as_of': '2026-01-01'}))
    db.add(run); db.commit()
    result = impact(context, row, parent).impact
    assert result['changed_count'] == 1 and result['truth_verified'] is False
    logs = list(db.scalars(select(AuditLog)))
    assert 'Synthetic comparison' not in json.dumps([item.after_data for item in logs])
    assert 'SYNTHETIC REPORT ORIGINAL' not in json.dumps([item.after_data for item in logs])
