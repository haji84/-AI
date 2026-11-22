"""Synthetic database evidence for private, read-only feedback pattern summaries."""
from datetime import datetime, timedelta, timezone
from importlib import import_module
import json
from uuid import UUID, uuid4

from fastapi import HTTPException
import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker


CORE = 'ER-NONTRANSPORT-URGENCY'
OTHER_CORE = 'ER-TRANSFER-URGENCY'
PRIVATE = 'SYNTHETIC_PRIVATE_PERSON_AND_QUOTED_REPORT_TEXT'
SOURCE_HASH = 'c2' * 32


@pytest.fixture
def environment(tmp_path, monkeypatch):
    from app import bootstrap  # register shared foreign-key targets
    from app import emergency_audit_models  # register this feature before create_all
    from app.db import Base, BoundSession
    from app.models import Employee, Permission, Role, RolePermission, User, UserRole
    from app.settings import settings

    monkeypatch.setattr(settings, 'emergency_audit_enabled', True)
    monkeypatch.setattr(settings, 'emergency_audit_internal_enabled', False)
    monkeypatch.setattr(settings, 'tenant_id', None)
    monkeypatch.setattr(settings, 'production_mode', False)
    monkeypatch.setattr(settings, 'storage_root', str(tmp_path / 'private-storage'))
    key = tmp_path / 'private.key'; key.write_bytes(b'p' * 32); key.chmod(0o600)
    monkeypatch.setattr(settings, 'emergency_audit_key_file', str(key))
    engine = create_engine('sqlite+pysqlite:///:memory:')
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, class_=BoundSession, expire_on_commit=False)
    with factory() as db:
        role = Role(code='synthetic-pattern-reader', name='Synthetic pattern reader')
        db.add(role); db.flush()
        for code in ('emergency.case.read', 'emergency.patient.read', 'emergency.report.read'):
            permission = Permission(code=code); db.add(permission); db.flush()
            db.add(RolePermission(role_id=role.role_id, permission_id=permission.permission_id))
        users = []
        for label in ('owner', 'independent', 'outside'):
            employee = Employee(display_name=PRIVATE + label); db.add(employee); db.flush()
            user = User(username='synthetic-pattern-' + label, employee_id=employee.employee_id,
                        password_hash='not-used-for-login')
            db.add(user); db.flush(); db.add(UserRole(user_id=user.user_id, role_id=role.role_id))
            users.append(user)
        db.commit()
        yield {'db': db, 'engine': engine, 'owner': users[0], 'reviewer': users[1], 'outside': users[2], 'tick': 0}
    engine.dispose()


def instant(env):
    env['tick'] += 1
    return datetime(2026, 1, 1, tzinfo=timezone.utc) + timedelta(seconds=env['tick'])


def report(env, *, owner=None):
    from app.emergency_audit_models import AuditReport, AuditRevision
    db = env['db']; actor = owner or env['owner']
    parent = AuditReport(request_id=str(uuid4()), request_sha256=SOURCE_HASH,
        owner_id=actor.user_id, owner_employee_id=actor.employee_id,
        reviewer_id=env['reviewer'].user_id, reviewer_employee_id=env['reviewer'].employee_id,
        dataset_kind='synthetic', created_at=instant(env))
    db.add(parent); db.flush()
    revision = AuditRevision(report_id=parent.report_id, number=1, request_id=str(uuid4()),
        request_sha256=SOURCE_HASH, source_sha256=SOURCE_HASH, media_type='application/pdf',
        size_bytes=20, page_count=1, created_by=actor.user_id, created_at=instant(env))
    db.add(revision); db.flush(); parent.current_revision_id = revision.revision_id
    db.commit()
    return parent, revision


def run(env, parent, revision, rules, *, mode='candidate', configuration=None):
    from app.emergency_audit_models import AuditRun
    from app.emergency_vault import seal_json
    identity = str(uuid4())
    body = {'source_sha256': SOURCE_HASH, 'input_fields': {'name': {'value': PRIVATE}}, 'findings': [
        {'rule_id': rule, 'status': status, 'message': PRIVATE, 'source_reference': PRIVATE,
         'evidence': {'quote': PRIVATE}} for rule, status in rules]}
    row = AuditRun(run_id=identity, report_id=parent.report_id, revision_id=revision.revision_id,
        revision_version=revision.version, report_version=parent.version, rule_set_id=configuration,
        mode=mode, payload_cipher=seal_json('run', identity, body), created_by=env['owner'].user_id,
        created_at=instant(env))
    env['db'].add(row); env['db'].commit(); return row


def record(env, parent, kind, payload, *, supersedes=None):
    from app.emergency_audit_models import AuditEvent
    row = AuditEvent(event_id=str(uuid4()), report_id=parent.report_id, kind=kind,
        supersedes_id=supersedes.event_id if supersedes else None, request_sha256=SOURCE_HASH,
        payload=payload, actor_id=env['reviewer'].user_id, actor_employee_id=env['reviewer'].employee_id,
        created_at=instant(env))
    env['db'].add(row); env['db'].commit(); return row


def truth(env, parent, checked, items, *, complete=True, supersedes=None, missed=None):
    return record(env, parent, 'truth_review', {'run_id': checked.run_id, 'complete': complete,
        'whole_report_checked': complete, 'items': items, 'missed_errors': missed or []}, supersedes=supersedes)


def known(rule, truth='correct', error=None, **extra):
    return {'rule_id': rule, 'truth': truth, 'error_id': str(error) if error else None,
            'verified_read_state': 'confirmed', 'detected_in_run_ids': [], **extra}


def decisions(env, parent, checked, items, *, supersedes=None):
    return record(env, parent, 'dispositions', {'run_id': checked.run_id, 'decisions': items}, supersedes=supersedes)


def summary(env, parents, *, user=None):
    return import_module('app.emergency_audit_learning').summarize_patterns(
        env['db'], user or env['owner'], [UUID(row.report_id) for row in parents])


def item(result, rule, config=None):
    return next(value for value in result['items'] if value['rule_id'] == rule and value['rule_set_id'] == config)


def test_empty_history_is_explicit_and_duplicate_report_selection_does_not_inflate(environment):
    env = environment; parent, _ = report(env)
    assert summary(env, [parent, parent]) == {'report_count': 1, 'run_count': 0,
        'unreviewed_run_count': 0, 'verified_error_count': 0, 'items': [],
        'group_totals_additive': False, 'automatic_rule_updates': False, 'model_training_performed': False}


def test_all_revisions_and_later_unreviewed_runs_are_counted(environment):
    from app.emergency_audit_models import AuditRevision
    env = environment; parent, revision = report(env)
    first = run(env, parent, revision, [(CORE, 'REVIEW_REQUIRED')])
    actual_error = uuid4()
    truth(env, parent, first, [known(CORE, 'error', actual_error)])
    decisions(env, parent, first, [{'rule_id': CORE, 'decision': 'correction_needed', 'reason_code': 'code_selection'}])
    later_revision = AuditRevision(report_id=parent.report_id, number=2, request_id=str(uuid4()),
        request_sha256=SOURCE_HASH, source_sha256=SOURCE_HASH, media_type='application/pdf',
        size_bytes=20, page_count=1, created_by=env['owner'].user_id)
    env['db'].add(later_revision); env['db'].flush(); parent.current_revision_id = later_revision.revision_id
    env['db'].commit()
    later = run(env, parent, later_revision, [(CORE, 'REVIEW_REQUIRED')])
    result = summary(env, [parent]); group = item(result, CORE)
    assert (result['report_count'], result['run_count'], result['unreviewed_run_count']) == (1, 2, 1)
    assert group['warning_count'] == 2 and group['report_count'] == 1
    assert group['decision_counts'] == {'correction_needed': 1, 'false_alarm': 0, 'exception': 0, 'unresolved': 1}
    assert group['reason_counts']['code_selection'] == 1 and group['reason_counts']['unknown'] == 1
    assert group['verified_error_count'] == 1 and group['unresolved_truth_count'] == 1
    assert later.run_id not in json.dumps(result)


def test_dispositions_never_become_error_truth_and_partial_updates_preserve_other_decisions(environment):
    env = environment; parent, revision = report(env)
    checked = run(env, parent, revision, [(CORE, 'REVIEW_REQUIRED'), (OTHER_CORE, 'REVIEW_REQUIRED')])
    decisions(env, parent, checked, [
        {'rule_id': CORE, 'decision': 'correction_needed', 'reason_code': 'missing'},
        {'rule_id': OTHER_CORE, 'decision': 'exception', 'reason_code': 'local_rule'}])
    decisions(env, parent, checked, [{'rule_id': CORE, 'decision': 'false_alarm', 'reason_code': 'reading_error'}])
    result = summary(env, [parent])
    assert result['verified_error_count'] == 0 and result['unreviewed_run_count'] == 1
    first = item(result, CORE); second = item(result, OTHER_CORE)
    assert first['decision_counts']['false_alarm'] == 1 and first['decision_counts']['correction_needed'] == 0
    assert first['reason_counts']['reading_error'] == 1 and first['reason_counts']['missing'] == 0
    assert second['decision_counts']['exception'] == 1 and second['reason_counts']['local_rule'] == 1
    assert first['verified_error_count'] == second['verified_error_count'] == 0
    assert first['unresolved_truth_count'] == second['unresolved_truth_count'] == 1


def test_error_identity_is_deduplicated_across_repeated_rule_and_ai_findings(environment):
    env = environment; parent, revision = report(env); error = uuid4()
    first = run(env, parent, revision, [(CORE, 'REVIEW_REQUIRED')])
    second = run(env, parent, revision, [(CORE, 'REVIEW_REQUIRED')])
    ai_rules = ['AI-AI-' + 'a' * 16, 'AI-AI-' + 'b' * 16]
    assisted = run(env, parent, revision, [(key, 'REVIEW_REQUIRED') for key in ai_rules], mode='ai')
    for checked in (first, second): truth(env, parent, checked, [known(CORE, 'error', error)])
    truth(env, parent, assisted, [known(key, 'error', error) for key in ai_rules])
    result = summary(env, [parent])
    assert result['verified_error_count'] == 1 and result['group_totals_additive'] is False
    assert result['unreviewed_run_count'] == 0
    assert item(result, CORE)['verified_error_count'] == item(result, 'AI-TEXT')['verified_error_count'] == 1
    assert item(result, CORE)['warning_count'] == item(result, 'AI-TEXT')['warning_count'] == 2
    assert item(result, 'AI-TEXT')['label'] == 'AIによる確認候補'
    assert not any(key in json.dumps(result) for key in ai_rules + [str(error)])


def test_superseded_truth_and_dispositions_do_not_keep_obsolete_errors_or_reasons(environment):
    env = environment; parent, revision = report(env)
    checked = run(env, parent, revision, [(CORE, 'REVIEW_REQUIRED')])
    old = truth(env, parent, checked, [known(CORE, 'error', uuid4())])
    truth(env, parent, checked, [known(CORE)], supersedes=old)
    old_decision = decisions(env, parent, checked, [{'rule_id': CORE, 'decision': 'correction_needed', 'reason_code': 'missing'}])
    decisions(env, parent, checked, [{'rule_id': CORE, 'decision': 'false_alarm'}], supersedes=old_decision)
    result = summary(env, [parent]); group = item(result, CORE)
    assert result['verified_error_count'] == group['verified_error_count'] == 0
    assert result['unreviewed_run_count'] == group['unresolved_truth_count'] == 0
    assert group['decision_counts']['false_alarm'] == group['reason_counts']['unknown'] == 1
    assert group['decision_counts']['correction_needed'] == group['reason_counts']['missing'] == 0


def test_explicit_independent_link_resolves_only_the_named_later_opportunity(environment):
    env = environment; parent, revision = report(env); error = uuid4()
    first = run(env, parent, revision, [(CORE, 'NOT_TESTED')])
    linked = run(env, parent, revision, [(CORE, 'REVIEW_REQUIRED')])
    unlinked = run(env, parent, revision, [(CORE, 'REVIEW_REQUIRED')])
    truth(env, parent, first, [known(CORE, 'error', error, detected_in_run_ids=[linked.run_id])])
    result = summary(env, [parent]); group = item(result, CORE)
    assert result['run_count'] == 3 and result['unreviewed_run_count'] == 2
    assert group['warning_count'] == 2 and group['unresolved_truth_count'] == 1
    assert result['verified_error_count'] == group['verified_error_count'] == 1
    assert unlinked.run_id not in json.dumps(result)


def test_missed_errors_are_global_truth_without_an_invented_rule_cause(environment):
    env = environment; parent, revision = report(env); error = uuid4()
    checked = run(env, parent, revision, [(CORE, 'NO_ISSUE_DETECTED')])
    truth(env, parent, checked, [known(CORE)], missed=[{'opportunity_id': str(uuid4()),
        'error_id': str(error), 'read_state': 'unmapped', 'verified_read_state': 'unmapped'}])
    result = summary(env, [parent])
    assert result['verified_error_count'] == 1
    assert item(result, CORE)['verified_error_count'] == item(result, CORE)['warning_count'] == 0


def test_affected_report_count_excludes_other_reports_where_the_rule_did_not_warn(environment):
    env = environment; warned, first_revision = report(env); clear, second_revision = report(env)
    run(env, warned, first_revision, [(CORE, 'REVIEW_REQUIRED')])
    run(env, warned, first_revision, [(CORE, 'REVIEW_REQUIRED')])
    run(env, clear, second_revision, [(CORE, 'NO_ISSUE_DETECTED')])
    result = summary(env, [warned, clear]); group = item(result, CORE)
    assert result['report_count'] == 2 and result['run_count'] == 3
    assert group['warning_count'] == 2 and group['report_count'] == 1


def add_configuration(env, label):
    from app.emergency_audit_models import AuditConfiguration
    from app.emergency_vault import seal_json
    identity = str(uuid4())
    definition = {'label': 'Synthetic conditions', 'form_key': 'synthetic', 'valid_from': '2026-01-01', 'rules': [
        {'rule_id': 'CUSTOM-1', 'label': label, 'message': PRIVATE, 'severity': 'review',
         'source': {'document_title': PRIVATE, 'version': '1', 'page': '1', 'sha256': SOURCE_HASH},
         'assertion': {'kind': 'field', 'field': 'sample', 'operator': 'not_blank'}}]}
    row = AuditConfiguration(config_id=identity, request_id=str(uuid4()), request_sha256=SOURCE_HASH,
        kind='rules', label='Synthetic conditions', form_key='synthetic', status='approved',
        definition_cipher=seal_json('config', identity, definition), created_by=env['owner'].user_id)
    env['db'].add(row); env['db'].commit(); return identity


def test_rule_versions_keep_separate_configured_labels_without_copying_private_snapshots(environment, caplog, capsys):
    from app.emergency_review_core import evaluate_confirmed_fields
    env = environment; parent, revision = report(env)
    earlier = add_configuration(env, '旧版の確認項目'); later = add_configuration(env, '改訂版の確認項目')
    run(env, parent, revision, [('CUSTOM-1', 'REVIEW_REQUIRED')], configuration=earlier)
    run(env, parent, revision, [('CUSTOM-1', 'REVIEW_REQUIRED')], configuration=later)
    run(env, parent, revision, [(CORE, 'REVIEW_REQUIRED'), (SOURCE_HASH, 'REVIEW_REQUIRED')])
    run(env, parent, revision, [('AI-VISION-' + SOURCE_HASH[:16], 'REVIEW_REQUIRED')], mode='vision')
    statements = []
    def capture(connection, cursor, statement, parameters, context, executemany):
        statements.append(statement.lstrip().split()[0].upper())
    event.listen(env['engine'], 'before_cursor_execute', capture)
    try:
        result = summary(env, [parent])
    finally:
        event.remove(env['engine'], 'before_cursor_execute', capture)
    assert set(statements) <= {'SELECT'} and statements
    assert item(result, 'CUSTOM-1', earlier)['label'] == '旧版の確認項目'
    assert item(result, 'CUSTOM-1', later)['label'] == '改訂版の確認項目'
    assert item(result, CORE)['label'] == next(value.message for value in evaluate_confirmed_fields({}) if value.rule_id == CORE)
    assert item(result, 'UNKNOWN')['label'] == '確認項目'
    assert item(result, 'AI-VISION')['label'] == 'AIによる確認候補'
    output = json.dumps(result, ensure_ascii=False) + caplog.text + capsys.readouterr().out
    assert PRIVATE not in output and SOURCE_HASH not in output
    assert env['owner'].employee_id not in output and parent.report_id not in output


def test_any_unavailable_report_rejects_whole_summary_without_partial_disclosure(environment):
    env = environment; own, revision = report(env); other, _ = report(env, owner=env['outside'])
    run(env, own, revision, [(CORE, 'REVIEW_REQUIRED')])
    with pytest.raises(HTTPException) as denied:
        summary(env, [own, other])
    assert denied.value.status_code == 404
    assert PRIVATE not in str(denied.value.detail) and other.report_id not in str(denied.value.detail)
    with pytest.raises(HTTPException) as outside:
        summary(env, [own], user=env['outside'])
    assert outside.value.status_code == 404
    assert summary(env, [own], user=env['reviewer'])['report_count'] == 1


def test_visibility_is_checked_before_attempting_to_open_any_snapshot(environment):
    env = environment; own, revision = report(env); hidden, _ = report(env, owner=env['outside'])
    checked = run(env, own, revision, [(CORE, 'REVIEW_REQUIRED')])
    checked.payload_cipher = b'invalid-synthetic-ciphertext'
    env['db'].commit()
    with pytest.raises(HTTPException) as denied:
        summary(env, [own, hidden])
    assert denied.value.status_code == 404


def test_reassigned_owner_account_does_not_keep_former_employee_reports(environment):
    from app.models import Employee
    env = environment; parent, _ = report(env)
    replacement = Employee(display_name='Synthetic replacement')
    env['db'].add(replacement); env['db'].flush()
    env['owner'].employee_id = replacement.employee_id; env['db'].commit()
    with pytest.raises(HTTPException) as denied:
        summary(env, [parent])
    assert denied.value.status_code == 404


def test_revoked_detail_permission_blocks_existing_owner(environment):
    from app.models import UserRole
    from sqlalchemy import delete
    env = environment; parent, _ = report(env)
    env['db'].execute(delete(UserRole).where(UserRole.user_id == env['owner'].user_id)); env['db'].commit()
    with pytest.raises(HTTPException) as denied:
        summary(env, [parent])
    assert denied.value.status_code == 403


@pytest.mark.parametrize('identities', [[], [uuid4() for _ in range(1001)], ['not-a-valid-id']])
def test_direct_function_rejects_unbounded_or_malformed_selection(environment, identities):
    module = import_module('app.emergency_audit_learning')
    with pytest.raises(HTTPException) as failed:
        module.summarize_patterns(environment['db'], environment['owner'], identities)
    assert failed.value.status_code == 422
