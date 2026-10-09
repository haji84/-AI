"""Read-only financial work pointers; no ledger values or original prose."""
from sqlalchemy import select

from .authz import permission_codes
from .finance_models import FinanceProposal
from .inquiries_service import permission_closure


def finance_work_items(db, user, as_of, make_item):
    for row in db.scalars(select(FinanceProposal).where(
            FinanceProposal.status.in_(('draft', 'reviewed')))):
        # A pointer never substitutes for the source API's own live authorization.
        db.refresh(row)
        if row.status not in ('draft', 'reviewed'):
            continue
        nodes = [('source', 'finance', row.proposal_id)]
        required = {'document.read'} | permission_closure(db, nodes)
        permissions = permission_codes(db, user.user_id)
        if not required <= permissions:
            continue
        relationships = ['created_by_me'] if row.created_by == user.user_id else []
        action = 'finance.review' if row.status == 'draft' else 'finance.approve'
        kind, label = 'draft', '財務草案' if row.status == 'draft' else '財務確認済・正式承認待ち'
        if action in permissions:
            required.add(action)
            relationships.append('available_to_my_role')
            kind, label = ('review', '財務根拠確認') if row.status == 'draft' else ('approval', '財務正式承認')
        if not relationships or not required <= permission_codes(db, user.user_id):
            continue
        yield make_item(module='budget', kind=kind, title=label,
            source_type='finance_proposal', source=row, status=row.status, as_of=as_of,
            permissions=required, navigation={'surface': 'finance_proposal', 'id': row.proposal_id},
            source_api='/finance/proposals/'+row.proposal_id, relationships=relationships)
