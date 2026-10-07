"""Real PostgreSQL intake transactions, including deliberately stale read snapshots.

SQLite is never concurrency evidence. Set FIRE_AI_TEST_POSTGRES_URL to the
approved disposable cluster; the shared fixture migrates a fresh database.
"""
import threading
from concurrent.futures import ThreadPoolExecutor

import pytest
from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from test_learning import learning_environment
from test_intake_integrity import intake_environment, setup_analysis, review, proposals, confirm, apply
from test_workforce_concurrency import compete


@pytest.fixture
def intake_pg(intake_environment):
    client, engine = intake_environment
    if engine.dialect.name != 'postgresql':
        pytest.skip('real PostgreSQL transaction interleaving required')
    return client, engine


def _direct(engine, operation, analysis, facility, proposal):
    from app.models import User
    from app.routers import intake
    from app.schemas import DocumentAnalysisReview, FacilityChangeProposalApply, IntakeConfirmReceipt
    with Session(engine, expire_on_commit=False) as db:
        user = db.scalar(select(User).where(User.username == 'learning-admin'))
        try:
            if operation == 'confirm':
                intake.confirm_receipt(analysis['document_analysis_id'], IntakeConfirmReceipt(expected_version=analysis['version'], official_number='9001'), db, user)
                return 201
            if operation == 'review':
                intake.review_analysis(analysis['document_analysis_id'], DocumentAnalysisReview(expected_version=analysis['version'], building_id=facility['building_id'], submission_type_code='equipment_inspection_report'), db, user)
            else:
                intake.apply_change_proposal(proposal['facility_change_proposal_id'], FacilityChangeProposalApply(expected_version=proposal['version'], expected_facility_version=proposal['expected_facility_version'], accepted_paths=['facility.address']), db, user)
            return 200
        except HTTPException as exc:
            return exc.status_code


@pytest.mark.parametrize('operation', ['confirm', 'review', 'apply'])
def test_same_snapshot_transactions_have_one_winner_and_no_orphan_effects(intake_pg, monkeypatch, operation):
    from app.models import AuditLog, DocumentAnalysis, EquipmentInspectionReport, Facility, FacilityChangeProposal, Submission, SubmissionFile
    from app.routers import intake
    client, engine = intake_pg
    a, b, _, analysis = setup_analysis(client)
    reviewed = review(client, analysis, a).json()
    pending = proposals(client, analysis)[0]
    # Exercise the lifecycle SQL independently of the global authority lock:
    # both real transactions must finish reading the same lifecycle revision.
    barrier = threading.Barrier(2)
    original = intake._guard_inquiry_analysis
    def same_snapshot(db, user, row):
        original(db, user, row)
        barrier.wait(timeout=10)
    monkeypatch.setattr(intake, '_guard_inquiry_analysis', same_snapshot)
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(_direct, engine, operation, reviewed, target, pending) for target in (a, b)]
        outcomes = [future.result(timeout=20) for future in futures]
    assert sorted(outcomes) == [201 if operation == 'confirm' else 200, 409], outcomes
    with Session(engine) as db:
        final = db.get(DocumentAnalysis, analysis['document_analysis_id'])
        assert final.version == reviewed['version'] + 1
        assert db.scalar(select(func.count()).select_from(AuditLog).where(AuditLog.action == 'document_analysis.review')) == 1 + (operation == 'review')
        assert db.scalar(select(func.count()).select_from(AuditLog).where(AuditLog.action == 'facility_change_proposal.supersede')) == (1 if operation == 'review' else 0)
        expected_proposals = 1 + (operation == 'review' and final.selected_building_id == a['building_id'])
        assert db.scalar(select(func.count()).select_from(FacilityChangeProposal)) == expected_proposals
        receipts = 1 if operation == 'confirm' else 0
        for model in (Submission, SubmissionFile, EquipmentInspectionReport):
            assert db.scalar(select(func.count()).select_from(model)) == receipts
        assert db.scalar(select(func.count()).select_from(AuditLog).where(AuditLog.action == 'document_analysis.confirm_receipt')) == receipts
        applied = 1 if operation == 'apply' else 0
        assert db.scalar(select(func.count()).select_from(AuditLog).where(AuditLog.action == 'facility_change_proposal.apply')) == applied
        assert db.get(Facility, a['building_id']).version == 1 + applied
        current = db.scalars(select(FacilityChangeProposal).where(FacilityChangeProposal.status == 'pending')).all()
        assert len(current) <= 1
        assert all(row.building_id == final.selected_building_id and row.changes == final.difference_candidates for row in current)


@pytest.mark.parametrize('loser,winner', [('confirm', 'review'), ('review', 'confirm'), ('apply', 'review'), ('review', 'apply'), ('confirm', 'apply')])
def test_winning_transition_invalidates_other_transactions_loaded_snapshot(intake_pg, monkeypatch, loser, winner):
    from app.models import AuditLog, DocumentAnalysis, Facility, Submission
    from app.routers import intake
    client, engine = intake_pg
    a, b, _, analysis = setup_analysis(client)
    reviewed = review(client, analysis, a).json()
    pending = proposals(client, analysis)[0]
    loaded = threading.Event()
    release = threading.Event()
    original = intake._guard_inquiry_analysis
    def delay_loser(db, user, row):
        original(db, user, row)
        if threading.current_thread().name.startswith('intake-stale'):
            loaded.set()
            assert release.wait(timeout=15), 'winner did not finish'
    monkeypatch.setattr(intake, '_guard_inquiry_analysis', delay_loser)
    with ThreadPoolExecutor(max_workers=1, thread_name_prefix='intake-stale') as pool:
        future = pool.submit(_direct, engine, loser, reviewed, a, pending)
        assert loaded.wait(timeout=10), 'loser did not load the previous revision'
        try:
            response = confirm(client, reviewed) if winner == 'confirm' else apply(client, pending) if winner == 'apply' else review(client, reviewed, b)
            assert response.status_code == (201 if winner == 'confirm' else 200), response.text
        finally:
            release.set()
        assert future.result(timeout=20) == 409
    with Session(engine) as db:
        final = db.get(DocumentAnalysis, analysis['document_analysis_id'])
        assert final.version == reviewed['version'] + 1
        assert final.status == ('receipt_confirmed' if winner == 'confirm' else 'reviewed')
        assert db.get(Facility, a['building_id']).address == (b['address'] if winner == 'apply' else a['address'])
        assert db.scalar(select(func.count()).select_from(Submission)) == (1 if winner == 'confirm' else 0)
        assert db.scalar(select(func.count()).select_from(AuditLog).where(AuditLog.action == 'facility_change_proposal.apply')) == (1 if winner == 'apply' else 0)


def test_http_double_confirmation_keeps_one_receipt_and_document_link(intake_pg):
    from app.models import EquipmentInspectionReport, Submission, SubmissionFile
    client, engine = intake_pg
    _, b, _, analysis = setup_analysis(client)
    reviewed = review(client, analysis, b).json()
    request = ('/document-analyses/' + analysis['document_analysis_id'] + '/confirm-receipt', {'expected_version': reviewed['version'], 'official_number': '9001'})
    assert sorted(compete(client, [request, request])) == [201, 409]
    with Session(engine) as db:
        for model in (Submission, SubmissionFile, EquipmentInspectionReport):
            assert db.scalar(select(func.count()).select_from(model)) == 1
