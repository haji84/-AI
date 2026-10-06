"""Human-managed organization and effective-dated personnel role assignments."""
from datetime import date, datetime
from zoneinfo import ZoneInfo
from sqlalchemy import Boolean, BigInteger, CheckConstraint, Date, DateTime, ForeignKey, String, Uuid, select, or_, text
from sqlalchemy.orm import Mapped, mapped_column
from .db import Base
from .models import Employee, User, UserRole, uuid_str, now_utc


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


def business_date():
    return datetime.now(ZoneInfo('Asia/Tokyo')).date()


def employee_available(db, user):
    return user.employee_id is None or bool((employee := db.get(Employee, user.employee_id)) and employee.active)


def effective_role_ids(db, user_id):
    user = db.get(User, user_id)
    if not user or not user.active or not employee_available(db, user):
        return set()
    roles = set(db.scalars(select(UserRole.role_id).where(UserRole.user_id == user_id)))
    if user.employee_id:
        today = business_date()
        roles.update(db.scalars(select(AssignmentRole.role_id)
            .join(EmployeeAssignment, EmployeeAssignment.assignment_id == AssignmentRole.assignment_id)
            .join(OrganizationUnit, OrganizationUnit.organization_id == EmployeeAssignment.organization_id)
            .where(EmployeeAssignment.employee_id == user.employee_id, OrganizationUnit.active.is_(True),
                   EmployeeAssignment.valid_from <= today,
                   or_(EmployeeAssignment.valid_to.is_(None), EmployeeAssignment.valid_to >= today))))
    return roles


def account_change_lock(db):
    # Shared by authentication and Human administration; transaction releases it.
    if db.bind.dialect.name == 'postgresql':
        db.execute(text("SELECT pg_advisory_xact_lock(hashtext('fire-ai-personnel-administration'))"))
    db.expire_all()
