"""Authority must remain valid after a queued financial write acquires its lock."""
import pytest
from sqlalchemy import select
from app.models import User,UserSession,Employee,Permission,RolePermission,now_utc
from app.finance_models import FinanceYear
from test_run_b_finance import client,SessionLocal

@pytest.mark.parametrize('change',['session','permission','employee','password'])
def test_finance_mutation_rechecks_authority_after_wait(client,monkeypatch,change):
    from app import authz
    original=authz.account_change_lock
    def invalidate(db):
        original(db)
        user=db.scalar(select(User).where(User.username=='finance'))
        if change=='session':
            for row in db.scalars(select(UserSession)):row.revoked_at=now_utc()
        elif change=='permission':
            permission=db.scalar(select(Permission).where(Permission.code=='finance.admin'))
            for row in db.scalars(select(RolePermission).where(RolePermission.permission_id==permission.permission_id)):db.delete(row)
        elif change=='employee':db.get(Employee,user.employee_id).active=False
        else:user.password_expires_at=now_utc()
        db.flush()
    monkeypatch.setattr(authz,'account_change_lock',invalidate)
    response=client.post('/finance/years',json={'fiscal_year':2026,'currency':'JPY','decimal_places':0,'reason':'Synthetic Human policy'})
    assert response.status_code in (401,403),response.text
    with SessionLocal() as db:assert db.scalar(select(FinanceYear)) is None


@pytest.mark.parametrize('operation',['create','counterparty','patch','approve'])
def test_legacy_contract_mutation_revalidates_originating_session(client,monkeypatch,operation):
    from app import authz
    from app.models import ContractCase,ContractCounterparty
    contract=client.post('/contracts',json={'title':'Synthetic draft'}).json()
    original=authz.account_change_lock
    def revoked(db):
        original(db)
        for session in db.scalars(select(UserSession)):session.revoked_at=now_utc()
        db.flush()
    monkeypatch.setattr(authz,'account_change_lock',revoked)
    if operation=='create':response=client.post('/contracts',json={'title':'Queued draft'})
    elif operation=='counterparty':response=client.post('/contracts/counterparties',json={'name':'Queued party'})
    elif operation=='patch':response=client.patch('/contracts/'+contract['contract_case_id'],json={'expected_version':1,'title':'Queued edit'})
    else:response=client.post('/contracts/'+contract['contract_case_id']+'/approve',json={'expected_version':1})
    assert response.status_code==401,response.text
    with SessionLocal() as db:
        row=db.get(ContractCase,contract['contract_case_id']);assert row.status=='draft' and row.title=='Synthetic draft'
        assert not db.scalar(select(ContractCase).where(ContractCase.title=='Queued draft'))
        assert not db.scalar(select(ContractCounterparty).where(ContractCounterparty.name=='Queued party'))
