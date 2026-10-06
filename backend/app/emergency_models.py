from datetime import datetime
from sqlalchemy import BigInteger, DateTime, ForeignKey, JSON, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column
from .db import Base
from .models import uuid_str, now_utc

class EmergencyTreatment(Base):
    __tablename__ = 'emergency_treatments'
    treatment_id: Mapped[str] = mapped_column(Uuid(as_uuid=False), primary_key=True, default=uuid_str)
    emergency_patient_id: Mapped[str] = mapped_column(ForeignKey('emergency_patients.emergency_patient_id'), nullable=False, index=True)
    code: Mapped[str] = mapped_column(String(50), nullable=False)
    performed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    notes: Mapped[str | None] = mapped_column(Text)
    source_document_id: Mapped[str | None] = mapped_column(ForeignKey('documents.document_id'))
    created_by: Mapped[str] = mapped_column(ForeignKey('app_users.user_id'), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)

class EmergencyReportDraft(Base):
    __tablename__ = 'emergency_report_drafts'
    report_id: Mapped[str] = mapped_column(Uuid(as_uuid=False), primary_key=True, default=uuid_str)
    emergency_case_id: Mapped[str] = mapped_column(ForeignKey('emergency_cases.emergency_case_id'), nullable=False, index=True)
    kind: Mapped[str] = mapped_column(String(50), nullable=False)
    content: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    source_snapshot: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default='draft')
    version: Mapped[int] = mapped_column(BigInteger, nullable=False, default=1)
    created_by: Mapped[str] = mapped_column(ForeignKey('app_users.user_id'), nullable=False)
    reviewed_by: Mapped[str | None] = mapped_column(ForeignKey('app_users.user_id'))
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    review_note: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)
