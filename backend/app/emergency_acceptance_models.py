"""Private, immutable measurement snapshots. No original report or patient text."""
from datetime import datetime

from sqlalchemy import BigInteger, CheckConstraint, DateTime, ForeignKey, JSON, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from .db import Base
from .models import now_utc, uuid_str


class EmergencyAcceptanceEvaluation(Base):
    __tablename__ = 'emergency_acceptance_evaluations'
    __table_args__ = (
        CheckConstraint("dataset_kind IN ('synthetic','internal_trial')", name='em_acceptance_kind'),
        CheckConstraint("status IN ('recorded','reviewed')", name='em_acceptance_status'),
        CheckConstraint('version >= 1', name='em_acceptance_version'),
        CheckConstraint("review_decision IS NULL OR review_decision IN ('confirmed','rejected')",
                        name='em_acceptance_decision'),
        CheckConstraint("status <> 'reviewed' OR (reviewed_by IS NOT NULL AND reviewed_at IS NOT NULL "
                        "AND reviewed_by <> created_by AND reviewed_employee_id IS NOT NULL "
                        "AND created_employee_id IS NOT NULL AND reviewed_employee_id <> created_employee_id "
                        "AND review_decision IS NOT NULL)", name='em_acceptance_independent_review'),
    )
    evaluation_id: Mapped[str] = mapped_column(Uuid(as_uuid=False), primary_key=True, default=uuid_str)
    request_id: Mapped[str] = mapped_column(Uuid(as_uuid=False), nullable=False, unique=True)
    request_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    supersedes_id: Mapped[str | None] = mapped_column(ForeignKey('emergency_acceptance_evaluations.evaluation_id'), unique=True)
    dataset_kind: Mapped[str] = mapped_column(String(20), nullable=False)
    measurement: Mapped[dict] = mapped_column(JSON, nullable=False)
    summary: Mapped[dict] = mapped_column(JSON, nullable=False)
    evidence: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default='recorded')
    version: Mapped[int] = mapped_column(BigInteger, nullable=False, default=1)
    review_decision: Mapped[str | None] = mapped_column(String(20))
    created_by: Mapped[str] = mapped_column(ForeignKey('app_users.user_id'), nullable=False)
    created_employee_id: Mapped[str | None] = mapped_column(ForeignKey('employees.employee_id'))
    reviewed_by: Mapped[str | None] = mapped_column(ForeignKey('app_users.user_id'))
    reviewed_employee_id: Mapped[str | None] = mapped_column(ForeignKey('employees.employee_id'))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=now_utc)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
