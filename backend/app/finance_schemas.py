from datetime import date
from decimal import Decimal
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, field_validator

class Strict(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)
class Version(Strict):
    expected_version: int = Field(ge=1)
class Action(Version):
    reason: str = Field(min_length=1,max_length=4000)
from .finance_models import DEFAULT_LEVELS
class AccountLevel(Strict):
    code: str = Field(min_length=1,max_length=50)
    label: str = Field(min_length=1,max_length=80)
class HierarchyPolicy(Strict):
    @field_validator('account_levels',check_fields=False)
    @classmethod
    def unique_levels(cls,values):
        if values is not None and len({v.code for v in values})!=len(values):raise ValueError('hierarchy level codes must be unique')
        return values

class YearInput(HierarchyPolicy):
    fiscal_year: int = Field(ge=1900,le=2200)
    currency: Literal['JPY','USD','EUR']
    decimal_places: int = Field(ge=0,le=2)
    reason: str = Field(min_length=1,max_length=4000)
    require_invoice_on_payment: bool = False
    account_levels: list[AccountLevel] = Field(default_factory=lambda:[AccountLevel(**level) for level in DEFAULT_LEVELS],min_length=1,max_length=32)
class YearPatch(Version,HierarchyPolicy):
    currency: Literal['JPY','USD','EUR'] | None = None
    decimal_places: int | None = Field(None,ge=0,le=2)
    reason: str | None = Field(None,min_length=1,max_length=4000)
    require_invoice_on_payment: bool | None = None
    account_levels: list[AccountLevel] | None = Field(None,min_length=1,max_length=32)
class AccountInput(Strict):
    year_id: str
    parent_id: str | None = None
    level: int = Field(ge=1,le=32)
    code: str = Field(min_length=1,max_length=100)
    name: str = Field(min_length=1,max_length=300)
class AccountPatch(Version):
    name: str = Field(min_length=1,max_length=300)

class ProposalInput(Strict):
    kind: Literal['initial','amendment','transfer','commitment','payment','reversal']
    account_id: str
    to_account_id: str | None = None
    amount: Decimal = Field(max_digits=18,decimal_places=2,allow_inf_nan=False)
    currency: Literal['JPY','USD','EUR']
    document_id: str
    contract_case_id: str | None = None
    commitment_id: str | None = None
    invoice_id: str | None = None
    reverses_id: str | None = None
    idempotency_key: str = Field(min_length=1,max_length=200)
    reason: str = Field(min_length=1,max_length=4000)
    @field_validator('amount',mode='before')
    @classmethod
    def exact_money(cls,value):
        if isinstance(value,float):raise ValueError('money must be an exact decimal string or integer')
        return value
class ProposalPatch(Version):
    amount: Decimal | None = Field(None,max_digits=18,decimal_places=2,allow_inf_nan=False)
    reason: str | None = Field(None,min_length=1,max_length=4000)
    document_id: str | None = None
    @field_validator('amount',mode='before')
    @classmethod
    def exact_money(cls,value):return ProposalInput.exact_money(value)

class CounterpartyInput(Strict):
    name: str = Field(min_length=1,max_length=500)
    registration_no: str | None = None
    address: str | None = None
    contact: str | None = None
class CounterpartyPatch(Version):
    name: str | None = Field(None,min_length=1,max_length=500)
    registration_no: str | None = None
    address: str | None = None
    contact: str | None = None
    active: bool | None = None
class ContractInput(Strict):
    title: str = Field(min_length=1,max_length=500)
    contract_no: str | None = None
    counterparty_id: str | None = None
    contract_method: str | None = None
    amount: Decimal = Field(ge=0,max_digits=18,decimal_places=2,allow_inf_nan=False)
    currency: Literal['JPY','USD','EUR']
    year_id: str
    document_id: str
    start_date: date | None = None
    end_date: date | None = None
    renewal_on: date | None = None
    @field_validator('amount',mode='before')
    @classmethod
    def exact_money(cls,value):return ProposalInput.exact_money(value)
class ProfileInput(Version):
    year_id: str
    renewal_on: date | None = None
class DocumentLink(Strict):
    document_id: str
    document_role: str = Field(min_length=1,max_length=100)
class CandidateInput(Strict):
    kind: Literal['quote','request','estimate']
    year_id: str
    account_id: str
    title: str = Field(min_length=1,max_length=300)
    amount: Decimal = Field(ge=0,max_digits=18,decimal_places=2,allow_inf_nan=False)
    currency: Literal['JPY','USD','EUR']
    document_id: str
    contract_case_id: str | None = None
    counterparty_id: str | None = None
    @field_validator('amount',mode='before')
    @classmethod
    def exact_money(cls,value):return ProposalInput.exact_money(value)
class AmendmentInput(Strict):
    expected_contract_version: int = Field(ge=1)
    amount: Decimal = Field(ge=0,max_digits=18,decimal_places=2,allow_inf_nan=False)
    end_date: date | None = None
    document_id: str
    reason: str = Field(min_length=1,max_length=4000)
    @field_validator('amount',mode='before')
    @classmethod
    def exact_money(cls,value):return ProposalInput.exact_money(value)

class ImportConfirm(Version):
    file_sha256: str = Field(pattern='^[a-f0-9]{64}$')
class RenderInput(Strict):
    form_template_id: str

class ContractPatch(Version):
    title: str | None = Field(None,min_length=1,max_length=500)
    contract_method: str | None = None
    amount: Decimal | None = Field(None,ge=0,max_digits=18,decimal_places=2,allow_inf_nan=False)
    start_date: date | None = None
    end_date: date | None = None
    @field_validator('amount',mode='before')
    @classmethod
    def exact_money(cls,value):return ProposalInput.exact_money(value)

class CandidatePatch(Version):
    title: str | None = Field(None,min_length=1,max_length=300)
    amount: Decimal | None = Field(None,ge=0,max_digits=18,decimal_places=2,allow_inf_nan=False)
    document_id: str | None = None
    @field_validator('amount',mode='before')
    @classmethod
    def exact_money(cls,value):return ProposalInput.exact_money(value)

class EventInput(Strict):
    contract_case_id: str
    kind: Literal['delivery','inspection','invoice']
    occurred_on: date
    description: str = Field(min_length=1,max_length=4000)
    amount: Decimal = Field(default=Decimal('0'),ge=0,max_digits=18,decimal_places=2,allow_inf_nan=False)
    currency: Literal['JPY','USD','EUR']
    document_id: str
    related_event_id: str | None = None
    @field_validator('amount',mode='before')
    @classmethod
    def exact_money(cls,value):return ProposalInput.exact_money(value)
class EventPatch(Version):
    description: str | None = Field(None,min_length=1,max_length=4000)
    occurred_on: date | None = None
    amount: Decimal | None = Field(None,ge=0,max_digits=18,decimal_places=2,allow_inf_nan=False)
    document_id: str | None = None
    @field_validator('amount',mode='before')
    @classmethod
    def exact_money(cls,value):return ProposalInput.exact_money(value)

class DocumentDiff(Strict):
    before_document_id: str
    after_document_id: str
class Calculation(Strict):
    amounts: list[Decimal] = Field(min_length=1,max_length=1000)
    @field_validator('amounts',mode='before')
    @classmethod
    def exact_values(cls,values):
        return [ProposalInput.exact_money(v) for v in values]
    @field_validator('amounts')
    @classmethod
    def supported_values(cls,values):
        if any(not v.is_finite() or abs(v)>=Decimal('10000000000000000') or v!=v.quantize(Decimal('.01')) for v in values):raise ValueError('finite exact NUMERIC(18,2) operands required')
        return values
