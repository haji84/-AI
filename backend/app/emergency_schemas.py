from datetime import date, datetime, time
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field

class Strict(BaseModel):
    model_config = ConfigDict(extra='forbid')

class Version(Strict):
    expected_version: int = Field(ge=1)

class CaseInput(Strict):
    call_date: date
    station_code: str = Field(min_length=1, max_length=100)
    dispatch_number: str = Field(min_length=1, max_length=100)
    call_time: time | None = None
    dispatch_time: time | None = None
    scene_arrival_time: time | None = None
    leave_scene_time: time | None = None
    return_station_time: time | None = None
    incident_address: str | None = None
    incident_type: str | None = None
    activity_type: str | None = None
    command_text: str | None = None

class CasePatch(Version):
    call_date: date | None = None
    call_time: time | None = None
    dispatch_time: time | None = None
    scene_arrival_time: time | None = None
    leave_scene_time: time | None = None
    return_station_time: time | None = None
    incident_address: str | None = None
    incident_type: str | None = None
    activity_type: str | None = None
    command_text: str | None = None

class PatientInput(Strict):
    patient_number: int = Field(ge=1)
    age: int | None = Field(default=None, ge=0, le=130)
    sex: str | None = None
    hospital_code: str | None = None
    severity_code: str | None = None
    diagnosis_text: str | None = None
    condition_text: str | None = None
    symptoms_text: str | None = None
    injury_class_major: str | None = None
    injury_class_middle: str | None = None
    injury_class_minor: str | None = None
    other_information_text: str | None = None

class PatientPatch(Version):
    age: int | None = Field(default=None, ge=0, le=130)
    sex: str | None = None
    hospital_code: str | None = None
    severity_code: str | None = None
    diagnosis_text: str | None = None
    condition_text: str | None = None
    symptoms_text: str | None = None
    injury_class_major: str | None = None
    injury_class_middle: str | None = None
    injury_class_minor: str | None = None
    other_information_text: str | None = None

class TreatmentInput(Strict):
    code: Literal['cpr','chest_compressions','ventilation','aed','defibrillation','oxygen','other']
    performed_at: datetime | None = None
    notes: str | None = None
    source_document_id: str | None = None

class Review(Version):
    decision: Literal['confirmed','rejected']
    note: str | None = None

class CrewInput(Strict):
    employee_id: str
    crew_role: str = Field(min_length=1)
    qualification: str | None = None

class ReportInput(Strict):
    kind: Literal['emergency_report','post_review','lifesaving_record']
    content: dict = Field(default_factory=dict)
