"""Hazardous evaluation candidates remain separate from permits and violations."""
from datetime import date, datetime
from sqlalchemy import BigInteger, CheckConstraint, Date, DateTime, ForeignKey, JSON, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column
from .db import Base
from .models import uuid_str, now_utc


class HazardousEvaluation(Base):
    __tablename__ = 'hazardous_evaluations'
    __table_args__ = (
        CheckConstraint("status IN ('candidate','reviewed')", name='hazardous_evaluation_status'),
        CheckConstraint("coverage_status IN ('evaluated','unavailable')", name='hazardous_evaluation_coverage'),
        CheckConstraint('version >= 1', name='hazardous_evaluation_version'),
        CheckConstraint("status <> 'reviewed' OR (reviewed_by IS NOT NULL AND reviewed_at IS NOT NULL)", name='hazardous_evaluation_review'),
    )
    evaluation_id: Mapped[str] = mapped_column(Uuid(as_uuid=False), primary_key=True, default=uuid_str)
    installation_id: Mapped[str] = mapped_column(ForeignKey('hazardous_installations.installation_id'), nullable=False, index=True)
    legal_profile_id: Mapped[str] = mapped_column(ForeignKey('legal_profiles.legal_profile_id'), nullable=False)
    evaluation_date: Mapped[date] = mapped_column(Date, nullable=False)
    input_snapshot: Mapped[dict] = mapped_column(JSON, nullable=False)
    rules_snapshot: Mapped[list] = mapped_column(JSON, nullable=False)
    results: Mapped[list] = mapped_column(JSON, nullable=False)
    coverage_status: Mapped[str] = mapped_column(String(20), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default='candidate')
    version: Mapped[int] = mapped_column(BigInteger, nullable=False, default=1)
    reason: Mapped[str | None] = mapped_column(Text)
    created_by: Mapped[str] = mapped_column(ForeignKey('app_users.user_id'), nullable=False)
    reviewed_by: Mapped[str | None] = mapped_column(ForeignKey('app_users.user_id'))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=now_utc)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
