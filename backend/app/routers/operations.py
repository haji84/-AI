from datetime import date
from typing import Literal
from fastapi import APIRouter,Depends,File,HTTPException,Query,Response,UploadFile
from sqlalchemy import or_,select
from sqlalchemy.orm import Session
from ..authz import current_user,permission_codes,require_permission,require_mutation_permission
from ..db import get_db
from ..audit import write_audit
from ..models import Employee,User,now_utc
from ..operations_models import Incident,Vehicle,Dispatch,DispatchCrew,AllowanceRate,VehicleTrip,FuelEntry,VehicleService
from ..operations_schemas import IncidentInput,IncidentPatch,VehicleInput,VehiclePatch,DispatchInput,DispatchPatch,CrewInput,RateInput,Calculate,TripInput,FuelInput,ServiceInput,Action,Version,ServiceApprove,ImportConfirm
from .. import operations_service as ops
from .. import vehicle_assignment_service as assignments
from ..operations_schemas import VehicleAssignmentInput

def no_store(response:Response):response.headers['Cache-Control']='no-store'
router=APIRouter(prefix='/operations',tags=['operations'],dependencies=[Depends(no_store)])

def result(db,user,row):
    ops.save(db)
    if isinstance(row,Dispatch):return dispatch_dict(db,user,row)
    if isinstance(row,(VehicleTrip,FuelEntry,VehicleService)):return history_dict(db,user,row)
    return ops.row_dict(row)

def incident_result(db,user,row):ops.save(db);return ops.incident_dict(db,row,permission_codes(db,user.user_id))

def dispatch_dict(db,user,row):
    out=ops.row_dict(row);perms=permission_codes(db,user.user_id)
    if 'incident.crew.read' not in perms:
        out.pop('review_snapshot');out.pop('calculation')
    if 'document.read' not in perms:
        out.pop('document_id',None)
        for field in ['review_snapshot','calculation']:
            if field in out:
                out[field]={**out[field],'dispatch_fields':{k:v for k,v in out[field].get('dispatch_fields',{}).items() if k!='document_id'}}
    return out

@router.get('/incidents')
def incidents(q:str=Query('',max_length=300),limit:int=Query(50,ge=1,le=200),offset:int=Query(0,ge=0),db:Session=Depends(get_db),user:User=Depends(require_permission('incident.read'))):
    stmt=select(Incident)
    if q:stmt=stmt.where(or_(Incident.title.contains(q),Incident.number.contains(q),Incident.address.contains(q)))
    perms=permission_codes(db,user.user_id)
    return [ops.incident_dict(db,r,perms) for r in db.scalars(stmt.order_by(Incident.created_at.desc(),Incident.incident_id).offset(offset).limit(limit))]

@router.post('/incidents',status_code=201)
def create_incident(payload:IncidentInput,db:Session=Depends(get_db),user:User=Depends(require_permission('incident.create'))):
    ops.need(db,user,'incident.read');return incident_result(db,user,ops.create_incident(db,user,payload))

@router.get('/incidents/{key}')
def incident(key:str,db:Session=Depends(get_db),user:User=Depends(require_permission('incident.read'))):return ops.incident_dict(db,ops.get_row(db,Incident,key),permission_codes(db,user.user_id))

@router.patch('/incidents/{key}')
def patch_incident(key:str,payload:IncidentPatch,db:Session=Depends(get_db),user:User=Depends(require_permission('incident.update'))):
    ops.need(db,user,'incident.read');return incident_result(db,user,ops.patch_incident(db,user,ops.get_row(db,Incident,key,True),payload))

@router.post('/incidents/{key}/cancel')
def cancel_incident(key:str,payload:Action,db:Session=Depends(get_db),user:User=Depends(require_permission('incident.admin'))):
    ops.need(db,user,'incident.read');row=ops.get_row(db,Incident,key,True);ops.source_need(db,user,row)
    if row.status=='cancelled':raise HTTPException(409,'already cancelled')
    if db.scalar(select(Dispatch).where(Dispatch.incident_id==key,Dispatch.status!='cancelled')):raise HTTPException(409,'cancel active dispatches first')
    return incident_result(db,user,ops.change(db,user,row,payload.expected_version,{'status':'cancelled','notes':payload.note},'incident.cancel'))

@router.get('/vehicles')
def vehicles(q:str=Query('',max_length=300),limit:int=Query(50,ge=1,le=200),offset:int=Query(0,ge=0),db:Session=Depends(get_db),user:User=Depends(require_permission('fleet.read'))):
    stmt=select(Vehicle)
    if q:stmt=stmt.where(or_(Vehicle.name.contains(q),Vehicle.code.contains(q),Vehicle.registration.contains(q)))
    return [ops.row_dict(r) for r in db.scalars(stmt.order_by(Vehicle.code).offset(offset).limit(limit))]

@router.get('/fleet-organizations')
def fleet_organizations(q:str=Query('',max_length=300),limit:int=Query(100,ge=1,le=200),offset:int=Query(0,ge=0),db:Session=Depends(get_db),user:User=Depends(require_permission('fleet.read'))):
    return assignments.list_organizations(db,q,limit,offset)

@router.get('/vehicles/{key}/assignments')
def vehicle_assignments(key:str,limit:int=Query(50,ge=1,le=200),offset:int=Query(0,ge=0),db:Session=Depends(get_db),user:User=Depends(require_permission('fleet.read'))):
    return assignments.history(db,key,limit,offset)

@router.post('/vehicles/{key}/assignments',status_code=201)
def change_vehicle_assignment(key:str,payload:VehicleAssignmentInput,db:Session=Depends(get_db),user:User=Depends(require_mutation_permission('fleet.update'))):
    result=assignments.change_assignment(db,user,key,payload)
    ops.save(db)
    return result

@router.post('/vehicles',status_code=201)
def create_vehicle(payload:VehicleInput,db:Session=Depends(get_db),user:User=Depends(require_permission('fleet.create'))):
    ops.need(db,user,'fleet.read');return result(db,user,ops.create_vehicle(db,user,payload))

@router.get('/vehicles/{key}')
def vehicle(key:str,db:Session=Depends(get_db),user:User=Depends(require_permission('fleet.read'))):return ops.row_dict(ops.get_row(db,Vehicle,key))

@router.patch('/vehicles/{key}')
def patch_vehicle(key:str,payload:VehiclePatch,db:Session=Depends(get_db),user:User=Depends(require_permission('fleet.update'))):
    ops.need(db,user,'fleet.read');row=ops.get_row(db,Vehicle,key,True);values=payload.model_dump(exclude={'expected_version'},exclude_unset=True)
    if values.get('name',row.name) is None or values.get('active',row.active) is None:raise HTTPException(422,'name and active must not be null')
    return result(db,user,ops.change(db,user,row,payload.expected_version,values,'fleet.vehicle.update'))

@router.get('/incidents/{key}/dispatches')
def dispatches(key:str,db:Session=Depends(get_db),user:User=Depends(require_permission('incident.read'))):
    parent=ops.get_row(db,Incident,key);ops.source_need(db,user,parent)
    return [dispatch_dict(db,user,r) for r in db.scalars(select(Dispatch).where(Dispatch.incident_id==key).order_by(Dispatch.created_at))]

@router.get('/dispatches/{key}')
def dispatch(key:str,db:Session=Depends(get_db),user:User=Depends(require_permission('incident.read'))):
    row=ops.get_row(db,Dispatch,key);ops.source_need(db,user,ops.get_row(db,Incident,row.incident_id));return dispatch_dict(db,user,row)

@router.post('/incidents/{key}/dispatches',status_code=201)
def create_dispatch(key:str,payload:DispatchInput,db:Session=Depends(get_db),user:User=Depends(require_permission('incident.create'))):
    ops.need(db,user,'incident.read');row=ops.create_dispatch(db,user,key,payload);ops.save(db);return dispatch_dict(db,user,row)

@router.patch('/dispatches/{key}')
def patch_dispatch(key:str,payload:DispatchPatch,db:Session=Depends(get_db),user:User=Depends(require_permission('incident.update'))):
    ops.need(db,user,'incident.read');row=ops.patch_dispatch(db,user,key,payload);ops.save(db);return dispatch_dict(db,user,row)

@router.get('/employees')
def employees(q:str=Query('',max_length=300),db:Session=Depends(get_db),user:User=Depends(require_permission('incident.crew.read'))):
    stmt=select(Employee).where(Employee.active.is_(True))
    if q:stmt=stmt.where(or_(Employee.display_name.contains(q),Employee.employee_code.contains(q)))
    return [{'employee_id':e.employee_id,'display_name':e.display_name,'employee_code':e.employee_code} for e in db.scalars(stmt.order_by(Employee.display_name).limit(200))]

@router.get('/dispatches/{key}/crew')
def crew(key:str,db:Session=Depends(get_db),user:User=Depends(require_permission('incident.crew.read'))):
    ops.need(db,user,'incident.read');ops.dispatch_parent(db,user,key)
    return [ops.row_dict(r) for r in db.scalars(select(DispatchCrew).where(DispatchCrew.dispatch_id==key))]

@router.post('/dispatches/{key}/crew',status_code=201)
def add_crew(key:str,payload:CrewInput,db:Session=Depends(get_db),user:User=Depends(require_permission('incident.crew.manage'))):
    ops.need(db,user,'incident.read','incident.crew.read');return result(db,user,ops.add_crew(db,user,key,payload))

@router.post('/crew/{key}/remove')
def remove_crew(key:str,payload:Action,db:Session=Depends(get_db),user:User=Depends(require_permission('incident.crew.manage'))):
    ops.need(db,user,'incident.read','incident.crew.read');crew=ops.get_row(db,DispatchCrew,key);row,parent=ops.dispatch_parent(db,user,crew.dispatch_id);ops.draft(row)
    ops.change(db,user,row,payload.expected_version,{'candidate_amount':None,'rate_id':None,'calculation':{}},'incident.crew.remove');ops.audit(db,user,'incident.crew.remove',crew,ops.row_dict(crew),{'note':payload.note});db.delete(crew);ops.save(db);return {'removed':key}

@router.get('/allowance-rates')
def rates(db:Session=Depends(get_db),user:User=Depends(require_permission('incident.read'))):return [ops.row_dict(r) for r in db.scalars(select(AllowanceRate).order_by(AllowanceRate.code))]

@router.post('/allowance-rates',status_code=201)
def create_rate(payload:RateInput,db:Session=Depends(get_db),user:User=Depends(require_permission('incident.admin'))):
    ops.need(db,user,'incident.read');row=AllowanceRate(**payload.model_dump());db.add(row);ops.flush(db);ops.audit(db,user,'incident.rate.create',row);return result(db,user,row)

@router.post('/allowance-rates/{key}/approve')
def approve_rate(key:str,payload:Action,db:Session=Depends(get_db),user:User=Depends(require_permission('incident.approve'))):
    ops.need(db,user,'incident.read');row=ops.get_row(db,AllowanceRate,key,True);ops.draft(row)
    return result(db,user,ops.change(db,user,row,payload.expected_version,{'status':'approved','approved_by':user.user_id,'approved_at':now_utc(),'approval_note':payload.note},'incident.rate.approve'))

@router.post('/dispatches/{key}/calculate')
def calculate(key:str,payload:Calculate,db:Session=Depends(get_db),user:User=Depends(require_permission('incident.update'))):
    ops.need(db,user,'incident.read','incident.crew.read');return result(db,user,ops.calculate(db,user,key,payload))

@router.post('/dispatches/{key}/review')
def review_dispatch(key:str,payload:Action,db:Session=Depends(get_db),user:User=Depends(require_permission('incident.review'))):
    ops.need(db,user,'incident.read','incident.crew.read');return result(db,user,ops.review_dispatch(db,user,key,payload))

@router.post('/dispatches/{key}/approve')
def approve_dispatch(key:str,payload:Action,db:Session=Depends(get_db),user:User=Depends(require_permission('incident.approve'))):
    ops.need(db,user,'incident.read','incident.crew.read');return result(db,user,ops.review_dispatch(db,user,key,payload,True))

@router.post('/dispatches/{key}/cancel')
def cancel_dispatch(key:str,payload:Action,db:Session=Depends(get_db),user:User=Depends(require_permission('incident.admin'))):
    ops.need(db,user,'incident.read','incident.crew.read');return result(db,user,ops.cancel_dispatch(db,user,key,payload))

@router.post('/vehicles/{key}/trips',status_code=201)
def create_trip(key:str,payload:TripInput,db:Session=Depends(get_db),user:User=Depends(require_permission('fleet.create'))):
    ops.need(db,user,'fleet.read');return result(db,user,ops.trip(db,user,key,payload))

@router.post('/vehicles/{key}/fuel',status_code=201)
def create_fuel(key:str,payload:FuelInput,db:Session=Depends(get_db),user:User=Depends(require_permission('fleet.create'))):
    ops.need(db,user,'fleet.read');return result(db,user,ops.fuel(db,user,key,payload))

@router.post('/vehicles/{key}/services',status_code=201)
def create_service(key:str,payload:ServiceInput,db:Session=Depends(get_db),user:User=Depends(require_permission('fleet.create'))):
    ops.need(db,user,'fleet.read');return result(db,user,ops.service(db,user,key,payload))

@router.post('/services/{key}/review')
def review_service(key:str,payload:Action,db:Session=Depends(get_db),user:User=Depends(require_permission('fleet.review'))):
    ops.need(db,user,'fleet.read');return result(db,user,ops.review_service(db,user,key,payload))

@router.post('/services/{key}/approve')
def approve_service(key:str,payload:ServiceApprove,db:Session=Depends(get_db),user:User=Depends(require_permission('fleet.approve'))):
    ops.need(db,user,'fleet.read');return result(db,user,ops.review_service(db,user,key,payload,True))

@router.post('/services/{key}/cancel')
def cancel_service(key:str,payload:Action,db:Session=Depends(get_db),user:User=Depends(require_permission('fleet.admin'))):
    ops.need(db,user,'fleet.read');initial=ops.get_row(db,VehicleService,key);v=ops.get_row(db,Vehicle,initial.vehicle_id,True);row=ops.get_row(db,VehicleService,key,True)
    if row.status not in ['draft','reviewed']:raise HTTPException(409,'approved service history is immutable')
    return result(db,user,ops.change(db,user,row,payload.expected_version,{'status':'cancelled','review_note':payload.note},'fleet.service.cancel'))

def history_dict(db,user,row):
    perms=permission_codes(db,user.user_id);item=ops.row_dict(row)
    if isinstance(row,VehicleTrip):
        if 'incident.crew.read' not in perms:item.pop('driver_employee_id')
        if item.get('dispatch_id'):
            dispatch=ops.get_row(db,Dispatch,item['dispatch_id']);incident=ops.get_row(db,Incident,dispatch.incident_id)
            if 'incident.read' not in perms or (ops.source_permission(incident) and ops.source_permission(incident) not in perms):item.pop('dispatch_id')
    if 'document.read' not in perms:item.pop('document_id')
    return item


def history_rows(db,user,key):
    return {name:[history_dict(db,user,row) for row in db.scalars(select(model).where(model.vehicle_id==key).order_by(model.created_at))]
            for name,model in [('trips',VehicleTrip),('fuel',FuelEntry),('services',VehicleService)]}

@router.get('/vehicles/{key}/history')
def history(key:str,db:Session=Depends(get_db),user:User=Depends(require_permission('fleet.read'))):
    ops.get_row(db,Vehicle,key);return history_rows(db,user,key)

@router.get('/statistics')
def statistics(year:int=Query(...,ge=1900,le=9998),month:int|None=Query(None,ge=1,le=12),db:Session=Depends(get_db),user:User=Depends(require_permission('incident.aggregate'))):return ops.statistics(db,user,year,month)

@router.get('/fleet-statistics')
def fleet_statistics(year:int=Query(...,ge=1900,le=9998),month:int|None=Query(None,ge=1,le=12),db:Session=Depends(get_db),user:User=Depends(require_permission('fleet.aggregate'))):
    def matches(d):return d.year==year and (month is None or d.month==month)
    trips=[r for r in db.scalars(select(VehicleTrip)) if matches(r.started_at)]
    fuel=[r for r in db.scalars(select(FuelEntry)) if matches(r.occurred_at)]
    services=[r for r in db.scalars(select(VehicleService)) if matches(r.performed_on) and r.status=='approved']
    from decimal import Decimal
    out={'year':year,'month':month,'trips':len(trips),'distance':str(sum((r.end_odometer-r.start_odometer for r in trips),Decimal('0'))),'fuel_liters_by_kind':{k:str(sum((r.liters for r in fuel if r.kind==k),Decimal('0'))) for k in ['receipt','issue','refuel']},'fuel_purchase_expense':str(sum((r.amount for r in fuel if r.kind in ['receipt','refuel']),Decimal('0'))),'fuel_issue_valuation':str(sum((r.amount for r in fuel if r.kind=='issue'),Decimal('0'))),'approved_service_cost':str(sum((r.cost for r in services),Decimal('0')))}
    if 'fleet.read' in permission_codes(db,user.user_id):out['source_vehicle_ids']=sorted({r.vehicle_id for r in trips+fuel+services})
    return out

@router.get('/alerts')
def alerts(as_of:date|None=None,db:Session=Depends(get_db),user:User=Depends(require_permission('fleet.read'))):return ops.alerts(db,as_of or date.today())

@router.post('/import/{dataset}')
async def import_table(dataset:str,file:UploadFile=File(...),db:Session=Depends(get_db),user:User=Depends(current_user)):
    raw=await file.read(5*1024*1024+1);return ops.import_preview(db,user,dataset,raw,file.filename or '')

@router.post('/import-previews/{key}/confirm')
def confirm_import(key:str,payload:ImportConfirm,db:Session=Depends(get_db),user:User=Depends(current_user)):
    return ops.confirm_import(db,user,key,payload)

@router.get('/import-template/{dataset}')
def import_template(dataset:str,db:Session=Depends(get_db),user:User=Depends(current_user)):
    if dataset not in ops.IMPORT_SCHEMA:raise HTTPException(422,'unknown dataset')
    domain='incident' if dataset in ['incidents','dispatches','crew'] else 'fleet';ops.need(db,user,domain+'.import')
    headers=list(ops.IMPORT_SCHEMA[dataset].model_fields)
    if dataset in ops.IMPORT_PARENT:headers=[ops.IMPORT_PARENT[dataset]]+headers
    content,mime=ops.render_table([], 'csv',headers);return Response(content,media_type=mime,headers={'Content-Disposition':f'attachment; filename="{dataset}-import.csv"','Cache-Control':'no-store'})

@router.get('/export/{dataset}')
def export_table(dataset:str,format:Literal['csv','xlsx']='csv',year:int=Query(2026,ge=1900,le=9998),month:int|None=Query(None,ge=1,le=12),db:Session=Depends(get_db),user:User=Depends(current_user)):
    perms=permission_codes(db,user.user_id)
    if dataset=='summary':
        ops.need(db,user,'incident.aggregate','incident.export');summary=ops.statistics(db,user,year,month);summary.pop('source_incident_ids',None);rows=[summary];domain='incident'
    elif dataset=='fleet-summary':
        ops.need(db,user,'fleet.aggregate','fleet.export');summary=fleet_statistics(year,month,db,user);summary.pop('source_vehicle_ids',None);rows=[summary];domain='fleet'
    elif dataset=='incidents':
        ops.need(db,user,'incident.read','incident.export');rows=[ops.incident_dict(db,r,perms) for r in db.scalars(select(Incident))];domain='incident'
    elif dataset=='dispatches':
        ops.need(db,user,'incident.read','incident.export');rows=[dispatch_dict(db,user,r) for r in db.scalars(select(Dispatch)) if not ops.source_permission(ops.get_row(db,Incident,r.incident_id)) or ops.source_permission(ops.get_row(db,Incident,r.incident_id)) in perms];domain='incident'
    elif dataset=='crew':
        ops.need(db,user,'incident.read','incident.crew.read','incident.export');rows=[];domain='incident'
        for r in db.scalars(select(DispatchCrew)):
            d=ops.get_row(db,Dispatch,r.dispatch_id);i=ops.get_row(db,Incident,d.incident_id)
            if not ops.source_permission(i) or ops.source_permission(i) in perms:rows.append(ops.row_dict(r))
    elif dataset=='vehicles':
        ops.need(db,user,'fleet.read','fleet.export');rows=[ops.row_dict(r) for r in db.scalars(select(Vehicle))];domain='fleet'
    elif dataset in ['trips','fuel','services']:
        ops.need(db,user,'fleet.read','fleet.export');rows=[];domain='fleet'
        for v in db.scalars(select(Vehicle)):rows.extend(history_rows(db,user,v.vehicle_id)[dataset])
    else:raise HTTPException(422,'unknown export dataset')
    content,mime=ops.render_table(rows,format)
    write_audit(db,user_id=user.user_id,action=f'{domain}.export',entity_type=f'operations_{dataset}',after={'format':format,'rows':len(rows),'year':year,'month':month});ops.save(db)
    return Response(content,media_type=mime,headers={'Content-Disposition':f'attachment; filename="operations-{dataset}.{format}"','Cache-Control':'no-store'})
