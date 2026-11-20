"""Narrow transport contracts; source values are allowed only in transient checks."""
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .emergency_acceptance_schemas import EvaluationInput
from .emergency_review_core import Observation


class Strict(BaseModel):
    model_config = ConfigDict(extra='forbid', hide_input_in_errors=True)


class SaveEvaluation(Strict):
    request_id: UUID
    measurement: EvaluationInput
    supersedes_id: UUID | None = None
    expected_previous_version: int | None = Field(default=None, ge=1, strict=True)

    @model_validator(mode='after')
    def parent_and_version(self):
        if (self.supersedes_id is None) != (self.expected_previous_version is None):
            raise ValueError('previous evaluation and version must be specified together')
        return self


EvidenceGate = Literal['protocol', 'current_rules', 'form_mapping', 'real_reading', 'correction_loop',
                       'network_egress', 'access_control', 'protected_storage', 'logs_and_cache', 'restore']
EVIDENCE_GATES = ('protocol', 'current_rules', 'form_mapping', 'real_reading', 'correction_loop',
                  'network_egress', 'access_control', 'protected_storage', 'logs_and_cache', 'restore')


class EvidenceReference(Strict):
    gate: EvidenceGate
    document_id: UUID
    result: Literal['passed', 'failed']


class ReviewEvaluation(Strict):
    expected_version: int = Field(ge=1, strict=True)
    decision: Literal['confirmed', 'rejected']
    evidence: list[EvidenceReference] = Field(default_factory=list, max_length=10)

    @model_validator(mode='after')
    def unique_gates(self):
        if len({item.gate for item in self.evidence}) != len(self.evidence):
            raise ValueError('duplicate evidence gate')
        return self


FieldName = Literal['transported', 'transfer_transport', 'urgency', 'place_major', 'place_minor',
                    'occurrence_floor', 'form_version', 'incident_type_first', 'incident_type_second',
                    'vital_phase', 'age_band', 'pulse', 'respirations', 'systolic', 'spo2', 'jcs']


class CheckObservation(Strict):
    state: Literal['confirmed', 'unconfirmed', 'unreadable', 'not_printed', 'unmapped']
    value: str | int | float | bool | None = Field(default=None, union_mode='smart')

    @model_validator(mode='before')
    @classmethod
    def bounded_scalar(cls, values):
        if isinstance(values, dict):
            value = values.get('value')
            if value is not None and type(value) not in (str, int, float, bool):
                raise ValueError('unsupported observation value')
            if isinstance(value, str) and len(value) > 200:
                raise ValueError('observation value exceeds limit')
            if type(value) in (int, float):
                import math
                try:
                    finite = math.isfinite(value)
                except (ValueError, OverflowError):
                    finite = False
                if not finite:
                    raise ValueError('finite observation required')
        return values

    @model_validator(mode='after')
    def confirmed_only(self):
        Observation(self.state, self.value)
        return self


class CandidateCheck(Strict):
    fields: dict[FieldName, CheckObservation] = Field(default_factory=dict, max_length=16)

    @model_validator(mode='after')
    def field_types(self):
        boolean_fields = {'transported', 'transfer_transport'}
        numeric_fields = {'pulse', 'respirations', 'systolic', 'spo2', 'jcs'}
        for name, item in self.fields.items():
            if item.value is None:
                continue
            expected = (bool,) if name in boolean_fields else (int, float) if name in numeric_fields else (str,)
            if type(item.value) not in expected:
                raise ValueError('observation type does not match the normalized field')
        return self
