from datetime import date
from uuid import UUID
from pydantic import Field, model_validator
from .workforce_schemas import Strict, Version


class TeamCreate(Strict):
    organization_id:UUID
    code:str=Field(min_length=1,max_length=100)
    name:str=Field(min_length=1,max_length=200)
    reason:str=Field(min_length=1,max_length=4000)


class TeamPatch(Version):
    name:str|None=Field(None,min_length=1,max_length=200)
    active:bool|None=None
    reason:str=Field(min_length=1,max_length=4000)
    @model_validator(mode='after')
    def change(self):
        if self.name is None and self.active is None:raise ValueError('explicit team change is required')
        return self


class MembershipCreate(Strict):
    expected_team_version:int=Field(ge=1)
    expected_assignment_version:int=Field(ge=1)
    employee_id:UUID
    assignment_id:UUID
    valid_from:date
    valid_to:date|None=None
    reason:str=Field(min_length=1,max_length=4000)
    @model_validator(mode='after')
    def dates(self):
        if self.valid_to and self.valid_to<self.valid_from:raise ValueError('valid_to cannot precede valid_from')
        return self


class MembershipPatch(Version):
    expected_team_version:int=Field(ge=1)
    active:bool
    reason:str=Field(min_length=1,max_length=4000)
