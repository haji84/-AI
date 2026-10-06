"""Shared-contract finance authority, exact money and immutable approved postings."""
from datetime import date, datetime
from decimal import Decimal
from sqlalchemy import BigInteger, Boolean, CheckConstraint, Date, DateTime, ForeignKey, JSON, Numeric, String, Text, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column
from .db import Base
from .models import uuid_str, now_utc

from .finance_money import ExactMoney

def sqlite_money_format(column):
    # Validate canonical decimal characters/positions, never compare monetary TEXT numerically.
    sign=f"(substr({column},1,1) = '-')"
    body=f"typeof({column}) = 'text' AND {column} NOT GLOB '*[^0-9.-]*' AND length({column}) BETWEEN 4 AND 20 AND instr({column},'.') = length({column})-2 AND length({column})-length(replace({column},'.','')) = 1 AND length({column})-length(replace({column},'-','')) <= 1 AND instr({column},'-') IN (0,1) AND instr({column},'.')-1-{sign} BETWEEN 1 AND 16 AND (substr({column},1+{sign},1) <> '0' OR instr({column},'.') = 2+{sign})"
    return CheckConstraint(body,name='ck_finance_'+column+'_canonical').ddl_if(dialect='sqlite')

class Versioned:
    version: Mapped[int] = mapped_column(BigInteger, nullable=False, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=now_utc)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=now_utc)

DEFAULT_LEVELS=[{'code':c,'label':label} for c,label in [('kan','款'),('kou','項'),('moku','目'),('setsu','節'),('saisetsu','細節')]]

class FinanceYear(Versioned, Base):
    __tablename__ = 'finance_years'
    year_id: Mapped[str] = mapped_column(Uuid(as_uuid=False), primary_key=True, default=uuid_str)
    fiscal_year: Mapped[int] = mapped_column(BigInteger, nullable=False, unique=True)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    decimal_places: Mapped[int] = mapped_column(BigInteger, nullable=False)
    require_invoice_on_payment: Mapped[bool] = mapped_column(Boolean,nullable=False,default=False)
    account_levels: Mapped[list] = mapped_column(JSON,nullable=False,default=lambda:[dict(level) for level in DEFAULT_LEVELS])
    status: Mapped[str] = mapped_column(String(20), nullable=False, default='draft')
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    approved_by: Mapped[str | None] = mapped_column(ForeignKey('app_users.user_id'))
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    __table_args__ = (CheckConstraint("currency IN ('JPY','USD','EUR') AND decimal_places BETWEEN 0 AND 2", name='ck_finance_year_policy'),)

class BudgetAccount(Versioned, Base):
    __tablename__ = 'finance_accounts'
    account_id: Mapped[str] = mapped_column(Uuid(as_uuid=False), primary_key=True, default=uuid_str)
    year_id: Mapped[str] = mapped_column(ForeignKey('finance_years.year_id'), nullable=False, index=True)
    parent_id: Mapped[str | None] = mapped_column(ForeignKey('finance_accounts.account_id'))
    level: Mapped[int] = mapped_column(BigInteger, nullable=False)
    code: Mapped[str] = mapped_column(String(100), nullable=False)
    name: Mapped[str] = mapped_column(String(300), nullable=False)
    __table_args__ = (UniqueConstraint('year_id','code',name='uq_finance_account_code'), CheckConstraint('level BETWEEN 1 AND 32',name='ck_finance_account_level'))

class FinanceProposal(Versioned, Base):
    __tablename__ = 'finance_proposals'
    proposal_id: Mapped[str] = mapped_column(Uuid(as_uuid=False), primary_key=True, default=uuid_str)
    kind: Mapped[str] = mapped_column(String(30), nullable=False)
    account_id: Mapped[str] = mapped_column(ForeignKey('finance_accounts.account_id'), nullable=False, index=True)
    to_account_id: Mapped[str | None] = mapped_column(ForeignKey('finance_accounts.account_id'))
    amount: Mapped[Decimal] = mapped_column(ExactMoney(), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    document_id: Mapped[str] = mapped_column(ForeignKey('documents.document_id'), nullable=False)
    contract_case_id: Mapped[str | None] = mapped_column(ForeignKey('contract_cases.contract_case_id'))
    commitment_id: Mapped[str | None] = mapped_column(ForeignKey('finance_proposals.proposal_id'))
    invoice_id: Mapped[str | None] = mapped_column(ForeignKey('finance_procurement_events.event_id'))
    reverses_id: Mapped[str | None] = mapped_column(ForeignKey('finance_proposals.proposal_id'))
    idempotency_key: Mapped[str] = mapped_column(String(200), unique=True, nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default='draft')
    review_snapshot: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    reviewed_by: Mapped[str | None] = mapped_column(ForeignKey('app_users.user_id'))
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    approved_by: Mapped[str | None] = mapped_column(ForeignKey('app_users.user_id'))
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_by: Mapped[str] = mapped_column(ForeignKey('app_users.user_id'), nullable=False)
    __table_args__ = (CheckConstraint("kind IN ('initial','amendment','transfer','commitment','payment','reversal')",name='ck_finance_proposal_kind'),CheckConstraint("status IN ('draft','reviewed','approved','cancelled')",name='ck_finance_proposal_status'),CheckConstraint("amount >= 0 OR kind='amendment'",name='ck_finance_proposal_amount').ddl_if(dialect='postgresql'),CheckConstraint("substr(amount,1,1) <> '-' OR amount='-0.00' OR kind='amendment'",name='ck_finance_proposal_sign').ddl_if(dialect='sqlite'),sqlite_money_format('amount'),CheckConstraint("status <> 'approved' OR (approved_by IS NOT NULL AND reviewed_by IS NOT NULL AND approved_at IS NOT NULL)",name='ck_finance_proposal_human'))

class FinanceJournal(Base):
    __tablename__ = 'finance_journal'
    journal_id: Mapped[str] = mapped_column(Uuid(as_uuid=False), primary_key=True, default=uuid_str)
    version: Mapped[int] = mapped_column(BigInteger, nullable=False, default=1)
    proposal_id: Mapped[str] = mapped_column(ForeignKey('finance_proposals.proposal_id'), nullable=False, index=True)
    account_id: Mapped[str] = mapped_column(ForeignKey('finance_accounts.account_id'), nullable=False, index=True)
    allocated: Mapped[Decimal] = mapped_column(ExactMoney(), nullable=False, default=Decimal('0'))
    reserved: Mapped[Decimal] = mapped_column(ExactMoney(), nullable=False, default=Decimal('0'))
    spent: Mapped[Decimal] = mapped_column(ExactMoney(), nullable=False, default=Decimal('0'))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=now_utc)
    __table_args__ = (UniqueConstraint('proposal_id','account_id',name='uq_finance_posting_account'),sqlite_money_format('allocated'),sqlite_money_format('reserved'),sqlite_money_format('spent'))

class ProcurementProfile(Versioned, Base):
    __tablename__ = 'finance_contract_profiles'
    profile_id: Mapped[str] = mapped_column(Uuid(as_uuid=False), primary_key=True, default=uuid_str)
    contract_case_id: Mapped[str] = mapped_column(ForeignKey('contract_cases.contract_case_id'), nullable=False, unique=True)
    year_id: Mapped[str] = mapped_column(ForeignKey('finance_years.year_id'), nullable=False)
    renewal_on: Mapped[date | None] = mapped_column(Date)
    approved_evidence: Mapped[dict | None] = mapped_column(JSON)

class FinanceCandidate(Versioned, Base):
    __tablename__ = 'finance_candidates'
    candidate_id: Mapped[str] = mapped_column(Uuid(as_uuid=False), primary_key=True, default=uuid_str)
    kind: Mapped[str] = mapped_column(String(20), nullable=False)
    year_id: Mapped[str] = mapped_column(ForeignKey('finance_years.year_id'), nullable=False)
    account_id: Mapped[str] = mapped_column(ForeignKey('finance_accounts.account_id'), nullable=False)
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    amount: Mapped[Decimal] = mapped_column(ExactMoney(), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    document_id: Mapped[str] = mapped_column(ForeignKey('documents.document_id'), nullable=False)
    contract_case_id: Mapped[str | None] = mapped_column(ForeignKey('contract_cases.contract_case_id'))
    counterparty_id: Mapped[str | None] = mapped_column(ForeignKey('contract_counterparties.counterparty_id'))
    status: Mapped[str] = mapped_column(String(20), nullable=False, default='candidate')
    review_snapshot: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    reviewed_by: Mapped[str | None] = mapped_column(ForeignKey('app_users.user_id'))
    reason: Mapped[str | None] = mapped_column(Text)
    __table_args__ = (CheckConstraint("kind IN ('quote','request','estimate') AND amount >= 0",name='ck_finance_candidate').ddl_if(dialect='postgresql'),CheckConstraint("kind IN ('quote','request','estimate')",name='ck_finance_candidate_kind').ddl_if(dialect='sqlite'),CheckConstraint("substr(amount,1,1) <> '-' OR amount='-0.00'",name='ck_finance_candidate_sign').ddl_if(dialect='sqlite'),sqlite_money_format('amount'))

class FinanceContractAmendment(Versioned, Base):
    __tablename__ = 'finance_contract_amendments'
    amendment_id: Mapped[str] = mapped_column(Uuid(as_uuid=False), primary_key=True, default=uuid_str)
    contract_case_id: Mapped[str] = mapped_column(ForeignKey('contract_cases.contract_case_id'), nullable=False,index=True)
    expected_contract_version: Mapped[int] = mapped_column(BigInteger,nullable=False)
    amount: Mapped[Decimal] = mapped_column(ExactMoney(),nullable=False)
    end_date: Mapped[date | None] = mapped_column(Date)
    document_id: Mapped[str] = mapped_column(ForeignKey('documents.document_id'),nullable=False)
    reason: Mapped[str] = mapped_column(Text,nullable=False)
    status: Mapped[str] = mapped_column(String(20),nullable=False,default='draft')
    review_snapshot: Mapped[dict] = mapped_column(JSON,nullable=False,default=dict)
    reviewed_by: Mapped[str | None] = mapped_column(ForeignKey('app_users.user_id'))
    approved_by: Mapped[str | None] = mapped_column(ForeignKey('app_users.user_id'))
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    __table_args__=(CheckConstraint('amount >= 0',name='ck_finance_contract_amendment_amount').ddl_if(dialect='postgresql'),CheckConstraint("substr(amount,1,1) <> '-' OR amount='-0.00'",name='ck_finance_amendment_sign').ddl_if(dialect='sqlite'),sqlite_money_format('amount'))

class FinanceImportPreview(Versioned, Base):
    __tablename__ = 'finance_import_previews'
    preview_id: Mapped[str] = mapped_column(Uuid(as_uuid=False),primary_key=True,default=uuid_str)
    dataset: Mapped[str] = mapped_column(String(30),nullable=False)
    file_sha256: Mapped[str] = mapped_column(String(64),nullable=False)
    source_document_id: Mapped[str] = mapped_column(ForeignKey('documents.document_id'),nullable=False)
    row_data: Mapped[list] = mapped_column(JSON,nullable=False)
    created_by: Mapped[str] = mapped_column(ForeignKey('app_users.user_id'),nullable=False)
    status: Mapped[str] = mapped_column(String(20),nullable=False,default='preview')
    applied_ids: Mapped[list] = mapped_column(JSON,nullable=False,default=list)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True),nullable=False)
    __table_args__=(UniqueConstraint('dataset','file_sha256',name='uq_finance_import_hash'),)

class FinanceRenderedForm(Versioned, Base):
    __tablename__ = 'finance_rendered_forms'
    rendered_id: Mapped[str] = mapped_column(Uuid(as_uuid=False),primary_key=True,default=uuid_str)
    proposal_id: Mapped[str] = mapped_column(ForeignKey('finance_proposals.proposal_id'),nullable=False)
    form_template_id: Mapped[str] = mapped_column(ForeignKey('form_templates.form_template_id'),nullable=False)
    document_id: Mapped[str] = mapped_column(ForeignKey('documents.document_id'),nullable=False)
    manifest: Mapped[dict] = mapped_column(JSON,nullable=False)
    created_by: Mapped[str] = mapped_column(ForeignKey('app_users.user_id'),nullable=False)

class ProcurementEvent(Versioned, Base):
    __tablename__='finance_procurement_events'
    event_id: Mapped[str] = mapped_column(Uuid(as_uuid=False),primary_key=True,default=uuid_str)
    contract_case_id: Mapped[str] = mapped_column(ForeignKey('contract_cases.contract_case_id'),nullable=False,index=True)
    kind: Mapped[str] = mapped_column(String(20),nullable=False)
    occurred_on: Mapped[date] = mapped_column(Date,nullable=False)
    description: Mapped[str] = mapped_column(Text,nullable=False)
    amount: Mapped[Decimal] = mapped_column(ExactMoney(),nullable=False,default=Decimal('0'))
    currency: Mapped[str] = mapped_column(String(3),nullable=False)
    document_id: Mapped[str] = mapped_column(ForeignKey('documents.document_id'),nullable=False)
    related_event_id: Mapped[str | None] = mapped_column(ForeignKey('finance_procurement_events.event_id'))
    status: Mapped[str] = mapped_column(String(20),nullable=False,default='draft')
    review_snapshot: Mapped[dict] = mapped_column(JSON,nullable=False,default=dict)
    reviewed_by: Mapped[str | None] = mapped_column(ForeignKey('app_users.user_id'))
    approved_by: Mapped[str | None] = mapped_column(ForeignKey('app_users.user_id'))
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    reason: Mapped[str | None] = mapped_column(Text)
    __table_args__=(CheckConstraint("kind IN ('delivery','inspection','invoice') AND amount >= 0",name='ck_finance_procurement_event').ddl_if(dialect='postgresql'),CheckConstraint("kind IN ('delivery','inspection','invoice')",name='ck_finance_event_kind').ddl_if(dialect='sqlite'),CheckConstraint("substr(amount,1,1) <> '-' OR amount='-0.00'",name='ck_finance_event_sign').ddl_if(dialect='sqlite'),sqlite_money_format('amount'),CheckConstraint("status IN ('draft','reviewed','approved','cancelled')",name='ck_finance_event_status'),CheckConstraint("status <> 'approved' OR (reviewed_by IS NOT NULL AND approved_by IS NOT NULL AND approved_at IS NOT NULL)",name='ck_finance_event_human'))
