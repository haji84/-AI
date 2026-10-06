"""Workforce scheduling and time/leave ledgers backed by canonical Employee/Organization history."""
from datetime import date,datetime,time
from sqlalchemy import BigInteger,Boolean,CheckConstraint,Date,DateTime,ForeignKey,JSON,String,Text,Time,UniqueConstraint,Uuid
from sqlalchemy.orm import Mapped,mapped_column
from .db import Base
from .models import uuid_str,now_utc

class Versioned:
    version:Mapped[int]=mapped_column(BigInteger,nullable=False,default=1)
    created_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),nullable=False,default=now_utc)
    updated_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),nullable=False,default=now_utc)

class WorkforceShiftType(Versioned,Base):
    __tablename__='workforce_shift_types'
    shift_type_id:Mapped[str]=mapped_column(Uuid(as_uuid=False),primary_key=True,default=uuid_str)
    code:Mapped[str]=mapped_column(String(100),nullable=False,unique=True)
    name:Mapped[str]=mapped_column(String(200),nullable=False)
    start_time:Mapped[time]=mapped_column(Time,nullable=False)
    end_time:Mapped[time]=mapped_column(Time,nullable=False)
    timezone_name:Mapped[str]=mapped_column(String(80),nullable=False,default='Asia/Tokyo')
    cross_midnight:Mapped[bool]=mapped_column(Boolean,nullable=False,default=False)
    payable_minutes:Mapped[int]=mapped_column(BigInteger,nullable=False)
    active:Mapped[bool]=mapped_column(Boolean,nullable=False,default=True)
    __table_args__=(CheckConstraint('payable_minutes > 0 AND payable_minutes <= 2880',name='ck_workforce_shift_payable'),)

class WorkforceEmployeeQualification(Versioned,Base):
    __tablename__='workforce_employee_qualifications'
    qualification_id:Mapped[str]=mapped_column(Uuid(as_uuid=False),primary_key=True,default=uuid_str)
    employee_id:Mapped[str]=mapped_column(ForeignKey('employees.employee_id'),nullable=False,index=True)
    code:Mapped[str]=mapped_column(String(100),nullable=False)
    label:Mapped[str]=mapped_column(String(200),nullable=False)
    valid_from:Mapped[date]=mapped_column(Date,nullable=False)
    valid_to:Mapped[date|None]=mapped_column(Date)
    document_id:Mapped[str|None]=mapped_column(ForeignKey('documents.document_id'))
    active:Mapped[bool]=mapped_column(Boolean,nullable=False,default=True)
    created_by:Mapped[str]=mapped_column(ForeignKey('app_users.user_id'),nullable=False)
    __table_args__=(UniqueConstraint('employee_id','code','valid_from',name='uq_workforce_employee_qualification'),CheckConstraint('valid_to IS NULL OR valid_to >= valid_from',name='ck_workforce_qualification_dates'))

class WorkforceStaffingRule(Versioned,Base):
    __tablename__='workforce_staffing_rules'
    staffing_rule_id:Mapped[str]=mapped_column(Uuid(as_uuid=False),primary_key=True,default=uuid_str)
    organization_id:Mapped[str]=mapped_column(ForeignKey('organization_units.organization_id'),nullable=False,index=True)
    shift_type_id:Mapped[str]=mapped_column(ForeignKey('workforce_shift_types.shift_type_id'),nullable=False,index=True)
    shift_type_version:Mapped[int]=mapped_column(BigInteger,nullable=False)
    organization_version:Mapped[int]=mapped_column(BigInteger,nullable=False)
    min_staff:Mapped[int]=mapped_column(BigInteger,nullable=False)
    qualification_code:Mapped[str|None]=mapped_column(String(100))
    effective_from:Mapped[date]=mapped_column(Date,nullable=False)
    effective_to:Mapped[date|None]=mapped_column(Date)
    status:Mapped[str]=mapped_column(String(20),nullable=False,default='draft')
    rule_note:Mapped[str|None]=mapped_column(Text)
    created_by:Mapped[str]=mapped_column(ForeignKey('app_users.user_id'),nullable=False)
    reviewed_by:Mapped[str|None]=mapped_column(ForeignKey('app_users.user_id'))
    reviewed_at:Mapped[datetime|None]=mapped_column(DateTime(timezone=True))
    approved_by:Mapped[str|None]=mapped_column(ForeignKey('app_users.user_id'))
    approved_at:Mapped[datetime|None]=mapped_column(DateTime(timezone=True))
    __table_args__=(CheckConstraint('min_staff > 0',name='ck_workforce_min_staff'),CheckConstraint("status IN ('draft','reviewed','approved','cancelled')",name='ck_workforce_staffing_status'),CheckConstraint('effective_to IS NULL OR effective_to >= effective_from',name='ck_workforce_staffing_dates'))

class WorkforceRosterEntry(Versioned,Base):
    __tablename__='workforce_roster_entries'
    roster_entry_id:Mapped[str]=mapped_column(Uuid(as_uuid=False),primary_key=True,default=uuid_str)
    employee_id:Mapped[str]=mapped_column(ForeignKey('employees.employee_id'),nullable=False,index=True)
    organization_id:Mapped[str]=mapped_column(ForeignKey('organization_units.organization_id'),nullable=False,index=True)
    assignment_id:Mapped[str|None]=mapped_column(ForeignKey('employee_assignments.assignment_id'))
    assignment_version:Mapped[int|None]=mapped_column(BigInteger)
    shift_type_id:Mapped[str]=mapped_column(ForeignKey('workforce_shift_types.shift_type_id'),nullable=False,index=True)
    work_date:Mapped[date]=mapped_column(Date,nullable=False,index=True)
    starts_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),nullable=False)
    ends_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),nullable=False)
    payable_minutes:Mapped[int]=mapped_column(BigInteger,nullable=False)
    support_placement:Mapped[bool]=mapped_column(Boolean,nullable=False,default=False)
    status:Mapped[str]=mapped_column(String(20),nullable=False,default='draft')
    note:Mapped[str|None]=mapped_column(Text)
    document_id:Mapped[str|None]=mapped_column(ForeignKey('documents.document_id'))
    created_by:Mapped[str]=mapped_column(ForeignKey('app_users.user_id'),nullable=False)
    reviewed_by:Mapped[str|None]=mapped_column(ForeignKey('app_users.user_id'))
    reviewed_at:Mapped[datetime|None]=mapped_column(DateTime(timezone=True))
    approved_by:Mapped[str|None]=mapped_column(ForeignKey('app_users.user_id'))
    approved_at:Mapped[datetime|None]=mapped_column(DateTime(timezone=True))
    __table_args__=(CheckConstraint('ends_at > starts_at',name='ck_workforce_roster_period'),CheckConstraint('payable_minutes > 0',name='ck_workforce_roster_payable'),CheckConstraint("status IN ('draft','reviewed','approved','cancelled')",name='ck_workforce_roster_status'))

class WorkforceLeaveEntry(Versioned,Base):
    __tablename__='workforce_leave_entries'
    leave_entry_id:Mapped[str]=mapped_column(Uuid(as_uuid=False),primary_key=True,default=uuid_str)
    employee_id:Mapped[str]=mapped_column(ForeignKey('employees.employee_id'),nullable=False,index=True)
    leave_type:Mapped[str]=mapped_column(String(30),nullable=False)
    kind:Mapped[str]=mapped_column(String(20),nullable=False)
    quantity_minutes:Mapped[int]=mapped_column(BigInteger,nullable=False)
    effective_on:Mapped[date]=mapped_column(Date,nullable=False,index=True)
    leave_start_at:Mapped[datetime|None]=mapped_column(DateTime(timezone=True))
    leave_end_at:Mapped[datetime|None]=mapped_column(DateTime(timezone=True))
    expires_on:Mapped[date|None]=mapped_column(Date)
    private_reason:Mapped[str|None]=mapped_column(Text)
    status:Mapped[str]=mapped_column(String(20),nullable=False,default='draft')
    created_by:Mapped[str]=mapped_column(ForeignKey('app_users.user_id'),nullable=False)
    reviewed_by:Mapped[str|None]=mapped_column(ForeignKey('app_users.user_id'))
    reviewed_at:Mapped[datetime|None]=mapped_column(DateTime(timezone=True))
    approved_by:Mapped[str|None]=mapped_column(ForeignKey('app_users.user_id'))
    approved_at:Mapped[datetime|None]=mapped_column(DateTime(timezone=True))
    __table_args__=(CheckConstraint("leave_type IN ('annual','special','compensatory')",name='ck_workforce_leave_type'),CheckConstraint("kind IN ('grant','use','adjustment_add','adjustment_subtract','expire')",name='ck_workforce_leave_kind'),CheckConstraint('quantity_minutes > 0',name='ck_workforce_leave_quantity'),CheckConstraint('expires_on IS NULL OR expires_on >= effective_on',name='ck_workforce_leave_expiry'),CheckConstraint("(kind = 'use' AND leave_start_at IS NOT NULL AND leave_end_at IS NOT NULL AND leave_end_at > leave_start_at) OR (kind <> 'use' AND leave_start_at IS NULL AND leave_end_at IS NULL)",name='ck_workforce_leave_period'),CheckConstraint("status IN ('draft','reviewed','approved','cancelled')",name='ck_workforce_leave_status'))

class WorkforceAttendance(Versioned,Base):
    __tablename__='workforce_attendance'
    attendance_id:Mapped[str]=mapped_column(Uuid(as_uuid=False),primary_key=True,default=uuid_str)
    employee_id:Mapped[str]=mapped_column(ForeignKey('employees.employee_id'),nullable=False,index=True)
    roster_entry_id:Mapped[str|None]=mapped_column(ForeignKey('workforce_roster_entries.roster_entry_id'))
    work_date:Mapped[date]=mapped_column(Date,nullable=False,index=True)
    check_in_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),nullable=False)
    check_out_at:Mapped[datetime|None]=mapped_column(DateTime(timezone=True))
    worked_minutes:Mapped[int|None]=mapped_column(BigInteger)
    calculation:Mapped[dict]=mapped_column(JSON,nullable=False,default=dict)
    status:Mapped[str]=mapped_column(String(20),nullable=False,default='draft')
    created_by:Mapped[str]=mapped_column(ForeignKey('app_users.user_id'),nullable=False)
    reviewed_by:Mapped[str|None]=mapped_column(ForeignKey('app_users.user_id'))
    reviewed_at:Mapped[datetime|None]=mapped_column(DateTime(timezone=True))
    approved_by:Mapped[str|None]=mapped_column(ForeignKey('app_users.user_id'))
    approved_at:Mapped[datetime|None]=mapped_column(DateTime(timezone=True))
    __table_args__=(UniqueConstraint('roster_entry_id',name='uq_workforce_attendance_roster'),CheckConstraint('check_out_at IS NULL OR check_out_at > check_in_at',name='ck_workforce_attendance_period'),CheckConstraint('worked_minutes IS NULL OR worked_minutes >= 0',name='ck_workforce_attendance_minutes'),CheckConstraint("status IN ('draft','reviewed','approved','cancelled')",name='ck_workforce_attendance_status'))

class WorkforceTimeEntry(Versioned,Base):
    __tablename__='workforce_time_entries'
    time_entry_id:Mapped[str]=mapped_column(Uuid(as_uuid=False),primary_key=True,default=uuid_str)
    employee_id:Mapped[str]=mapped_column(ForeignKey('employees.employee_id'),nullable=False,index=True)
    attendance_id:Mapped[str|None]=mapped_column(ForeignKey('workforce_attendance.attendance_id'))
    kind:Mapped[str]=mapped_column(String(30),nullable=False)
    minutes:Mapped[int]=mapped_column(BigInteger,nullable=False)
    occurred_on:Mapped[date]=mapped_column(Date,nullable=False,index=True)
    note:Mapped[str|None]=mapped_column(Text)
    status:Mapped[str]=mapped_column(String(20),nullable=False,default='draft')
    created_by:Mapped[str]=mapped_column(ForeignKey('app_users.user_id'),nullable=False)
    reviewed_by:Mapped[str|None]=mapped_column(ForeignKey('app_users.user_id'))
    reviewed_at:Mapped[datetime|None]=mapped_column(DateTime(timezone=True))
    approved_by:Mapped[str|None]=mapped_column(ForeignKey('app_users.user_id'))
    approved_at:Mapped[datetime|None]=mapped_column(DateTime(timezone=True))
    __table_args__=(CheckConstraint("kind IN ('overtime','comp_grant','comp_use')",name='ck_workforce_time_kind'),CheckConstraint('minutes > 0',name='ck_workforce_time_minutes'),CheckConstraint("status IN ('draft','reviewed','approved','cancelled')",name='ck_workforce_time_status'))

class WorkforceImportPreview(Versioned,Base):
    __tablename__='workforce_import_previews'
    preview_id:Mapped[str]=mapped_column(Uuid(as_uuid=False),primary_key=True,default=uuid_str)
    dataset:Mapped[str]=mapped_column(String(30),nullable=False)
    schema_version:Mapped[str]=mapped_column(String(30),nullable=False)
    filename:Mapped[str]=mapped_column(Text,nullable=False)
    file_sha256:Mapped[str]=mapped_column(String(64),nullable=False)
    document_id:Mapped[str|None]=mapped_column(ForeignKey('documents.document_id'))
    row_data:Mapped[list]=mapped_column(JSON,nullable=False)
    status:Mapped[str]=mapped_column(String(20),nullable=False,default='preview')
    created_by:Mapped[str]=mapped_column(ForeignKey('app_users.user_id'),nullable=False)
    expires_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),nullable=False)
    __table_args__=(CheckConstraint("dataset IN ('rosters')",name='ck_workforce_import_dataset'),CheckConstraint("status IN ('preview','applied')",name='ck_workforce_import_status'))
