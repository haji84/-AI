"""Synthetic register evidence only; these fixtures assert no real legal classification."""
from functools import partial
from importlib.util import find_spec
from pathlib import Path

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from test_learning import learning_environment
from test_violations import sources


@pytest.fixture
def hazardous_env(learning_environment, tmp_path, monkeypatch):
    from app.models import Permission, Role, RolePermission, FeatureFlag, Inspection
    from app.routers import documents
    from app.settings import settings
    client, engine = learning_environment
    monkeypatch.setattr(settings, 'storage_root', str(tmp_path / 'storage'))
    client.app.include_router(documents.router)
    if find_spec('app.routers.hazardous'):
        from app.routers import hazardous
        from app import hazardous_models
        if engine.dialect.name == 'sqlite':
            hazardous_models.Base.metadata.create_all(engine)
        client.app.include_router(hazardous.router)
    with Session(engine) as db:
        role = db.scalar(select(Role).where(Role.code == 'system_admin'))
        for code in ('hazardous.read', 'hazardous.create', 'hazardous.update', 'hazardous.review'):
            permission = db.scalar(select(Permission).where(Permission.code == code))
            if not permission:
                permission = Permission(code=code)
                db.add(permission)
                db.flush()
            if not db.scalar(select(RolePermission).where(RolePermission.role_id == role.role_id, RolePermission.permission_id == permission.permission_id)):
                db.add(RolePermission(role_id=role.role_id, permission_id=permission.permission_id))
        if not db.scalar(select(FeatureFlag).where(FeatureFlag.key == 'module.hazardous_materials.enabled')):
            db.add(FeatureFlag(key='module.hazardous_materials.enabled', module_code='hazardous_materials', enabled=True))
        db.commit()
    refs = sources(client, partial(Session, engine), username='learning-admin')
    with Session(engine) as db:
        refs['inspection_id'] = db.scalar(select(Inspection).where(Inspection.building_id == refs['building_id'])).inspection_id
    return client, engine, refs


def install(client, refs, **changes):
    payload = {'building_id': refs['building_id'], 'name': 'Synthetic tank', 'category_label': 'Human-entered label',
               'materials': [{'name': 'Synthetic material', 'category_label': 'Recorded category', 'quantity': '1.230000', 'quantity_unit': 'L', 'capacity': '1000.000001', 'capacity_unit': 'L'}]}
    response = client.post('/hazardous/installations', json={**payload, **changes})
    assert response.status_code == 201, response.text
    return response.json()


def record(client, installation, refs, **changes):
    payload = {'expected_installation_version': installation['version'], 'kind': 'permit', 'title': 'Synthetic original permit evidence',
               'recorded_on': '2026-10-01', 'due_on': '2026-10-10', 'document_ids': [refs['proof']],
               'legal_source_version_ids': [refs['legal_source_version_id']], 'inspection_ids': [refs['inspection_id']]}
    response = client.post(f"/hazardous/installations/{installation['installation_id']}/records", json={**payload, **changes})
    assert response.status_code == 201, response.text
    return response.json()


def action(client, installation, row, verb, status=200, **changes):
    payload = {'expected_installation_version': installation['version'], 'expected_version': row['version'], 'reason': 'Synthetic Human verification'}
    if verb != 'revisions':
        payload['human_acknowledged'] = True
    response = client.post(f"/hazardous/installations/{installation['installation_id']}/records/{row['record_id']}/{verb}", json={**payload, **changes})
    assert response.status_code == status, response.text
    return response.json()


def detail(client, installation):
    response = client.get('/hazardous/installations/' + installation['installation_id'])
    assert response.status_code == 200, response.text
    return response.json()


def revoke(engine, *codes):
    from app.models import Permission, RolePermission
    with Session(engine) as db:
        for permission in db.scalars(select(Permission).where(Permission.code.in_(codes))):
            for link in db.scalars(select(RolePermission).where(RolePermission.permission_id == permission.permission_id)):
                db.delete(link)
        db.commit()


def test_exact_materials_original_confirmation_and_append_only_revision(hazardous_env):
    client, engine, refs = hazardous_env
    installation = install(client, refs)
    assert installation['materials'][0]['quantity'] == '1.230000'
    old = action(client, installation, record(client, installation, refs), 'confirm')
    assert old['confirmation_current'] is True and old['confirmed_by']
    assert old['source_snapshot']['documents'][0]['sha256']
    assert old['source_snapshot']['legal_sources'][0]['legal_source_version_id'] == refs['legal_source_version_id']
    revision = action(client, installation, old, 'revisions', 201)
    assert revision['supersedes_record_id'] == old['record_id'] and revision['status'] == 'draft'
    new = action(client, installation, revision, 'confirm')
    final = detail(client, installation)
    assert final['version'] == installation['version'], 'sibling evidence does not change installation facts'
    previous = next(row for row in final['evidence_records'] if row['record_id'] == old['record_id'])
    assert previous['status'] == 'superseded' and previous['confirmed_by'] == old['confirmed_by']
    assert new['confirmation_current'] is True
    assert len(final['history']) >= 5


def test_detail_reuses_one_permission_snapshot_across_guarded_history(hazardous_env, monkeypatch):
    """A detail read must not re-query unchanged authority for every nested source."""
    from app import hazardous_service

    client, _, refs = hazardous_env
    installation = install(client, refs)
    original = action(client, installation, record(client, installation, refs), 'confirm')
    revision = action(client, installation, original, 'revisions', 201)
    action(client, installation, revision, 'confirm')

    calls = 0
    permission_codes = hazardous_service.permission_codes

    def counted(db, user_id):
        nonlocal calls
        calls += 1
        return permission_codes(db, user_id)

    monkeypatch.setattr(hazardous_service, 'permission_codes', counted)
    shown = detail(client, installation)

    assert len(shown['evidence_records']) == 2
    assert shown['history']
    assert calls == 1


@pytest.mark.parametrize('quantity', ['NaN', 'Infinity', '-1', '0.0000001', '9999999999999999999', '1e3', 1.2, True])
def test_rejects_nonexact_or_overprecision_quantities(hazardous_env, quantity):
    client, _, refs = hazardous_env
    response = client.post('/hazardous/installations', json={'building_id': refs['building_id'], 'name': 'Synthetic', 'category_label': 'Human', 'materials': [{'name': 'Synthetic', 'quantity': quantity, 'quantity_unit': 'kg'}]})
    assert response.status_code == 422, response.text


@pytest.mark.parametrize('change', ['installation', 'original', 'legal_version', 'inspection'])
def test_source_changes_make_confirmation_historical(hazardous_env, change):
    from app.models import Document, LegalSourceDocumentVersion, Inspection
    from app.settings import settings
    client, engine, refs = hazardous_env
    installation = install(client, refs)
    row = action(client, installation, record(client, installation, refs), 'confirm')
    if change == 'installation':
        response = client.patch('/hazardous/installations/' + installation['installation_id'], json={'expected_version': 1, 'reason': 'Human changed quantity', 'materials': [{'name': 'Synthetic', 'quantity': '2', 'quantity_unit': 'kg'}]})
        assert response.status_code == 200, response.text
    else:
        with Session(engine) as db:
            if change == 'original':
                doc = db.get(Document, refs['proof'])
                (Path(settings.storage_root) / doc.storage_path).write_text('Changed bytes')
            elif change == 'legal_version':
                db.get(LegalSourceDocumentVersion, refs['legal_source_version_id']).source_url = 'https://synthetic.invalid/changed'
            else:
                db.get(Inspection, refs['inspection_id']).version += 1
            db.commit()
    shown = detail(client, installation)['evidence_records'][0]
    assert shown['status'] == 'confirmed' and shown['confirmation_current'] is False
    assert shown['source_snapshot'] == row['source_snapshot']


def test_requires_original_and_human_ack_and_fresh_versions(hazardous_env):
    client, _, refs = hazardous_env
    installation = install(client, refs)
    empty = record(client, installation, refs, document_ids=[])
    action(client, installation, empty, 'confirm', 409)
    row = record(client, installation, refs)
    action(client, installation, row, 'confirm', 422, human_acknowledged=False)
    action(client, installation, row, 'confirm', 409, expected_installation_version=2)
    action(client, installation, row, 'confirm', 409, expected_version=2)
    assert all(r['status'] == 'draft' for r in detail(client, installation)['evidence_records'])


def test_hidden_evidence_not_leaked_through_history_deadlines_or_pagination(hazardous_env):
    client, engine, refs = hazardous_env
    installation = install(client, refs)
    hidden = action(client, installation, record(client, installation, refs), 'confirm')
    visible = record(client, installation, refs, title='Public draft', document_ids=[], legal_source_version_ids=[], inspection_ids=[])
    revoke(engine, 'document.read')
    shown = detail(client, installation)
    text = str(shown)
    assert hidden['record_id'] not in text and refs['proof'] not in text and hidden['title'] not in text
    assert [row['record_id'] for row in shown['evidence_records']] == [visible['record_id']]
    response = client.get('/hazardous/deadlines?limit=1')
    assert response.status_code == 200 and [r['record_id'] for r in response.json()] == [visible['record_id']]
    assert client.get('/hazardous/sources/documents').status_code == 403


def test_same_building_links_and_source_selectors(hazardous_env):
    from app.models import Facility, Inspection
    from datetime import date
    client, engine, refs = hazardous_env
    installation = install(client, refs)
    with Session(engine) as db:
        other = Facility(name='Synthetic other facility'); db.add(other); db.flush()
        inspection = Inspection(building_id=other.building_id, inspected_at=date(2026, 10, 1)); db.add(inspection); db.commit()
        other_id = inspection.inspection_id
    response = client.post(f"/hazardous/installations/{installation['installation_id']}/records", json={'expected_installation_version': 1, 'kind': 'change', 'title': 'Synthetic mismatch', 'recorded_on': '2026-10-01', 'inspection_ids': [other_id]})
    assert response.status_code == 409
    for kind in ('facilities', 'documents', 'legal', 'inspections', 'violations'):
        response = client.get(f"/hazardous/sources/{kind}?building_id={refs['building_id']}&limit=1")
        assert response.status_code == 200, response.text
        assert len(response.json()) <= 1
        if response.json(): assert response.json()[0]['label']


def test_retirement_cancellation_and_confirmed_immutability(hazardous_env):
    client, _, refs = hazardous_env
    installation = install(client, refs)
    row = action(client, installation, record(client, installation, refs), 'confirm')
    path = f"/hazardous/installations/{installation['installation_id']}/records/{row['record_id']}"
    assert client.patch(path, json={'expected_version': row['version'], 'expected_installation_version': 1, 'reason': 'Edit', 'title': 'Overwrite'}).status_code == 409
    assert client.delete(path).status_code == 405
    cancelled = action(client, installation, row, 'cancel')
    assert cancelled['status'] == 'cancelled' and cancelled['source_snapshot'] == row['source_snapshot']
    response = client.post('/hazardous/installations/' + installation['installation_id'] + '/retire', json={'expected_version': 1, 'reason': 'Synthetic closure', 'human_acknowledged': True})
    assert response.status_code == 200 and response.json()['status'] == 'retired'
    assert client.get('/hazardous/deadlines').json() == []


def test_revoked_session_and_module_flag_block_writes(hazardous_env, monkeypatch):
    from app import authz
    from app.models import UserSession, FeatureFlag, now_utc
    client, engine, refs = hazardous_env
    installation = install(client, refs)
    with Session(engine) as db:
        flag = db.scalar(select(FeatureFlag).where(FeatureFlag.key == 'module.hazardous_materials.enabled')); flag.enabled = False; db.commit()
    assert client.get('/hazardous/installations').status_code == 503
    with Session(engine) as db:
        db.scalar(select(FeatureFlag).where(FeatureFlag.key == 'module.hazardous_materials.enabled')).enabled = True; db.commit()
    original = authz.account_change_lock
    def revoked(db):
        original(db)
        for row in db.scalars(select(UserSession)): row.revoked_at = now_utc()
        db.flush()
    monkeypatch.setattr(authz, 'account_change_lock', revoked)
    response = client.patch('/hazardous/installations/' + installation['installation_id'], json={'expected_version': 1, 'reason': 'Synthetic change', 'name': 'Changed'})
    assert response.status_code == 401, response.text


def test_protected_inquiry_original_is_filtered_before_source_paging(hazardous_env):
    from app.models import Document, User
    from app.inquiries_models import Inquiry
    client, engine, refs = hazardous_env
    installation = install(client, refs)
    with Session(engine) as db:
        user = db.scalar(select(User).where(User.username == 'learning-admin'))
        doc = db.get(Document, refs['proof'])
        doc.document_type = 'inquiry_import_original'
        db.add(Inquiry(year=2026, question='Protected synthetic inquiry',
                       provenance={'source_document_id': doc.document_id, 'required_permissions': ['finance.read']}, created_by=user.user_id))
        db.commit()
    row = action(client, installation, record(client, installation, refs), 'confirm')
    revoke(engine, 'finance.read')
    sources_result = client.get('/hazardous/sources/documents?limit=200')
    assert sources_result.status_code == 200
    assert refs['proof'] not in sources_result.text
    shown = detail(client, installation)
    assert row['record_id'] not in str(shown) and refs['proof'] not in str(shown)
    response = client.post(f"/hazardous/installations/{installation['installation_id']}/records", json={'expected_installation_version': 1, 'kind': 'permit', 'title': 'Restricted synthetic', 'recorded_on': '2026-10-01', 'document_ids': [refs['proof']]})
    assert response.status_code == 403


def test_failed_patch_rolls_back_facts_history_and_audit(hazardous_env):
    from app.models import AuditLog
    from app.hazardous_models import HazardousHistory
    client, engine, refs = hazardous_env
    installation = install(client, refs)
    row = record(client, installation, refs)
    with Session(engine) as db:
        before_history = len(list(db.scalars(select(HazardousHistory))))
        before_audit = len(list(db.scalars(select(AuditLog).where(AuditLog.action.like('hazardous.%')))))
    response = client.patch(f"/hazardous/installations/{installation['installation_id']}/records/{row['record_id']}", json={'expected_installation_version': 1, 'expected_version': row['version'], 'reason': 'Bad source', 'title': 'Should roll back', 'document_ids': ['00000000-0000-0000-0000-000000000001']})
    assert response.status_code == 404
    assert detail(client, installation)['evidence_records'][0]['title'] == row['title']
    with Session(engine) as db:
        assert len(list(db.scalars(select(HazardousHistory)))) == before_history
        assert len(list(db.scalars(select(AuditLog).where(AuditLog.action.like('hazardous.%'))))) == before_audit


def test_confirm_snapshot_names_exact_record_revision(hazardous_env):
    client, _, refs = hazardous_env
    installation = install(client, refs)
    row = action(client, installation, record(client, installation, refs), 'confirm')
    assert row['source_snapshot']['record'] == {'record_id': row['record_id'], 'version': row['version']}


def test_migration052_is_additive_and_parses_trigger_bodies():
    from app.migrations import split_sql
    path = Path(__file__).resolve().parents[2] / 'db/migrations/052_hazardous_materials_register.sql'
    assert path.is_file()
    statements = split_sql(path.read_text())
    assert any('CREATE TABLE hazardous_installations' in sql for sql in statements)
    assert any('CREATE TABLE hazardous_records' in sql for sql in statements)
    assert any('CREATE TABLE hazardous_history' in sql for sql in statements)
    assert any('BEFORE UPDATE OR DELETE ON hazardous_history' in sql for sql in statements)
    assert not any('DROP TABLE' in sql for sql in statements)


@pytest.mark.parametrize('changed', ['installation', 'original_metadata'])
def test_confirmation_rejects_changed_draft_evidence_until_human_refresh(hazardous_env, changed):
    from hashlib import sha256
    from app.models import Document
    from app.settings import settings
    client, engine, refs = hazardous_env
    parent = install(client, refs)
    row = record(client, parent, refs)
    if changed == 'installation':
        response = client.patch('/hazardous/installations/' + parent['installation_id'], json={'expected_version': 1, 'reason': 'Human changed installation facts', 'name': 'Changed synthetic tank'})
        assert response.status_code == 200
        parent = response.json()
    else:
        with Session(engine) as db:
            doc = db.get(Document, refs['proof'])
            raw = b'Changed synthetic original and metadata'
            (Path(settings.storage_root) / doc.storage_path).write_bytes(raw)
            doc.sha256 = sha256(raw).hexdigest()
            db.commit()
    action(client, parent, row, 'confirm', 409)
    response = client.patch(f"/hazardous/installations/{parent['installation_id']}/records/{row['record_id']}", json={'expected_installation_version': parent['version'], 'expected_version': row['version'], 'reason': 'Human rechecked refreshed evidence'})
    assert response.status_code == 200, response.text
    assert action(client, parent, response.json(), 'confirm')['confirmation_current'] is True


def test_generic_audit_does_not_disclose_hazardous_or_source_content(hazardous_env):
    from app.routers import administration
    client, engine, refs = hazardous_env
    client.app.include_router(administration.router)
    parent = install(client, refs)
    row = action(client, parent, record(client, parent, refs), 'confirm')
    revoke(engine, 'hazardous.read', 'document.read', 'legal_source.read')
    response = client.get('/administration/audit?action=hazardous.record.confirm')
    assert response.status_code == 200, response.text
    for private in (row['title'], row['record_id'], parent['installation_id'], refs['proof'], refs['legal_source_version_id'], 'synthetic-proof.txt'):
        assert private not in response.text
    assert 'change_sha256' in response.text


def test_violation_links_require_same_building_and_underlying_source_rights(hazardous_env):
    from app.models import Facility, User
    from app.violation_models import ViolationCase
    from datetime import date
    client, engine, refs = hazardous_env
    parent = install(client, refs)
    with Session(engine) as db:
        user = db.scalar(select(User).where(User.username == 'learning-admin'))
        other = Facility(name='Synthetic other building'); db.add(other); db.flush()
        linked = ViolationCase(building_id=refs['building_id'], observed_on=date(2026, 10, 1), possible_issue='Restricted synthetic case', evidence_document_ids=[refs['proof']], created_by=user.user_id)
        wrong = ViolationCase(building_id=other.building_id, observed_on=date(2026, 10, 1), possible_issue='Wrong synthetic building', created_by=user.user_id)
        db.add_all([linked, wrong]); db.commit()
        linked_id, wrong_id = linked.case_id, wrong.case_id
    data = {'expected_installation_version': 1, 'kind': 'change', 'title': 'Synthetic case link', 'recorded_on': '2026-10-01'}
    path = '/hazardous/installations/' + parent['installation_id'] + '/records'
    assert client.post(path, json={**data, 'violation_case_ids': [wrong_id]}).status_code == 409
    linked_record = client.post(path, json={**data, 'violation_case_ids': [linked_id]})
    assert linked_record.status_code == 201, linked_record.text
    revoke(engine, 'document.read')
    assert linked_record.json()['record_id'] not in str(detail(client, parent))
    choices = client.get('/hazardous/sources/violations?building_id=' + refs['building_id'])
    assert choices.status_code == 200 and choices.json() == []


def test_granular_mutation_permissions_are_revalidated_after_queue(hazardous_env, monkeypatch):
    from app import authz
    from app.models import Permission, RolePermission
    client, _, refs = hazardous_env
    parent = install(client, refs)
    original = authz.account_change_lock
    def revoke_in_queue(db):
        original(db)
        permission = db.scalar(select(Permission).where(Permission.code == 'hazardous.update'))
        for link in db.scalars(select(RolePermission).where(RolePermission.permission_id == permission.permission_id)):
            db.delete(link)
        db.flush()
    monkeypatch.setattr(authz, 'account_change_lock', revoke_in_queue)
    response = client.patch('/hazardous/installations/' + parent['installation_id'], json={'expected_version': 1, 'reason': 'Synthetic change', 'name': 'Should not change'})
    assert response.status_code == 403
    assert detail(client, parent)['name'] == parent['name']


def test_ordinary_original_enforces_current_ownership_permissions(hazardous_env):
    from app.models import LegalSourceDocumentVersion
    client, engine, refs = hazardous_env
    with Session(engine) as db:
        identity = db.get(LegalSourceDocumentVersion, refs['legal_source_version_id']).raw_document_id
    revoke(engine, 'legal_source.read')
    response = client.get('/hazardous/sources/documents')
    assert response.status_code == 200
    assert identity not in response.text and 'synthetic-rule.txt' not in response.text
    parent = install(client, refs)
    response = client.post('/hazardous/installations/' + parent['installation_id'] + '/records', json={'expected_installation_version': 1, 'kind': 'change', 'title': 'Attempted ordinary original shortcut', 'recorded_on': '2026-10-01', 'document_ids': [identity]})
    assert response.status_code == 403


def test_original_beneath_linked_violation_invalidates_confirmation(hazardous_env):
    from app.models import Document, User
    from app.violation_models import ViolationCase
    from app.settings import settings
    from datetime import date
    client, engine, refs = hazardous_env
    parent = install(client, refs)
    with Session(engine) as db:
        user = db.scalar(select(User).where(User.username == 'learning-admin'))
        linked = ViolationCase(building_id=refs['building_id'], observed_on=date(2026, 10, 1), possible_issue='Synthetic linked case', evidence_document_ids=[refs['proof']], created_by=user.user_id)
        db.add(linked); db.commit(); identity = linked.case_id
    row = action(client, parent, record(client, parent, refs, document_ids=[refs['procedure']], violation_case_ids=[identity]), 'confirm')
    with Session(engine) as db:
        doc = db.get(Document, refs['proof'])
        (Path(settings.storage_root) / doc.storage_path).write_bytes(b'Changed original under linked case')
    shown = detail(client, parent)['evidence_records'][0]
    assert shown['confirmation_current'] is False
    assert shown['source_snapshot'] == row['source_snapshot']
