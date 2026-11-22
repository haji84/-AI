"""Audit-only originals and derivatives; intentionally not generic Documents."""
from datetime import datetime

from sqlalchemy import BigInteger, CheckConstraint, DateTime, ForeignKey, JSON, LargeBinary, String, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from .db import Base
from .models import now_utc, uuid_str


class AuditSource(Base):
    __tablename__ = 'emergency_audit_sources'
    source_id: Mapped[str] = mapped_column(Uuid(as_uuid=False), primary_key=True, default=uuid_str)
    request_id: Mapped[str] = mapped_column(Uuid(as_uuid=False), unique=True, nullable=False)
    source_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    media_type: Mapped[str] = mapped_column(String(30), nullable=False)
    size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    page_count: Mapped[int] = mapped_column(BigInteger, nullable=False)
    created_by: Mapped[str] = mapped_column(ForeignKey('app_users.user_id'), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc, nullable=False)


class AuditConfiguration(Base):
    __tablename__ = 'emergency_audit_configurations'
    __table_args__ = (
        CheckConstraint("kind IN ('profile','rules')", name='em_audit_config_kind'),
        CheckConstraint("status IN ('draft','approved','retired')", name='em_audit_config_status'),
        CheckConstraint('version >= 1', name='em_audit_config_version'),
    )
    config_id: Mapped[str] = mapped_column(Uuid(as_uuid=False), primary_key=True, default=uuid_str)
    request_id: Mapped[str] = mapped_column(Uuid(as_uuid=False), unique=True, nullable=False)
    request_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    supersedes_id: Mapped[str | None] = mapped_column(ForeignKey('emergency_audit_configurations.config_id'), unique=True)
    kind: Mapped[str] = mapped_column(String(10), nullable=False)
    label: Mapped[str] = mapped_column(String(100), nullable=False)
    form_key: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    definition_cipher: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    source_id: Mapped[str | None] = mapped_column(ForeignKey('emergency_audit_sources.source_id'))
    status: Mapped[str] = mapped_column(String(12), default='draft', nullable=False)
    version: Mapped[int] = mapped_column(BigInteger, default=1, nullable=False)
    impact: Mapped[dict | None] = mapped_column(JSON)
    created_by: Mapped[str] = mapped_column(ForeignKey('app_users.user_id'), nullable=False)
    created_employee_id: Mapped[str | None] = mapped_column(ForeignKey('employees.employee_id'))
    approved_by: Mapped[str | None] = mapped_column(ForeignKey('app_users.user_id'))
    approved_employee_id: Mapped[str | None] = mapped_column(ForeignKey('employees.employee_id'))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc, nullable=False)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class AuditReport(Base):
    __tablename__ = 'emergency_audit_reports'
    __table_args__ = (
        CheckConstraint("dataset_kind IN ('synthetic','internal_trial')", name='em_audit_dataset'),
        CheckConstraint('version >= 1', name='em_audit_report_version'),
    )
    report_id: Mapped[str] = mapped_column(Uuid(as_uuid=False), primary_key=True, default=uuid_str)
    request_id: Mapped[str] = mapped_column(Uuid(as_uuid=False), unique=True, nullable=False)
    request_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    owner_id: Mapped[str] = mapped_column(ForeignKey('app_users.user_id'), nullable=False, index=True)
    owner_employee_id: Mapped[str | None] = mapped_column(ForeignKey('employees.employee_id'))
    reviewer_id: Mapped[str | None] = mapped_column(ForeignKey('app_users.user_id'))
    reviewer_employee_id: Mapped[str | None] = mapped_column(ForeignKey('employees.employee_id'))
    dataset_kind: Mapped[str] = mapped_column(String(20), nullable=False)
    current_revision_id: Mapped[str | None] = mapped_column(Uuid(as_uuid=False))
    version: Mapped[int] = mapped_column(BigInteger, default=1, nullable=False)
    revision_number: Mapped[int] = mapped_column(BigInteger, default=1, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc, nullable=False)


class AuditRevision(Base):
    __tablename__ = 'emergency_audit_revisions'
    __table_args__ = (UniqueConstraint('report_id', 'number', name='em_audit_revision_number'),)
    revision_id: Mapped[str] = mapped_column(Uuid(as_uuid=False), primary_key=True, default=uuid_str)
    report_id: Mapped[str] = mapped_column(ForeignKey('emergency_audit_reports.report_id'), nullable=False, index=True)
    number: Mapped[int] = mapped_column(BigInteger, nullable=False)
    request_id: Mapped[str] = mapped_column(Uuid(as_uuid=False), unique=True, nullable=False)
    request_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    source_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    media_type: Mapped[str] = mapped_column(String(30), nullable=False)
    size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    page_count: Mapped[int] = mapped_column(BigInteger, nullable=False)
    profile_id: Mapped[str | None] = mapped_column(ForeignKey('emergency_audit_configurations.config_id'))
    version: Mapped[int] = mapped_column(BigInteger, default=1, nullable=False)
    processing_status: Mapped[str] = mapped_column(String(20), default='queued', nullable=False)
    error_code: Mapped[str | None] = mapped_column(String(60))
    reading_cipher: Mapped[bytes | None] = mapped_column(LargeBinary)
    fields_cipher: Mapped[bytes | None] = mapped_column(LargeBinary)
    ai_cipher: Mapped[bytes | None] = mapped_column(LargeBinary)
    created_by: Mapped[str] = mapped_column(ForeignKey('app_users.user_id'), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc, nullable=False)


class AuditJob(Base):
    __tablename__ = 'emergency_audit_jobs'
    __table_args__ = (
        CheckConstraint("kind IN ('read','ai','vision')", name='em_audit_job_kind'),
        CheckConstraint("status IN ('queued','processing','done','failed','cancelled')", name='em_audit_job_status'),
    )
    job_id: Mapped[str] = mapped_column(Uuid(as_uuid=False), primary_key=True, default=uuid_str)
    revision_id: Mapped[str] = mapped_column(ForeignKey('emergency_audit_revisions.revision_id'), nullable=False, index=True)
    kind: Mapped[str] = mapped_column(String(8), nullable=False)
    page_number: Mapped[int | None] = mapped_column(BigInteger)
    status: Mapped[str] = mapped_column(String(12), default='queued', nullable=False, index=True)
    attempts: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)
    source_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    revision_version: Mapped[int] = mapped_column(BigInteger, nullable=False)
    requested_by: Mapped[str] = mapped_column(ForeignKey('app_users.user_id'), nullable=False)
    requested_employee_id: Mapped[str | None] = mapped_column(ForeignKey('employees.employee_id'))
    lease_token: Mapped[str | None] = mapped_column(Uuid(as_uuid=False))
    lease_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    error_code: Mapped[str | None] = mapped_column(String(60))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc, nullable=False)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class AuditRun(Base):
    __tablename__ = 'emergency_audit_runs'
    run_id: Mapped[str] = mapped_column(Uuid(as_uuid=False), primary_key=True, default=uuid_str)
    report_id: Mapped[str] = mapped_column(ForeignKey('emergency_audit_reports.report_id'), nullable=False, index=True)
    revision_id: Mapped[str] = mapped_column(ForeignKey('emergency_audit_revisions.revision_id'), nullable=False)
    revision_version: Mapped[int] = mapped_column(BigInteger, nullable=False)
    report_version: Mapped[int] = mapped_column(BigInteger, nullable=False)
    rule_set_id: Mapped[str | None] = mapped_column(ForeignKey('emergency_audit_configurations.config_id'))
    mode: Mapped[str] = mapped_column(String(12), nullable=False)
    payload_cipher: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    created_by: Mapped[str] = mapped_column(ForeignKey('app_users.user_id'), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc, nullable=False)


class AuditEvent(Base):
    __tablename__ = 'emergency_audit_events'
    event_id: Mapped[str] = mapped_column(Uuid(as_uuid=False), primary_key=True)
    supersedes_id: Mapped[str | None] = mapped_column(ForeignKey('emergency_audit_events.event_id'), unique=True)
    report_id: Mapped[str] = mapped_column(ForeignKey('emergency_audit_reports.report_id'), nullable=False, index=True)
    kind: Mapped[str] = mapped_column(String(30), nullable=False)
    request_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    payload: Mapped[dict] = mapped_column(JSON, nullable=False)
    actor_id: Mapped[str] = mapped_column(ForeignKey('app_users.user_id'), nullable=False)
    actor_employee_id: Mapped[str | None] = mapped_column(ForeignKey('employees.employee_id'))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc, nullable=False)


class AuditWorkerHeartbeat(Base):
    __tablename__ = 'emergency_audit_worker_heartbeats'
    worker_id: Mapped[str] = mapped_column(Uuid(as_uuid=False), primary_key=True)
    seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=now_utc)
