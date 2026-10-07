"""Register facts and immutable evidence history; no executable legal decisions."""
from sqlalchemy import BigInteger, CheckConstraint, Date, DateTime, ForeignKey, JSON, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from .db import Base
from .models import uuid_str, now_utc


class HazardousInstallation(Base):
    __tablename__ = 'hazardous_installations'
    __table_args__ = (CheckConstraint("status IN ('active','retired')", name='hazardous_installation_status'), CheckConstraint('version >= 1', name='hazardous_installation_version'))
    installation_id: Mapped[str] = mapped_column(Uuid(as_uuid=False), primary_key=True, default=uuid_str)
    building_id: Mapped[str] = mapped_column(ForeignKey('facilities.building_id'), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(500), nullable=False)
    category_label: Mapped[str] = mapped_column(String(500), nullable=False)
    location_detail: Mapped[str] = mapped_column(Text, nullable=False, default='')
    notes: Mapped[str] = mapped_column(Text, nullable=False, default='')
    materials: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default='active')
    version: Mapped[int] = mapped_column(BigInteger, nullable=False, default=1)
    created_by: Mapped[str] = mapped_column(ForeignKey('app_users.user_id'), nullable=False)
    created_at: Mapped[object] = mapped_column(DateTime(timezone=True), nullable=False, default=now_utc)
    updated_at: Mapped[object] = mapped_column(DateTime(timezone=True), nullable=False, default=now_utc)


class HazardousRecord(Base):
    __tablename__ = 'hazardous_records'
    __table_args__ = (CheckConstraint("kind IN ('permit','notification','change')", name='hazardous_record_kind'), CheckConstraint("status IN ('draft','confirmed','cancelled','superseded')", name='hazardous_record_status'), CheckConstraint('version >= 1', name='hazardous_record_version'))
    record_id: Mapped[str] = mapped_column(Uuid(as_uuid=False), primary_key=True, default=uuid_str)
    installation_id: Mapped[str] = mapped_column(ForeignKey('hazardous_installations.installation_id'), nullable=False, index=True)
    supersedes_record_id: Mapped[str | None] = mapped_column(ForeignKey('hazardous_records.record_id'))
    kind: Mapped[str] = mapped_column(String(30), nullable=False)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    reference_no: Mapped[str | None] = mapped_column(String(400))
    recorded_on: Mapped[object] = mapped_column(Date, nullable=False)
    due_on: Mapped[object | None] = mapped_column(Date, index=True)
    notes: Mapped[str] = mapped_column(Text, nullable=False, default='')
    document_ids: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    legal_source_version_ids: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    inspection_ids: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    violation_case_ids: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default='draft')
    version: Mapped[int] = mapped_column(BigInteger, nullable=False, default=1)
    source_snapshot: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    confirmed_by: Mapped[str | None] = mapped_column(ForeignKey('app_users.user_id'))
    confirmed_at: Mapped[object | None] = mapped_column(DateTime(timezone=True))
    last_human_reason: Mapped[str | None] = mapped_column(Text)
    created_by: Mapped[str] = mapped_column(ForeignKey('app_users.user_id'), nullable=False)
    created_at: Mapped[object] = mapped_column(DateTime(timezone=True), nullable=False, default=now_utc)
    updated_at: Mapped[object] = mapped_column(DateTime(timezone=True), nullable=False, default=now_utc)


class HazardousHistory(Base):
    __tablename__ = 'hazardous_history'
    history_id: Mapped[str] = mapped_column(Uuid(as_uuid=False), primary_key=True, default=uuid_str)
    installation_id: Mapped[str] = mapped_column(ForeignKey('hazardous_installations.installation_id'), nullable=False, index=True)
    record_id: Mapped[str | None] = mapped_column(ForeignKey('hazardous_records.record_id'), index=True)
    action: Mapped[str] = mapped_column(String(50), nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    before: Mapped[dict | None] = mapped_column(JSON)
    after: Mapped[dict] = mapped_column(JSON, nullable=False)
    created_by: Mapped[str] = mapped_column(ForeignKey('app_users.user_id'), nullable=False)
    created_at: Mapped[object] = mapped_column(DateTime(timezone=True), nullable=False, default=now_utc)
