"""Bounded audit requests. No free-text notes in ordinary workflow events."""
from datetime import date, datetime
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StrictBool, StrictFloat, StrictInt, StrictStr, field_validator, model_validator

from .emergency_acceptance_schemas import ReadState
from .emergency_mapping import Identifier as FieldIdentifier
from .emergency_rule_schemas import Identifier as RuleIdentifier


class StrictInput(BaseModel):
    model_config = ConfigDict(extra='forbid', hide_input_in_errors=True, allow_inf_nan=False)


class VersionInput(StrictInput):
    expected_version: Annotated[StrictInt, Field(ge=1)]


class FieldValue(StrictInput):
    field_id: FieldIdentifier
    state: ReadState
    value: StrictBool | StrictInt | StrictFloat | Annotated[StrictStr, Field(max_length=8000)] | None = None

    @model_validator(mode='after')
    def unconfirmed_value(self):
        if self.state == 'confirmed' and 'value' not in self.model_fields_set:
            raise ValueError('Explicit value, including deliberate null, is required.')
        if self.state != 'confirmed' and self.value is not None:
            raise ValueError('Unconfirmed values cannot be asserted.')
        return self


class ConfirmFields(VersionInput):
    confirmed_from_original: StrictBool
    fields: list[FieldValue] = Field(min_length=1, max_length=200)

    @model_validator(mode='after')
    def unique_fields(self):
        if self.confirmed_from_original is not True:
            raise ValueError('Original confirmation is required.')
        if len({item.field_id for item in self.fields}) != len(self.fields):
            raise ValueError('Duplicate field.')
        return self


class MapRevision(VersionInput):
    profile_id: UUID


class CheckRevision(VersionInput):
    rule_set_id: UUID | None = None
    mode: Literal['candidate', 'approved'] = 'candidate'
    as_of: date

    @field_validator('as_of', mode='before')
    @classmethod
    def exact_date(cls, value):
        if type(value) is date:
            return value
        if not isinstance(value, str) or len(value) != 10 or value[4] != '-' or value[7] != '-':
            raise ValueError('Explicit ISO date is required.')
        return date.fromisoformat(value)


class Disposition(StrictInput):
    rule_id: RuleIdentifier
    decision: Literal['correction_needed', 'false_alarm', 'exception', 'unresolved']
    reason_code: Literal['missing', 'inconsistent', 'code_selection', 'format', 'reading_error', 'local_rule', 'unknown'] = 'unknown'


class SaveDispositions(VersionInput):
    decisions: list[Disposition] = Field(min_length=1, max_length=500)


class AssignReviewer(VersionInput):
    reviewer_id: UUID


class SaveConfiguration(StrictInput):
    request_id: UUID
    definition: dict
    source_id: UUID | None = None
    supersedes_id: UUID | None = None


class ImpactInput(StrictInput):
    report_ids: list[UUID] = Field(min_length=1, max_length=100)


class ApproveConfiguration(VersionInput):
    source_verified: StrictBool
    mapping_verified: StrictBool

    @model_validator(mode='after')
    def explicit_approval(self):
        if self.source_verified is not True or self.mapping_verified is not True:
            raise ValueError('Source and mapping confirmation are required.')
        return self


class StudyEvent(StrictInput):
    cohort: Literal['baseline', 'assisted']
    activity_kind: Literal['transport', 'nontransport', 'transfer', 'unknown'] = 'unknown'


class SubmittedEvent(StrictInput):
    occurred_at: datetime


class FollowupEvent(StrictInput):
    complete: StrictBool
    corrected_after_submission: StrictBool | None = None
    work_complete: StrictBool = False


class WorkEvent(StrictInput):
    stage: Literal['import', 'read_review', 'check', 'correction', 'recheck', 'second_review', 'post_submission']
    started_at: datetime
    ended_at: datetime


class TruthItem(StrictInput):
    rule_id: RuleIdentifier
    truth: Literal['error', 'correct', 'unknown', 'not_applicable']
    error_id: UUID | None = None
    verified_read_state: ReadState | None = None
    detected_in_run_ids: list[UUID] = Field(default_factory=list, max_length=50)

    @model_validator(mode='after')
    def truth_error(self):
        if (self.truth == 'error') != (self.error_id is not None):
            raise ValueError('Error identity must match independent truth.')
        return self


class MissedError(StrictInput):
    opportunity_id: UUID
    error_id: UUID
    read_state: ReadState
    verified_read_state: ReadState


class TruthEvent(StrictInput):
    run_id: UUID
    complete: StrictBool = False
    whole_report_checked: StrictBool = False
    items: list[TruthItem] = Field(default_factory=list, max_length=500)
    missed_errors: list[MissedError] = Field(default_factory=list, max_length=500)


class SaveEvent(VersionInput):
    event_id: UUID
    supersedes_event_id: UUID | None = None
    kind: Literal['study', 'submitted', 'followup', 'work_interval', 'truth_review']
    payload: dict


class MeasurementExport(StrictInput):
    report_ids: list[UUID] = Field(min_length=1, max_length=100)


class VisionInput(VersionInput):
    page: Annotated[StrictInt, Field(ge=1, le=50)]


class PatternInput(StrictInput):
    report_ids: list[UUID] = Field(min_length=1, max_length=1000)
