"""Shared operations domain. No copies of linked emergency/fire source facts."""
from datetime import date, datetime
from decimal import Decimal
from sqlalchemy import BigInteger, Boolean, CheckConstraint, Date, DateTime, ForeignKey, ForeignKeyConstraint, JSON, Numeric, String, Text, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column
from .db import Base
from .models import uuid_str, now_utc

class Versioned:
    version: Mapped[int] = mapped_column(BigInteger, nullable=False, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=now_utc)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=now_utc)

class Incident(Versioned, Base):
    __tablename__='operation_incidents'
    incident_id: Mapped[str] = mapped_column(Uuid(as_uuid=False), primary_key=True, default=uuid_str)
    kind: Mapped[str] = mapped_column(String(30), nullable=False)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    occurred_at: Mapped[datetime|None] = mapped_column(DateTime(timezone=True))
    address: Mapped[str|None] = mapped_column(Text)
    number: Mapped[str|None] = mapped_column(String(120))
    emergency_case_id: Mapped[str|None] = mapped_column(ForeignKey('emergency_cases.emergency_case_id'), unique=True)
    fire_investigation_case_id: Mapped[str|None] = mapped_column(ForeignKey('fire_investigation_cases.fire_investigation_case_id'), unique=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default='active')
    notes: Mapped[str|None] = mapped_column(Text)
    __table_args__=(CheckConstraint("kind IN ('fire','rescue','emergency_support','watch','storm','other')",name='ck_incident_kind'),CheckConstraint("NOT (emergency_case_id IS NOT NULL AND fire_investigation_case_id IS NOT NULL)",name='ck_incident_single_source'),CheckConstraint("(emergency_case_id IS NULL AND fire_investigation_case_id IS NULL) OR (occurred_at IS NULL AND address IS NULL AND number IS NULL)",name='ck_incident_no_source_copy'),CheckConstraint("emergency_case_id IS NULL OR kind = 'emergency_support'",name='ck_incident_emergency_kind'),CheckConstraint("fire_investigation_case_id IS NULL OR kind = 'fire'",name='ck_incident_fire_kind'),CheckConstraint("status IN ('active','cancelled')",name='ck_incident_status'))

class Vehicle(Versioned, Base):
    __tablename__='operation_vehicles'
    vehicle_id: Mapped[str] = mapped_column(Uuid(as_uuid=False), primary_key=True, default=uuid_str)
    code: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    registration: Mapped[str|None] = mapped_column(String(100))
    active: Mapped[bool] = mapped_column(Boolean,nullable=False,default=True)
    odometer: Mapped[Decimal] = mapped_column(Numeric(14,1),nullable=False,default=Decimal('0'))
    fuel_stock: Mapped[Decimal] = mapped_column(Numeric(14,2),nullable=False,default=Decimal('0'))
    next_inspection_on: Mapped[date|None] = mapped_column(Date)
    next_service_on: Mapped[date|None] = mapped_column(Date)
    next_service_odometer: Mapped[Decimal|None] = mapped_column(Numeric(14,1))
    notes: Mapped[str|None] = mapped_column(Text)
    __table_args__=(CheckConstraint('odometer >= 0 AND fuel_stock >= 0',name='ck_vehicle_nonnegative'),CheckConstraint('next_service_odometer IS NULL OR next_service_odometer >= 0',name='ck_vehicle_service_odometer'))

class AllowanceRate(Versioned, Base):
    __tablename__='operation_allowance_rates'
    rate_id: Mapped[str] = mapped_column(Uuid(as_uuid=False),primary_key=True,default=uuid_str)
    code: Mapped[str] = mapped_column(String(100),nullable=False,unique=True)
    label: Mapped[str] = mapped_column(String(300),nullable=False)
    amount: Mapped[Decimal] = mapped_column(Numeric(14,2),nullable=False)
    basis: Mapped[str] = mapped_column(String(30),nullable=False)
    rounding: Mapped[str] = mapped_column(String(20),nullable=False)
    approval_reference: Mapped[str] = mapped_column(Text,nullable=False)
    status: Mapped[str] = mapped_column(String(20),nullable=False,default='draft')
    approved_by: Mapped[str|None] = mapped_column(ForeignKey('app_users.user_id'))
    approved_at: Mapped[datetime|None] = mapped_column(DateTime(timezone=True))
    approval_note: Mapped[str|None] = mapped_column(Text)
    __table_args__=(CheckConstraint("rounding IN ('half_up','half_even','down')",name='ck_rate_rounding'),CheckConstraint('amount >= 0',name='ck_rate_amount'),CheckConstraint("basis IN ('per_dispatch','per_crew','per_hour')",name='ck_rate_basis'),CheckConstraint("status IN ('draft','approved')",name='ck_rate_status'),CheckConstraint("status <> 'approved' OR (approved_by IS NOT NULL AND approved_at IS NOT NULL)",name='ck_rate_human'))

class Dispatch(Versioned, Base):
    __tablename__='operation_dispatches'
    dispatch_id: Mapped[str] = mapped_column(Uuid(as_uuid=False),primary_key=True,default=uuid_str)
    incident_id: Mapped[str] = mapped_column(ForeignKey('operation_incidents.incident_id'),nullable=False,index=True)
    unit: Mapped[str] = mapped_column(String(200),nullable=False)
    vehicle_id: Mapped[str|None] = mapped_column(ForeignKey('operation_vehicles.vehicle_id'))
    departed_at: Mapped[datetime|None] = mapped_column(DateTime(timezone=True))
    arrived_at: Mapped[datetime|None] = mapped_column(DateTime(timezone=True))
    returned_at: Mapped[datetime|None] = mapped_column(DateTime(timezone=True))
    activity: Mapped[str|None] = mapped_column(Text)
    report: Mapped[str|None] = mapped_column(Text)
    document_id: Mapped[str|None] = mapped_column(ForeignKey('documents.document_id'))
    status: Mapped[str] = mapped_column(String(20),nullable=False,default='draft')
    rate_id: Mapped[str|None] = mapped_column(ForeignKey('operation_allowance_rates.rate_id'))
    candidate_amount: Mapped[Decimal|None] = mapped_column(Numeric(14,2))
    calculation: Mapped[dict] = mapped_column(JSON,nullable=False,default=dict)
    official_amount: Mapped[Decimal|None] = mapped_column(Numeric(14,2))
    reviewed_by: Mapped[str|None] = mapped_column(ForeignKey('app_users.user_id'))
    reviewed_at: Mapped[datetime|None] = mapped_column(DateTime(timezone=True))
    approved_by: Mapped[str|None] = mapped_column(ForeignKey('app_users.user_id'))
    approved_at: Mapped[datetime|None] = mapped_column(DateTime(timezone=True))
    review_snapshot: Mapped[dict] = mapped_column(JSON,nullable=False,default=dict)
    review_note: Mapped[str|None] = mapped_column(Text)
    cancellation_note: Mapped[str|None] = mapped_column(Text)
    cancelled_by: Mapped[str|None] = mapped_column(ForeignKey('app_users.user_id'))
    cancelled_at: Mapped[datetime|None] = mapped_column(DateTime(timezone=True))
    __table_args__=(UniqueConstraint('dispatch_id','vehicle_id',name='uq_dispatch_vehicle'),CheckConstraint("status IN ('draft','reviewed','approved','cancelled')",name='ck_dispatch_status'),CheckConstraint('candidate_amount IS NULL OR candidate_amount >= 0',name='ck_dispatch_candidate'),CheckConstraint('official_amount IS NULL OR official_amount >= 0',name='ck_dispatch_official'),CheckConstraint("official_amount IS NULL OR (status IN ('approved','cancelled') AND approved_by IS NOT NULL)",name='ck_dispatch_official_gate'),CheckConstraint("status <> 'approved' OR (approved_by IS NOT NULL AND approved_at IS NOT NULL AND reviewed_by IS NOT NULL)",name='ck_dispatch_human'),CheckConstraint('returned_at IS NULL OR (departed_at IS NOT NULL AND returned_at >= departed_at)',name='ck_dispatch_return'),CheckConstraint('arrived_at IS NULL OR (departed_at IS NOT NULL AND arrived_at >= departed_at AND (returned_at IS NULL OR arrived_at <= returned_at))',name='ck_dispatch_arrival'))

class DispatchCrew(Base):
    __tablename__='operation_dispatch_crew'
    crew_id: Mapped[str] = mapped_column(Uuid(as_uuid=False),primary_key=True,default=uuid_str)
    dispatch_id: Mapped[str] = mapped_column(ForeignKey('operation_dispatches.dispatch_id'),nullable=False,index=True)
    employee_id: Mapped[str] = mapped_column(ForeignKey('employees.employee_id'),nullable=False)
    role: Mapped[str] = mapped_column(String(100),nullable=False)
    __table_args__=(UniqueConstraint('dispatch_id','employee_id',name='uq_dispatch_employee'),)

class History:
    created_by: Mapped[str] = mapped_column(ForeignKey('app_users.user_id'),nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True),nullable=False,default=now_utc)
    document_id: Mapped[str|None] = mapped_column(ForeignKey('documents.document_id'))

class VehicleTrip(History, Base):
    __tablename__='operation_vehicle_trips'
    trip_id: Mapped[str] = mapped_column(Uuid(as_uuid=False),primary_key=True,default=uuid_str)
    vehicle_id: Mapped[str] = mapped_column(ForeignKey('operation_vehicles.vehicle_id'),nullable=False,index=True)
    dispatch_id: Mapped[str|None] = mapped_column(ForeignKey('operation_dispatches.dispatch_id'))
    driver_employee_id: Mapped[str|None] = mapped_column(ForeignKey('employees.employee_id'))
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True),nullable=False)
    ended_at: Mapped[datetime] = mapped_column(DateTime(timezone=True),nullable=False)
    start_odometer: Mapped[Decimal] = mapped_column(Numeric(14,1),nullable=False)
    end_odometer: Mapped[Decimal] = mapped_column(Numeric(14,1),nullable=False)
    purpose: Mapped[str] = mapped_column(Text,nullable=False)
    __table_args__=(ForeignKeyConstraint(['dispatch_id','vehicle_id'],['operation_dispatches.dispatch_id','operation_dispatches.vehicle_id'],name='fk_trip_dispatch_vehicle'),CheckConstraint('end_odometer >= start_odometer AND start_odometer >= 0',name='ck_trip_mileage'),CheckConstraint('ended_at >= started_at',name='ck_trip_times'),UniqueConstraint('vehicle_id','started_at',name='uq_trip_start'))

class FuelEntry(History, Base):
    __tablename__='operation_fuel_entries'
    fuel_id: Mapped[str] = mapped_column(Uuid(as_uuid=False),primary_key=True,default=uuid_str)
    vehicle_id: Mapped[str] = mapped_column(ForeignKey('operation_vehicles.vehicle_id'),nullable=False,index=True)
    kind: Mapped[str] = mapped_column(String(20),nullable=False)
    liters: Mapped[Decimal] = mapped_column(Numeric(14,2),nullable=False)
    amount: Mapped[Decimal] = mapped_column(Numeric(14,2),nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True),nullable=False)
    notes: Mapped[str|None] = mapped_column(Text)
    __table_args__=(CheckConstraint("kind IN ('receipt','issue','refuel')",name='ck_fuel_kind'),CheckConstraint('liters > 0 AND amount >= 0',name='ck_fuel_amount'))

class VehicleService(Versioned, History, Base):
    __tablename__='operation_vehicle_services'
    service_id: Mapped[str] = mapped_column(Uuid(as_uuid=False),primary_key=True,default=uuid_str)
    vehicle_id: Mapped[str] = mapped_column(ForeignKey('operation_vehicles.vehicle_id'),nullable=False,index=True)
    kind: Mapped[str] = mapped_column(String(30),nullable=False)
    performed_on: Mapped[date] = mapped_column(Date,nullable=False)
    description: Mapped[str] = mapped_column(Text,nullable=False)
    cost: Mapped[Decimal] = mapped_column(Numeric(14,2),nullable=False,default=Decimal('0'))
    next_inspection_on: Mapped[date|None] = mapped_column(Date)
    next_service_on: Mapped[date|None] = mapped_column(Date)
    next_service_odometer: Mapped[Decimal|None] = mapped_column(Numeric(14,1))
    status: Mapped[str] = mapped_column(String(20),nullable=False,default='draft')
    reviewed_by: Mapped[str|None] = mapped_column(ForeignKey('app_users.user_id'))
    approved_by: Mapped[str|None] = mapped_column(ForeignKey('app_users.user_id'))
    approved_at: Mapped[datetime|None] = mapped_column(DateTime(timezone=True))
    review_note: Mapped[str|None] = mapped_column(Text)
    resolves_fault_id: Mapped[str|None] = mapped_column(ForeignKey('operation_vehicle_services.service_id'))
    resolved_by_service_id: Mapped[str|None] = mapped_column(ForeignKey('operation_vehicle_services.service_id'))
    resolved_at: Mapped[datetime|None] = mapped_column(DateTime(timezone=True))
    __table_args__=(UniqueConstraint('service_id','vehicle_id',name='uq_service_vehicle'),ForeignKeyConstraint(['resolves_fault_id','vehicle_id'],['operation_vehicle_services.service_id','operation_vehicle_services.vehicle_id'],name='fk_repair_fault_vehicle'),ForeignKeyConstraint(['resolved_by_service_id','vehicle_id'],['operation_vehicle_services.service_id','operation_vehicle_services.vehicle_id'],name='fk_fault_repair_vehicle'),CheckConstraint("resolves_fault_id IS NULL OR (kind = 'repair' AND resolves_fault_id <> service_id)",name='ck_repair_fault_link'),CheckConstraint("resolved_by_service_id IS NULL OR (kind = 'fault' AND resolved_by_service_id <> service_id AND resolved_at IS NOT NULL)",name='ck_fault_resolution'),CheckConstraint("kind IN ('inspection','vehicle_inspection','repair','fault','service')",name='ck_service_kind'),CheckConstraint('cost >= 0',name='ck_service_cost'),CheckConstraint('next_service_odometer IS NULL OR next_service_odometer >= 0',name='ck_service_odometer'),CheckConstraint('next_inspection_on IS NULL OR next_inspection_on >= performed_on',name='ck_service_inspection_date'),CheckConstraint('next_service_on IS NULL OR next_service_on >= performed_on',name='ck_service_service_date'),CheckConstraint("status IN ('draft','reviewed','approved','cancelled')",name='ck_service_status'),CheckConstraint("status <> 'approved' OR (reviewed_by IS NOT NULL AND approved_by IS NOT NULL AND approved_at IS NOT NULL)",name='ck_service_human'))

class OperationsImportPreview(Versioned, Base):
    __tablename__='operation_import_previews'
    preview_id: Mapped[str] = mapped_column(Uuid(as_uuid=False),primary_key=True,default=uuid_str)
    dataset: Mapped[str] = mapped_column(String(30),nullable=False)
    filename: Mapped[str] = mapped_column(Text,nullable=False)
    file_sha256: Mapped[str] = mapped_column(String(64),nullable=False)
    row_data: Mapped[list] = mapped_column(JSON,nullable=False)
    created_by: Mapped[str] = mapped_column(ForeignKey('app_users.user_id'),nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True),nullable=False)
    status: Mapped[str] = mapped_column(String(20),nullable=False,default='preview')
    applied_ids: Mapped[list] = mapped_column(JSON,nullable=False,default=list)
    __table_args__=(CheckConstraint("status IN ('preview','applied')",name='ck_import_status'),CheckConstraint("dataset IN ('incidents','vehicles','dispatches','trips','fuel','services','crew')",name='ck_import_dataset'))
