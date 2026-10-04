from __future__ import annotations

import uuid
from datetime import date, datetime, time, timezone
from decimal import Decimal

from sqlalchemy import (
    BigInteger,
    Boolean,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    JSON,
    Numeric,
    String,
    Text,
    Time,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.orm import Mapped, mapped_column

from .db import Base


def uuid_str() -> str:
    return str(uuid.uuid4())


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


class Employee(Base):
    __tablename__ = "employees"
    employee_id: Mapped[str] = mapped_column(Uuid(as_uuid=False), primary_key=True, default=uuid_str)
    employee_code: Mapped[str | None] = mapped_column(String(100), unique=True)
    display_name: Mapped[str] = mapped_column(String(200), nullable=False)
    organization_unit: Mapped[str | None] = mapped_column(String(200))
    title: Mapped[str | None] = mapped_column(String(200))
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)


class User(Base):
    __tablename__ = "app_users"
    user_id: Mapped[str] = mapped_column(Uuid(as_uuid=False), primary_key=True, default=uuid_str)
    employee_id: Mapped[str | None] = mapped_column(ForeignKey("employees.employee_id"), unique=True)
    username: Mapped[str] = mapped_column(String(100), unique=True, nullable=False, index=True)
    password_hash: Mapped[str] = mapped_column(Text, nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    version: Mapped[int] = mapped_column(BigInteger, nullable=False, default=1)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)


class Role(Base):
    __tablename__ = "roles"
    role_id: Mapped[str] = mapped_column(Uuid(as_uuid=False), primary_key=True, default=uuid_str)
    code: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    system_role: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)


class Permission(Base):
    __tablename__ = "permissions"
    permission_id: Mapped[str] = mapped_column(Uuid(as_uuid=False), primary_key=True, default=uuid_str)
    code: Mapped[str] = mapped_column(String(150), unique=True, nullable=False)
    description: Mapped[str | None] = mapped_column(Text)


class UserRole(Base):
    __tablename__ = "user_roles"
    user_id: Mapped[str] = mapped_column(ForeignKey("app_users.user_id", ondelete="CASCADE"), primary_key=True)
    role_id: Mapped[str] = mapped_column(ForeignKey("roles.role_id", ondelete="CASCADE"), primary_key=True)


class RolePermission(Base):
    __tablename__ = "role_permissions"
    role_id: Mapped[str] = mapped_column(ForeignKey("roles.role_id", ondelete="CASCADE"), primary_key=True)
    permission_id: Mapped[str] = mapped_column(ForeignKey("permissions.permission_id", ondelete="CASCADE"), primary_key=True)


class UserSession(Base):
    __tablename__ = "user_sessions"
    session_id: Mapped[str] = mapped_column(Uuid(as_uuid=False), primary_key=True, default=uuid_str)
    user_id: Mapped[str] = mapped_column(ForeignKey("app_users.user_id", ondelete="CASCADE"), nullable=False, index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    client_info: Mapped[dict | None] = mapped_column(JSON)


class AuditLog(Base):
    __tablename__ = "audit_logs"
    audit_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc, index=True)
    request_id: Mapped[str | None] = mapped_column(Uuid(as_uuid=False))
    user_id: Mapped[str | None] = mapped_column(ForeignKey("app_users.user_id"))
    action: Mapped[str] = mapped_column(String(120), nullable=False)
    entity_type: Mapped[str] = mapped_column(String(120), nullable=False)
    entity_id: Mapped[str | None] = mapped_column(String(120))
    before_data: Mapped[dict | list | str | None] = mapped_column(JSON)
    after_data: Mapped[dict | list | str | None] = mapped_column(JSON)
    success: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    ai_used: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    ai_model_version: Mapped[str | None] = mapped_column(String(200))
    client_info: Mapped[dict | None] = mapped_column(JSON)


class Facility(Base):
    __tablename__ = "facilities"
    building_id: Mapped[str] = mapped_column(Uuid(as_uuid=False), primary_key=True, default=uuid_str)
    legacy_internal_key: Mapped[str | None] = mapped_column(String(200), unique=True, index=True)
    legacy_category_key: Mapped[str | None] = mapped_column(Text)
    legacy_serial_no: Mapped[str | None] = mapped_column(Text)
    legacy_global_serial: Mapped[str | None] = mapped_column(Text)
    name: Mapped[str] = mapped_column(String(500), nullable=False)
    phone: Mapped[str | None] = mapped_column(Text)
    address: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="active")
    version: Mapped[int] = mapped_column(BigInteger, nullable=False, default=1)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    deleted_by: Mapped[str | None] = mapped_column(ForeignKey("app_users.user_id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)


class LegacyFacilitySourceRow(Base):
    __tablename__ = "legacy_facility_source_rows"
    source_row_id: Mapped[str] = mapped_column(Uuid(as_uuid=False), primary_key=True, default=uuid_str)
    source_file_id: Mapped[str] = mapped_column(ForeignKey("source_files.source_file_id"), nullable=False, index=True)
    building_id: Mapped[str] = mapped_column(ForeignKey("facilities.building_id"), nullable=False, index=True)
    legacy_internal_key: Mapped[str] = mapped_column(String(200), nullable=False, index=True)
    source_sheet: Mapped[str] = mapped_column(String(200), nullable=False, default="DB保存")
    source_row_no: Mapped[int] = mapped_column(Integer, nullable=False)
    raw_payload: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)
    __table_args__ = (UniqueConstraint("source_file_id", "source_sheet", "source_row_no", name="uq_legacy_facility_source_row"),)


class Document(Base):
    __tablename__ = "documents"
    document_id: Mapped[str] = mapped_column(Uuid(as_uuid=False), primary_key=True, default=uuid_str)
    building_id: Mapped[str | None] = mapped_column(ForeignKey("facilities.building_id"))
    storage_path: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    original_filename: Mapped[str] = mapped_column(Text, nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    size_bytes: Mapped[int | None] = mapped_column(BigInteger)
    mime_type: Mapped[str | None] = mapped_column(String(200))
    document_type: Mapped[str | None] = mapped_column(String(200))
    created_by: Mapped[str | None] = mapped_column(ForeignKey("app_users.user_id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)


class SourceFile(Base):
    __tablename__ = "source_files"
    source_file_id: Mapped[str] = mapped_column(Uuid(as_uuid=False), primary_key=True, default=uuid_str)
    source_kind: Mapped[str] = mapped_column(String(100), nullable=False)
    original_filename: Mapped[str] = mapped_column(Text, nullable=False)
    storage_path: Mapped[str | None] = mapped_column(Text)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    size_bytes: Mapped[int | None] = mapped_column(BigInteger)
    imported_by: Mapped[str | None] = mapped_column(ForeignKey("app_users.user_id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)
    __table_args__ = (UniqueConstraint("source_kind", "sha256", name="uq_source_kind_sha256"),)


class ImportRun(Base):
    __tablename__ = "import_runs"
    import_run_id: Mapped[str] = mapped_column(Uuid(as_uuid=False), primary_key=True, default=uuid_str)
    source_file_id: Mapped[str | None] = mapped_column(ForeignKey("source_files.source_file_id"))
    import_type: Mapped[str] = mapped_column(String(100), nullable=False)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="pending")
    started_by: Mapped[str | None] = mapped_column(ForeignKey("app_users.user_id"))
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    inserted_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    updated_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    skipped_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    error_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    details: Mapped[dict | None] = mapped_column(JSON)


class EmergencyImportBatch(Base):
    __tablename__ = "emergency_import_batches"
    batch_id: Mapped[str] = mapped_column(Uuid(as_uuid=False), primary_key=True, default=uuid_str)
    import_run_id: Mapped[str | None] = mapped_column(ForeignKey("import_runs.import_run_id"))
    target_period: Mapped[str | None] = mapped_column(String(100))
    station_scope: Mapped[str | None] = mapped_column(String(100))
    source_system: Mapped[str] = mapped_column(String(100), nullable=False, default="legacy_xlsm")
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="pending")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class EmergencyCase(Base):
    __tablename__ = "emergency_cases"
    emergency_case_id: Mapped[str] = mapped_column(Uuid(as_uuid=False), primary_key=True, default=uuid_str)
    source_case_key: Mapped[str] = mapped_column(Text, nullable=False, unique=True, index=True)
    call_month: Mapped[str | None] = mapped_column(String(100), index=True)
    station_code: Mapped[str | None] = mapped_column(String(100), index=True)
    dispatch_number: Mapped[str | None] = mapped_column(String(100))
    ambulance_code: Mapped[str | None] = mapped_column(String(100))
    call_date: Mapped[date | None] = mapped_column(Date)
    call_time: Mapped[time | None] = mapped_column(Time)
    dispatch_time: Mapped[time | None] = mapped_column(Time)
    scene_arrival_time: Mapped[time | None] = mapped_column(Time)
    leave_scene_time: Mapped[time | None] = mapped_column(Time)
    return_station_time: Mapped[time | None] = mapped_column(Time)
    incident_area_code: Mapped[str | None] = mapped_column(String(100))
    incident_address: Mapped[str | None] = mapped_column(Text)
    activity_type: Mapped[str | None] = mapped_column(Text)
    incident_type: Mapped[str | None] = mapped_column(Text)
    incident_place: Mapped[str | None] = mapped_column(Text)
    dispatch_vehicle: Mapped[str | None] = mapped_column(Text)
    command_text: Mapped[str | None] = mapped_column(Text)
    cpr_wishes_none: Mapped[str | None] = mapped_column(Text)
    source_batch_id: Mapped[str | None] = mapped_column(ForeignKey("emergency_import_batches.batch_id"))
    raw_payload: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    version: Mapped[int] = mapped_column(BigInteger, nullable=False, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)


class EmergencyPatient(Base):
    __tablename__ = "emergency_patients"
    emergency_patient_id: Mapped[str] = mapped_column(Uuid(as_uuid=False), primary_key=True, default=uuid_str)
    emergency_case_id: Mapped[str] = mapped_column(ForeignKey("emergency_cases.emergency_case_id", ondelete="CASCADE"), nullable=False, index=True)
    patient_number: Mapped[int] = mapped_column(Integer, nullable=False)
    sex: Mapped[str | None] = mapped_column(Text)
    age: Mapped[int | None] = mapped_column(Integer)
    age_class: Mapped[str | None] = mapped_column(Text)
    residence_class: Mapped[str | None] = mapped_column(Text)
    hospital_code: Mapped[str | None] = mapped_column(Text, index=True)
    hospital_category: Mapped[str | None] = mapped_column(Text)
    department_code: Mapped[str | None] = mapped_column(Text)
    severity_code: Mapped[str | None] = mapped_column(Text, index=True)
    injury_class_major: Mapped[str | None] = mapped_column(Text)
    injury_class_middle: Mapped[str | None] = mapped_column(Text)
    injury_class_minor: Mapped[str | None] = mapped_column(Text)
    resuscitation_code: Mapped[str | None] = mapped_column(Text)
    first_aid_flag: Mapped[str | None] = mapped_column(Text)
    condition_text: Mapped[str | None] = mapped_column(Text)
    diagnosis_text: Mapped[str | None] = mapped_column(Text)
    symptoms_text: Mapped[str | None] = mapped_column(Text)
    medical_history_text: Mapped[str | None] = mapped_column(Text)
    other_information_text: Mapped[str | None] = mapped_column(Text)
    team_urgency: Mapped[str | None] = mapped_column(Text)
    source_batch_id: Mapped[str | None] = mapped_column(ForeignKey("emergency_import_batches.batch_id"))
    raw_payload: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    version: Mapped[int] = mapped_column(BigInteger, nullable=False, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)
    __table_args__ = (UniqueConstraint("emergency_case_id", "patient_number", name="uq_emergency_patient_case_no"),)


class EmergencyCrewAssignment(Base):
    __tablename__ = "emergency_crew_assignments"
    crew_assignment_id: Mapped[str] = mapped_column(Uuid(as_uuid=False), primary_key=True, default=uuid_str)
    emergency_case_id: Mapped[str] = mapped_column(ForeignKey("emergency_cases.emergency_case_id", ondelete="CASCADE"), nullable=False, index=True)
    source_record_key: Mapped[str] = mapped_column(Text, nullable=False, unique=True, index=True)
    source_row_no: Mapped[int | None] = mapped_column(Integer)
    source_identity_status: Mapped[str] = mapped_column(String(50), nullable=False, default="complete")
    crew_role: Mapped[str] = mapped_column(Text, nullable=False)
    source_crew_code: Mapped[str | None] = mapped_column(Text)
    employee_id: Mapped[str | None] = mapped_column(ForeignKey("employees.employee_id"), index=True)
    qualification: Mapped[str | None] = mapped_column(Text)
    rank_name: Mapped[str | None] = mapped_column(Text)
    source_batch_id: Mapped[str | None] = mapped_column(ForeignKey("emergency_import_batches.batch_id"))
    raw_payload: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)


class EmergencyClinicalFlag(Base):
    __tablename__ = "emergency_clinical_flags"
    flag_id: Mapped[str] = mapped_column(Uuid(as_uuid=False), primary_key=True, default=uuid_str)
    emergency_patient_id: Mapped[str] = mapped_column(ForeignKey("emergency_patients.emergency_patient_id", ondelete="CASCADE"), nullable=False, index=True)
    flag_type: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    flag_value: Mapped[str] = mapped_column(Text, nullable=False)
    derivation_method: Mapped[str] = mapped_column(String(30), nullable=False)
    evidence: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    confidence: Mapped[float | None] = mapped_column(Float)
    review_status: Mapped[str] = mapped_column(String(30), nullable=False, default="unreviewed")
    confirmed_by: Mapped[str | None] = mapped_column(ForeignKey("app_users.user_id"))
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)


class ModuleDefinition(Base):
    __tablename__ = "module_definitions"
    module_id: Mapped[str] = mapped_column(Uuid(as_uuid=False), primary_key=True, default=uuid_str)
    code: Mapped[str] = mapped_column(String(100), unique=True, nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    version: Mapped[str] = mapped_column(String(50), nullable=False, default="1.0.0")
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="active")
    manifest: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)


class FeatureFlag(Base):
    __tablename__ = "feature_flags"
    feature_flag_id: Mapped[str] = mapped_column(Uuid(as_uuid=False), primary_key=True, default=uuid_str)
    key: Mapped[str] = mapped_column(String(150), unique=True, nullable=False, index=True)
    module_code: Mapped[str | None] = mapped_column(String(100), index=True)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    config: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    version: Mapped[int] = mapped_column(BigInteger, nullable=False, default=1)
    updated_by: Mapped[str | None] = mapped_column(ForeignKey("app_users.user_id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)


class FormTemplate(Base):
    __tablename__ = "form_templates"
    form_template_id: Mapped[str] = mapped_column(Uuid(as_uuid=False), primary_key=True, default=uuid_str)
    template_code: Mapped[str] = mapped_column(String(150), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(300), nullable=False)
    module_code: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    document_id: Mapped[str] = mapped_column(ForeignKey("documents.document_id"), nullable=False)
    version_label: Mapped[str] = mapped_column(String(80), nullable=False)
    issuer: Mapped[str | None] = mapped_column(String(300))
    effective_from: Mapped[date | None] = mapped_column(Date)
    effective_to: Mapped[date | None] = mapped_column(Date)
    field_mapping: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    print_settings: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    modification_policy: Mapped[str] = mapped_column(String(50), nullable=False, default="fill_only")
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="active")
    created_by: Mapped[str | None] = mapped_column(ForeignKey("app_users.user_id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)
    __table_args__ = (UniqueConstraint("template_code", "version_label", name="uq_form_template_version"),)


class ChangeRequest(Base):
    __tablename__ = "change_requests"
    change_request_id: Mapped[str] = mapped_column(Uuid(as_uuid=False), primary_key=True, default=uuid_str)
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    request_text: Mapped[str] = mapped_column(Text, nullable=False)
    target_module: Mapped[str | None] = mapped_column(String(100), index=True)
    target_surface: Mapped[str | None] = mapped_column(String(200))
    status: Mapped[str] = mapped_column(String(40), nullable=False, default="draft", index=True)
    risk_level: Mapped[str] = mapped_column(String(30), nullable=False, default="unassessed")
    analysis: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    proposed_changes: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    acceptance_criteria: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    sandbox_result: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    requester_id: Mapped[str | None] = mapped_column(ForeignKey("app_users.user_id"), index=True)
    approved_by: Mapped[str | None] = mapped_column(ForeignKey("app_users.user_id"))
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    version: Mapped[int] = mapped_column(BigInteger, nullable=False, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)


class ExtensionIntake(Base):
    __tablename__ = "extension_intakes"
    extension_intake_id: Mapped[str] = mapped_column(Uuid(as_uuid=False), primary_key=True, default=uuid_str)
    source_document_id: Mapped[str] = mapped_column(ForeignKey("documents.document_id"), nullable=False, index=True)
    requested_goal: Mapped[str | None] = mapped_column(Text)
    target_module: Mapped[str | None] = mapped_column(String(100), index=True)
    detected_kind: Mapped[str | None] = mapped_column(String(100))
    status: Mapped[str] = mapped_column(String(40), nullable=False, default="pending_analysis", index=True)
    analysis: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    diff: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    proposed_manifest: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    sandbox_result: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    submitted_by: Mapped[str | None] = mapped_column(ForeignKey("app_users.user_id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)


class ContractCounterparty(Base):
    __tablename__ = "contract_counterparties"
    counterparty_id: Mapped[str] = mapped_column(Uuid(as_uuid=False), primary_key=True, default=uuid_str)
    name: Mapped[str] = mapped_column(String(500), nullable=False, index=True)
    registration_no: Mapped[str | None] = mapped_column(String(100), index=True)
    address: Mapped[str | None] = mapped_column(Text)
    contact: Mapped[str | None] = mapped_column(Text)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    version: Mapped[int] = mapped_column(BigInteger, nullable=False, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)


class ContractCase(Base):
    __tablename__ = "contract_cases"
    contract_case_id: Mapped[str] = mapped_column(Uuid(as_uuid=False), primary_key=True, default=uuid_str)
    contract_no: Mapped[str | None] = mapped_column(String(150), unique=True, index=True)
    title: Mapped[str] = mapped_column(String(500), nullable=False, index=True)
    counterparty_id: Mapped[str | None] = mapped_column(ForeignKey("contract_counterparties.counterparty_id"), index=True)
    contract_method: Mapped[str | None] = mapped_column(String(150))
    amount: Mapped[Decimal | None] = mapped_column(Numeric(18, 2))
    currency: Mapped[str] = mapped_column(String(10), nullable=False, default="JPY")
    start_date: Mapped[date | None] = mapped_column(Date)
    end_date: Mapped[date | None] = mapped_column(Date)
    status: Mapped[str] = mapped_column(String(40), nullable=False, default="draft", index=True)
    version: Mapped[int] = mapped_column(BigInteger, nullable=False, default=1)
    created_by: Mapped[str | None] = mapped_column(ForeignKey("app_users.user_id"))
    approved_by: Mapped[str | None] = mapped_column(ForeignKey("app_users.user_id"))
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)


class ContractDocument(Base):
    __tablename__ = "contract_documents"
    contract_document_id: Mapped[str] = mapped_column(Uuid(as_uuid=False), primary_key=True, default=uuid_str)
    contract_case_id: Mapped[str] = mapped_column(ForeignKey("contract_cases.contract_case_id", ondelete="CASCADE"), nullable=False, index=True)
    document_id: Mapped[str] = mapped_column(ForeignKey("documents.document_id"), nullable=False)
    document_role: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    form_template_id: Mapped[str | None] = mapped_column(ForeignKey("form_templates.form_template_id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)
    __table_args__ = (UniqueConstraint("contract_case_id", "document_id", name="uq_contract_document"),)


class ContractChange(Base):
    __tablename__ = "contract_changes"
    contract_change_id: Mapped[str] = mapped_column(Uuid(as_uuid=False), primary_key=True, default=uuid_str)
    contract_case_id: Mapped[str] = mapped_column(ForeignKey("contract_cases.contract_case_id", ondelete="CASCADE"), nullable=False, index=True)
    sequence_no: Mapped[int] = mapped_column(Integer, nullable=False)
    reason: Mapped[str | None] = mapped_column(Text)
    before_data: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    after_data: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    created_by: Mapped[str | None] = mapped_column(ForeignKey("app_users.user_id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)
    __table_args__ = (UniqueConstraint("contract_case_id", "sequence_no", name="uq_contract_change_sequence"),)


class ImportAdapterDefinition(Base):
    __tablename__ = "import_adapter_definitions"
    import_adapter_id: Mapped[str] = mapped_column(Uuid(as_uuid=False), primary_key=True, default=uuid_str)
    code: Mapped[str] = mapped_column(String(150), unique=True, nullable=False, index=True)
    module_code: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    source_kind: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    version: Mapped[str] = mapped_column(String(50), nullable=False)
    config: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="active")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)


class ExtensionDeployment(Base):
    __tablename__ = "extension_deployments"
    extension_deployment_id: Mapped[str] = mapped_column(Uuid(as_uuid=False), primary_key=True, default=uuid_str)
    change_request_id: Mapped[str] = mapped_column(ForeignKey("change_requests.change_request_id"), nullable=False, index=True)
    module_code: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    release_version: Mapped[str] = mapped_column(String(80), nullable=False)
    previous_version: Mapped[str | None] = mapped_column(String(80))
    migration_version: Mapped[str | None] = mapped_column(String(120))
    feature_flag_key: Mapped[str | None] = mapped_column(String(150))
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="applied", index=True)
    rollback_of: Mapped[str | None] = mapped_column(ForeignKey("extension_deployments.extension_deployment_id"))
    evidence: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    applied_by: Mapped[str | None] = mapped_column(ForeignKey("app_users.user_id"))
    applied_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)

class FacilityDetail(Base):
    __tablename__ = "facility_details"
    building_id: Mapped[str] = mapped_column(ForeignKey("facilities.building_id", ondelete="CASCADE"), primary_key=True)
    legacy_book_type: Mapped[str | None] = mapped_column(Text)
    content_as_of: Mapped[str | None] = mapped_column(Text)
    classification_code: Mapped[str | None] = mapped_column(Text, index=True)
    classification_detail_1: Mapped[str | None] = mapped_column(Text)
    classification_detail_2: Mapped[str | None] = mapped_column(Text)
    zoning: Mapped[str | None] = mapped_column(Text)
    article8_partition: Mapped[str | None] = mapped_column(Text)
    structure: Mapped[str | None] = mapped_column(Text)
    above_ground_floors: Mapped[int | None] = mapped_column(Integer)
    basement_floors: Mapped[int | None] = mapped_column(Integer)
    building_area: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    total_floor_area: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    occupancy_total: Mapped[int | None] = mapped_column(Integer)
    employee_total: Mapped[int | None] = mapped_column(Integer)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)


class FacilityContact(Base):
    __tablename__ = "facility_contacts"
    building_id: Mapped[str] = mapped_column(ForeignKey("facilities.building_id", ondelete="CASCADE"), primary_key=True)
    representative_name: Mapped[str | None] = mapped_column(Text)
    representative_title: Mapped[str | None] = mapped_column(Text)
    representative_address: Mapped[str | None] = mapped_column(Text)
    representative_phone: Mapped[str | None] = mapped_column(Text)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)


class FacilityFloor(Base):
    __tablename__ = "facility_floors"
    facility_floor_id: Mapped[str] = mapped_column(Uuid(as_uuid=False), primary_key=True, default=uuid_str)
    building_id: Mapped[str] = mapped_column(ForeignKey("facilities.building_id", ondelete="CASCADE"), nullable=False, index=True)
    floor_number: Mapped[int] = mapped_column(Integer, nullable=False)
    floor_label: Mapped[str | None] = mapped_column(String(50))
    floor_area: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    use_name: Mapped[str | None] = mapped_column(Text)
    occupancy_count: Mapped[int | None] = mapped_column(Integer)
    employee_count: Mapped[int | None] = mapped_column(Integer)
    windowless_status: Mapped[str | None] = mapped_column(Text)
    curtain_status: Mapped[str | None] = mapped_column(Text)
    carpet_status: Mapped[str | None] = mapped_column(Text)
    plywood_status: Mapped[str | None] = mapped_column(Text)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)
    __table_args__ = (UniqueConstraint("building_id", "floor_number", name="uq_facility_floor_no"),)


class Inspection(Base):
    __tablename__ = "inspections"
    inspection_id: Mapped[str] = mapped_column(Uuid(as_uuid=False), primary_key=True, default=uuid_str)
    building_id: Mapped[str] = mapped_column(ForeignKey("facilities.building_id", ondelete="CASCADE"), nullable=False, index=True)
    inspected_at: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    inspection_type: Mapped[str] = mapped_column(String(120), nullable=False, default="general")
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="open", index=True)
    notes: Mapped[str | None] = mapped_column(Text)
    version: Mapped[int] = mapped_column(BigInteger, nullable=False, default=1)
    created_by: Mapped[str | None] = mapped_column(ForeignKey("app_users.user_id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)


class InspectionFinding(Base):
    __tablename__ = "inspection_findings"
    finding_id: Mapped[str] = mapped_column(Uuid(as_uuid=False), primary_key=True, default=uuid_str)
    inspection_id: Mapped[str] = mapped_column(ForeignKey("inspections.inspection_id", ondelete="CASCADE"), nullable=False, index=True)
    category: Mapped[str | None] = mapped_column(String(200))
    finding_text: Mapped[str] = mapped_column(Text, nullable=False)
    severity: Mapped[str | None] = mapped_column(String(30))
    corrective_status: Mapped[str] = mapped_column(String(30), nullable=False, default="open", index=True)
    due_date: Mapped[date | None] = mapped_column(Date)
    completed_at: Mapped[date | None] = mapped_column(Date)
    notes: Mapped[str | None] = mapped_column(Text)
    version: Mapped[int] = mapped_column(BigInteger, nullable=False, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)


class SubmissionType(Base):
    __tablename__ = "submission_types"
    submission_type_id: Mapped[str] = mapped_column(Uuid(as_uuid=False), primary_key=True, default=uuid_str)
    code: Mapped[str] = mapped_column(String(120), unique=True, nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(300), nullable=False)
    category: Mapped[str | None] = mapped_column(String(120))
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    requires_document: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    rules: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)


class Submission(Base):
    __tablename__ = "submissions"
    submission_id: Mapped[str] = mapped_column(Uuid(as_uuid=False), primary_key=True, default=uuid_str)
    building_id: Mapped[str] = mapped_column(ForeignKey("facilities.building_id", ondelete="CASCADE"), nullable=False, index=True)
    submission_type_id: Mapped[str] = mapped_column(ForeignKey("submission_types.submission_type_id"), nullable=False, index=True)
    official_number: Mapped[str | None] = mapped_column(String(30), index=True)
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=now_utc, index=True)
    submitted_at: Mapped[date | None] = mapped_column(Date)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="received", index=True)
    submitted_by: Mapped[str | None] = mapped_column(Text)
    notes: Mapped[str | None] = mapped_column(Text)
    payload_data: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    version: Mapped[int] = mapped_column(BigInteger, nullable=False, default=1)
    created_by: Mapped[str | None] = mapped_column(ForeignKey("app_users.user_id"))
    reviewed_by: Mapped[str | None] = mapped_column(ForeignKey("app_users.user_id"))
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)


class SubmissionFile(Base):
    __tablename__ = "submission_files"
    submission_id: Mapped[str] = mapped_column(ForeignKey("submissions.submission_id", ondelete="CASCADE"), primary_key=True)
    document_id: Mapped[str] = mapped_column(ForeignKey("documents.document_id", ondelete="RESTRICT"), primary_key=True)
    file_role: Mapped[str] = mapped_column(String(80), nullable=False, default="original")
    page_order: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)


class EquipmentInspectionReport(Base):
    __tablename__ = "equipment_inspection_reports"
    report_id: Mapped[str] = mapped_column(Uuid(as_uuid=False), primary_key=True, default=uuid_str)
    building_id: Mapped[str] = mapped_column(ForeignKey("facilities.building_id", ondelete="CASCADE"), nullable=False, index=True)
    submission_id: Mapped[str | None] = mapped_column(ForeignKey("submissions.submission_id", ondelete="CASCADE"), unique=True)
    equipment_label: Mapped[str | None] = mapped_column(Text)
    submitted_at: Mapped[date | None] = mapped_column(Date)
    inspection_date: Mapped[date | None] = mapped_column(Date)
    result_summary: Mapped[str | None] = mapped_column(Text)
    next_due_at: Mapped[date | None] = mapped_column(Date)
    source_kind: Mapped[str] = mapped_column(String(30), nullable=False, default="submission", index=True)
    raw_result_text: Mapped[str | None] = mapped_column(Text)
    raw_report_text: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)


class FireManagementAssignment(Base):
    __tablename__ = "fire_management_assignments"
    assignment_id: Mapped[str] = mapped_column(Uuid(as_uuid=False), primary_key=True, default=uuid_str)
    building_id: Mapped[str] = mapped_column(ForeignKey("facilities.building_id", ondelete="CASCADE"), nullable=False, index=True)
    submission_id: Mapped[str | None] = mapped_column(ForeignKey("submissions.submission_id", ondelete="CASCADE"), unique=True)
    manager_name: Mapped[str | None] = mapped_column(Text)
    manager_title: Mapped[str | None] = mapped_column(Text)
    appointed_at: Mapped[date | None] = mapped_column(Date)
    appointment_submitted_at: Mapped[date | None] = mapped_column(Date)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="active")
    source_kind: Mapped[str] = mapped_column(String(30), nullable=False, default="submission", index=True)
    legacy_slot: Mapped[int | None] = mapped_column(Integer)
    raw_submission_text: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)


class FirePlan(Base):
    __tablename__ = "fire_plans"
    fire_plan_id: Mapped[str] = mapped_column(Uuid(as_uuid=False), primary_key=True, default=uuid_str)
    building_id: Mapped[str] = mapped_column(ForeignKey("facilities.building_id", ondelete="CASCADE"), nullable=False, index=True)
    submission_id: Mapped[str | None] = mapped_column(ForeignKey("submissions.submission_id", ondelete="CASCADE"), unique=True)
    submitted_at: Mapped[date | None] = mapped_column(Date)
    plan_version_label: Mapped[str | None] = mapped_column(String(120))
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="submitted")
    source_kind: Mapped[str] = mapped_column(String(30), nullable=False, default="submission", index=True)
    legacy_slot: Mapped[int | None] = mapped_column(Integer)
    raw_submission_text: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)


class InspectionReportingProfile(Base):
    __tablename__ = "inspection_reporting_profiles"
    building_id: Mapped[str] = mapped_column(ForeignKey("facilities.building_id", ondelete="CASCADE"), primary_key=True)
    report_cycle_years: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    next_due_date: Mapped[date | None] = mapped_column(Date)
    raw_cycle_text: Mapped[str | None] = mapped_column(Text)
    raw_next_due_text: Mapped[str | None] = mapped_column(Text)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)


class GuidanceRecord(Base):
    __tablename__ = "guidance_records"
    guidance_id: Mapped[str] = mapped_column(Uuid(as_uuid=False), primary_key=True, default=uuid_str)
    building_id: Mapped[str] = mapped_column(ForeignKey("facilities.building_id", ondelete="CASCADE"), nullable=False, index=True)
    subject: Mapped[str | None] = mapped_column(Text)
    issued_at: Mapped[date | None] = mapped_column(Date)
    content: Mapped[str | None] = mapped_column(Text)
    legacy_slot: Mapped[int | None] = mapped_column(Integer)
    source_kind: Mapped[str] = mapped_column(String(30), nullable=False, default="legacy", index=True)
    raw_issued_text: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)


class DocumentAnalysis(Base):
    __tablename__ = "document_analyses"
    document_analysis_id: Mapped[str] = mapped_column(Uuid(as_uuid=False), primary_key=True, default=uuid_str)
    document_id: Mapped[str] = mapped_column(ForeignKey("documents.document_id", ondelete="CASCADE"), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(40), nullable=False, default="analyzed", index=True)
    extraction_method: Mapped[str] = mapped_column(String(80), nullable=False)
    extracted_text: Mapped[str] = mapped_column(Text, nullable=False, default="")
    page_count: Mapped[int | None] = mapped_column(Integer)
    detected_submission_type_code: Mapped[str | None] = mapped_column(String(120), index=True)
    detected_fields: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    facility_candidates: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    difference_candidates: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    confidence: Mapped[float | None] = mapped_column(Float)
    evidence: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    selected_building_id: Mapped[str | None] = mapped_column(ForeignKey("facilities.building_id"), index=True)
    selected_submission_type_code: Mapped[str | None] = mapped_column(String(120))
    reviewed_by: Mapped[str | None] = mapped_column(ForeignKey("app_users.user_id"))
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    version: Mapped[int] = mapped_column(BigInteger, nullable=False, default=1)
    created_by: Mapped[str | None] = mapped_column(ForeignKey("app_users.user_id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)


class FacilityChangeProposal(Base):
    __tablename__ = "facility_change_proposals"
    facility_change_proposal_id: Mapped[str] = mapped_column(Uuid(as_uuid=False), primary_key=True, default=uuid_str)
    document_analysis_id: Mapped[str] = mapped_column(ForeignKey("document_analyses.document_analysis_id", ondelete="CASCADE"), nullable=False, index=True)
    building_id: Mapped[str] = mapped_column(ForeignKey("facilities.building_id", ondelete="CASCADE"), nullable=False, index=True)
    expected_facility_version: Mapped[int] = mapped_column(BigInteger, nullable=False)
    changes: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="pending", index=True)
    reviewed_by: Mapped[str | None] = mapped_column(ForeignKey("app_users.user_id"))
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    applied_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    version: Mapped[int] = mapped_column(BigInteger, nullable=False, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)

class LegalRule(Base):
    __tablename__ = "legal_rules"
    rule_id: Mapped[str] = mapped_column(Uuid(as_uuid=False), primary_key=True, default=uuid_str)
    rule_code: Mapped[str] = mapped_column(String(150), unique=True, nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(300), nullable=False)
    domain: Mapped[str] = mapped_column(String(60), nullable=False, index=True)
    description: Mapped[str | None] = mapped_column(Text)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_by: Mapped[str | None] = mapped_column(ForeignKey("app_users.user_id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)


class LegalRuleVersion(Base):
    __tablename__ = "legal_rule_versions"
    legal_rule_version_id: Mapped[str] = mapped_column(Uuid(as_uuid=False), primary_key=True, default=uuid_str)
    rule_id: Mapped[str] = mapped_column(ForeignKey("legal_rules.rule_id", ondelete="CASCADE"), nullable=False, index=True)
    version_no: Mapped[int] = mapped_column(Integer, nullable=False)
    effective_from: Mapped[date] = mapped_column(Date, nullable=False)
    effective_to: Mapped[date | None] = mapped_column(Date)
    conditions: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    outcome: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    source_document_id: Mapped[str | None] = mapped_column(ForeignKey("documents.document_id"))
    source_reference: Mapped[str | None] = mapped_column(Text)
    source_legal_document_version_id: Mapped[str | None] = mapped_column(ForeignKey("legal_source_document_versions.legal_source_document_version_id"))
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="draft")
    approved_by: Mapped[str | None] = mapped_column(ForeignKey("app_users.user_id"))
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    version: Mapped[int] = mapped_column(BigInteger, nullable=False, default=1)
    created_by: Mapped[str | None] = mapped_column(ForeignKey("app_users.user_id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)
    __table_args__ = (UniqueConstraint("rule_id", "version_no", name="uq_legal_rule_version"),)


class RequirementEvaluation(Base):
    __tablename__ = "requirement_evaluations"
    evaluation_id: Mapped[str] = mapped_column(Uuid(as_uuid=False), primary_key=True, default=uuid_str)
    building_id: Mapped[str] = mapped_column(ForeignKey("facilities.building_id", ondelete="CASCADE"), nullable=False, index=True)
    domain: Mapped[str] = mapped_column(String(60), nullable=False, index=True)
    evaluation_date: Mapped[date] = mapped_column(Date, nullable=False)
    facility_version: Mapped[int] = mapped_column(BigInteger, nullable=False)
    engine_version: Mapped[str] = mapped_column(String(50), nullable=False, default="phase5-v1")
    input_snapshot: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    results: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="candidate")
    reviewed_by: Mapped[str | None] = mapped_column(ForeignKey("app_users.user_id"))
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_by: Mapped[str | None] = mapped_column(ForeignKey("app_users.user_id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)

class LegalJurisdiction(Base):
    __tablename__ = "legal_jurisdictions"
    jurisdiction_id: Mapped[str] = mapped_column(Uuid(as_uuid=False), primary_key=True, default=uuid_str)
    code: Mapped[str] = mapped_column(String(150), unique=True, nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(300), nullable=False)
    jurisdiction_type: Mapped[str] = mapped_column(String(40), nullable=False)
    parent_jurisdiction_id: Mapped[str | None] = mapped_column(ForeignKey("legal_jurisdictions.jurisdiction_id"))
    official_base_url: Mapped[str | None] = mapped_column(Text)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)


class LegalProfile(Base):
    __tablename__ = "legal_profiles"
    legal_profile_id: Mapped[str] = mapped_column(Uuid(as_uuid=False), primary_key=True, default=uuid_str)
    code: Mapped[str] = mapped_column(String(150), unique=True, nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(300), nullable=False)
    fire_department_name: Mapped[str | None] = mapped_column(String(300))
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_by: Mapped[str | None] = mapped_column(ForeignKey("app_users.user_id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)


class LegalProfileJurisdiction(Base):
    __tablename__ = "legal_profile_jurisdictions"
    legal_profile_id: Mapped[str] = mapped_column(ForeignKey("legal_profiles.legal_profile_id", ondelete="CASCADE"), primary_key=True)
    jurisdiction_id: Mapped[str] = mapped_column(ForeignKey("legal_jurisdictions.jurisdiction_id", ondelete="CASCADE"), primary_key=True)
    applicability: Mapped[str] = mapped_column(String(40), nullable=False, default="applicable")
    priority: Mapped[int] = mapped_column(Integer, nullable=False, default=100)


class LegalSource(Base):
    __tablename__ = "legal_sources"
    legal_source_id: Mapped[str] = mapped_column(Uuid(as_uuid=False), primary_key=True, default=uuid_str)
    legal_profile_id: Mapped[str | None] = mapped_column(ForeignKey("legal_profiles.legal_profile_id", ondelete="CASCADE"), index=True)
    jurisdiction_id: Mapped[str] = mapped_column(ForeignKey("legal_jurisdictions.jurisdiction_id", ondelete="CASCADE"), nullable=False, index=True)
    source_code: Mapped[str] = mapped_column(String(180), nullable=False)
    name: Mapped[str] = mapped_column(String(300), nullable=False)
    source_type: Mapped[str] = mapped_column(String(60), nullable=False)
    adapter_type: Mapped[str] = mapped_column(String(80), nullable=False)
    base_url: Mapped[str] = mapped_column(Text, nullable=False)
    index_url: Mapped[str | None] = mapped_column(Text)
    update_mode: Mapped[str] = mapped_column(String(30), nullable=False, default="online")
    content_scope: Mapped[str] = mapped_column(String(30), nullable=False, default="all")
    sync_frequency: Mapped[str] = mapped_column(String(30), nullable=False, default="daily")
    trust_level: Mapped[str] = mapped_column(String(30), nullable=False, default="official")
    parser_config: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    content_current_date: Mapped[date | None] = mapped_column(Date)
    last_checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_success_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    etag: Mapped[str | None] = mapped_column(Text)
    last_modified: Mapped[str | None] = mapped_column(Text)
    index_hash: Mapped[str | None] = mapped_column(String(64))
    coverage_status: Mapped[str] = mapped_column(String(30), nullable=False, default="unverified")
    expected_document_count: Mapped[int | None] = mapped_column(Integer)
    captured_document_count: Mapped[int | None] = mapped_column(Integer)
    last_full_sync_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    stale_after_hours: Mapped[int] = mapped_column(Integer, nullable=False, default=168)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)
    __table_args__ = (UniqueConstraint("jurisdiction_id", "source_code", name="uq_legal_source_code"),)


class LegalSourceDocument(Base):
    __tablename__ = "legal_source_documents"
    legal_source_document_id: Mapped[str] = mapped_column(Uuid(as_uuid=False), primary_key=True, default=uuid_str)
    legal_source_id: Mapped[str] = mapped_column(ForeignKey("legal_sources.legal_source_id", ondelete="CASCADE"), nullable=False, index=True)
    external_id: Mapped[str] = mapped_column(Text, nullable=False)
    document_type: Mapped[str] = mapped_column(String(80), nullable=False)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    document_number: Mapped[str | None] = mapped_column(Text)
    promulgation_date: Mapped[date | None] = mapped_column(Date)
    enacted_date: Mapped[date | None] = mapped_column(Date)
    current_status: Mapped[str] = mapped_column(String(30), nullable=False, default="current")
    source_url: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)
    __table_args__ = (UniqueConstraint("legal_source_id", "external_id", name="uq_legal_source_document"),)


class LegalSourceDocumentVersion(Base):
    __tablename__ = "legal_source_document_versions"
    legal_source_document_version_id: Mapped[str] = mapped_column(Uuid(as_uuid=False), primary_key=True, default=uuid_str)
    legal_source_document_id: Mapped[str] = mapped_column(ForeignKey("legal_source_documents.legal_source_document_id", ondelete="CASCADE"), nullable=False, index=True)
    version_label: Mapped[str | None] = mapped_column(String(160))
    revision_external_id: Mapped[str | None] = mapped_column(Text)
    effective_from: Mapped[date | None] = mapped_column(Date)
    effective_to: Mapped[date | None] = mapped_column(Date)
    source_current_date: Mapped[date | None] = mapped_column(Date)
    retrieved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)
    raw_document_id: Mapped[str | None] = mapped_column(ForeignKey("documents.document_id"))
    normalized_text: Mapped[str] = mapped_column(Text, nullable=False, default="")
    structured_content: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    source_url: Mapped[str | None] = mapped_column(Text)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    previous_version_id: Mapped[str | None] = mapped_column(ForeignKey("legal_source_document_versions.legal_source_document_version_id"))
    change_summary: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    parse_status: Mapped[str] = mapped_column(String(30), nullable=False, default="stored")
    structure_status: Mapped[str] = mapped_column(String(30), nullable=False, default="unparsed")
    structure_parser_version: Mapped[str | None] = mapped_column(String(80))
    provision_count: Mapped[int | None] = mapped_column(Integer)
    structured_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)
    __table_args__ = (UniqueConstraint("legal_source_document_id", "sha256", name="uq_legal_source_document_hash"),)


class LegalSyncRun(Base):
    __tablename__ = "legal_sync_runs"
    legal_sync_run_id: Mapped[str] = mapped_column(Uuid(as_uuid=False), primary_key=True, default=uuid_str)
    legal_source_id: Mapped[str] = mapped_column(ForeignKey("legal_sources.legal_source_id", ondelete="CASCADE"), nullable=False, index=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="running")
    checked_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    new_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    amended_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    repealed_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    unchanged_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    error_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    details: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)


class LegalUpdateCandidate(Base):
    __tablename__ = "legal_update_candidates"
    legal_update_candidate_id: Mapped[str] = mapped_column(Uuid(as_uuid=False), primary_key=True, default=uuid_str)
    legal_source_document_version_id: Mapped[str] = mapped_column(ForeignKey("legal_source_document_versions.legal_source_document_version_id", ondelete="CASCADE"), nullable=False)
    previous_version_id: Mapped[str | None] = mapped_column(ForeignKey("legal_source_document_versions.legal_source_document_version_id"))
    change_type: Mapped[str] = mapped_column(String(30), nullable=False)
    diff_payload: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    impacted_rule_ids: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    impacted_modules: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="review_required", index=True)
    reviewed_by: Mapped[str | None] = mapped_column(ForeignKey("app_users.user_id"))
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)



class LegalProvision(Base):
    __tablename__ = "legal_provisions"
    legal_provision_id: Mapped[str] = mapped_column(Uuid(as_uuid=False), primary_key=True, default=uuid_str)
    legal_source_document_version_id: Mapped[str] = mapped_column(
        ForeignKey("legal_source_document_versions.legal_source_document_version_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    parent_provision_id: Mapped[str | None] = mapped_column(
        ForeignKey("legal_provisions.legal_provision_id", ondelete="CASCADE"),
        index=True,
    )
    provision_type: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    provision_key: Mapped[str] = mapped_column(Text, nullable=False)
    sequence_no: Mapped[int] = mapped_column(Integer, nullable=False)
    display_label: Mapped[str | None] = mapped_column(Text)
    heading_text: Mapped[str | None] = mapped_column(Text)
    body_text: Mapped[str] = mapped_column(Text, nullable=False, default="")
    source_anchor: Mapped[str | None] = mapped_column(Text)
    source_path: Mapped[str | None] = mapped_column(Text)
    source_meta: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    content_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)
    __table_args__ = (
        UniqueConstraint(
            "legal_source_document_version_id",
            "provision_key",
            name="uq_legal_provision_key",
        ),
    )


class LegalRuleCitation(Base):
    __tablename__ = "legal_rule_citations"
    legal_rule_version_id: Mapped[str] = mapped_column(
        ForeignKey("legal_rule_versions.legal_rule_version_id", ondelete="CASCADE"),
        primary_key=True,
    )
    legal_provision_id: Mapped[str] = mapped_column(
        ForeignKey("legal_provisions.legal_provision_id", ondelete="RESTRICT"),
        primary_key=True,
    )
    citation_role: Mapped[str] = mapped_column(String(40), primary_key=True, default="primary")
    cited_text_snapshot: Mapped[str] = mapped_column(Text, nullable=False, default="")
    created_by: Mapped[str | None] = mapped_column(ForeignKey("app_users.user_id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)
