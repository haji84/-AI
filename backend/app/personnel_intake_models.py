"""Personnel notice candidates are separate from authoritative assignments."""
from datetime import datetime
from sqlalchemy import BigInteger, CheckConstraint, DateTime, ForeignKey, JSON, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column
from .db import Base
from .models import uuid_str, now_utc


class PersonnelDocumentProposal(Base):
    __tablename__ = 'personnel_document_proposals'
    proposal_id: Mapped[str] = mapped_column(Uuid(as_uuid=False), primary_key=True, default=uuid_str)
    source_document_id: Mapped[str] = mapped_column(ForeignKey('documents.document_id'), nullable=False, index=True)
    source_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    extraction_method: Mapped[str] = mapped_column(String(100), nullable=False)
    source_text: Mapped[str] = mapped_column(Text, nullable=False)
    source_quote: Mapped[str] = mapped_column(Text, nullable=False)
    proposed: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    errors: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    before_snapshot: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    after_snapshot: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    employee_id: Mapped[str | None] = mapped_column(ForeignKey('employees.employee_id'))
    organization_id: Mapped[str | None] = mapped_column(ForeignKey('organization_units.organization_id'))
    status: Mapped[str] = mapped_column(String(20), nullable=False, default='candidate')
    version: Mapped[int] = mapped_column(BigInteger, nullable=False, default=1)
    reason: Mapped[str] = mapped_column(Text, nullable=False, default='deterministic notice extraction')
    created_by: Mapped[str] = mapped_column(ForeignKey('app_users.user_id'), nullable=False)
    reviewed_by: Mapped[str | None] = mapped_column(ForeignKey('app_users.user_id'))
    applied_by: Mapped[str | None] = mapped_column(ForeignKey('app_users.user_id'))
    applied_assignment_id: Mapped[str | None] = mapped_column(ForeignKey('employee_assignments.assignment_id'))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=now_utc)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    applied_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    __table_args__ = (
        CheckConstraint("status IN ('candidate','reviewed','applied','rejected')", name='personnel_proposal_status'),
        CheckConstraint('version >= 1', name='personnel_proposal_version'),
        CheckConstraint("status NOT IN ('reviewed','applied') OR (reviewed_by IS NOT NULL AND reviewed_at IS NOT NULL)", name='personnel_proposal_review'),
        CheckConstraint("status <> 'applied' OR (applied_by IS NOT NULL AND applied_at IS NOT NULL AND applied_assignment_id IS NOT NULL)", name='personnel_proposal_apply'),
    )
