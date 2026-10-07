"""Financial work pointers never copy ledger values or source prose."""
from decimal import Decimal
import json
from uuid import uuid4

import pytest

from app.finance_models import FinanceYear, BudgetAccount, FinanceProposal, ProcurementEvent
from app.models import Document, FeatureFlag, Permission, ContractCase, ContractDocument, Facility, now_utc
from test_work_queue import queue, AS_OF


@pytest.fixture
def finance_queue(queue):
    with queue.sessions() as db:
        for code in ('finance.read', 'finance.review', 'finance.approve', 'contract.read', 'facility.read'):
            db.add(Permission(code=code))
        db.commit()
    year = queue.add(FinanceYear(fiscal_year=2026, currency='JPY', decimal_places=0, reason='PRIVATE fiscal policy'))
    account = queue.add(BudgetAccount(year_id=year.year_id, code='SYNTHETIC', name='PRIVATE account', level=1))
    doc = queue.add(Document(original_filename='PRIVATE source.txt', storage_path='unused-synthetic', sha256='a'*64,
                             mime_type='text/plain', size_bytes=1, created_by=queue.user_id))

    def proposal(**values):
        return queue.add(FinanceProposal(kind=values.pop('kind', 'initial'), account_id=account.account_id, document_id=values.pop('document_id', doc.document_id),
            amount=Decimal('12000.00'), currency='JPY', reason='PRIVATE financial reason',
            created_by=values.pop('created_by', queue.user_id), idempotency_key=str(uuid4()), **values))

    return queue, proposal


def test_finance_review_approval_and_own_drafts_are_live_pointers(finance_queue):
    queue, proposal = finance_queue
    own = proposal()
    review = proposal(created_by=queue.other_id)
    approval = proposal(status='reviewed', created_by=queue.other_id)
    proposal(status='cancelled')
    queue.permissions('finance.read', 'document.read', 'finance.review', 'finance.approve')
    result = queue.queue()
    assert result['counts'] == {'budget': 3}
    assert {r['source_id']: r['kind'] for r in result['items']} == {
        own.proposal_id: 'review', review.proposal_id: 'review', approval.proposal_id: 'approval'}
    pointer = next(r for r in result['items'] if r['source_id'] == own.proposal_id)
    assert pointer['navigation'] == {'surface': 'finance_proposal', 'id': own.proposal_id}
    assert pointer['source_version'] == 1
    assert pointer['provenance']['source_api'] == '/finance/proposals/'+own.proposal_id
    assert 'created_by_me' in pointer['relationships']
    assert 'PRIVATE' not in json.dumps(result)
    assert '12000' not in json.dumps(result)
    queue.permissions('finance.read', 'document.read')
    assert queue.queue()['total'] == 1
    assert queue.queue()['items'][0]['kind'] == 'draft'
    queue.update(FinanceProposal, own.proposal_id, status='cancelled', version=2)
    assert queue.queue()['total'] == 0


def test_finance_rights_and_module_filter_before_counts_and_pagination(finance_queue):
    queue, proposal = finance_queue
    row = proposal()
    queue.asset(next_calibration_on=AS_OF)
    queue.permissions('asset.read', 'finance.review', 'document.read')
    result = queue.queue(limit=1)
    assert result['counts'] == {'operational_assets': 1}
    assert row.proposal_id not in json.dumps(result)
    queue.permissions('finance.read', 'finance.review')
    assert queue.queue()['total'] == 0
    queue.permissions('finance.read', 'document.read', 'finance.review')
    assert queue.queue()['total'] == 1
    queue.add(FeatureFlag(key='module.budget.enabled', module_code='budget', enabled=False))
    assert queue.queue()['total'] == 0


def test_finance_related_scope_and_permission_revocation(finance_queue):
    queue, proposal = finance_queue
    own, other = proposal(), proposal(created_by=queue.other_id)
    queue.permissions('finance.read', 'document.read', 'finance.review')
    result = queue.queue(scope='related')
    assert result['total'] == 1
    assert result['items'][0]['source_id'] == own.proposal_id
    assert other.proposal_id not in json.dumps(result)
    queue.permissions('document.read')
    assert queue.queue()['total'] == 0


def test_finance_contract_original_closure_is_required_before_existence_is_exposed(finance_queue):
    queue, proposal = finance_queue
    contract = queue.add(ContractCase(title='PRIVATE contract'))
    facility = queue.add(Facility(name='PRIVATE contract facility'))
    original = queue.add(Document(original_filename='PRIVATE contract evidence', storage_path='unused-contract-synthetic',
        sha256='b'*64, mime_type='text/plain', size_bytes=1, building_id=facility.building_id))
    queue.add(ContractDocument(contract_case_id=contract.contract_case_id, document_id=original.document_id,
        document_role='evidence'))
    row = proposal(contract_case_id=contract.contract_case_id)
    queue.permissions('finance.read', 'document.read', 'finance.review')
    assert queue.queue()['total'] == 0
    queue.permissions('finance.read', 'document.read', 'finance.review', 'contract.read')
    assert queue.queue()['total'] == 0
    queue.permissions('finance.read', 'document.read', 'finance.review', 'contract.read', 'facility.read')
    result = queue.queue()
    assert result['total'] == 1
    assert result['items'][0]['source_id'] == row.proposal_id


def test_invoice_related_event_cycle_keeps_every_original_permission(finance_queue):
    queue, proposal = finance_queue
    placeholder = proposal(status='cancelled')
    contract = queue.add(ContractCase(title='PRIVATE cyclic procurement'))
    facility = queue.add(Facility(name='PRIVATE linked inspection facility'))
    original = queue.add(Document(original_filename='PRIVATE linked inspection original', storage_path='unused-linked-inspection',
        sha256='d'*64, mime_type='text/plain', size_bytes=1, building_id=facility.building_id))
    human = dict(status='approved', reviewed_by=queue.user_id, approved_by=queue.user_id, approved_at=now_utc())
    invoice = queue.add(ProcurementEvent(kind='invoice', contract_case_id=contract.contract_case_id,
        document_id=placeholder.document_id, occurred_on=AS_OF, description='PRIVATE invoice',
        amount=Decimal('12000.00'), currency='JPY', **human))
    inspection = queue.add(ProcurementEvent(kind='inspection', contract_case_id=contract.contract_case_id,
        document_id=original.document_id, related_event_id=invoice.event_id, occurred_on=AS_OF,
        description='PRIVATE inspection', amount=Decimal('12000.00'), currency='JPY', **human))
    queue.update(ProcurementEvent, invoice.event_id, related_event_id=inspection.event_id)
    row = proposal(kind='payment', invoice_id=invoice.event_id, contract_case_id=contract.contract_case_id)
    queue.permissions('finance.read', 'finance.review', 'document.read', 'contract.read')
    assert queue.queue()['total'] == 0
    queue.permissions('finance.read', 'finance.review', 'document.read', 'contract.read', 'facility.read')
    result = queue.queue()
    assert result['total'] == 1
    assert result['items'][0]['source_id'] == row.proposal_id
    assert 'facility.read' in result['items'][0]['required_permissions']
    assert {'contract.read', 'facility.read'} <= set(result['items'][0]['required_permissions'])
    queue.permissions('finance.read', 'document.read', 'finance.review', 'facility.read')
    assert queue.queue()['counts'] == {}


def test_own_reviewed_pointer_does_not_grant_approval_and_approved_is_removed(finance_queue):
    queue, proposal = finance_queue
    row = proposal(status='reviewed', reviewed_by=queue.other_id)
    queue.permissions('finance.read', 'document.read')
    result = queue.queue()
    assert result['total'] == 1
    pointer = result['items'][0]
    assert pointer['title'] == '財務確認済・正式承認待ち'
    assert pointer['relationships'] == ['created_by_me']
    assert 'finance.approve' not in pointer['required_permissions']
    queue.update(FinanceProposal, row.proposal_id, status='approved', approved_by=queue.other_id,
        approved_at=now_utc(), version=2)
    assert queue.queue()['total'] == 0


@pytest.mark.parametrize('edge', ['reverses_id', 'commitment_id', 'invoice_id'])
def test_finance_indirect_procurement_evidence_cannot_bypass_source_rights(finance_queue, edge):
    queue, proposal = finance_queue
    contract = queue.add(ContractCase(title='PRIVATE indirect contract'))
    facility = queue.add(Facility(name='PRIVATE indirect facility'))
    original = queue.add(Document(original_filename='PRIVATE indirect evidence', storage_path='unused-indirect-synthetic',
        sha256='c'*64, mime_type='text/plain', size_bytes=1, building_id=facility.building_id))
    human = dict(status='approved', reviewed_by=queue.user_id, approved_by=queue.user_id, approved_at=now_utc())
    if edge == 'invoice_id':
        target = queue.add(ProcurementEvent(kind='invoice', contract_case_id=contract.contract_case_id,
            document_id=original.document_id, occurred_on=AS_OF, description='PRIVATE invoice',
            amount=Decimal('12000.00'), currency='JPY', **human))
        identity = target.event_id
    else:
        target = proposal(kind='commitment', document_id=original.document_id,
            contract_case_id=contract.contract_case_id, **human)
        identity = target.proposal_id
    row = proposal(kind='reversal' if edge == 'reverses_id' else 'payment', **{edge: identity})
    queue.permissions('finance.read', 'document.read', 'finance.review')
    assert queue.queue()['total'] == 0
    queue.permissions('finance.read', 'document.read', 'finance.review', 'contract.read')
    assert queue.queue()['total'] == 0
    queue.permissions('finance.read', 'document.read', 'finance.review', 'contract.read', 'facility.read')
    result = queue.queue()
    assert result['total'] == 1
    assert result['items'][0]['source_id'] == row.proposal_id
