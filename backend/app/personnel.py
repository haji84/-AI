"""Human-managed organization and effective-dated personnel role assignments."""
from datetime import date, datetime
from zoneinfo import ZoneInfo
from sqlalchemy import Boolean, BigInteger, CheckConstraint, Date, DateTime, ForeignKey, String, Uuid, select, or_, text
from sqlalchemy.orm import Mapped, mapped_column
from .db import Base
from .models import Employee, User, UserRole, Role, Document, uuid_str, now_utc


class OrganizationUnit(Base):
    __tablename__ = 'organization_units'
    organization_id: Mapped[str] = mapped_column(Uuid(as_uuid=False), primary_key=True, default=uuid_str)
    code: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    parent_id: Mapped[str | None] = mapped_column(ForeignKey('organization_units.organization_id'))
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    version: Mapped[int] = mapped_column(BigInteger, nullable=False, default=1)


class EmployeeAssignment(Base):
    __tablename__ = 'employee_assignments'
    __table_args__ = (CheckConstraint("kind IN ('primary', 'secondary')", name='employee_assignment_kind'),
                     CheckConstraint('valid_to IS NULL OR valid_to >= valid_from', name='employee_assignment_dates'))
    assignment_id: Mapped[str] = mapped_column(Uuid(as_uuid=False), primary_key=True, default=uuid_str)
    employee_id: Mapped[str] = mapped_column(ForeignKey('employees.employee_id'), nullable=False, index=True)
    organization_id: Mapped[str] = mapped_column(ForeignKey('organization_units.organization_id'), nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    kind: Mapped[str] = mapped_column(String(20), nullable=False, default='primary')
    valid_from: Mapped[date] = mapped_column(Date, nullable=False)
    valid_to: Mapped[date | None] = mapped_column(Date)
    version: Mapped[int] = mapped_column(BigInteger, nullable=False, default=1)


class AssignmentRole(Base):
    __tablename__ = 'employee_assignment_roles'
    assignment_id: Mapped[str] = mapped_column(ForeignKey('employee_assignments.assignment_id'), primary_key=True)
    role_id: Mapped[str] = mapped_column(ForeignKey('roles.role_id'), primary_key=True)


class PasswordHistory(Base):
    __tablename__ = 'account_password_history'
    history_id: Mapped[str] = mapped_column(Uuid(as_uuid=False), primary_key=True, default=uuid_str)
    user_id: Mapped[str] = mapped_column(ForeignKey('app_users.user_id'), nullable=False, index=True)
    password_hash: Mapped[str] = mapped_column(String(500), nullable=False)
    changed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=now_utc)


from .authorization_models import HumanRoleRule,TemporaryRoleGrant

def business_date():
    return datetime.now(ZoneInfo('Asia/Tokyo')).date()


def employee_available(db, user):
    return user.employee_id is None or bool((employee := db.get(Employee, user.employee_id)) and employee.active)


def effective_role_sources(db,user_id):
    user=db.get(User,user_id)
    if not user or not user.active or not employee_available(db,user):return []
    today=business_date();sources=[]
    def add(role_id,origin,start=None,finish=None):
        sources.append({'role_id':role_id,'origin':origin,'valid_from':start.isoformat() if start else None,'valid_to':finish.isoformat() if finish else None})
    def source_valid(row):
        return row.source_document_id is None or bool((document:=db.get(Document,row.source_document_id)) and document.sha256==row.source_sha256)
    for identity in db.scalars(select(UserRole.role_id).where(UserRole.user_id==user_id)):add(identity,'permanent')
    for grant in db.scalars(select(TemporaryRoleGrant).join(Role,Role.role_id==TemporaryRoleGrant.role_id).where(Role.code!='system_admin',TemporaryRoleGrant.user_id==user_id,TemporaryRoleGrant.revoked_at.is_(None),TemporaryRoleGrant.valid_from<=today,TemporaryRoleGrant.valid_to>=today)):
        principal=db.get(Employee,grant.acting_for_employee_id) if grant.acting_for_employee_id else None
        if source_valid(grant) and (grant.acting_for_employee_id is None or principal and principal.active):add(grant.role_id,'acting' if principal else 'temporary',grant.valid_from,grant.valid_to)
    if user.employee_id:
        assignments=db.scalars(select(EmployeeAssignment).join(OrganizationUnit,OrganizationUnit.organization_id==EmployeeAssignment.organization_id)
            .where(EmployeeAssignment.employee_id==user.employee_id,OrganizationUnit.active.is_(True),EmployeeAssignment.valid_from<=today,or_(EmployeeAssignment.valid_to.is_(None),EmployeeAssignment.valid_to>=today))).all()
        if assignments:
            by_id={row.assignment_id:row for row in assignments}
            for grant in db.scalars(select(AssignmentRole).where(AssignmentRole.assignment_id.in_(by_id))):
                row=by_id[grant.assignment_id];add(grant.role_id,'appointment',row.valid_from,row.valid_to)
            rules=db.scalars(select(HumanRoleRule).join(Role,Role.role_id==HumanRoleRule.role_id).where(Role.code!='system_admin',HumanRoleRule.active.is_(True),HumanRoleRule.valid_from<=today,or_(HumanRoleRule.valid_to.is_(None),HumanRoleRule.valid_to>=today)))
            for rule in rules:
                if source_valid(rule) and any((rule.organization_id is None or rule.organization_id==row.organization_id) and (rule.title is None or rule.title==row.title) and (rule.kind is None or rule.kind==row.kind) for row in assignments):add(rule.role_id,'human_rule',rule.valid_from,rule.valid_to)
    identities={row['role_id'] for row in sources}
    active=set(db.scalars(select(Role.role_id).where(Role.role_id.in_(identities),Role.active.is_(True)))) if identities else set()
    return [row for row in sources if row['role_id'] in active]


def effective_role_ids(db,user_id):
    return {row['role_id'] for row in effective_role_sources(db,user_id)}


def account_change_lock(db):
    # Shared by authentication and Human administration; transaction releases it.
    if db.bind.dialect.name == 'postgresql':
        db.execute(text("SELECT pg_advisory_xact_lock(hashtext('fire-ai-personnel-administration'))"))
    db.expire_all()
