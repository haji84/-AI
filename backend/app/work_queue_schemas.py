"""Closed, read-only pointers into the existing business modules."""
from datetime import date
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

Module = Literal['operational_assets', 'fleet', 'violations', 'inquiries', 'budget']
Relationship = Literal['created_by_me', 'borrowed_by_me', 'available_to_my_role', 'shared_deadline']
SourceType = Literal['asset', 'asset_lot', 'asset_loan', 'vehicle', 'vehicle_service', 'corrective_action', 'inquiry', 'finance_proposal']


class Navigation(BaseModel):
    model_config = ConfigDict(extra='forbid')
    surface: Literal['asset', 'vehicle', 'violation', 'inquiry', 'finance_proposal']
    id: str


class Provenance(BaseModel):
    model_config = ConfigDict(extra='forbid')
    source_api: str
    as_of: date
    source_version: int
    parent_source_type: Literal['asset', 'vehicle', 'violation'] | None = None
    parent_source_id: str | None = None
    parent_source_version: int | None = None


class WorkQueueItem(BaseModel):
    model_config = ConfigDict(extra='forbid')
    key: str
    module: Module
    kind: str
    title: str
    source_type: SourceType
    source_id: str
    source_version: int
    status: str
    due_on: date | None
    overdue: bool
    relationships: list[Relationship]
    required_permissions: list[str]
    navigation: Navigation
    provenance: Provenance


class WorkQueueResponse(BaseModel):
    model_config = ConfigDict(extra='forbid')
    schema_version: Literal['work-queue-v1'] = 'work-queue-v1'
    as_of: date
    through: date
    business_timezone: str
    scope: Literal['all', 'related']
    limit: int
    offset: int
    total: int
    counts: dict[Module, int] = Field(default_factory=dict)
    items: list[WorkQueueItem] = Field(default_factory=list)
