"""Bounded, server-defined observed queries. No client evidence or date-zone overrides."""
import re
from datetime import date, datetime
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

METRIC_KEYS = ('emergency.cases', 'emergency.patient_records', 'operations.incidents',
               'operations.dispatches', 'operations.approved_dispatches', 'fleet.trips', 'fleet.distance_km',
               'workforce.approved_rosters', 'workforce.approved_worked_minutes', 'workforce.approved_overtime_minutes')
MetricKey = Literal['emergency.cases', 'emergency.patient_records', 'operations.incidents',
                    'operations.dispatches', 'operations.approved_dispatches', 'fleet.trips', 'fleet.distance_km',
                    'workforce.approved_rosters', 'workforce.approved_worked_minutes', 'workforce.approved_overtime_minutes']


class Strict(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)


class StatisticsQuery(Strict):
    start_date: date
    end_date: date
    metric_keys: list[MetricKey] = Field(min_length=1, max_length=len(METRIC_KEYS))

    @field_validator('start_date', 'end_date', mode='before')
    @classmethod
    def exact_date(cls, value):
        if isinstance(value, datetime) or not isinstance(value, (str, date)):
            raise ValueError('Use an explicit YYYY-MM-DD date')
        if isinstance(value, str) and not re.fullmatch(r'\d{4}-\d{2}-\d{2}', value):
            raise ValueError('Use an explicit YYYY-MM-DD date')
        return value

    @model_validator(mode='after')
    def bounded(self):
        if self.start_date > self.end_date or self.end_date == date.max:
            raise ValueError('Invalid date range or exclusive-end overflow')
        if len(set(self.metric_keys)) != len(self.metric_keys):
            raise ValueError('Metric keys must be distinct')
        return self


class ConfirmStatistics(Strict):
    expected_version: int = Field(ge=1, strict=True)
    acknowledged: Literal[True]
    review_note: str = Field(min_length=1, max_length=4000)

    @field_validator('acknowledged', mode='before')
    @classmethod
    def explicit_acknowledgement(cls, value):
        if value is not True:
            raise ValueError('Explicit Human acknowledgement is required')
        return value


class ReplaceStatistics(Strict):
    expected_version: int = Field(ge=1, strict=True)
    reason: str = Field(min_length=1, max_length=4000)
