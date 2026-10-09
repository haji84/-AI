"""Human team grouping; no roster, dispatch, role or salary side effects."""
from uuid import UUID
import json
from hashlib import sha256
from fastapi import HTTPException
from sqlalchemy import select, or_
from sqlalchemy.exc import IntegrityError
from .authz import current_user, revalidate_session
from .models import Employee, now_utc, uuid_str
from .audit import write_audit
from .personnel import EmployeeAssignment, OrganizationUnit
from .statistics_sources import require_workforce_available
from .workforce_models import WorkforceTeam, WorkforceTeamMembership, WorkforceTeamChange
from . import workforce_service as service


def flush(db):
    try:db.flush()
    except IntegrityError:
        db.rollback();raise HTTPException(409,'Workforce team data conflict') from None


def digest(value):
    return sha256(json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()).hexdigest()


def audit(db,user,action,record,before=None,team_version=None):
    after=service.row_dict(record)
    membership=isinstance(record,WorkforceTeamMembership)
    team_id=record.team_id
    evidence={'action':action,'actor_id':user.user_id,'team_id':team_id,
              'membership_id':record.membership_id if membership else None,
              'reason':record.reason,'before_data':before,'after_data':after}
    history=WorkforceTeamChange(change_id=uuid_str(),**evidence,evidence_sha256=digest(evidence))
    db.add(history);flush(db)
    def projection(data):
        if data is None:return None
        result={key:data[key] for key in ('team_id','membership_id','organization_id','employee_id','assignment_id','assignment_version','version','active') if key in data}
        for key in ('code','name','reason','assignment_snapshot'):
            if key in data:result[key+'_sha256']=digest(data[key])
        return result
    public={**projection(after),'history_id':history.change_id,'history_sha256':history.evidence_sha256}
    if team_version is not None:public['team_version']=team_version
    write_audit(db,user_id=user.user_id,action=action,entity_type=record.__tablename__,
        entity_id=record.membership_id if membership else team_id,before=projection(before),after=public)


def authority(db,user,mutation=False):
    revalidate_session(db,user.user_id);current_user(user)
    service.need(db,user,'workforce.admin' if mutation else 'workforce.read','personnel.read')
    require_workforce_available(db)


def row(db,model,key,lock=False):
    try:key=str(UUID(str(key)))
    except (ValueError,TypeError):raise HTTPException(404,'Workforce team record not found') from None
    return service.get_row(db,model,key,lock)


def snapshot(assignment):
    return service.row_dict(assignment)


def membership_payload(db,team,member):
    assignment=db.get(EmployeeAssignment,member.assignment_id,populate_existing=True)
    employee=db.get(Employee,member.employee_id,populate_existing=True)
    organization=db.get(OrganizationUnit,team.organization_id,populate_existing=True)
    current=bool(assignment and employee and employee.active and organization and organization.active
        and team.active and member.active and assignment.version==member.assignment_version
        and assignment.employee_id==member.employee_id and assignment.organization_id==team.organization_id
        and assignment.kind=='primary' and snapshot(assignment)==member.assignment_snapshot)
    return {**service.row_dict(member),'employee_name':employee.display_name if employee else None,
            'operational_status':'current' if current else 'unavailable',
            'formal_crew_assignment':False}


def create(db,user,payload):
    authority(db,user,True)
    organization=row(db,OrganizationUnit,payload.organization_id,True)
    if not organization.active:raise HTTPException(409,'Team organization is inactive')
    team=WorkforceTeam(**{**payload.model_dump(),'organization_id':str(payload.organization_id)},created_by=user.user_id)
    db.add(team);flush(db);audit(db,user,'workforce.team.create',team)
    authority(db,user,True);return team


def patch(db,user,key,payload):
    authority(db,user,True);team=row(db,WorkforceTeam,key,True)
    service.check_version(team,payload.expected_version);before=service.row_dict(team)
    for field in ('name','active'):
        if getattr(payload,field) is not None:setattr(team,field,getattr(payload,field))
    team.reason=payload.reason;team.version+=1;team.updated_at=now_utc()
    flush(db);audit(db,user,'workforce.team.update',team,before)
    authority(db,user,True);return team


def validate_assignment(db,team,payload):
    employee=row(db,Employee,payload.employee_id,True)
    assignment=row(db,EmployeeAssignment,payload.assignment_id,True)
    service.check_version(assignment,getattr(payload,'expected_assignment_version',getattr(payload,'assignment_version',None)))
    organization=row(db,OrganizationUnit,team.organization_id,True)
    if not team.active or not employee.active or not organization.active:raise HTTPException(409,'Team membership source is inactive')
    if assignment.employee_id!=employee.employee_id or assignment.organization_id!=team.organization_id or assignment.kind!='primary':
        raise HTTPException(422,'Membership must reuse this employee primary assignment in the team organization')
    if payload.valid_from<assignment.valid_from or (assignment.valid_to and (payload.valid_to is None or payload.valid_to>assignment.valid_to)):
        raise HTTPException(422,'Membership dates must fit the explicit assignment period')
    return assignment


def overlap(db,team_id,employee_id,start,end,exclude=None):
    stmt=select(WorkforceTeamMembership.membership_id).where(
        WorkforceTeamMembership.team_id==team_id,WorkforceTeamMembership.employee_id==employee_id,
        WorkforceTeamMembership.active.is_(True),
        or_(WorkforceTeamMembership.valid_to.is_(None),WorkforceTeamMembership.valid_to>=start))
    if end:stmt=stmt.where(WorkforceTeamMembership.valid_from<=end)
    if exclude:stmt=stmt.where(WorkforceTeamMembership.membership_id!=exclude)
    if db.scalar(stmt.limit(1)):raise HTTPException(409,'Overlapping membership in the same team')


def add_member(db,user,key,payload):
    authority(db,user,True);team=row(db,WorkforceTeam,key,True)
    service.check_version(team,payload.expected_team_version)
    assignment=validate_assignment(db,team,payload)
    overlap(db,team.team_id,str(payload.employee_id),payload.valid_from,payload.valid_to)
    member=WorkforceTeamMembership(team_id=team.team_id,employee_id=str(payload.employee_id),
        assignment_id=assignment.assignment_id,assignment_version=assignment.version,assignment_snapshot=snapshot(assignment),
        valid_from=payload.valid_from,valid_to=payload.valid_to,reason=payload.reason,created_by=user.user_id)
    team.version+=1;team.updated_at=now_utc();db.add(member);flush(db)
    audit(db,user,'workforce.team.membership.create',member,team_version=team.version)
    authority(db,user,True);return team,member


def patch_member(db,user,key,member_key,payload):
    authority(db,user,True);team=row(db,WorkforceTeam,key,True)
    service.check_version(team,payload.expected_team_version)
    member=row(db,WorkforceTeamMembership,member_key,True)
    if member.team_id!=team.team_id:raise HTTPException(404,'Workforce team record not found')
    service.check_version(member,payload.expected_version)
    if payload.active:
        if membership_payload(db,team,member)['operational_status']!='current':
            # Inactive membership can be restored only if its captured source is unchanged.
            assignment=validate_assignment(db,team,member)
            if snapshot(assignment)!=member.assignment_snapshot:raise HTTPException(409,'Team membership source changed; create a new dated membership')
        overlap(db,team.team_id,member.employee_id,member.valid_from,member.valid_to,member.membership_id)
    before=service.row_dict(member)
    member.active=payload.active;member.reason=payload.reason;member.version+=1;member.updated_at=now_utc()
    team.version+=1;team.updated_at=now_utc();flush(db)
    audit(db,user,'workforce.team.membership.update',member,before,team_version=team.version)
    authority(db,user,True);return team,member
