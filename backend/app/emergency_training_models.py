"""Private append-only teacher records and dataset manifests."""
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, LargeBinary, String, Uuid, text
from sqlalchemy.orm import Mapped, mapped_column

from .db import Base
from .models import now_utc, uuid_str


class TrainingFamilyMember(Base):
    __tablename__ = 'emergency_training_family_members'
    report_id: Mapped[str] = mapped_column(ForeignKey('emergency_audit_reports.report_id'), primary_key=True)
    family_id: Mapped[str] = mapped_column(Uuid(as_uuid=False), nullable=False, index=True)
    created_by: Mapped[str] = mapped_column(ForeignKey('app_users.user_id'), nullable=False)
    created_employee_id: Mapped[str] = mapped_column(ForeignKey('employees.employee_id'), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc, nullable=False)


class TrainingFamilyPartition(Base):
    __tablename__ = 'emergency_training_family_partitions'
    __table_args__ = (CheckConstraint("split IN ('train','validation','holdout')", name='em_training_partition'),)
    family_id: Mapped[str] = mapped_column(Uuid(as_uuid=False), primary_key=True)
    split: Mapped[str] = mapped_column(String(12), nullable=False)
    created_by: Mapped[str] = mapped_column(ForeignKey('app_users.user_id'), nullable=False)
    created_employee_id: Mapped[str] = mapped_column(ForeignKey('employees.employee_id'), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc, nullable=False)


class TrainingTruth(Base):
    __tablename__ = 'emergency_training_truths'
    __table_args__ = (
        CheckConstraint("task IN ('transcription','content_review')", name='em_training_truth_task'),
        Index('em_training_truth_root', 'revision_id', 'task', unique=True,
              postgresql_where=text('supersedes_id IS NULL'), sqlite_where=text('supersedes_id IS NULL')),
    )
    truth_id: Mapped[str] = mapped_column(Uuid(as_uuid=False), primary_key=True, default=uuid_str)
    request_id: Mapped[str] = mapped_column(Uuid(as_uuid=False), unique=True, nullable=False)
    request_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    supersedes_id: Mapped[str | None] = mapped_column(ForeignKey('emergency_training_truths.truth_id'), unique=True)
    revision_id: Mapped[str] = mapped_column(ForeignKey('emergency_audit_revisions.revision_id'), nullable=False, index=True)
    task: Mapped[str] = mapped_column(String(20), nullable=False)
    payload_cipher: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    created_by: Mapped[str] = mapped_column(ForeignKey('app_users.user_id'), nullable=False)
    created_employee_id: Mapped[str] = mapped_column(ForeignKey('employees.employee_id'), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc, nullable=False)


class TrainingDataset(Base):
    __tablename__ = 'emergency_training_datasets'
    __table_args__ = (CheckConstraint("task IN ('transcription','content_review')", name='em_training_dataset_task'),)
    dataset_id: Mapped[str] = mapped_column(Uuid(as_uuid=False), primary_key=True, default=uuid_str)
    request_id: Mapped[str] = mapped_column(Uuid(as_uuid=False), unique=True, nullable=False)
    request_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    supersedes_id: Mapped[str | None] = mapped_column(ForeignKey('emergency_training_datasets.dataset_id'), unique=True)
    task: Mapped[str] = mapped_column(String(20), nullable=False)
    manifest_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    manifest_cipher: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    created_by: Mapped[str] = mapped_column(ForeignKey('app_users.user_id'), nullable=False)
    created_employee_id: Mapped[str] = mapped_column(ForeignKey('employees.employee_id'), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc, nullable=False)
