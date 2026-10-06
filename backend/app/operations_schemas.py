from datetime import datetime,date,timezone
from decimal import Decimal
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, model_validator

class Strict(BaseModel):
    model_config=ConfigDict(extra='forbid',str_strip_whitespace=True)
    @model_validator(mode='after')
    def aware_times(self):
        for name in type(self).model_fields:
            value=getattr(self,name)
            if isinstance(value,datetime):
                if value.tzinfo is None:raise ValueError(f'{name} requires timezone')
                setattr(self,name,value.astimezone(timezone.utc))
        return self
class Version(Strict):
    expected_version:int=Field(ge=1)
class Action(Version):
    note:str=Field(min_length=1,max_length=4000)
Kind=Literal['fire','rescue','emergency_support','watch','storm','other']
Money=Field(ge=0,max_digits=14,decimal_places=2)
Mileage=Field(ge=0,max_digits=14,decimal_places=1)
class IncidentInput(Strict):
    kind:Kind
    title:str=Field(min_length=1,max_length=500)
    occurred_at:datetime|None=None
    address:str|None=None
    number:str|None=Field(None,max_length=120)
    emergency_case_id:str|None=None
    fire_investigation_case_id:str|None=None
    notes:str|None=None
    @model_validator(mode='after')
    def source_fields(self):
        if self.emergency_case_id and self.fire_investigation_case_id:raise ValueError('one linked source only')
        if self.emergency_case_id or self.fire_investigation_case_id:
            if self.address is not None or self.occurred_at is not None or self.number is not None:raise ValueError('linked source facts must not be copied')
        if self.emergency_case_id and self.kind!='emergency_support':raise ValueError('emergency link requires emergency_support')
        if self.fire_investigation_case_id and self.kind!='fire':raise ValueError('fire link requires fire')
        return self
class IncidentPatch(Version):
    title:str|None=Field(None,min_length=1,max_length=500)
    kind:Kind|None=None
    occurred_at:datetime|None=None
    address:str|None=None
    number:str|None=Field(None,max_length=120)
    notes:str|None=None
class VehicleInput(Strict):
    code:str=Field(min_length=1,max_length=100)
    name:str=Field(min_length=1,max_length=200)
    registration:str|None=Field(None,max_length=100)
    odometer:Decimal=Field(default=Decimal('0'),ge=0,max_digits=14,decimal_places=1)
    notes:str|None=None
class VehiclePatch(Version):
    name:str|None=Field(None,min_length=1,max_length=200)
    registration:str|None=Field(None,max_length=100)
    active:bool|None=None
    notes:str|None=None
class DispatchFields(Strict):
    unit:str=Field(min_length=1,max_length=200)
    vehicle_id:str|None=None
    departed_at:datetime|None=None
    arrived_at:datetime|None=None
    returned_at:datetime|None=None
    activity:str|None=None
    report:str|None=None
    document_id:str|None=None
    @model_validator(mode='after')
    def times(self):
        if self.returned_at and (not self.departed_at or self.returned_at<self.departed_at):raise ValueError('invalid return time')
        if self.arrived_at and (not self.departed_at or self.arrived_at<self.departed_at or (self.returned_at and self.arrived_at>self.returned_at)):raise ValueError('invalid arrival time')
        return self
class DispatchInput(DispatchFields,Version):pass
class DispatchPatch(Version):
    unit:str|None=Field(None,min_length=1,max_length=200)
    vehicle_id:str|None=None
    departed_at:datetime|None=None
    arrived_at:datetime|None=None
    returned_at:datetime|None=None
    activity:str|None=None
    report:str|None=None
    document_id:str|None=None
class CrewInput(Version):
    employee_id:str
    role:str=Field(min_length=1,max_length=100)
class RateInput(Strict):
    code:str=Field(min_length=1,max_length=100)
    label:str=Field(min_length=1,max_length=300)
    amount:Decimal=Money
    basis:Literal['per_dispatch','per_crew','per_hour']
    rounding:Literal['half_up','half_even','down']
    approval_reference:str=Field(min_length=1,max_length=4000)
class Calculate(Version):rate_id:str
class TripInput(Version):
    dispatch_id:str|None=None
    driver_employee_id:str|None=None
    started_at:datetime
    ended_at:datetime
    start_odometer:Decimal=Mileage
    end_odometer:Decimal=Mileage
    purpose:str=Field(min_length=1,max_length=4000)
    document_id:str|None=None
    @model_validator(mode='after')
    def ranges(self):
        if self.ended_at<self.started_at or self.end_odometer<self.start_odometer:raise ValueError('negative mileage or invalid times')
        return self
class FuelInput(Version):
    kind:Literal['receipt','issue','refuel']
    liters:Decimal=Field(gt=0,max_digits=14,decimal_places=2)
    amount:Decimal=Money
    occurred_at:datetime
    document_id:str|None=None
    notes:str|None=None
class ServiceInput(Version):
    resolves_fault_id:str|None=None
    kind:Literal['inspection','vehicle_inspection','repair','fault','service']
    performed_on:date
    description:str=Field(min_length=1,max_length=4000)
    cost:Decimal=Field(default=Decimal('0'),ge=0,max_digits=14,decimal_places=2)
    next_inspection_on:date|None=None
    next_service_on:date|None=None
    next_service_odometer:Decimal|None=Field(None,ge=0,max_digits=14,decimal_places=1)
    document_id:str|None=None
    @model_validator(mode='after')
    def dates(self):
        if any(x and x<self.performed_on for x in [self.next_service_on,self.next_inspection_on]):raise ValueError('deadline precedes service')
        return self

class ServiceApprove(Action):
    expected_vehicle_version:int=Field(ge=1)
    expected_fault_version:int|None=Field(None,ge=1)
class ImportConfirm(Version):
    file_sha256:str=Field(pattern=r'^[a-f0-9]{64}$')
