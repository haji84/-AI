"""Human-defined exact role rules and explicit, revocable timed delegation."""
from sqlalchemy import BigInteger,Boolean,CheckConstraint,Date,DateTime,ForeignKey,String,Text,Uuid
from sqlalchemy.orm import Mapped,mapped_column
from .db import Base
from .models import uuid_str,now_utc


class HumanRoleRule(Base):
    __tablename__='human_role_rules'
    __table_args__=(CheckConstraint('valid_to IS NULL OR valid_to >= valid_from',name='role_rule_dates'),CheckConstraint("kind IS NULL OR kind IN ('primary','secondary')",name='role_rule_kind'),CheckConstraint('organization_id IS NOT NULL OR title IS NOT NULL',name='role_rule_exact_selector'),CheckConstraint('(source_document_id IS NULL AND source_sha256 IS NULL) OR (source_document_id IS NOT NULL AND source_sha256 IS NOT NULL)',name='role_rule_source'))
    rule_id:Mapped[str]=mapped_column(Uuid(as_uuid=False),primary_key=True,default=uuid_str)
    name:Mapped[str]=mapped_column(String(200),nullable=False)
    role_id:Mapped[str]=mapped_column(ForeignKey('roles.role_id'),nullable=False,index=True)
    organization_id:Mapped[str|None]=mapped_column(ForeignKey('organization_units.organization_id'))
    title:Mapped[str|None]=mapped_column(String(200))
    kind:Mapped[str|None]=mapped_column(String(20))
    valid_from:Mapped[object]=mapped_column(Date,nullable=False)
    valid_to:Mapped[object|None]=mapped_column(Date)
    active:Mapped[bool]=mapped_column(Boolean,nullable=False,default=True)
    source_document_id:Mapped[str|None]=mapped_column(ForeignKey('documents.document_id'))
    source_sha256:Mapped[str|None]=mapped_column(String(64))
    reason:Mapped[str]=mapped_column(Text,nullable=False)
    created_by:Mapped[str]=mapped_column(ForeignKey('app_users.user_id'),nullable=False)
    version:Mapped[int]=mapped_column(BigInteger,nullable=False,default=1)
    created_at:Mapped[object]=mapped_column(DateTime(timezone=True),default=now_utc)


class TemporaryRoleGrant(Base):
    __tablename__='temporary_role_grants'
    __table_args__=(CheckConstraint('valid_to >= valid_from',name='temporary_role_dates'),CheckConstraint('(source_document_id IS NULL AND source_sha256 IS NULL) OR (source_document_id IS NOT NULL AND source_sha256 IS NOT NULL)',name='temporary_role_source'))
    grant_id:Mapped[str]=mapped_column(Uuid(as_uuid=False),primary_key=True,default=uuid_str)
    user_id:Mapped[str]=mapped_column(ForeignKey('app_users.user_id'),nullable=False,index=True)
    role_id:Mapped[str]=mapped_column(ForeignKey('roles.role_id'),nullable=False,index=True)
    acting_for_employee_id:Mapped[str|None]=mapped_column(ForeignKey('employees.employee_id'))
    valid_from:Mapped[object]=mapped_column(Date,nullable=False)
    valid_to:Mapped[object]=mapped_column(Date,nullable=False)
    source_document_id:Mapped[str|None]=mapped_column(ForeignKey('documents.document_id'))
    source_sha256:Mapped[str|None]=mapped_column(String(64))
    reason:Mapped[str]=mapped_column(Text,nullable=False)
    created_by:Mapped[str]=mapped_column(ForeignKey('app_users.user_id'),nullable=False)
    version:Mapped[int]=mapped_column(BigInteger,nullable=False,default=1)
    revoked_at:Mapped[object|None]=mapped_column(DateTime(timezone=True))
    revoked_by:Mapped[str|None]=mapped_column(ForeignKey('app_users.user_id'))
    revocation_reason:Mapped[str|None]=mapped_column(Text)
    created_at:Mapped[object]=mapped_column(DateTime(timezone=True),default=now_utc)
