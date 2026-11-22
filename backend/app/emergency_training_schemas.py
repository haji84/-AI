"""Bounded independent teacher records; never infer labels from model agreement."""
from datetime import date
from typing import Annotated, Literal
from uuid import UUID

from pydantic import Field, StrictBool, StrictInt, StrictStr, field_validator, model_validator

from .emergency_acceptance_schemas import ReadState
from .emergency_audit_schemas import StrictInput, VersionInput, CheckRevision
from .emergency_mapping import Identifier, _bbox

Task = Literal['transcription', 'content_review']
Split = Literal['train', 'validation', 'holdout']
Digest = Annotated[StrictStr, Field(pattern=r'^[0-9a-f]{64}$')]
Text = Annotated[StrictStr, Field(max_length=2000)]


class RegisterFamily(StrictInput):
    family_id: UUID
    report_ids: list[UUID] = Field(min_length=1, max_length=100)

    @model_validator(mode='after')
    def unique_reports(self):
        if len(set(self.report_ids)) != len(self.report_ids):
            raise ValueError('Duplicate report.')
        return self


class Annotation(StrictInput):
    field_id: Identifier
    page: Annotated[StrictInt, Field(ge=1, le=50)]
    bbox: list[float] | None
    read_state: ReadState
    truth: Literal['error', 'correct', 'unknown', 'not_applicable']
    error_id: UUID | None = None
    observed_text: Text | None
    allowed_corrections: list[Text] = Field(default_factory=list, max_length=5)
    evidence: Text

    @field_validator('bbox', mode='before')
    @classmethod
    def region(cls, value):
        return _bbox(value) if value is not None else None

    @model_validator(mode='after')
    def explicit_truth(self):
        if (self.truth == 'error') != (self.error_id is not None):
            raise ValueError('Independent error identity required.')
        if self.truth != 'error' and self.allowed_corrections:
            raise ValueError('Corrections require an independently identified error.')
        if self.read_state != 'confirmed' and self.truth not in {'unknown', 'not_applicable'}:
            raise ValueError('Unconfirmed reading is not a teacher label.')
        if self.read_state == 'confirmed' and (self.observed_text is None or self.bbox is None):
            raise ValueError('Explicit transcription and position required, including a deliberate blank.')
        if self.truth in {'error', 'correct'} and not self.evidence.strip():
            raise ValueError('Independent source evidence required.')
        if len(set(self.allowed_corrections)) != len(self.allowed_corrections):
            raise ValueError('Duplicate correction.')
        return self


class RegisterTruth(VersionInput):
    request_id: UUID
    supersedes_id: UUID | None = None
    task: Task
    basis: Literal['as_written', 'contemporaneous', 'current']
    form_as_of: date
    as_of: date
    rule_set_id: UUID | None = None
    source_verified: StrictBool
    whole_scope_checked: StrictBool
    annotations: list[Annotation] = Field(min_length=1, max_length=200)

    @field_validator('as_of', 'form_as_of', mode='before')
    @classmethod
    def exact_date(cls, value):
        return CheckRevision.exact_date(value)

    @model_validator(mode='after')
    def independent_source(self):
        if not self.source_verified:
            raise ValueError('Independent source review required.')
        if self.task == 'transcription' and (self.basis != 'as_written' or self.rule_set_id):
            raise ValueError('Transcription records what was written, not a rule verdict.')
        if self.task == 'content_review' and (self.basis == 'as_written' or not self.rule_set_id):
            raise ValueError('Content review requires an explicit rule basis and version.')
        scopes = {(a.field_id, a.page, tuple(a.bbox) if a.bbox is not None else None) for a in self.annotations}
        if len(scopes) != len(self.annotations):
            raise ValueError('Duplicate annotated scope.')
        if self.basis == 'contemporaneous' and self.as_of != self.form_as_of:
            raise ValueError('Contemporaneous review uses the original applicable date.')
        if self.basis == 'current' and self.as_of < self.form_as_of:
            raise ValueError('Current review cannot precede the original applicable date.')
        return self


class FamilySplit(StrictInput):
    family_id: UUID
    split: Split


class RegisterDataset(StrictInput):
    request_id: UUID
    supersedes_id: UUID | None = None
    task: Task
    preprocessing_sha256: Digest
    truth_ids: list[UUID] = Field(min_length=3, max_length=100)
    family_splits: list[FamilySplit] = Field(min_length=3, max_length=100)

    @model_validator(mode='after')
    def fixed_partition(self):
        if len(set(self.truth_ids)) != len(self.truth_ids):
            raise ValueError('Duplicate truth.')
        if len({f.family_id for f in self.family_splits}) != len(self.family_splits):
            raise ValueError('A family cannot cross partitions.')
        if {f.split for f in self.family_splits} != {'train', 'validation', 'holdout'}:
            raise ValueError('All partitions must be explicitly represented.')
        return self
