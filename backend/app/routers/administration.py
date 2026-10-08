"""Explicit Human administration; no AI-authored changes are finalized here."""
from datetime import date, datetime, timedelta
from typing import Literal
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, Field, model_validator, field_validator
from sqlalchemy import select, update, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from ..db import get_db
from ..authz import require_permission, permission_codes, current_user, authenticated_user, revalidate_session
from ..models import Employee, User, UserRole, Role, UserSession, AuditLog, now_utc
from ..personnel import OrganizationUnit, EmployeeAssignment, AssignmentRole, PasswordHistory, effective_role_ids, employee_available
from ..security import hash_password, verify_password
from ..settings import settings
from ..password_policy import initial_password_dates,password_expired,next_password_expiry,utc,password_metadata
from ..tenant import TenantIdentity
from ..personnel import business_date, account_change_lock
from ..audit import write_audit

router = APIRouter(prefix='/administration', tags=['administration'])


class HumanChange(BaseModel):
    @field_validator('reason', check_fields=False)
    @classmethod
    def nonblank_reason(cls, value):
        if not value.strip(): raise ValueError('Human reason is required')
        return value.strip()


class OrganizationCreate(BaseModel):
    code: str = Field(min_length=1, max_length=100)
    name: str = Field(min_length=1, max_length=200)
    parent_id: UUID | None = None


class OrganizationPatch(HumanChange):
    expected_version: int = Field(ge=1)
    name: str | None = Field(default=None, min_length=1, max_length=200)
    parent_id: UUID | None = None
    active: bool | None = None
    reason: str = Field(min_length=1, max_length=1000)


class EmployeeCreate(BaseModel):
    employee_code: str = Field(min_length=1, max_length=100)
    display_name: str = Field(min_length=1, max_length=200)


class EmployeePatch(HumanChange):
    expected_version: int = Field(ge=1)
    display_name: str | None = Field(default=None, min_length=1, max_length=200)
    active: bool | None = None
    reason: str = Field(min_length=1, max_length=1000)


class AssignmentInput(HumanChange):
    expected_version: int = Field(ge=1)
    organization_id: UUID
    title: str = Field(min_length=1, max_length=200)
    kind: Literal['primary', 'secondary'] = 'primary'
    valid_from: date
    valid_to: date | None = None
    role_ids: list[UUID] = Field(default_factory=list, max_length=20)
    reason: str = Field(min_length=1, max_length=1000)

    @model_validator(mode='after')
    def ordered_dates(self):
        if self.valid_to is not None and self.valid_to < self.valid_from:
            raise ValueError('end date precedes start date')
        return self


class AccountCreate(HumanChange):
    employee_id: UUID
    username: str = Field(min_length=1, max_length=100)
    password: str = Field(min_length=12, max_length=128)
    reason: str = Field(min_length=1, max_length=1000)


def output(row):
    return {column.name: getattr(row, column.name) for column in row.__table__.columns}


def get(db, model, identity):
    row = db.get(model, str(identity))
    if row is None: raise HTTPException(404, 'record not found')
    return row


def commit(db):
    try: db.commit()
    except IntegrityError:
        db.rollback();raise HTTPException(409, 'duplicate or conflicting record') from None


def administration_lock(db, actor=None, permission=None):
    account_change_lock(db)
    if actor is not None:
        revalidate_session(db,actor.user_id)
        fresh=db.get(User,actor.user_id,populate_existing=True)
        if not fresh or not fresh.active or not employee_available(db,fresh):raise HTTPException(403,'Human account no longer active')
        current_user(fresh)
        if permission not in permission_codes(db,actor.user_id):raise HTTPException(403,'administration permission no longer effective')


def retain_administrator(db):
    db.flush()
    role = db.scalar(select(Role).where(Role.code == 'system_admin'))
    if role is None: raise HTTPException(409, 'system administrator role unavailable')
    users = db.scalars(select(User).where(User.active.is_(True))).all()
    if not any(role.role_id in effective_role_ids(db, user.user_id) for user in users):
        raise HTTPException(409, 'at least one active Human administrator must remain')


def audit(db, actor, action, row, before=None, reason=None, extra=None):
    write_audit(db, user_id=actor.user_id, action=action, entity_type=row.__tablename__,
                entity_id=str(next(iter(output(row).values()))),
                before={key: value.isoformat() if isinstance(value,date) else value for key,value in before.items()} if before else None,
                after={**{key: value.isoformat() if isinstance(value, date) else value for key,value in output(row).items()}, 'reason': reason, **(extra or {})})


@router.get('/organizations')
def organizations(actor=Depends(require_permission('personnel.read')), db: Session=Depends(get_db)):
    return [output(row) for row in db.scalars(select(OrganizationUnit).order_by(OrganizationUnit.code))]


@router.post('/organizations', status_code=201)
def create_organization(payload: OrganizationCreate, actor=Depends(require_permission('personnel.manage')), db: Session=Depends(get_db)):
    administration_lock(db,actor,'personnel.manage')
    if payload.parent_id and not get(db,OrganizationUnit,payload.parent_id).active: raise HTTPException(409,'parent organization inactive')
    row=OrganizationUnit(code=payload.code,name=payload.name,parent_id=str(payload.parent_id) if payload.parent_id else None)
    db.add(row)
    try: db.flush()
    except IntegrityError: db.rollback();raise HTTPException(409,'organization code already exists') from None
    audit(db,actor,'organization.create',row);commit(db);return output(row)


@router.patch('/organizations/{organization_id}')
def edit_organization(organization_id: UUID, payload: OrganizationPatch, actor=Depends(require_permission('personnel.manage')), db: Session=Depends(get_db)):
    administration_lock(db,actor,"personnel.manage");row=get(db,OrganizationUnit,organization_id);before=output(row)
    changes=payload.model_dump(exclude_unset=True,exclude={'expected_version','reason'})
    if 'active' in changes and changes['active'] != row.active and 'account.manage' not in permission_codes(db,actor.user_id):
        raise HTTPException(403,'account.manage required for effective state changes')
    if 'parent_id' in changes:
        parent=str(changes['parent_id']) if changes['parent_id'] else None
        cursor=parent;seen={row.organization_id}
        while cursor:
            if cursor in seen: raise HTTPException(409,'organization cycle is forbidden')
            seen.add(cursor);ancestor=get(db,OrganizationUnit,cursor);cursor=ancestor.parent_id
        changes['parent_id']=parent
    if not changes or any(value is None for key,value in changes.items() if key!='parent_id'): raise HTTPException(422,'invalid empty change')
    changed=db.execute(update(OrganizationUnit).where(OrganizationUnit.organization_id==row.organization_id,OrganizationUnit.version==payload.expected_version)
        .values(**changes,version=payload.expected_version+1)).rowcount
    if changed!=1: raise HTTPException(409,'organization version conflict')
    db.refresh(row);retain_administrator(db);audit(db,actor,'organization.update',row,before,payload.reason);commit(db);return output(row)


@router.get('/account-staff')
def account_staff(actor=Depends(require_permission('account.manage')),db: Session=Depends(get_db)):
    return [{'employee_id':row.employee_id,'employee_code':row.employee_code,'display_name':row.display_name,'active':row.active}
            for row in db.scalars(select(Employee).order_by(Employee.employee_code,Employee.display_name))]


@router.get('/staff')
def employees(actor=Depends(require_permission('personnel.read')), db: Session=Depends(get_db)):
    return [output(row) for row in db.scalars(select(Employee).order_by(Employee.employee_code,Employee.display_name))]


@router.post('/staff', status_code=201)
def create_employee(payload: EmployeeCreate, actor=Depends(require_permission('personnel.manage')), db: Session=Depends(get_db)):
    administration_lock(db,actor,'personnel.manage')
    row=Employee(**payload.model_dump());db.add(row)
    try:db.flush()
    except IntegrityError:db.rollback();raise HTTPException(409,'employee code already exists') from None
    audit(db,actor,'personnel.create',row);commit(db);return output(row)


@router.patch('/staff/{employee_id}')
def edit_employee(employee_id: UUID,payload: EmployeePatch,actor=Depends(require_permission('personnel.manage')),db: Session=Depends(get_db)):
    administration_lock(db,actor,"personnel.manage");row=get(db,Employee,employee_id);before=output(row)
    changes=payload.model_dump(exclude_unset=True,exclude={'expected_version','reason'})
    if 'active' in changes and changes['active'] != row.active and 'account.manage' not in permission_codes(db,actor.user_id):
        raise HTTPException(403,'account.manage required for effective state changes')
    if not changes or any(value is None for value in changes.values()):raise HTTPException(422,'invalid empty change')
    changed=db.execute(update(Employee).where(Employee.employee_id==str(employee_id),Employee.version==payload.expected_version)
        .values(**changes,version=payload.expected_version+1,updated_at=now_utc())).rowcount
    if changed!=1:raise HTTPException(409,'employee version conflict')
    db.refresh(row);retain_administrator(db)
    if not row.active:
        user=db.scalar(select(User).where(User.employee_id==row.employee_id))
        if user:db.execute(update(UserSession).where(UserSession.user_id==user.user_id,UserSession.revoked_at.is_(None)).values(revoked_at=now_utc()))
    audit(db,actor,'personnel.update',row,before,payload.reason);commit(db);return output(row)


@router.get('/staff/{employee_id}/assignments')
def assignments(employee_id: UUID,actor=Depends(require_permission('personnel.read')),db: Session=Depends(get_db)):
    get(db,Employee,employee_id)
    result=[]
    for row in db.scalars(select(EmployeeAssignment).where(EmployeeAssignment.employee_id==str(employee_id)).order_by(EmployeeAssignment.valid_from)):
        result.append({**output(row),'role_ids':list(db.scalars(select(AssignmentRole.role_id).where(AssignmentRole.assignment_id==row.assignment_id)))})
    return result


def guard_rule_assignment(db,actor,assignment):
    # Check all overlapping planned dates, not merely today's effective roles.
    if 'account.manage' in permission_codes(db,actor.user_id):return
    for rule in db.scalars(select(HumanRoleRule).join(Role,Role.role_id==HumanRoleRule.role_id).where(HumanRoleRule.active.is_(True),Role.active.is_(True))):
        if rule.source_document_id and get(db,Document,rule.source_document_id).sha256!=rule.source_sha256:continue
        if exact_assignment(rule,assignment) and rule.valid_from<=(assignment.valid_to or date.max) and assignment.valid_from<=(rule.valid_to or date.max):
            raise HTTPException(403,'account.manage required for assignment changes affecting Human Role Rules')


def assign(db, actor, employee_id, payload, transfer=False, commit_result=True):
    administration_lock(db,actor,"personnel.manage");employee=get(db,Employee,employee_id)
    if not employee.active:raise HTTPException(409,'employee inactive')
    organization=get(db,OrganizationUnit,payload.organization_id)
    if not organization.active:raise HTTPException(409,'organization inactive')
    if payload.role_ids and 'account.manage' not in permission_codes(db,actor.user_id):
        raise HTTPException(403,'explicit account authority required to grant appointment roles')
    roles=[get(db,Role,role_id) for role_id in set(payload.role_ids)]
    if any(not role.active for role in roles):raise HTTPException(409,'role inactive')
    if any(role.code=='system_admin' for role in roles):raise HTTPException(422,'system administrator must use an explicit permanent account grant')
    from types import SimpleNamespace
    guard_rule_assignment(db,actor,SimpleNamespace(organization_id=str(payload.organization_id),title=payload.title,kind=payload.kind,valid_from=payload.valid_from,valid_to=payload.valid_to))
    if transfer and payload.kind!='primary':raise HTTPException(422,'transfer applies to primary assignment')
    changed=db.execute(update(Employee).where(Employee.employee_id==str(employee_id),Employee.version==payload.expected_version)
        .values(version=payload.expected_version+1,updated_at=now_utc())).rowcount
    if changed!=1:raise HTTPException(409,'employee version conflict')
    prior=db.scalars(select(EmployeeAssignment).where(EmployeeAssignment.employee_id==str(employee_id),EmployeeAssignment.kind=='primary')).all()
    if transfer:
        for previous in prior:
            if previous.valid_from < payload.valid_from and (previous.valid_to is None or previous.valid_to >= payload.valid_from):
                guard_rule_assignment(db,actor,previous)
                before=output(previous)
                previous.valid_to=payload.valid_from-timedelta(days=1);previous.version+=1
                audit(db,actor,'personnel.assignment.close',previous,before,reason=payload.reason)
    if payload.kind=='primary':
        finish=payload.valid_to or date.max
        if any(row.valid_from<=finish and (row.valid_to or date.max)>=payload.valid_from for row in prior):
            raise HTTPException(409,'primary assignment dates overlap')
    row=EmployeeAssignment(employee_id=str(employee_id),organization_id=str(payload.organization_id),title=payload.title,
        kind=payload.kind,valid_from=payload.valid_from,valid_to=payload.valid_to)
    db.add(row);db.flush()
    for role in roles:db.add(AssignmentRole(assignment_id=row.assignment_id,role_id=role.role_id))
    audit(db,actor,'personnel.transfer' if transfer else 'personnel.assignment.create',row,reason=payload.reason,
          extra={'role_ids':[role.role_id for role in roles],'employee_version':payload.expected_version+1})
    if commit_result:commit(db)
    return {**output(row),'role_ids':[role.role_id for role in roles],'employee_version':payload.expected_version+1}


@router.post('/staff/{employee_id}/assignments',status_code=201)
def create_assignment(employee_id: UUID,payload: AssignmentInput,actor=Depends(require_permission('personnel.manage')),db: Session=Depends(get_db)):
    return assign(db,actor,employee_id,payload)


@router.post('/staff/{employee_id}/transfer',status_code=201)
def transfer_employee(employee_id: UUID,payload: AssignmentInput,actor=Depends(require_permission('personnel.manage')),db: Session=Depends(get_db)):
    return assign(db,actor,employee_id,payload,transfer=True)


@router.get('/roles')
def roles(actor=Depends(current_user),db: Session=Depends(get_db)):
    if not ({'account.manage','personnel.read'} & permission_codes(db,actor.user_id)):
        raise HTTPException(403,'role registry access forbidden')
    return [output(row) for row in db.scalars(select(Role).order_by(Role.code))]


@router.post('/accounts',status_code=201)
def create_account(payload: AccountCreate,actor=Depends(require_permission('account.manage')),db: Session=Depends(get_db)):
    administration_lock(db,actor,'account.manage')
    employee=get(db,Employee,payload.employee_id)
    if not employee.active:raise HTTPException(409,'employee inactive')
    row=User(employee_id=employee.employee_id,username=payload.username,password_hash=hash_password(payload.password),**initial_password_dates())
    db.add(row)
    try:db.flush()
    except IntegrityError:db.rollback();raise HTTPException(409,'account already exists') from None
    db.add(PasswordHistory(user_id=row.user_id,password_hash=row.password_hash))
    write_audit(db,user_id=actor.user_id,action='account.create',entity_type='user',entity_id=row.user_id,
        after={'username':row.username,'employee_id':row.employee_id,'reason':payload.reason,**password_metadata(row)})
    commit(db);return {'user_id':row.user_id,'username':row.username,'employee_id':row.employee_id,'active':row.active,'version':row.version}


@router.get('/audit')
def audits(limit: int=100,before_id: int|None=None,action: str|None=None,entity_type: str|None=None,actor=Depends(require_permission('audit.read')),db: Session=Depends(get_db)):
    if not 1<=limit<=500 or (before_id is not None and before_id<1):raise HTTPException(422,'invalid audit page')
    if any(value is not None and len(value)>120 for value in (action,entity_type)):raise HTTPException(422,'audit filter too long')
    query=select(AuditLog)
    if before_id is not None:query=query.where(AuditLog.audit_id<before_id)
    if action is not None:query=query.where(AuditLog.action==action)
    if entity_type is not None:query=query.where(AuditLog.entity_type==entity_type)
    return [output(row) for row in db.scalars(query.order_by(AuditLog.audit_id.desc()).limit(limit))]



class AccountPatch(HumanChange):
    expected_version: int = Field(ge=1)
    active: bool | None = None
    role_ids: list[UUID] | None = Field(default=None, max_length=20)
    reason: str = Field(min_length=1, max_length=1000)


class PasswordChange(BaseModel):
    current_password: str = Field(min_length=1, max_length=128)
    new_password: str = Field(min_length=12, max_length=128)


class PasswordReset(HumanChange):
    expected_version: int = Field(ge=1)
    new_password: str = Field(min_length=12, max_length=128)
    reason: str = Field(min_length=1, max_length=1000)


def public_account(db, row):
    return {'user_id':row.user_id,'employee_id':row.employee_id,'username':row.username,
            'active':row.active,'version':row.version,
            'password_changed_at':utc(row.password_changed_at).isoformat(),
            'password_expires_at':utc(row.password_expires_at).isoformat() if row.password_expires_at else None,
            'password_change_required':password_expired(row.password_expires_at),
            'permanent_role_ids':list(db.scalars(select(UserRole.role_id).where(UserRole.user_id==row.user_id))),
            'effective_role_ids':sorted(effective_role_ids(db,row.user_id))}


def revoke_sessions(db,user_id):
    db.execute(update(UserSession).where(UserSession.user_id==user_id,UserSession.revoked_at.is_(None)).values(revoked_at=now_utc()))


@router.get('/accounts')
def accounts(actor=Depends(require_permission('account.manage')),db: Session=Depends(get_db)):
    return [public_account(db,row) for row in db.scalars(select(User).order_by(User.username))]


@router.patch('/accounts/{user_id}')
def edit_account(user_id: UUID,payload: AccountPatch,actor=Depends(require_permission('account.manage')),db: Session=Depends(get_db)):
    administration_lock(db,actor,'account.manage');row=get(db,User,user_id);before=public_account(db,row)
    if payload.active is None and payload.role_ids is None:raise HTTPException(422,'empty account change')
    if payload.role_ids is not None:
        role_ids={str(identity) for identity in payload.role_ids}
        for identity in role_ids:
            if not get(db,Role,identity).active:raise HTTPException(409,'role inactive')
    changes={'version':payload.expected_version+1,'updated_at':now_utc()}
    if payload.active is not None:changes['active']=payload.active
    changed=db.execute(update(User).where(User.user_id==str(user_id),User.version==payload.expected_version).values(**changes)).rowcount
    if changed!=1:raise HTTPException(409,'account version conflict')
    if payload.role_ids is not None:
        for grant in db.scalars(select(UserRole).where(UserRole.user_id==str(user_id))):db.delete(grant)
        db.flush()
        for identity in role_ids:db.add(UserRole(user_id=str(user_id),role_id=identity))
    db.refresh(row);retain_administrator(db);revoke_sessions(db,str(user_id))
    write_audit(db,user_id=actor.user_id,action='account.update',entity_type='user',entity_id=str(user_id),
        before=before,after={**public_account(db,row),'reason':payload.reason})
    commit(db);return public_account(db,row)


def replace_password(db,row,new_password,expected_version):
    recent=db.scalars(select(PasswordHistory).where(PasswordHistory.user_id==row.user_id).where(PasswordHistory.password_hash!=row.password_hash).order_by(PasswordHistory.changed_at.desc()).limit(5)).all()
    if verify_password(row.password_hash,new_password) or any(verify_password(history.password_hash,new_password) for history in recent):
        raise HTTPException(422,'password reuse is forbidden')
    old_hash=row.password_hash;new_hash=hash_password(new_password)
    changed=db.execute(update(User).where(User.user_id==row.user_id,User.version==expected_version)
        .values(password_hash=new_hash,version=expected_version+1,updated_at=now_utc(),**initial_password_dates())).rowcount
    if changed!=1:raise HTTPException(409,'account version conflict')
    if not db.scalar(select(PasswordHistory.history_id).where(PasswordHistory.user_id==row.user_id,PasswordHistory.password_hash==old_hash).limit(1)):
        db.add(PasswordHistory(user_id=row.user_id,password_hash=old_hash))
    db.add(PasswordHistory(user_id=row.user_id,password_hash=new_hash));revoke_sessions(db,row.user_id)
    db.refresh(row)


@router.post('/password')
def change_password(payload: PasswordChange,response: Response,actor=Depends(authenticated_user),db: Session=Depends(get_db)):
    administration_lock(db);revalidate_session(db,actor.user_id);row=get(db,User,actor.user_id)
    if not row.active or not employee_available(db,row) or not verify_password(row.password_hash,payload.current_password):raise HTTPException(401,'current password invalid')
    replace_password(db,row,payload.new_password,row.version)
    write_audit(db,user_id=row.user_id,action='auth.password.change',entity_type='user',entity_id=row.user_id,
        after={'sessions_revoked':True,**password_metadata(row)})
    commit(db);response.delete_cookie(settings.cookie_name,path='/');return {'ok':True,'login_required':True}


@router.post('/accounts/{user_id}/password-reset')
def reset_password(user_id: UUID,payload: PasswordReset,actor=Depends(require_permission('account.manage')),db: Session=Depends(get_db)):
    administration_lock(db,actor,'account.manage');row=get(db,User,user_id)
    replace_password(db,row,payload.new_password,payload.expected_version)
    write_audit(db,user_id=actor.user_id,action='auth.password.reset',entity_type='user',entity_id=row.user_id,
        after={'sessions_revoked':True,'reason':payload.reason,**password_metadata(row)})
    commit(db);return {'user_id':row.user_id,'version':row.version,'sessions_revoked':True}


class AssignmentPatch(HumanChange):
    expected_version: int = Field(ge=1)
    expected_employee_version: int = Field(ge=1)
    valid_to: date | None = None
    title: str | None = Field(default=None,min_length=1,max_length=200)
    reason: str = Field(min_length=1,max_length=1000)


@router.patch('/assignments/{assignment_id}')
def edit_assignment(assignment_id: UUID,payload: AssignmentPatch,actor=Depends(require_permission('personnel.manage')),db: Session=Depends(get_db)):
    administration_lock(db,actor,'personnel.manage');row=get(db,EmployeeAssignment,assignment_id);before=output(row)
    if row.version!=payload.expected_version:raise HTTPException(409,'assignment version conflict')
    changes=payload.model_dump(exclude_unset=True,exclude={'expected_version','expected_employee_version','reason'})
    if not changes or ('title' in changes and changes['title'] is None):raise HTTPException(422,'invalid empty change')
    if 'valid_to' in changes and changes['valid_to'] != row.valid_to and db.scalar(select(AssignmentRole.assignment_id).where(AssignmentRole.assignment_id==row.assignment_id).limit(1)):
        if 'account.manage' not in permission_codes(db,actor.user_id):raise HTTPException(403,'account.manage required for role validity changes')
    from types import SimpleNamespace
    guard_rule_assignment(db,actor,row)
    guard_rule_assignment(db,actor,SimpleNamespace(**{**before,**changes}))
    end=changes.get('valid_to',row.valid_to)
    if end is not None and end<row.valid_from:raise HTTPException(422,'end date precedes start date')
    if row.kind=='primary':
        prior=db.scalars(select(EmployeeAssignment).where(EmployeeAssignment.employee_id==row.employee_id,
            EmployeeAssignment.assignment_id!=row.assignment_id,EmployeeAssignment.kind=='primary')).all()
        if any(other.valid_from<=(end or date.max) and (other.valid_to or date.max)>=row.valid_from for other in prior):
            raise HTTPException(409,'primary assignment dates overlap')
    changed=db.execute(update(Employee).where(Employee.employee_id==row.employee_id,Employee.version==payload.expected_employee_version)
        .values(version=payload.expected_employee_version+1,updated_at=now_utc())).rowcount
    if changed!=1:raise HTTPException(409,'employee version conflict')
    for key,value in changes.items():setattr(row,key,value)
    row.version+=1
    audit(db,actor,'personnel.assignment.update',row,before,payload.reason)
    commit(db);return {**output(row),'employee_version':payload.expected_employee_version+1}


@router.get('/context')
def context(actor=Depends(current_user),db: Session=Depends(get_db)):
    identity=db.get(TenantIdentity,1)
    return {'department':identity.name if identity else '開発環境',
            'department_id':identity.tenant_id if identity else None,'username':actor.username,
            'business_date':business_date(),'password_max_age_days':settings.password_max_age_days,'permissions':sorted(permission_codes(db,actor.user_id))}


class PasswordExpiry(HumanChange):
    expected_version: int = Field(ge=1)
    mode: Literal['policy','explicit','clear']
    expires_at: datetime | None = None
    reason: str = Field(min_length=1,max_length=1000)

    @model_validator(mode='after')
    def selected_date(self):
        if self.mode=='explicit':
            if self.expires_at is None or self.expires_at.tzinfo is None:
                raise ValueError('explicit expiry requires an ISO8601 time zone')
        elif self.expires_at is not None:raise ValueError('expiry date is only valid in explicit mode')
        return self


@router.post('/accounts/{user_id}/password-expiry')
def set_password_expiry(user_id: UUID,payload: PasswordExpiry,actor=Depends(require_permission('account.manage')),db: Session=Depends(get_db)):
    administration_lock(db,actor,'account.manage');row=get(db,User,user_id);before=public_account(db,row)
    if payload.mode=='policy':
        if settings.password_max_age_days is None:raise HTTPException(422,'department password-age policy is not configured')
        expiry=next_password_expiry(row.password_changed_at,settings.password_max_age_days)
    else:expiry=utc(payload.expires_at) if payload.expires_at else None
    changed=db.execute(update(User).where(User.user_id==str(user_id),User.version==payload.expected_version)
        .values(password_expires_at=expiry,version=payload.expected_version+1,updated_at=now_utc())).rowcount
    if changed!=1:raise HTTPException(409,'account version conflict')
    db.refresh(row);revoke_sessions(db,row.user_id)
    write_audit(db,user_id=actor.user_id,action='account.password.expiry',entity_type='user',entity_id=row.user_id,
        before=before,after={**public_account(db,row),'mode':payload.mode,'policy_max_age_days':settings.password_max_age_days if payload.mode=='policy' else None,'reason':payload.reason,'sessions_revoked':True})
    commit(db);return public_account(db,row)


# Human permission definitions are separate from code-owned seeded roles.
from uuid import uuid4
from pydantic import ConfigDict
from ..models import Permission,RolePermission,Document
from ..authorization_models import HumanRoleRule,TemporaryRoleGrant


class PermissionRoleCreate(HumanChange):
    model_config=ConfigDict(extra='forbid')
    name: str=Field(min_length=1,max_length=200)
    active: bool=True
    permission_codes: list[str]=Field(max_length=250)
    sensitive_acknowledged: bool=False
    reason: str=Field(min_length=1,max_length=1000)


class PermissionRolePatch(HumanChange):
    model_config=ConfigDict(extra='forbid')
    expected_version: int=Field(ge=1)
    name: str|None=Field(default=None,min_length=1,max_length=200)
    permission_codes: list[str]|None=Field(default=None,max_length=250)
    active: bool|None=None
    sensitive_acknowledged: bool=False
    reason: str=Field(min_length=1,max_length=1000)


class RoleRuleCreate(HumanChange):
    model_config=ConfigDict(extra='forbid')
    name: str=Field(min_length=1,max_length=200)
    role_id: UUID
    organization_id: UUID|None=None
    title: str|None=Field(default=None,min_length=1,max_length=200)
    kind: Literal['primary','secondary']|None=None
    valid_from: date
    valid_to: date|None=None
    source_document_id: UUID|None=None
    expected_source_sha256: str|None=Field(default=None,pattern=r'^[0-9a-f]{64}$')
    sensitive_acknowledged: bool=False
    reason: str=Field(min_length=1,max_length=1000)

    @model_validator(mode='after')
    def exact_rule(self):
        if (self.source_document_id is None)!=(self.expected_source_sha256 is None):raise ValueError('reviewed source hash is required with document')
        if not self.organization_id and not self.title:raise ValueError('exact organization or title is required')
        if self.title is not None and not self.title.strip():raise ValueError('title must not be blank')
        if self.valid_to is not None and self.valid_to<self.valid_from:raise ValueError('invalid rule dates')
        return self


class RoleGrantCreate(HumanChange):
    model_config=ConfigDict(extra='forbid')
    user_id: UUID
    role_id: UUID
    acting_for_employee_id: UUID|None=None
    valid_from: date
    valid_to: date
    source_document_id: UUID|None=None
    expected_source_sha256: str|None=Field(default=None,pattern=r'^[0-9a-f]{64}$')
    sensitive_acknowledged: bool=False
    reason: str=Field(min_length=1,max_length=1000)

    @model_validator(mode='after')
    def grant_dates(self):
        if (self.source_document_id is None)!=(self.expected_source_sha256 is None):raise ValueError('reviewed source hash is required with document')
        if self.valid_to<self.valid_from:raise ValueError('invalid grant dates')
        return self


class RoleRuleState(HumanChange):
    model_config=ConfigDict(extra='forbid')
    expected_version: int=Field(ge=1)
    sensitive_acknowledged: bool=False
    active: bool
    reason: str=Field(min_length=1,max_length=1000)


class RoleGrantRevoke(HumanChange):
    model_config=ConfigDict(extra='forbid')
    expected_version: int=Field(ge=1)
    reason: str=Field(min_length=1,max_length=1000)


def sensitive_permission(code):
    return code.startswith(('emergency.','fire_investigation.','personnel.','account.')) or code=='system.backup' or code.endswith(('.approve','.promote','.manage','.admin','.apply'))


def role_permissions(db,role_id):
    return sorted(db.scalars(select(Permission.code).join(RolePermission,RolePermission.permission_id==Permission.permission_id).where(RolePermission.role_id==role_id)))


def role_output(db,row):
    return {**output(row),'permission_codes':role_permissions(db,row.role_id)}


def approved_codes(db,codes,ack):
    codes=set(codes)
    rows=db.scalars(select(Permission).where(Permission.code.in_(codes))).all()
    if codes!={row.code for row in rows}:raise HTTPException(422,'unknown permission code')
    if any(sensitive_permission(code) for code in codes) and not ack:raise HTTPException(422,'Human sensitive permission acknowledgement is required')
    return rows


def grantable_role(db,identity,ack):
    role=get(db,Role,identity)
    if not role.active:raise HTTPException(409,'role inactive')
    if role.code=='system_admin':raise HTTPException(422,'system administrator requires a permanent explicit account grant')
    approv…10999 tokens truncated…lt = subprocess.run(['node', str(script), str(source)], text=True, capture_output=True, timeout=10)
    assert result.returncode == 0, result.stderr


def test_slow_old_list_cannot_replace_new_detail(tmp_path):
    run(tmp_path, r'''
handler=async(path)=>path==='/personnel-intake/proposals'?new Promise(resolve=>waiting=resolve):proposal;
const old=controller.load();await tick();assert.ok(waiting);
await controller.detail('NOTICE');assert.equal(shown.proposal.proposal_id,'NOTICE');
waiting([{proposal_id:'OLD PRIVATE'}]);await old;
assert.equal(shown.proposal.proposal_id,'NOTICE');
''')


def test_inflight_session_change_discards_private_detail(tmp_path):
    run(tmp_path, r'''
handler=async()=>new Promise(resolve=>waiting=resolve);
const old=controller.detail('NOTICE');await tick();authority.session_id='REPLACED';waiting(proposal);await old;
assert.equal(shown,null);assert.ok(clears>0);
''')


def test_lost_management_right_prevents_cached_review(tmp_path):
    run(tmp_path, r'''
handler=async()=>proposal;await controller.detail('NOTICE');
authority.permissions=authority.permissions.filter(x=>x!=='personnel.manage');
await controller.decision('review','Synthetic Human reason',true);
assert.equal(calls.filter(x=>x.method==='POST').length,0);assert.equal(shown,null);
''')


def test_human_acknowledgement_and_double_click_guard(tmp_path):
    run(tmp_path, r'''
handler=async()=>proposal;await controller.detail('NOTICE');
await controller.decision('review','Synthetic Human reason',false);
assert.equal(calls.filter(x=>x.method==='POST').length,0);
handler=async()=>new Promise(resolve=>waiting=resolve);
const first=controller.decision('review','Synthetic Human reason',true);await tick();
await controller.decision('review','Synthetic Human reason',true);
assert.equal(calls.filter(x=>x.method==='POST').length,1);
waiting({...proposal,status:'reviewed',version:2});await first;
assert.equal(shown.proposal.status,'reviewed');assert.equal(shown.busy,false);
''')


def test_permission_loss_after_mutation_cannot_restore_private_state(tmp_path):
    run(tmp_path, r'''
handler=async()=>proposal;await controller.detail('NOTICE');
handler=async()=>{authority.permissions=[];return {...proposal,status:'reviewed',version:2}};
await controller.decision('review','Synthetic Human reason',true);
assert.equal(shown,null);assert.ok(clears>0);
''')


def test_conflict_removes_cached_mutation_target(tmp_path):
    run(tmp_path, r'''
handler=async()=>proposal;await controller.detail('NOTICE');
handler=async()=>{throw Object.assign(new Error('source stale'),{status:409})};
await controller.decision('review','Synthetic Human reason',true);
assert.equal(shown.proposal,null);assert.equal(shown.busy,false);
const count=calls.length;await controller.decision('review','Synthetic Human reason',true);
assert.equal(calls.length,count);
''')


def test_focus_check_erases_private_state_while_mutation_is_pending(tmp_path):
    run(tmp_path, r'''
handler=async()=>proposal;await controller.detail('NOTICE');
handler=async()=>new Promise(resolve=>waiting=resolve);
const action=controller.decision('review','Synthetic Human reason',true);await tick();
authority.permissions=[];await controller.check();
assert.equal(shown,null,'permission loss must clear before pending mutation completes');
waiting({...proposal,status:'reviewed',version:2});await action;
assert.equal(shown,null);
''')


def test_unavailable_authority_clears_cached_source_before_reload(tmp_path):
    run(tmp_path, r'''
handler=async()=>proposal;await controller.detail('NOTICE');
assert.equal(shown.proposal.source_text,proposal.source_text);
authorityFailure=Object.assign(new Error('authority unavailable'),{status:503});
const before=calls.filter(x=>x.path.startsWith('/personnel-intake/')).length;
await controller.load();
assert.equal(shown,null,'failed authority verification must erase cached originals');
assert.equal(calls.filter(x=>x.path.startsWith('/personnel-intake/')).length,before);
''')


def test_invalid_authority_context_clears_cached_source_before_reload(tmp_path):
    run(tmp_path, r'''
handler=async()=>proposal;await controller.detail('NOTICE');
authority=null;
const before=calls.filter(x=>x.path.startsWith('/personnel-intake/')).length;
await controller.load();
assert.equal(shown,null,'malformed authority context must erase cached originals');
assert.equal(calls.filter(x=>x.path.startsWith('/personnel-intake/')).length,before);
''')
