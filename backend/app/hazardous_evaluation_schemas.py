from datetime import date
from uuid import UUID
from pydantic import Field, StrictBool, field_validator
from .hazardous_schemas import Strict


class EvaluationInput(Strict):
    expected_installation_version: int = Field(ge=1, strict=True)
    legal_profile_id: UUID
    evaluation_date: date


class EvaluationReview(Strict):
    expected_version: int = Field(ge=1, strict=True)
    reason: str = Field(min_length=1, max_length=4000)
    acknowledged: StrictBool

    @field_validator('acknowledged')
    @classmethod
    def explicit_human(cls, value):
        if value is not True:
            raise ValueError('explicit Human acknowledgement required')
        return value
