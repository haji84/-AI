from datetime import date
from typing import Literal
from fastapi import APIRouter,Depends,File,Form,HTTPException,Query,Response,UploadFile
from sqlalchemy import select
from sqlalchemy.orm import Session
from ..authz import permission_codes,require_permission
from ..db import get_db
from ..models import Employee,User
from ..assets_models import OperationalAsset,AssetLocation,AssetLot,AssetBalance,AssetLoan,AssetService,AssetImportPreview
from ..assets_schemas import AssetInput,AssetPatch,LocationInput,LocationPatch,LotInput,MovementInput,ServiceInput,Action,ServiceApprove,ImportConfirm
from .. import assets_service as svc

def no_store(response:Response):response.headers['Cache-Control']='no-store'
router=APIRouter(prefix='/assets',tags=['operational_assets'],dependencies=[Depends(no_store)])
def result(db,user,row):svc.save(db);return svc.visible(db,user,row)


@router.get('/policy')
def policy(db:Session=Depends(get_db),user:User=Depends(require_permission('asset.read'))):return {'schema_version':svc.SCHEMA_VERSION,'business_timezone':str(svc.BUSINESS_TIMEZONE),'business_date':svc.business_today().isoformat()}

@router.get('/registry')
def registry(q:str=Query('',max_length=300),limit:int=Query(50,ge=1,le=200),offset:int=Query(0,ge=0),db:Session=Depends(get_db),user:User=Depends(require_permission('asset.read'))):return [svc.visible(db,user,r) for r in svc.query_rows(db,user,'registry',q,limit=limit,offset=offset)]
@router.post('/registry',status_code=201)
def create_asset(payload:AssetInput,db:Session=Depends(get_db),user:User=Depends(require_permission('asset.create'))):svc.need(db,user,'asset.read');return result(db,user,svc.create_asset(db,user,payload))
@router.get('/registry/{key}')
def detail(key:str,db:Session=Depends(get_db),user:User=Depends(require_permission('asset.read'))):return svc.visible(db,user,svc.get_row(db,OperationalAsset,key))
@router.patch('/registry/{key}')
def patch_asset(key:str,payload:AssetPatch,db:Session=Depends(get_db),user:User=Depends(require_permission('asset.update'))):svc.need(db,user,'asset.read');return result(db,user,svc.patch_asset(db,user,key,payload))
@router.post('/registry/{key}/retire')
def retire(key:str,payload:Action,db:Session=Depends(get_db),user:User=Depends(require_permission('asset.admin'))):svc.need(db,user,'asset.read');return result(db,user,svc.retire_asset(db,user,key,payload))
@router.get('/registry/{key}/history')
def history(key:str,db:Session=Depends(get_db),user:User=Depends(require_permission('asset.read'))):return svc.history(db,user,key)
@router.get('/registry/{key}/lots')
def lots(key:str,q:str=Query('',max_length=300),limit:int=Query(200,ge=1,le=200),offset:int=Query(0,ge=0),db:Session=Depends(get_db),user:User=Depends(require_permission('asset.read'))):return [svc.visible(db,user,r) for r in svc.query_rows(db,user,'lots',q,key,limit,offset)]
@router.post('/registry/{key}/lots',status_code=201)
def create_lot(key:str,payload:LotInput,db:Session=Depends(get_db),user:User=Depends(require_permission('asset.create'))):svc.need(db,user,'asset.read');return result(db,user,svc.create_lot(db,user,key,payload))
@router.get('/locations')
def locations(q:str=Query('',max_length=300),limit:int=Query(200,ge=1,le=200),offset:int=Query(0,ge=0),db:Session=Depends(get_db),user:User=Depends(require_permission('asset.read'))):return [svc.visible(db,user,r) for r in svc.query_rows(db,user,'locations',q,limit=limit,offset=offset)]
@router.post('/locations',status_code=201)
def create_location(payload:LocationInput,db:Session=Depends(get_db),user:User=Depends(require_permission('asset.create'))):svc.need(db,user,'asset.read');return result(db,user,svc.create_location(db,user,payload))
@router.get('/locations/{key}')
def location_detail(key:str,db:Session=Depends(get_db),user:User=Depends(require_permission('asset.read'))):return svc.visible(db,user,svc.get_row(db,AssetLocation,key))
@router.patch('/locations/{key}')
def patch_location(key:str,payload:LocationPatch,db:Session=Depends(get_db),user:User=Depends(require_permission('asset.update'))):svc.need(db,user,'asset.read');return result(db,user,svc.patch_location(db,user,key,payload))
@router.get('/balances')
def balances(asset_id:str|None=None,limit:int=Query(200,ge=1,le=200),offset:int=Query(0,ge=0),db:Session=Depends(get_db),user:User=Depends(require_permission('asset.read'))):return [svc.visible(db,user,r) for r in svc.query_rows(db,user,'balances',asset_id=asset_id,limit=limit,offset=offset)]
@router.post('/movements',status_code=201)
def movement(payload:MovementInput,db:Session=Depends(get_db),user:User=Depends(require_permission('asset.update'))):svc.need(db,user,'asset.read');return result(db,user,svc.move(db,user,payload))
@router.get('/loans')
def loans(asset_id:str|None=None,limit:int=Query(200,ge=1,le=200),offset:int=Query(0,ge=0),db:Session=Depends(get_db),user:User=Depends(require_permission('asset.borrower.read'))):svc.need(db,user,'asset.read');return [svc.visible(db,user,r) for r in svc.query_rows(db,user,'loans',asset_id=asset_id,limit=limit,offset=offset)]
@router.get('/loans/{key}')
def loan(key:str,db:Session=Depends(get_db),user:User=Depends(require_permission('asset.borrower.read'))):svc.need(db,user,'asset.read');return svc.visible(db,user,svc.get_row(db,AssetLoan,key))
@router.get('/employees')
def employees(q:str=Query('',max_length=300),limit:int=Query(200,ge=1,le=200),offset:int=Query(0,ge=0),db:Session=Depends(get_db),user:User=Depends(require_permission('asset.borrower.read'))):
    svc.need(db,user,'asset.read');stmt=select(Employee).where(Employee.active.is_(True))
    if q:stmt=stmt.where(Employee.display_name.contains(q)|Employee.employee_code.contains(q))
    return [{'employee_id':r.employee_id,'employee_code':r.employee_code,'display_name':r.display_name} for r in db.scalars(stmt.order_by(Employee.display_name,Employee.employee_id).offset(offset).limit(limit))]
@router.post('/registry/{key}/services',status_code=201)
def service(key:str,payload:ServiceInput,db:Session=Depends(get_db),user:User=Depends(require_permission('asset.create'))):svc.need(db,user,'asset.read');return result(db,user,svc.create_service(db,user,key,payload))
@router.get('/services/{key}')
def service_detail(key:str,db:Session=Depends(get_db),user:User=Depends(require_permission('asset.read'))):return svc.visible(db,user,svc.get_row(db,AssetService,key))
@router.post('/services/{key}/review')
def review(key:str,payload:Action,db:Session=Depends(get_db),user:User=Depends(require_permission('asset.review'))):svc.need(db,user,'asset.read');return result(db,user,svc.service_action(db,user,key,payload,'review'))
@router.post('/services/{key}/approve')
def approve(key:str,payload:ServiceApprove,db:Session=Depends(get_db),user:User=Depends(require_permission('asset.approve'))):svc.need(db,user,'asset.read');return result(db,user,svc.service_action(db,user,key,payload,'approve'))
@router.post('/services/{key}/cancel')
def cancel(key:str,payload:Action,db:Session=Depends(get_db),user:User=Depends(require_permission('asset.admin'))):svc.need(db,user,'asset.read');return result(db,user,svc.service_action(db,user,key,payload,'cancel'))
@router.get('/alerts')
def alerts(as_of:date|None=None,days:int=Query(30,ge=0,le=365),db:Session=Depends(get_db),user:User=Depends(require_permission('asset.read'))):return svc.alerts(db,user,as_of or svc.business_today(),days)
@router.get('/reorder')
def reorder(db:Session=Depends(get_db),user:User=Depends(require_permission('asset.read'))):return svc.reorder(db)
@router.get('/import-template/{dataset}')
def template(dataset:str,format:Literal['csv','xlsx']='csv',db:Session=Depends(get_db),user:User=Depends(require_permission('asset.import'))):
    svc.need(db,user,'asset.read');columns=svc.headers(dataset);blob,mime=svc.tabular(columns,[],format)
    return Response(blob,media_type=mime,headers={'Content-Disposition':f'attachment; filename="assets-{dataset}-template.{format}"','Cache-Control':'no-store'})
@router.post('/import/{dataset}')
async def preview(dataset:str,file:UploadFile=File(...),document_id:str|None=Form(None),db:Session=Depends(get_db),user:User=Depends(require_permission('asset.import'))):
    row=svc.import_preview(db,user,dataset,await file.read(2*1024*1024+1),file.filename or 'uploaded',document_id);svc.save(db)
    return {'preview_id':row.preview_id,'version':row.version,'schema_version':row.schema_version,'status':row.status,'rows':len(row.row_data),'sample':row.row_data[:10],'file_sha256':row.file_sha256,'document_id':row.document_id,'expires_at':svc.scalar(row.expires_at)}
@router.post('/import-previews/{key}/confirm')
def confirm(key:str,payload:ImportConfirm,db:Session=Depends(get_db),user:User=Depends(require_permission('asset.import'))):out=svc.confirm_import(db,user,key,payload);svc.save(db);return out
@router.get('/export/{dataset}')
def export(dataset:str,format:Literal['csv','xlsx']='csv',q:str=Query('',max_length=300),asset_id:str|None=None,db:Session=Depends(get_db),user:User=Depends(require_permission('asset.export'))):
    svc.need(db,user,'asset.read');blob,mime=svc.export_data(db,user,dataset,q,asset_id,format)
    return Response(blob,media_type=mime,headers={'Content-Disposition':f'attachment; filename="assets-{dataset}.{format}"','Cache-Control':'no-store'})
