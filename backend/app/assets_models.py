"""Operational stock, distinct from installed FacilityEquipment."""
from datetime import date,datetime
from decimal import Decimal
from sqlalchemy import BigInteger,Boolean,CheckConstraint,Date,DateTime,ForeignKey,ForeignKeyConstraint,JSON,Numeric,String,Text,UniqueConstraint,Uuid
from sqlalchemy.orm import Mapped,mapped_column
from .db import Base
from .models import uuid_str,now_utc

class Versioned:
    version:Mapped[int]=mapped_column(BigInteger,nullable=False,default=1)
    created_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),nullable=False,default=now_utc)
    updated_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),nullable=False,default=now_utc)

class OperationalAsset(Versioned,Base):
    __tablename__='operational_assets'
    asset_id:Mapped[str]=mapped_column(Uuid(as_uuid=False),primary_key=True,default=uuid_str)
    code:Mapped[str]=mapped_column(String(100),unique=True,nullable=False)
    name:Mapped[str]=mapped_column(String(300),nullable=False)
    category:Mapped[str]=mapped_column(String(20),nullable=False)
    unit:Mapped[str]=mapped_column(String(100),nullable=False)
    reorder_threshold:Mapped[Decimal]=mapped_column(Numeric(14,3),nullable=False,default=Decimal('0'))
    active:Mapped[bool]=mapped_column(Boolean,nullable=False,default=True)
    document_id:Mapped[str|None]=mapped_column(ForeignKey('documents.document_id'))
    notes:Mapped[str|None]=mapped_column(Text)
    next_pressure_test_on:Mapped[date|None]=mapped_column(Date)
    next_use_on:Mapped[date|None]=mapped_column(Date)
    next_calibration_on:Mapped[date|None]=mapped_column(Date)
    next_service_on:Mapped[date|None]=mapped_column(Date)
    retired_reason:Mapped[str|None]=mapped_column(Text)
    retired_by:Mapped[str|None]=mapped_column(ForeignKey('app_users.user_id'))
    __table_args__=(CheckConstraint("category IN ('durable','consumable','drug')",name='ck_asset_category'),CheckConstraint('reorder_threshold >= 0',name='ck_asset_threshold'))

class AssetLocation(Versioned,Base):
    __tablename__='asset_locations'
    location_id:Mapped[str]=mapped_column(Uuid(as_uuid=False),primary_key=True,default=uuid_str)
    code:Mapped[str]=mapped_column(String(100),nullable=False,unique=True)
    name:Mapped[str]=mapped_column(String(300),nullable=False)
    building_id:Mapped[str|None]=mapped_column(ForeignKey('facilities.building_id'))
    vehicle_id:Mapped[str|None]=mapped_column(ForeignKey('operation_vehicles.vehicle_id'))
    active:Mapped[bool]=mapped_column(Boolean,nullable=False,default=True)
    notes:Mapped[str|None]=mapped_column(Text)

class AssetLot(Versioned,Base):
    __tablename__='asset_lots'
    lot_id:Mapped[str]=mapped_column(Uuid(as_uuid=False),primary_key=True,default=uuid_str)
    asset_id:Mapped[str]=mapped_column(ForeignKey('operational_assets.asset_id'),nullable=False,index=True)
    batch_code:Mapped[str]=mapped_column(String(200),nullable=False)
    expires_on:Mapped[date|None]=mapped_column(Date)
    provenance:Mapped[str]=mapped_column(Text,nullable=False)
    document_id:Mapped[str|None]=mapped_column(ForeignKey('documents.document_id'))
    expiry_approved_by:Mapped[str|None]=mapped_column(ForeignKey('app_users.user_id'))
    expiry_approved_at:Mapped[datetime|None]=mapped_column(DateTime(timezone=True))
    active:Mapped[bool]=mapped_column(Boolean,nullable=False,default=True)
    __table_args__=(UniqueConstraint('asset_id','batch_code',name='uq_asset_batch'),UniqueConstraint('lot_id','asset_id',name='uq_lot_asset'),CheckConstraint('expires_on IS NULL OR (expiry_approved_by IS NOT NULL AND expiry_approved_at IS NOT NULL)',name='ck_lot_expiry_human'))

class AssetBalance(Versioned,Base):
    __tablename__='asset_balances'
    balance_id:Mapped[str]=mapped_column(Uuid(as_uuid=False),primary_key=True,default=uuid_str)
    asset_id:Mapped[str]=mapped_column(ForeignKey('operational_assets.asset_id'),nullable=False,index=True)
    lot_id:Mapped[str]=mapped_column(Uuid(as_uuid=False),nullable=False)
    location_id:Mapped[str]=mapped_column(ForeignKey('asset_locations.location_id'),nullable=False)
    quantity:Mapped[Decimal]=mapped_column(Numeric(14,3),nullable=False,default=Decimal('0'))
    __table_args__=(ForeignKeyConstraint(['lot_id','asset_id'],['asset_lots.lot_id','asset_lots.asset_id'],name='fk_balance_lot_asset'),UniqueConstraint('lot_id','location_id',name='uq_lot_location'),CheckConstraint('quantity >= 0',name='ck_asset_balance_nonnegative'))

class AssetLoan(Versioned,Base):
    __tablename__='asset_loans'
    loan_id:Mapped[str]=mapped_column(Uuid(as_uuid=False),primary_key=True,default=uuid_str)
    asset_id:Mapped[str]=mapped_column(ForeignKey('operational_assets.asset_id'),nullable=False,index=True)
    lot_id:Mapped[str]=mapped_column(Uuid(as_uuid=False),nullable=False)
    location_id:Mapped[str]=mapped_column(ForeignKey('asset_locations.location_id'),nullable=False)
    borrower_employee_id:Mapped[str]=mapped_column(ForeignKey('employees.employee_id'),nullable=False)
    quantity:Mapped[Decimal]=mapped_column(Numeric(14,3),nullable=False)
    outstanding_quantity:Mapped[Decimal]=mapped_column(Numeric(14,3),nullable=False)
    loaned_on:Mapped[date]=mapped_column(Date,nullable=False)
    due_on:Mapped[date|None]=mapped_column(Date)
    reason:Mapped[str]=mapped_column(Text,nullable=False)
    created_by:Mapped[str]=mapped_column(ForeignKey('app_users.user_id'),nullable=False)
    __table_args__=(ForeignKeyConstraint(['lot_id','asset_id'],['asset_lots.lot_id','asset_lots.asset_id'],name='fk_loan_lot_asset'),UniqueConstraint('loan_id','asset_id','lot_id',name='uq_loan_lineage'),CheckConstraint('quantity > 0 AND outstanding_quantity >= 0 AND outstanding_quantity <= quantity',name='ck_asset_loan_quantity'),CheckConstraint('due_on IS NULL OR due_on >= loaned_on',name='ck_asset_loan_due'))

class AssetMovement(Base):
    __tablename__='asset_movements'
    movement_id:Mapped[str]=mapped_column(Uuid(as_uuid=False),primary_key=True,default=uuid_str)
    asset_id:Mapped[str]=mapped_column(ForeignKey('operational_assets.asset_id'),nullable=False,index=True)
    lot_id:Mapped[str]=mapped_column(Uuid(as_uuid=False),nullable=False)
    location_id:Mapped[str]=mapped_column(ForeignKey('asset_locations.location_id'),nullable=False)
    to_location_id:Mapped[str|None]=mapped_column(ForeignKey('asset_locations.location_id'))
    kind:Mapped[str]=mapped_column(String(30),nullable=False)
    quantity:Mapped[Decimal]=mapped_column(Numeric(14,3),nullable=False)
    unit:Mapped[str]=mapped_column(String(100),nullable=False)
    cost:Mapped[Decimal]=mapped_column(Numeric(14,2),nullable=False,default=Decimal('0'))
    loan_id:Mapped[str|None]=mapped_column(Uuid(as_uuid=False))
    handler_employee_id:Mapped[str|None]=mapped_column(ForeignKey('employees.employee_id'))
    incident_id:Mapped[str|None]=mapped_column(ForeignKey('operation_incidents.incident_id'))
    document_id:Mapped[str|None]=mapped_column(ForeignKey('documents.document_id'))
    idempotency_key:Mapped[str]=mapped_column(String(200),nullable=False,unique=True)
    request_sha256:Mapped[str]=mapped_column(String(64),nullable=False)
    reason:Mapped[str]=mapped_column(Text,nullable=False)
    created_by:Mapped[str]=mapped_column(ForeignKey('app_users.user_id'),nullable=False)
    created_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),nullable=False,default=now_utc)
    occurred_on:Mapped[date]=mapped_column(Date,nullable=False)
    asset_version:Mapped[int]=mapped_column(BigInteger,nullable=False)
    __table_args__=(ForeignKeyConstraint(['lot_id','asset_id'],['asset_lots.lot_id','asset_lots.asset_id'],name='fk_movement_lot_asset'),ForeignKeyConstraint(['loan_id','asset_id','lot_id'],['asset_loans.loan_id','asset_loans.asset_id','asset_loans.lot_id'],name='fk_movement_loan_lineage'),CheckConstraint("kind IN ('receive','issue','transfer','loan','return','disposal','expiry_writeoff')",name='ck_asset_movement_kind'),CheckConstraint('quantity > 0 AND cost >= 0',name='ck_asset_movement_positive'),CheckConstraint("(kind = 'transfer' AND to_location_id IS NOT NULL AND to_location_id <> location_id) OR (kind <> 'transfer' AND to_location_id IS NULL)",name='ck_asset_transfer_location'),CheckConstraint("kind NOT IN ('loan','return') OR loan_id IS NOT NULL",name='ck_asset_movement_loan'))

class AssetService(Versioned,Base):
    __tablename__='asset_services'
    service_id:Mapped[str]=mapped_column(Uuid(as_uuid=False),primary_key=True,default=uuid_str)
    asset_id:Mapped[str]=mapped_column(ForeignKey('operational_assets.asset_id'),nullable=False,index=True)
    kind:Mapped[str]=mapped_column(String(30),nullable=False)
    performed_on:Mapped[date]=mapped_column(Date,nullable=False)
    description:Mapped[str]=mapped_column(Text,nullable=False)
    cost:Mapped[Decimal]=mapped_column(Numeric(14,2),nullable=False,default=Decimal('0'))
    document_id:Mapped[str|None]=mapped_column(ForeignKey('documents.document_id'))
    lot_id:Mapped[str|None]=mapped_column(Uuid(as_uuid=False))
    location_id:Mapped[str|None]=mapped_column(ForeignKey('asset_locations.location_id'))
    quantity:Mapped[Decimal|None]=mapped_column(Numeric(14,3))
    next_pressure_test_on:Mapped[date|None]=mapped_column(Date)
    next_use_on:Mapped[date|None]=mapped_column(Date)
    next_calibration_on:Mapped[date|None]=mapped_column(Date)
    next_service_on:Mapped[date|None]=mapped_column(Date)
    status:Mapped[str]=mapped_column(String(20),nullable=False,default='draft')
    review_snapshot:Mapped[dict]=mapped_column(JSON,nullable=False,default=dict)
    reviewed_by:Mapped[str|None]=mapped_column(ForeignKey('app_users.user_id'))
    reviewed_at:Mapped[datetime|None]=mapped_column(DateTime(timezone=True))
    approved_by:Mapped[str|None]=mapped_column(ForeignKey('app_users.user_id'))
    approved_at:Mapped[datetime|None]=mapped_column(DateTime(timezone=True))
    reason:Mapped[str|None]=mapped_column(Text)
    created_by:Mapped[str]=mapped_column(ForeignKey('app_users.user_id'),nullable=False)
    movement_id:Mapped[str|None]=mapped_column(ForeignKey('asset_movements.movement_id'))
    __table_args__=(ForeignKeyConstraint(['lot_id','asset_id'],['asset_lots.lot_id','asset_lots.asset_id'],name='fk_service_lot_asset'),CheckConstraint("kind IN ('inspection','repair','renewal','pressure_test','calibration','disposal','expiry_writeoff')",name='ck_asset_service_kind'),CheckConstraint('cost >= 0',name='ck_asset_service_cost'),CheckConstraint("status IN ('draft','reviewed','approved','cancelled')",name='ck_asset_service_status'),CheckConstraint("status <> 'approved' OR (reviewed_by IS NOT NULL AND approved_by IS NOT NULL AND approved_at IS NOT NULL)",name='ck_asset_service_human'),CheckConstraint("kind NOT IN ('disposal','expiry_writeoff') OR (lot_id IS NOT NULL AND location_id IS NOT NULL AND quantity > 0)",name='ck_asset_service_writeoff'))

class AssetImportPreview(Versioned,Base):
    __tablename__='asset_import_previews'
    preview_id:Mapped[str]=mapped_column(Uuid(as_uuid=False),primary_key=True,default=uuid_str)
    dataset:Mapped[str]=mapped_column(String(30),nullable=False)
    schema_version:Mapped[str]=mapped_column(String(30),nullable=False)
    filename:Mapped[str]=mapped_column(Text,nullable=False)
    file_sha256:Mapped[str]=mapped_column(String(64),nullable=False)
    document_id:Mapped[str|None]=mapped_column(ForeignKey('documents.document_id'))
    row_data:Mapped[list]=mapped_column(JSON,nullable=False)
    created_by:Mapped[str]=mapped_column(ForeignKey('app_users.user_id'),nullable=False)
    expires_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),nullable=False)
    status:Mapped[str]=mapped_column(String(20),nullable=False,default='preview')
    applied_ids:Mapped[list]=mapped_column(JSON,nullable=False,default=list)
    __table_args__=(CheckConstraint("status IN ('preview','applied')",name='ck_asset_import_status'),CheckConstraint("dataset IN ('registry','locations','lots','movements','services')",name='ck_asset_import_dataset'))
