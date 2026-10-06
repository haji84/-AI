from datetime import date
from decimal import Decimal
from typing import Literal
from pydantic import BaseModel,ConfigDict,Field,model_validator

class Strict(BaseModel):
    model_config=ConfigDict(extra='forbid',str_strip_whitespace=True)
class Version(Strict):expected_version:int=Field(ge=1)
class Action(Version):reason:str=Field(min_length=1,max_length=4000)
Quantity=Field(ge=0,max_digits=14,decimal_places=3)
Positive=Field(gt=0,max_digits=14,decimal_places=3)
Money=Field(ge=0,max_digits=14,decimal_places=2)
Category=Literal['durable','consumable','drug']
class AssetInput(Strict):
    code:str=Field(min_length=1,max_length=100)
    name:str=Field(min_length=1,max_length=300)
    category:Category
    unit:str=Field(min_length=1,max_length=100)
    reorder_threshold:Decimal=Field(default=Decimal('0'),ge=0,max_digits=14,decimal_places=3)
    document_id:str|None=None
    notes:str|None=Field(None,max_length=4000)
class AssetPatch(Version):
    name:str|None=Field(None,min_length=1,max_length=300)
    unit:str|None=Field(None,min_length=1,max_length=100)
    reorder_threshold:Decimal|None=Field(None,ge=0,max_digits=14,decimal_places=3)
    document_id:str|None=None
    notes:str|None=Field(None,max_length=4000)
class LocationInput(Strict):
    code:str=Field(min_length=1,max_length=100)
    name:str=Field(min_length=1,max_length=300)
    building_id:str|None=None
    vehicle_id:str|None=None
    notes:str|None=Field(None,max_length=4000)
class LocationPatch(Version):
    name:str|None=Field(None,min_length=1,max_length=300)
    active:bool|None=None
    building_id:str|None=None
    vehicle_id:str|None=None
    notes:str|None=Field(None,max_length=4000)
class LotInput(Version):
    batch_code:str=Field(min_length=1,max_length=200)
    expires_on:date|None=None
    provenance:str=Field(min_length=1,max_length=4000)
    document_id:str|None=None
class MovementInput(Version):
    asset_id:str
    lot_id:str
    location_id:str
    to_location_id:str|None=None
    kind:Literal['receive','issue','transfer','loan','return']
    quantity:Decimal=Positive
    cost:Decimal=Field(default=Decimal('0'),ge=0,max_digits=14,decimal_places=2)
    borrower_employee_id:str|None=None
    handler_employee_id:str|None=None
    loan_id:str|None=None
    incident_id:str|None=None
    document_id:str|None=None
    occurred_on:date|None=None
    due_on:date|None=None
    idempotency_key:str=Field(min_length=1,max_length=200)
    reason:str=Field(min_length=1,max_length=4000)
    @model_validator(mode='after')
    def relations(self):
        if (self.kind=='transfer')!=(self.to_location_id is not None):raise ValueError('destination required only for transfer')
        if self.kind=='transfer' and self.to_location_id==self.location_id:raise ValueError('transfer requires different location')
        if (self.kind=='loan')!=(self.borrower_employee_id is not None):raise ValueError('borrower required only for loan')
        if (self.kind=='return')!=(self.loan_id is not None):raise ValueError('loan reference required only for return')
        if self.due_on and self.kind!='loan':raise ValueError('due date is for loan only')
        return self
class ServiceInput(Version):
    kind:Literal['inspection','repair','renewal','pressure_test','calibration','disposal','expiry_writeoff']
    performed_on:date
    description:str=Field(min_length=1,max_length=4000)
    cost:Decimal=Field(default=Decimal('0'),ge=0,max_digits=14,decimal_places=2)
    document_id:str|None=None
    lot_id:str|None=None
    location_id:str|None=None
    quantity:Decimal|None=Field(None,gt=0,max_digits=14,decimal_places=3)
    next_pressure_test_on:date|None=None
    next_use_on:date|None=None
    next_calibration_on:date|None=None
    next_service_on:date|None=None
    @model_validator(mode='after')
    def dates_stock(self):
        disposal=self.kind in ['disposal','expiry_writeoff']
        if disposal and not(self.lot_id and self.location_id and self.quantity):raise ValueError('write-off requires batch, location and quantity')
        if not disposal and(self.location_id or self.quantity is not None):raise ValueError('stock quantity/location allowed only for write-off')
        for k in ['next_pressure_test_on','next_use_on','next_calibration_on','next_service_on']:
            d=getattr(self,k)
            if d and d<self.performed_on:raise ValueError('next due date cannot precede performed date')
            if disposal and d:raise ValueError('write-off cannot change due dates')
        return self
class ServiceApprove(Action):expected_asset_version:int=Field(ge=1)
class ImportConfirm(Version):file_sha256:str=Field(pattern='^[a-f0-9]{64}$')
