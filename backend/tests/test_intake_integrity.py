"""Synthetic Document→Human review→receipt lifecycle and original preservation."""
from hashlib import sha256

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from test_learning import learning_environment


SOURCE = '消防用設備等点検結果報告書\n防火対象物名称: Synthetic Intake B\n所在地: New synthetic address\n電話番号: 1111\n'.encode()


@pytest.fixture
def intake_environment(learning_environment, tmp_path, monkeypatch):
    client, engine = learning_environment
    from app.routers import documents, facilities, intake, search, submissions
    from app.settings import settings
    from app.submission_seed import seed_submission_types
    monkeypatch.setattr(settings, 'storage_root', str(tmp_path / 'originals'))
    for router in (documents, facilities, intake, search, submissions):
        client.app.include_router(router.router)
    with Session(engine) as db:
        seed_submission_types(db)
        db.commit()
    return client, engine


def setup_analysis(client):
    a = client.post('/facilities', json={'name': 'Synthetic Intake A', 'address': 'Old synthetic address', 'phone': '0000'})
    b = client.post('/facilities', json={'name': 'Synthetic Intake B', 'address': 'New synthetic address', 'phone': '1111'})
    assert a.status_code == b.status_code == 201
    document = client.post('/documents/upload', files={'file': ('synthetic-intake.txt', SOURCE, 'text/plain')}, data={'document_type': 'submission_source'})
    assert document.status_code == 201, document.text
    analysis = client.post('/document-analyses', json={'document_id': document.json()['document_id']})
    assert analysis.status_code == 201, analysis.text
    return a.json(), b.json(), document.json(), analysis.json()


def review(client, analysis, facility):
    return client.post('/document-analyses/' + analysis['document_analysis_id'] + '/review', json={'expected_version': analysis['version'], 'building_id': facility['building_id'], 'submission_type_code': 'equipment_inspection_report'})


def proposals(client, analysis):
    result = client.get('/document-analyses/' + analysis['document_analysis_id'] + '/change-proposals')
    assert result.status_code == 200, result.text
    return result.json()


def apply(client, proposal):
    return client.post('/facility-change-proposals/' + proposal['facility_change_proposal_id'] + '/apply', json={'expected_version': proposal['version'], 'expected_facility_version': proposal['expected_facility_version'], 'accepted_paths': ['facility.address']})


def confirm(client, analysis):
    return client.post('/document-analyses/' + analysis['document_analysis_id'] + '/confirm-receipt', json={'expected_version': analysis['version'], 'official_number': '9001', 'submitted_at': '2026-10-07'})


def test_empty_rereview_supersedes_previous_target_without_changing_original(intake_environment):
    from app.models import AuditLog, Document
    from app.document_intake import _storage_path
    client, engine = intake_environment
    a, b, document, analysis = setup_analysis(client)
    first = review(client, analysis, a).json()
    old = proposals(client, analysis)[0]
    second = review(client, first, b)
    assert second.status_code == 200, second.text
    assert second.json()['difference_candidates'] == {}
    history = proposals(client, analysis)
    assert history[0]['status'] == 'superseded'
    assert history[0]['building_id'] == a['building_id']
    assert history[0]['changes'] == old['changes']
    assert apply(client, old).status_code == 409
    assert client.get('/facilities/' + a['building_id'] + '/detail').json()['facility']['address'] == a['address']
    with Session(engine) as db:
        row = db.get(Document, document['document_id'])
        assert row.sha256 == sha256(SOURCE).hexdigest()
        assert _storage_path(row).read_bytes() == SOURCE
        audit = db.scalar(select(AuditLog).where(AuditLog.action == 'facility_change_proposal.supersede'))
        assert audit and audit.entity_id == old['facility_change_proposal_id']


def test_rereview_preserves_old_proposal_and_only_new_revision_can_apply(intake_environment):
    client, _ = intake_environment
    a, b, _, analysis = setup_analysis(client)
    first = review(client, analysis, a).json()
    old = proposals(client, analysis)[0]
    changed = client.patch('/facilities/' + a['building_id'], json={'expected_version': 1, 'phone': '2222'})
    assert changed.status_code == 200, changed.text
    second = review(client, first, a)
    assert second.status_code == 200, second.text
    history = proposals(client, analysis)
    assert len(history) == 2
    assert history[0]['status'] == 'superseded' and history[0]['changes'] == old['changes']
    pending = next(row for row in history if row['status'] == 'pending')
    assert pending['facility_change_proposal_id'] != old['facility_change_proposal_id']
    assert apply(client, old).status_code == 409
    assert apply(client, pending).status_code == 200
    facility = client.get('/facilities/' + a['building_id'] + '/detail').json()['facility']
    assert facility['address'] == b['address'] and facility['phone'] == '2222'


def test_confirmed_receipt_is_terminal_and_exactly_once(intake_environment):
    from app.models import AuditLog, EquipmentInspectionReport, Submission, SubmissionFile
    client, engine = intake_environment
    _, b, document, analysis = setup_analysis(client)
    reviewed = review(client, analysis, b).json()
    first = confirm(client, reviewed)
    assert first.status_code == 201, first.text
    current = client.get('/document-analyses/' + analysis['document_analysis_id']).json()
    assert current['status'] == 'receipt_confirmed'
    assert review(client, current, b).status_code == 409
    assert confirm(client, current).status_code == 409
    assert confirm(client, reviewed).status_code == 409
    with Session(engine) as db:
        assert db.scalar(select(func.count()).select_from(Submission)) == 1
        assert db.scalar(select(func.count()).select_from(EquipmentInspectionReport)) == 1
        assert db.scalar(select(func.count()).select_from(SubmissionFile)) == 1
        assert db.scalar(select(func.count()).select_from(AuditLog).where(AuditLog.action == 'document_analysis.confirm_receipt')) == 1
        assert first.json()['document_ids'] == [document['document_id']]


def test_receipt_preserves_reviewed_proposal_for_explicit_selection_and_search(intake_environment):
    client, _ = intake_environment
    a, b, document, analysis = setup_analysis(client)
    reviewed = review(client, analysis, a).json()
    pending = proposals(client, analysis)[0]
    received = confirm(client, reviewed)
    assert received.status_code == 201, received.text
    assert client.get('/facilities/' + a['building_id'] + '/detail').json()['facility']['address'] == a['address']
    assert apply(client, pending).status_code == 200
    assert apply(client, pending).status_code == 409
    detail = client.get('/facilities/' + a['building_id'] + '/detail').json()['facility']
    assert detail['address'] == b['address'] and detail['phone'] == a['phone']
    result = client.get('/search', params={'q': 'New synthetic address', 'modules': 'facilities'})
    assert result.status_code == 200, result.text
    assert any(hit['source_id'] == a['building_id'] for hit in result.json()['hits'])
    assert client.get('/documents/' + document['document_id']).json()['sha256'] == document['sha256']


@pytest.mark.parametrize('operation,permission', [('analyze', 'intake.analyze'), ('review', 'intake.review'), ('confirm', 'submission.create'), ('apply', 'intake.apply')])
@pytest.mark.parametrize('change', ['session', 'permission'])
def test_queued_intake_mutation_revalidates_authority(intake_environment, monkeypatch, operation, permission, change):
    from app import authz
    from app.models import DocumentAnalysis, Facility, FacilityChangeProposal, Permission, RolePermission, Submission, UserSession, now_utc
    client, engine = intake_environment
    a, _, document, analysis = setup_analysis(client)
    reviewed = review(client, analysis, a).json()
    pending = proposals(client, analysis)[0]
    original = authz.account_change_lock
    def invalidate(db):
        original(db)
        if change == 'session':
            for row in db.scalars(select(UserSession)):
                row.revoked_at = now_utc()
        else:
            target = db.scalar(select(Permission).where(Permission.code == permission))
            for row in db.scalars(select(RolePermission).where(RolePermission.permission_id == target.permission_id)):
                db.delete(row)
        db.flush()
    monkeypatch.setattr(authz, 'account_change_lock', invalidate)
    if operation == 'analyze':
        response = client.post('/document-analyses', json={'document_id': document['document_id']})
    elif operation == 'review':
        response = review(client, reviewed, a)
    elif operation == 'confirm':
        response = confirm(client, reviewed)
    else:
        response = apply(client, pending)
    assert response.status_code == (401 if change == 'session' else 403), response.text
    with Session(engine) as db:
        assert db.scalar(select(func.count()).select_from(DocumentAnalysis)) == 1
        assert db.get(DocumentAnalysis, analysis['document_analysis_id']).version == reviewed['version']
        assert db.get(FacilityChangeProposal, pending['facility_change_proposal_id']).status == 'pending'
        assert db.get(Facility, a['building_id']).address == a['address']
        assert db.scalar(select(func.count()).select_from(Submission)) == 0


def test_legacy_pending_proposal_must_match_current_review_target(intake_environment):
    from app.models import DocumentAnalysis
    client, engine = intake_environment
    a, b, _, analysis = setup_analysis(client)
    review(client, analysis, a)
    old = proposals(client, analysis)[0]
    # Reproduce persisted state left by the pre-repair empty-difference bug.
    with Session(engine) as db:
        row = db.get(DocumentAnalysis, analysis['document_analysis_id'])
        row.selected_building_id = b['building_id']
        row.difference_candidates = {}
        row.version += 1
        db.commit()
    assert apply(client, old).status_code == 409
    assert client.get('/facilities/' + a['building_id'] + '/detail').json()['facility']['address'] == a['address']


@pytest.mark.parametrize('loser,winner', [('confirm', 'confirm'), ('review', 'review'), ('review', 'confirm'), ('apply', 'review')])
def test_stale_read_cannot_commit_side_effects_after_winning_transition(intake_environment, monkeypatch, loser, winner):
    from fastapi import HTTPException
    from app.models import AuditLog, DocumentAnalysis, Facility, Submission, User
    from app.routers import intake
    from app.schemas import DocumentAnalysisReview, FacilityChangeProposalApply, IntakeConfirmReceipt
    client, engine = intake_environment
    a, b, _, analysis = setup_analysis(client)
    reviewed = review(client, analysis, a).json()
    old = proposals(client, analysis)[0]
    guard = intake._guard_inquiry_analysis
    waiting = True
    def complete_winner(db, user, row):
        nonlocal waiting
        guard(db, user, row)
        if waiting:
            waiting = False
            won = confirm(client, reviewed) if winner == 'confirm' else review(client, reviewed, b)
            assert won.status_code == (201 if winner == 'confirm' else 200), won.text
    monkeypatch.setattr(intake, '_guard_inquiry_analysis', complete_winner)
    with Session(engine, expire_on_commit=False) as db:
        user = db.scalar(select(User).where(User.username == 'learning-admin'))
        with pytest.raises(HTTPException) as failure:
            if loser == 'review':
                intake.review_analysis(analysis['document_analysis_id'], DocumentAnalysisReview(expected_version=reviewed['version'], building_id=a['building_id']), db, user)
            elif loser == 'confirm':
                intake.confirm_receipt(analysis['document_analysis_id'], IntakeConfirmReceipt(expected_version=reviewed['version'], official_number='9002'), db, user)
            else:
                intake.apply_change_proposal(old['facility_change_proposal_id'], FacilityChangeProposalApply(expected_version=old['version'], expected_facility_version=1, accepted_paths=['facility.address']), db, user)
        assert failure.value.status_code == 409
    with Session(engine) as db:
        row = db.get(DocumentAnalysis, analysis['document_analysis_id'])
        assert row.version == reviewed['version'] + 1
        assert row.status == ('receipt_confirmed' if winner == 'confirm' else 'reviewed')
        assert db.get(Facility, a['building_id']).address == a['address']
        assert db.scalar(select(func.count()).select_from(Submission)) == (1 if winner == 'confirm' else 0)
        assert db.scalar(select(func.count()).select_from(AuditLog).where(AuditLog.action == 'facility_change_proposal.apply')) == 0


@pytest.mark.parametrize('loser', ['review', 'confirm'])
def test_applied_change_invalidates_preapplication_analysis_snapshot(intake_environment, monkeypatch, loser):
    from fastapi import HTTPException
    from app.models import DocumentAnalysis, Facility, Submission, User
    from app.routers import intake
    from app.schemas import DocumentAnalysisReview, IntakeConfirmReceipt
    client, engine = intake_environment
    a, b, _, analysis = setup_analysis(client)
    reviewed = review(client, analysis, a).json()
    pending = proposals(client, analysis)[0]
    original = intake._guard_inquiry_analysis
    waiting = True
    def apply_before_transition(db, user, row):
        nonlocal waiting
        original(db, user, row)
        if waiting:
            waiting = False
            response = apply(client, pending)
            assert response.status_code == 200, response.text
    monkeypatch.setattr(intake, '_guard_inquiry_analysis', apply_before_transition)
    with Session(engine, expire_on_commit=False) as db:
        user = db.scalar(select(User).where(User.username == 'learning-admin'))
        with pytest.raises(HTTPException) as failure:
            if loser == 'review':
                intake.review_analysis(analysis['document_analysis_id'], DocumentAnalysisReview(expected_version=reviewed['version'], building_id=b['building_id']), db, user)
            else:
                intake.confirm_receipt(analysis['document_analysis_id'], IntakeConfirmReceipt(expected_version=reviewed['version'], official_number='9001'), db, user)
        assert failure.value.status_code == 409
    with Session(engine) as db:
        assert db.get(DocumentAnalysis, analysis['document_analysis_id']).version == reviewed['version'] + 1
        assert db.get(Facility, a['building_id']).address == b['address']
        assert db.scalar(select(func.count()).select_from(Submission)) == 0


def test_invalid_specialized_receipt_rolls_back_lifecycle_link_and_document_binding(intake_environment):
    from app.models import AuditLog, Document, DocumentAnalysis, EquipmentInspectionReport, Submission, SubmissionFile
    client, engine = intake_environment
    a, _, document, analysis = setup_analysis(client)
    reviewed = review(client, analysis, a).json()
    failed = client.post('/document-analyses/' + analysis['document_analysis_id'] + '/confirm-receipt', json={'expected_version': reviewed['version'], 'official_number': '9001', 'payload_data': {'inspection_date': 'not-a-date'}})
    assert failed.status_code == 422, failed.text
    with Session(engine) as db:
        assert db.get(DocumentAnalysis, analysis['document_analysis_id']).status == 'reviewed'
        assert db.get(DocumentAnalysis, analysis['document_analysis_id']).version == reviewed['version']
        assert db.get(Document, document['document_id']).building_id is None
        for model in (Submission, SubmissionFile, EquipmentInspectionReport):
            assert db.scalar(select(func.count()).select_from(model)) == 0
        assert db.scalar(select(func.count()).select_from(AuditLog).where(AuditLog.action == 'document_analysis.confirm_receipt')) == 0
    # Failed confirmation has not consumed the user's reviewed version.
    assert confirm(client, reviewed).status_code == 201
