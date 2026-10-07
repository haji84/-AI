"""Immutable observations, private lineage and append-only Human history."""
from datetime import datetime
from sqlalchemy import BigInteger, CheckConstraint, DateTime, DDL, ForeignKey, JSON, String, Text, UniqueConstraint, Uuid, event
from sqlalchemy.orm import Mapped, mapped_column
from .db import Base
from .models import now_utc, uuid_str


class StatisticsReport(Base):
    __tablename__ = 'statistics_reports'
    report_id: Mapped[str] = mapped_column(Uuid(as_uuid=False), primary_key=True, default=uuid_str)
    snapshot: Mapped[dict] = mapped_column(JSON, nullable=False)
    metric_keys: Mapped[list] = mapped_column(JSON, nullable=False)
    state: Mapped[str] = mapped_column(String(20), nullable=False, default='saved')
    version: Mapped[int] = mapped_column(BigInteger, nullable=False, default=1)
    predecessor_id: Mapped[str | None] = mapped_column(ForeignKey('statistics_reports.report_id'), unique=True)
    successor_id: Mapped[str | None] = mapped_column(ForeignKey('statistics_reports.report_id'), unique=True)
    created_by: Mapped[str] = mapped_column(ForeignKey('app_users.user_id'), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc, nullable=False)
    confirmed_by: Mapped[str | None] = mapped_column(ForeignKey('app_users.user_id'))
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    __table_args__ = (CheckConstraint("state IN ('saved','confirmed')", name='ck_statistics_state'),
                     CheckConstraint("(state='saved' AND confirmed_by IS NULL AND confirmed_at IS NULL) OR (state='confirmed' AND confirmed_by IS NOT NULL AND confirmed_at IS NOT NULL)", name='ck_statistics_human'),
                     CheckConstraint('version >= 1', name='ck_statistics_version'))


class StatisticsEvidence(Base):
    __tablename__ = 'statistics_evidence'
    report_id: Mapped[str] = mapped_column(ForeignKey('statistics_reports.report_id'), primary_key=True)
    evidence: Mapped[dict] = mapped_column(JSON, nullable=False)
    fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)


class StatisticsHistory(Base):
    __tablename__ = 'statistics_history'
    history_id: Mapped[str] = mapped_column(Uuid(as_uuid=False), primary_key=True, default=uuid_str)
    report_id: Mapped[str] = mapped_column(ForeignKey('statistics_reports.report_id'), nullable=False, index=True)
    version: Mapped[int] = mapped_column(BigInteger, nullable=False)
    action: Mapped[str] = mapped_column(String(20), nullable=False)
    note: Mapped[str | None] = mapped_column(Text)
    actor_id: Mapped[str] = mapped_column(ForeignKey('app_users.user_id'), nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc, nullable=False)
    __table_args__ = (UniqueConstraint('report_id', 'version', name='uq_statistics_history_version'),
                     CheckConstraint("action IN ('saved','confirmed','replaced')", name='ck_statistics_history_action'))


# SQLite development parity: real SQL updates must obey immutable source/evidence rules too.
for model in [StatisticsReport, StatisticsEvidence, StatisticsHistory]:
    table = model.__tablename__
    event.listen(model.__table__, 'after_create', DDL(f"CREATE TRIGGER {table}_no_delete BEFORE DELETE ON {table} BEGIN SELECT RAISE(ABORT, 'statistics history is immutable'); END").execute_if(dialect='sqlite'))
    if model is not StatisticsReport:
        event.listen(model.__table__, 'after_create', DDL(f"CREATE TRIGGER {table}_no_update BEFORE UPDATE ON {table} BEGIN SELECT RAISE(ABORT, 'statistics evidence is immutable'); END").execute_if(dialect='sqlite'))

event.listen(StatisticsReport.__table__, 'after_create', DDL("""
CREATE TRIGGER statistics_reports_guard BEFORE UPDATE ON statistics_reports
WHEN NEW.report_id IS NOT OLD.report_id OR NEW.snapshot IS NOT OLD.snapshot OR NEW.metric_keys IS NOT OLD.metric_keys
 OR NEW.predecessor_id IS NOT OLD.predecessor_id OR NEW.created_by IS NOT OLD.created_by OR NEW.created_at IS NOT OLD.created_at
 OR NEW.version != OLD.version + 1
 OR NOT ((OLD.state='saved' AND NEW.state='confirmed' AND OLD.successor_id IS NULL AND NEW.successor_id IS NULL)
      OR (NEW.state=OLD.state AND NEW.confirmed_by IS OLD.confirmed_by AND NEW.confirmed_at IS OLD.confirmed_at AND OLD.successor_id IS NULL AND NEW.successor_id IS NOT NULL))
BEGIN SELECT RAISE(ABORT, 'statistics snapshot and previous Human facts are immutable'); END
""").execute_if(dialect='sqlite'))
