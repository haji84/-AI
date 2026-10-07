"""Human-entered facts. Decimal strings preserve precision without unit conversion."""
from datetime import date
from decimal import Decimal
import re
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class Strict(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)

    @field_validator('building_id', 'document_ids', 'legal_source_version_ids', 'inspection_ids', 'violation_case_ids', check_fields=False)
    @classmethod
    def identities(cls, value):
        if value is None:
            return value
        return list(dict.fromkeys(str(UUID(v)) for v in value)) if isinstance(value, list) else str(UUID(value))


class Material(Strict):
    name: str = Field(min_length=1, max_length=500)
    category_label: str = Field(default='', max_length=500)
    quantity: str = Field(min_length=1, max_length=25, strict=True)
    quantity_unit: str = Field(min_length=1, max_length=80)
    capacity: str | None = Field(default=None, max_length=25, strict=True)
    capacity_unit: str | None = Field(default=None, min_length=1, max_length=80)

    @field_validator('quantity', 'capacity')
    @classmethod
    def exact_decimal(cls, value):
        if value is not None:
            if not re.fullmatch(r'(?:0|[1-9][0-9]{0,17})(?:\.[0-9]{1,6})?', value) or not Decimal(value).is_finite():
                raise ValueError('use a nonnegative decimal string with at most 18 integer and 6 fractional digits; no rounding or conversion')
        return value

    @model_validator(mode='after')
    def paired_capacity(self):
        if (self.capacity is None) != (self.capacity_unit is None):
            raise ValueError('capacity and capacity_unit must be supplied together')
        return self


class InstallationInput(Strict):
    building_id: str
    name: str = Field(min_length=1, max_length=500)
    category_label: str = Field(min_length=1, max_length=500)
    location_detail: str = Field(default='', max_length=2000)
    notes: str = Field(default='', max_length=10000)
    materials: list[Material] = Field(default_factory=list, max_length=100)


class InstallationPatch(Strict):
    expected_version: int = Field(ge=1)
    reason: str = Field(min_length=1, max_length=4000)
    name: str | None = Field(default=None, min_length=1, max_length=500)
    category_label: str | None = Field(default=None, min_length=1, max_length=500)
    location_detail: str | None = Field(default=None, max_length=2000)
    notes: str | None = Field(default=None, max_length=10000)
    materials: list[Material] | None = Field(default=None, max_length=100)


class InstallationRetire(Strict):
    expected_version: int = Field(ge=1)
    reason: str = Field(min_length=1, max_length=4000)
    human_acknowledged: Literal[True]


class RecordInput(Strict):
    expected_installation_version: int = Field(ge=1)
    kind: Literal['permit', 'notification', 'change']
    title: str = Field(min_length=1, max_length=500)
    reference_no: str | None = Field(default=None, max_length=400)
    recorded_on: date
    due_on: date | None = None
    notes: str = Field(default='', max_length=10000)
    document_ids: list[str] = Field(default_factory=list, max_length=100)
    legal_source_version_ids: list[str] = Field(default_factory=list, max_length=100)
    inspection_ids: list[str] = Field(default_factory=list, max_length=100)
    violation_case_ids: list[str] = Field(default_factory=list, max_length=100)


class RecordRevision(Strict):
    expected_installation_version: int = Field(ge=1)
    expected_version: int = Field(ge=1)
    reason: str = Field(min_length=1, max_length=4000)


class RecordAction(RecordRevision):
    human_acknowledged: Literal[True]


class RecordPatch(RecordRevision):
    kind: Literal['permit', 'notification', 'change'] | None = None
    title: str | None = Field(default=None, min_length=1, max_length=500)
    reference_no: str | None = Field(default=None, max_length=400)
    recorded_on: date | None = None
    due_on: date | None = None
    notes: str | None = Field(default=None, max_length=10000)
    document_ids: list[str] | None = Field(default=None, max_length=100)
    legal_source_version_ids: list[str] | None = Field(default=None, max_length=100)
    inspection_ids: list[str] | None = Field(default=None, max_length=100)
    violation_case_ids: list[str] | None = Field(default=None, max_length=100)
