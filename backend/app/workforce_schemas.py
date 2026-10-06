from datetime import date,datetime,time
from typing import Literal
from pydantic import BaseModel,ConfigDict,Field,model_validator

class Strict(BaseModel):
    model_config=ConfigDict(extra='forbid',str_strip_whitespace=True)

class Version(Strict):
    expected_version:int=Field(ge=1)

class HumanAction(Version):
    note:str=Field(min_length=1,max_length=4000)

class ShiftTypeCreate(Strict):
    code:str=Field(min_length=1,max_length=100)
    name:str=Field(min_length=1,max_length=200)
    start_time:time
    end_time:time
    timezone_name:str=Field(default='Asia/Tokyo',min_length=1,max_length=80)
    cross_midnight:bool=False
    payable_minutes:int=Field(gt=0,le=2880)

class ShiftTypePatch(Version):
    name:str|None=Field(None,min_length=1,max_length=200)
    start_time:time|None=None
    end_time:time|None=None
    timezone_name:str|None=Field(None,min_length=1,max_length=80)
    cross_midnight:bool|None=None
    payable_minutes:int|None=Field(None,gt=0,le=2880)
    active:bool|None=None

class QualificationCreate(Strict):
    employee_id:str
    code:str=Field(min_length=1,max_length=100)
    label:str=Field(min_length=1,max_length=200)
    valid_from:date
    valid_to:date|None=None
    document_id:str|None=None
    @model_validator(mode='after')
    def dates(self):
        if self.valid_to and self.valid_to<self.valid_from:raise ValueError('valid_to cannot precede valid_from')
        return self

class StaffingRuleCreate(Strict):
    organization_id:str
    shift_type_id:str
    min_staff:int=Field(gt=0,le=1000)
    qualification_code:str|None=Field(None,max_length=100)
    effective_from:date
    effective_to:date|None=None
    rule_note:str|None=Field(None,max_length=4000)
    @model_validator(mode='after')
    def dates(self):
        if self.effective_to and self.effective_to<self.effective_from:raise ValueError('effective_to cannot precede effective_from')
        return self

class RosterCreate(Strict):
    employee_id:str
    organization_id:str
    shift_type_id:str
    work_date:date
    support_placement:bool=False
    note:str|None=Field(None,max_length=4000)
    document_id:str|None=None

class LeaveCreate(Strict):
    employee_id:str
    leave_type:Literal['annual','special','compensatory']
    kind:Literal['grant','use','adjustment_add','adjustment_subtract','expire']
    quantity_minutes:int=Field(gt=0,le=1000000)
    effective_on:date
    expires_on:date|None=None
    private_reason:str|None=Field(None,max_length=4000)
    @model_validator(mode='after')
    def dates(self):
        if self.expires_on and self.expires_on<self.effective_on:raise ValueError('expires_on cannot precede effective_on')
        return self

class AttendanceCreate(Strict):
    employee_id:str
    roster_entry_id:str|None=None
    work_date:date
    check_in_at:datetime
    check_out_at:datetime|None=None
    @model_validator(mode='after')
    def period(self):
        if self.check_out_at and self.check_out_at<=self.check_in_at:raise ValueError('check_out_at must follow check_in_at')
        return self

class AttendancePatch(Version):
    check_in_at:datetime|None=None
    check_out_at:datetime|None=None
    @model_validator(mode='after')
    def period(self):
        if self.check_in_at and self.check_out_at and self.check_out_at<=self.check_in_at:raise ValueError('check_out_at must follow check_in_at')
        return self

class TimeEntryCreate(Strict):
    employee_id:str
    attendance_id:str|None=None
    kind:Literal['overtime','comp_grant','comp_use']
    minutes:int=Field(gt=0,le=100000)
    occurred_on:date
    note:str|None=Field(None,max_length=4000)

class ImportConfirm(Version):
    file_sha256:str=Field(pattern='^[a-f0-9]{64}$')
