"""Closed notice fields; no client Role IDs, permissions or status transitions."""
from datetime import date
from typing import Literal
from uuid import UUID
from pydantic import BaseModel, ConfigDict, Field, StrictBool, field_validator, model_validator


class Closed(BaseModel):
    model_config = ConfigDict(extra='forbid')


class NoticeFields(Closed):
    employee_code: str = Field(min_length=1, max_length=100)
    organization_code: str = Field(min_length=1, max_length=100)
    title: str = Field(min_length=1, max_length=200)
    kind: Literal['primary', 'secondary'] = 'primary'
    valid_from: date
    valid_to: date | None = None
    mode: Literal['assignment', 'transfer'] = 'transfer'

    @model_validator(mode='after')
    def valid_dates(self):
        if self.valid_to is not None and self.valid_to < self.valid_from:
            raise ValueError('end date precedes start date')
        if self.mode == 'transfer' and self.kind != 'primary':
            raise ValueError('transfer requires primary assignment')
        return self


class NoticeCreate(Closed):
    document_id: UUID


class Reason(Closed):
    expected_version: int = Field(ge=1)
    reason: str = Field(min_length=1, max_length=1000)

    @field_validator('reason')
    @classmethod
    def nonblank(cls, value):
        if not value.strip():
            raise ValueError('Human reason required')
        return value.strip()


class NoticePatch(Reason):
    proposed: NoticeFields
    source_quote: str = Field(min_length=1, max_length=32000)


class NoticeDecision(Reason):
    acknowledged: StrictBool

    @field_validator('acknowledged')
    @classmethod
    def explicit_true(cls, value):
        if not value:
            raise ValueError('explicit Human acknowledgement required')
        return value
