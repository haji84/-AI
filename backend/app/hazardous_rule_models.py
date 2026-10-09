"""Immutable evidence of an explicit Human hazardous Rule approval."""
from datetime import datetime
from sqlalchemy import DateTime, ForeignKey, JSON, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from .db import Base
from .models import now_utc


class HazardousRuleApproval(Base):
    __tablename__ = 'hazardous_rule_approvals'
    legal_rule_version_id: Mapped[str] = mapped_column(Uuid(as_uuid=False),
        ForeignKey('legal_rule_versions.legal_rule_version_id'), primary_key=True)
    rule_snapshot: Mapped[dict] = mapped_column(JSON, nullable=False)
    source_snapshot: Mapped[dict] = mapped_column(JSON, nullable=False)
    citations: Mapped[list] = mapped_column(JSON, nullable=False)
    approved_by: Mapped[str] = mapped_column(ForeignKey('app_users.user_id'), nullable=False)
    approved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=now_utc)
