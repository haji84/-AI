"""Read-only pointers never duplicate protected hazardous facts or legal prose."""
import json
from datetime import date
import pytest
from sqlalchemy.orm import Session

from test_hazardous_evaluations import evaluation_env, create_evaluation
from test_hazardous_rule_authoring import author, revoke_original_access


def test_pending_hazardous_evaluation_is_live_generic_pointer_and_review_removes_it(evaluation_env):
    client, engine, installation, _, _ = evaluation_env
    candidate = create_evaluation(evaluation_env)
    response = client.get('/work-queue?as_of=2026-10-09')
    assert response.status_code == 200, response.text
    data = response.json()
    assert data['counts'] == {'hazardous_materials': 1}
    item = data['items'][0]
    assert item['source_id'] == candidate['evaluation_id']
    assert item['navigation'] == {'surface': 'hazardous_evaluation', 'id': candidate['evaluation_id']}
    assert item['source_version'] == 1 and 'created_by_me' in item['relationships']
    assert 'Synthetic material' not in json.dumps(data)
    assert 'Synthetic Article' not in json.dumps(data)
    assert '100.000000' not in json.dumps(data)
    assert candidate['rules_snapshot'][0]['source']['sha256'] not in json.dumps(data)
    reviewed = client.post('/hazardous/evaluations/' + candidate['evaluation_id'] + '/review',
        json={'expected_version': 1, 'acknowledged': True, 'reason': 'Synthetic separate source review'})
    assert reviewed.status_code == 200, reviewed.text
    assert client.get('/work-queue?as_of=2026-10-09').json()['total'] == 0


def test_original_rights_filter_hazardous_counts_before_paging(evaluation_env):
    client, engine, _, _, _ = evaluation_env
    candidate = create_evaluation(evaluation_env)
    revoke_original_access(engine)
    response = client.get('/work-queue?limit=1&as_of=2026-10-09')
    assert response.status_code == 200, response.text
    data = response.json()
    assert data['total'] == 0 and data['counts'] == {}
    assert candidate['evaluation_id'] not in json.dumps(data)


def test_linked_violation_record_review_and_deadline_remain_generic_pointers(evaluation_env):
    from sqlalchemy.orm import Session
    from app.models import User
    from app.violation_models import ViolationCase
    client, engine, installation, _, _ = evaluation_env
    with Session(engine) as db:
        case = ViolationCase(building_id=installation['building_id'], observed_on=date(2026, 10, 1),
            possible_issue='PRIVATE linked violation candidate', created_by=db.query(User).one().user_id)
        db.add(case); db.commit(); identity = case.case_id
    created = client.post('/hazardous/installations/' + installation['installation_id'] + '/records',
        json={'expected_installation_version': 1, 'kind': 'notification', 'title': 'PRIVATE notification title',
            'recorded_on': '2026-10-01', 'due_on': '2026-10-10', 'violation_case_ids': [identity]})
    assert created.status_code == 201, created.text
    response = client.get('/work-queue?as_of=2026-10-09')
    assert response.status_code == 200, response.text
    data = response.json()
    assert data['counts'] == {'hazardous_materials': 2}
    assert {item['kind'] for item in data['items']} == {'evidence_review', 'hazardous_deadline'}
    assert all(item['source_id'] == created.json()['record_id'] for item in data['items'])
    assert all('violation.read' in item['required_permissions'] for item in data['items'])
    assert 'PRIVATE' not in json.dumps(data)


@pytest.mark.parametrize('permission', ['hazardous.read', 'facility.read', 'document.read', 'legal_rule.read', 'legal_source.read'])
def test_each_source_right_filters_evaluation_before_counts(evaluation_env, permission):
    from app.models import Permission, RolePermission
    client, engine, _, _, _ = evaluation_env
    candidate = create_evaluation(evaluation_env)
    with Session(engine) as db:
        key = db.query(Permission).filter_by(code=permission).one().permission_id
        db.query(RolePermission).filter_by(permission_id=key).delete(); db.commit()
    data = client.get('/work-queue?limit=1&as_of=2026-10-09').json()
    assert data['total'] == 0 and data['counts'] == {}
    assert candidate['evaluation_id'] not in json.dumps(data)


def test_disabled_hazardous_module_filters_all_pointers(evaluation_env):
    from app.models import FeatureFlag
    client, engine, _, _, _ = evaluation_env
    create_evaluation(evaluation_env)
    with Session(engine) as db:
        db.add(FeatureFlag(key='module.hazardous_materials.enabled', module_code='hazardous_materials', enabled=False)); db.commit()
    data = client.get('/work-queue?as_of=2026-10-09').json()
    assert data['total'] == 0 and data['counts'] == {}


def test_retired_installation_removes_evaluation_pointer(evaluation_env):
    client, _, installation, _, _ = evaluation_env
    create_evaluation(evaluation_env)
    retired = client.post('/hazardous/installations/' + installation['installation_id'] + '/retire',
        json={'expected_version': 1, 'reason': 'Synthetic Human retirement', 'human_acknowledged': True})
    assert retired.status_code == 200, retired.text
    assert client.get('/work-queue?as_of=2026-10-09').json()['total'] == 0


def test_changed_facts_offer_recreation_instead_of_review(evaluation_env):
    client, _, installation, _, _ = evaluation_env
    candidate = create_evaluation(evaluation_env)
    changed = client.patch('/hazardous/installations/' + installation['installation_id'],
        json={'expected_version': 1, 'reason': 'Synthetic Human update', 'name': 'PRIVATE updated installation'})
    assert changed.status_code == 200, changed.text
    data = client.get('/work-queue?as_of=2026-10-09').json()
    assert data['items'][0]['kind'] == 'evaluation_refresh'
    assert data['items'][0]['source_id'] == candidate['evaluation_id']
    assert data['items'][0]['provenance']['parent_source_version'] == 2
    assert 'PRIVATE' not in json.dumps(data)


def test_related_scope_and_read_only_other_candidates(evaluation_env):
    from app.models import User, Permission, RolePermission
    from app.hazardous_evaluation_models import HazardousEvaluation
    client, engine, _, _, _ = evaluation_env
    candidate = create_evaluation(evaluation_env)
    with Session(engine) as db:
        other = User(username='synthetic-other-evaluation-creator', password_hash='synthetic-unused-hash')
        db.add(other); db.flush()
        db.get(HazardousEvaluation, candidate['evaluation_id']).created_by = other.user_id
        db.commit()
    assert client.get('/work-queue?scope=all').json()['total'] == 1
    assert client.get('/work-queue?scope=related').json()['total'] == 0
    with Session(engine) as db:
        keys = [row.permission_id for row in db.query(Permission).filter(Permission.code.in_(
            ['hazardous.review', 'hazardous.create', 'legal_rule.evaluate']))]
        db.query(RolePermission).filter(RolePermission.permission_id.in_(keys)).delete(); db.commit()
    assert client.get('/work-queue?scope=all').json()['total'] == 0


@pytest.mark.parametrize('protected_link', ['ancestor', 'violation'])
def test_inherited_or_later_added_private_original_filters_every_pointer(evaluation_env, protected_link):
    from hashlib import sha256
    from pathlib import Path
    from app.models import Document, User, Permission, RolePermission
    from app.hazardous_models import HazardousRecord
    from app.violation_models import ViolationCase
    from app.settings import settings
    client, engine, installation, _, _ = evaluation_env
    body = b'Synthetic protected personnel evidence'
    Path(settings.storage_root, 'synthetic-private.txt').write_bytes(body)
    with Session(engine) as db:
        user_id = db.query(User).one().user_id
        raw = Document(storage_path='synthetic-private.txt', original_filename='PRIVATE personnel.txt',
            sha256=sha256(body).hexdigest(), size_bytes=len(body), document_type='personnel_notice')
        db.add(raw); db.flush()
        current = HazardousRecord(installation_id=installation['installation_id'], kind='notification',
            title='PRIVATE current record', recorded_on=date(2026, 10, 1), due_on=date(2026, 10, 10),
            created_by=user_id)
        if protected_link == 'ancestor':
            ancestor = HazardousRecord(installation_id=installation['installation_id'], kind='notification',
                title='PRIVATE ancestor', recorded_on=date(2026, 9, 1), status='superseded',
                document_ids=[raw.document_id], created_by=user_id)
            db.add(ancestor); db.flush()
            current.supersedes_record_id = ancestor.record_id
        else:
            case = ViolationCase(building_id=installation['building_id'], observed_on=date(2026, 10, 1),
                possible_issue='PRIVATE case', created_by=user_id)
            db.add(case); db.flush()
            current.violation_case_ids = [case.case_id]
            # Later evidence is absent from the record's saved source snapshot.
            case.evidence_document_ids = [raw.document_id]
        db.add(current); db.commit(); record_id = current.record_id
    visible = client.get('/work-queue?as_of=2026-10-09').json()
    assert visible['total'] == 2 and visible['counts'] == {'hazardous_materials': 2}
    assert 'PRIVATE' not in json.dumps(visible)
    with Session(engine) as db:
        key = db.query(Permission).filter_by(code='personnel.read').one().permission_id
        db.query(RolePermission).filter_by(permission_id=key).delete(); db.commit()
    response = client.get('/work-queue?limit=1&as_of=2026-10-09')
    assert response.status_code == 200, response.text
    hidden = response.json()
    assert hidden['total'] == 0 and hidden['counts'] == {}
    assert record_id not in json.dumps(hidden)
