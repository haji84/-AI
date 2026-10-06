from datetime import date
from typing import Literal
from fastapi import APIRouter,Depends,File,Form,Query,Response,UploadFile
from sqlalchemy import or_,select
from sqlalchemy.orm import Session
from ..authz import require_permission
from ..db import get_db
from ..models import Employee,User
from ..personnel import OrganizationUnit
from ..workforce_models import (
    WorkforceShiftType,WorkforceEmployeeQualification,WorkforceStaffingRule,
    WorkforceRosterEntry,WorkforceLeaveEntry,WorkforceAttendance,WorkforceTimeEntry,
)
from ..workforce_schemas import (
    ShiftTypeCreate,ShiftTypePatch,QualificationCreate,QualificationPatch,StaffingRuleCreate,RosterCreate,
    LeaveCreate,AttendanceCreate,AttendancePatch,TimeEntryCreate,HumanAction,ImportConfirm,
)
from .. import workforce_service as svc

router=APIRouter(prefix='/workforce',tags=['workforce'])
def no_store(response:Response):response.headers['Cache-Control']='no-store'

@router.get('/policy',dependencies=[Depends(no_store)])
def policy(db:Session=Depends(get_db),user:User=Depends(require_permission('workforce.read'))):
    return {'schema_version':svc.SCHEMA_VERSION,'business_timezone':svc.DEFAULT_TIMEZONE,'ai_required':False}

@router.get('/employees',dependencies=[Depends(no_store)])
def employees(q:str=Query('',max_length=300),db:Session=Depends(get_db),user:User=Depends(require_permission('workforce.read'))):
    stmt=select(Employee).where(Employee.active.is_(True))
    if q:stmt=stmt.where(or_(Employee.display_name.ilike(f'%{q}%'),Employee.employee_code.ilike(f'%{q}%')))
    return [{'employee_id':x.employee_id,'employee_code':x.employee_code,'display_name':x.display_name,'version':x.version} for x in db.scalars(stmt.order_by(Employee.display_name).limit(200))]

@router.get('/organizations',dependencies=[Depends(no_store)])
def organizations(db:Session=Depends(get_db),user:User=Depends(require_permission('workforce.read'))):
    rows=db.scalars(select(OrganizationUnit).where(OrganizationUnit.active.is_(True)).order_by(OrganizationUnit.code)).all()
    return [{'organization_id':x.organization_id,'code':x.code,'name':x.name,'version':x.version} for x in rows]

@router.get('/shift-types',dependencies=[Depends(no_store)])
def shift_types(db:Session=Depends(get_db),user:User=Depends(require_permission('workforce.read'))):
    return [svc.visible(db,user,x) for x in db.scalars(select(WorkforceShiftType).order_by(WorkforceShiftType.code)).all()]

@router.post('/shift-types',status_code=201,dependencies=[Depends(no_store)])
def create_shift(payload:ShiftTypeCreate,db:Session=Depends(get_db),user:User=Depends(require_permission('workforce.admin'))):
    row=svc.create_shift(db,user,payload);svc.save(db);return svc.visible(db,user,row)

@router.patch('/shift-types/{key}',dependencies=[Depends(no_store)])
def patch_shift(key:str,payload:ShiftTypePatch,db:Session=Depends(get_db),user:User=Depends(require_permission('workforce.admin'))):
    row=svc.patch_shift(db,user,key,payload);svc.save(db);return svc.visible(db,user,row)

@router.get('/qualifications',dependencies=[Depends(no_store)])
def qualifications(employee_id:str|None=None,db:Session=Depends(get_db),user:User=Depends(require_permission('workforce.read'))):
    stmt=select(WorkforceEmployeeQualification)
    if employee_id:stmt=stmt.where(WorkforceEmployeeQualification.employee_id==employee_id)
    return [svc.visible(db,user,x) for x in db.scalars(stmt.order_by(WorkforceEmployeeQualification.valid_from.desc()).limit(500)).all()]

@router.post('/qualifications',status_code=201,dependencies=[Depends(no_store)])
def create_qualification(payload:QualificationCreate,db:Session=Depends(get_db),user:User=Depends(require_permission('workforce.admin'))):
    row=svc.create_qualification(db,user,payload);svc.save(db);return svc.visible(db,user,row)

@router.patch('/qualifications/{key}',dependencies=[Depends(no_store)])
def patch_qualification(key:str,payload:QualificationPatch,db:Session=Depends(get_db),user:User=Depends(require_permission('workforce.admin'))):
    row=svc.patch_qualification(db,user,key,payload);svc.save(db);return svc.visible(db,user,row)

@router.get('/staffing-rules',dependencies=[Depends(no_store)])
def staffing_rules(organization_id:str|None=None,db:Session=Depends(get_db),user:User=Depends(require_permission('workforce.read'))):
    stmt=select(WorkforceStaffingRule)
    if organization_id:stmt=stmt.where(WorkforceStaffingRule.organization_id==organization_id)
    return [svc.visible(db,user,x) for x in db.scalars(stmt.order_by(WorkforceStaffingRule.effective_from.desc()).limit(500)).all()]

@router.post('/staffing-rules',status_code=201,dependencies=[Depends(no_store)])
def create_staffing_rule(payload:StaffingRuleCreate,db:Session=Depends(get_db),user:User=Depends(require_permission('workforce.admin'))):
    row=svc.create_staffing_rule(db,user,payload);svc.save(db);return svc.visible(db,user,row)

@router.post('/staffing-rules/{key}/{action}',dependencies=[Depends(no_store)])
def staffing_rule_action(key:str,action:Literal['review','approve','cancel'],payload:HumanAction,db:Session=Depends(get_db),user:User=Depends(require_permission('workforce.review'))):
    if action=='approve':svc.need(db,user,'workforce.approve')
    row=svc.staffing_action(db,user,key,payload.expected_version,action,payload.note);svc.save(db);return svc.visible(db,user,row)

@router.get('/rosters',dependencies=[Depends(no_store)])
def rosters(from_date:date|None=None,to_date:date|None=None,organization_id:str|None=None,employee_id:str|None=None,status:str|None=None,
            db:Session=Depends(get_db),user:User=Depends(require_permission('workforce.read'))):
    stmt=select(WorkforceRosterEntry)
    if from_date:stmt=stmt.where(WorkforceRosterEntry.work_date>=from_date)
    if to_date:stmt=stmt.where(WorkforceRosterEntry.work_date<=to_date)
    if organization_id:stmt=stmt.where(WorkforceRosterEntry.organization_id==organization_id)
    if employee_id:stmt=stmt.where(WorkforceRosterEntry.employee_id==employee_id)
    if status:stmt=stmt.where(WorkforceRosterEntry.status==status)
    return [svc.visible(db,user,x) for x in db.scalars(stmt.order_by(WorkforceRosterEntry.work_date,WorkforceRosterEntry.starts_at).limit(1000)).all()]

@router.post('/rosters',status_code=201,dependencies=[Depends(no_store)])
def create_roster(payload:RosterCreate,db:Session=Depends(get_db),user:User=Depends(require_permission('workforce.create'))):
    row=svc.create_roster(db,user,payload);svc.save(db);return svc.visible(db,user,row)

@router.post('/rosters/{key}/{action}',dependencies=[Depends(no_store)])
def roster_action(key:str,action:Literal['review','approve','cancel'],payload:HumanAction,db:Session=Depends(get_db),
                  user:User=Depends(require_permission('workforce.review'))):
    if action=='approve':svc.need(db,user,'workforce.approve')
    row=svc.roster_action(db,user,key,payload.expected_version,action,payload.note);svc.save(db);return svc.visible(db,user,row)

@router.get('/leave',dependencies=[Depends(no_store)])
def leaves(employee_id:str|None=None,from_date:date|None=None,to_date:date|None=None,db:Session=Depends(get_db),user:User=Depends(require_permission('workforce.read'))):
    stmt=select(WorkforceLeaveEntry)
    if employee_id:stmt=stmt.where(WorkforceLeaveEntry.employee_id==employee_id)
    if from_date:stmt=stmt.where(WorkforceLeaveEntry.effective_on>=from_date)
    if to_date:stmt=stmt.where(WorkforceLeaveEntry.effective_on<=to_date)
    return [svc.visible(db,user,x) for x in db.scalars(stmt.order_by(WorkforceLeaveEntry.effective_on.desc()).limit(1000)).all()]

@router.post('/leave',status_code=201,dependencies=[Depends(no_store)])
def create_leave(payload:LeaveCreate,db:Session=Depends(get_db),user:User=Depends(require_permission('workforce.create'))):
    row=svc.create_leave(db,user,payload);svc.save(db);return svc.visible(db,user,row)

@router.post('/leave/{key}/{action}',dependencies=[Depends(no_store)])
def leave_action(key:str,action:Literal['review','approve','cancel'],payload:HumanAction,db:Session=Depends(get_db),user:User=Depends(require_permission('workforce.review'))):
    if action=='approve':svc.need(db,user,'workforce.approve')
    row=svc.leave_action(db,user,key,payload.expected_version,action,payload.note);svc.save(db);return svc.visible(db,user,row)

@router.get('/leave-balance/{employee_id}',dependencies=[Depends(no_store)])
def leave_balance(employee_id:str,as_of:date,db:Session=Depends(get_db),user:User=Depends(require_permission('workforce.read'))):
    return {'employee_id':employee_id,'as_of':as_of.isoformat(),**{kind:svc.leave_balance(db,employee_id,kind,as_of) for kind in ('annual','special','compensatory')}}

@router.get('/attendance',dependencies=[Depends(no_store)])
def attendance(employee_id:str|None=None,from_date:date|None=None,to_date:date|None=None,db:Session=Depends(get_db),user:User=Depends(require_permission('workforce.read'))):
    stmt=select(WorkforceAttendance)
    if employee_id:stmt=stmt.where(WorkforceAttendance.employee_id==employee_id)
    if from_date:stmt=stmt.where(WorkforceAttendance.work_date>=from_date)
    if to_date:stmt=stmt.where(WorkforceAttendance.work_date<=to_date)
    return [svc.visible(db,user,x) for x in db.scalars(stmt.order_by(WorkforceAttendance.work_date.desc()).limit(1000)).all()]

@router.post('/attendance',status_code=201,dependencies=[Depends(no_store)])
def create_attendance(payload:AttendanceCreate,db:Session=Depends(get_db),user:User=Depends(require_permission('workforce.create'))):
    row=svc.create_attendance(db,user,payload);svc.save(db);return svc.visible(db,user,row)

@router.patch('/attendance/{key}',dependencies=[Depends(no_store)])
def patch_attendance(key:str,payload:AttendancePatch,db:Session=Depends(get_db),user:User=Depends(require_permission('workforce.update'))):
    row=svc.patch_attendance(db,user,key,payload);svc.save(db);return svc.visible(db,user,row)

@router.post('/attendance/{key}/{action}',dependencies=[Depends(no_store)])
def attendance_action(key:str,action:Literal['review','approve','cancel'],payload:HumanAction,db:Session=Depends(get_db),user:User=Depends(require_permission('workforce.review'))):
    if action=='approve':svc.need(db,user,'workforce.approve')
    row=svc.attendance_action(db,user,key,payload.expected_version,action,payload.note);svc.save(db);return svc.visible(db,user,row)

@router.get('/time-entries',dependencies=[Depends(no_store)])
def time_entries(employee_id:str|None=None,from_date:date|None=None,to_date:date|None=None,db:Session=Depends(get_db),user:User=Depends(require_permission('workforce.read'))):
    stmt=select(WorkforceTimeEntry)
    if employee_id:stmt=stmt.where(WorkforceTimeEntry.employee_id==employee_id)
    if from_date:stmt=stmt.where(WorkforceTimeEntry.occurred_on>=from_date)
    if to_date:stmt=stmt.where(WorkforceTimeEntry.occurred_on<=to_date)
    return [svc.visible(db,user,x) for x in db.scalars(stmt.order_by(WorkforceTimeEntry.occurred_on.desc()).limit(1000)).all()]

@router.post('/time-entries',status_code=201,dependencies=[Depends(no_store)])
def create_time_entry(payload:TimeEntryCreate,db:Session=Depends(get_db),user:User=Depends(require_permission('workforce.create'))):
    row=svc.create_time_entry(db,user,payload);svc.save(db);return svc.visible(db,user,row)

@router.post('/time-entries/{key}/{action}',dependencies=[Depends(no_store)])
def time_action(key:str,action:Literal['review','approve','cancel'],payload:HumanAction,db:Session=Depends(get_db),user:User=Depends(require_permission('workforce.review'))):
    if action=='approve':svc.need(db,user,'workforce.approve')
    row=svc.time_action(db,user,key,payload.expected_version,action,payload.note);svc.save(db);return svc.visible(db,user,row)

@router.get('/comp-balance/{employee_id}',dependencies=[Depends(no_store)])
def comp_balance(employee_id:str,as_of:date,db:Session=Depends(get_db),user:User=Depends(require_permission('workforce.read'))):
    return {'employee_id':employee_id,'as_of':as_of.isoformat(),'minutes':svc.time_balance(db,employee_id,as_of)}

@router.get('/warnings',dependencies=[Depends(no_store)])
def warnings(on_date:date,organization_id:str|None=None,db:Session=Depends(get_db),user:User=Depends(require_permission('workforce.read'))):
    return svc.staffing_warnings(db,on_date,organization_id)

@router.get('/available-crew',dependencies=[Depends(no_store)])
def available_crew(on_date:date,organization_id:str|None=None,shift_type_id:str|None=None,db:Session=Depends(get_db),user:User=Depends(require_permission('workforce.read'))):
    return svc.available_crew(db,on_date,organization_id,shift_type_id)

@router.get('/statistics',dependencies=[Depends(no_store)])
def statistics(year:int=Query(...,ge=2000,le=2200),month:int|None=Query(None,ge=1,le=12),db:Session=Depends(get_db),user:User=Depends(require_permission('workforce.aggregate'))):
    return svc.statistics(db,year,month)

@router.post('/import/rosters',dependencies=[Depends(no_store)])
async def import_rosters(file:UploadFile=File(...),document_id:str|None=Form(None),db:Session=Depends(get_db),user:User=Depends(require_permission('workforce.import'))):
    row=svc.import_preview(db,user,await file.read(2*1024*1024+1),file.filename or 'uploaded',document_id);svc.save(db)
    return {'preview_id':row.preview_id,'version':row.version,'rows':len(row.row_data),'sample':row.row_data[:10],'file_sha256':row.file_sha256,'expires_at':svc.scalar(row.expires_at)}

@router.post('/import-previews/{key}/confirm',dependencies=[Depends(no_store)])
def confirm_import(key:str,payload:ImportConfirm,db:Session=Depends(get_db),user:User=Depends(require_permission('workforce.import'))):
    out=svc.confirm_import(db,user,key,payload.expected_version,payload.file_sha256);svc.save(db);return out

@router.get('/export/rosters',dependencies=[Depends(no_store)])
def export_rosters(format:Literal['csv','xlsx']='csv',from_date:date|None=None,to_date:date|None=None,db:Session=Depends(get_db),user:User=Depends(require_permission('workforce.export'))):
    blob,mime=svc.export_rosters(db,format,from_date,to_date)
    return Response(blob,media_type=mime,headers={'Content-Disposition':f'attachment; filename="workforce-rosters.{format}"','Cache-Control':'no-store'})
