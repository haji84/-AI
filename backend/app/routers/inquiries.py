from typing import Literal
from fastapi import APIRouter,Depends,Query,File,UploadFile,Response,HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session
from ..db import get_db
from ..authz import require_permission,require_mutation_permission
from ..models import User,FormTemplate
from ..inquiries_models import Inquiry,InquiryCandidate
from ..inquiries_schemas import InquiryInput,InquiryPatch,EvidenceInput,Action,CandidateAction,RenderInput
from .. import inquiries_service as svc
def no_store(response:Response):response.headers['Cache-Control']='no-store'
router=APIRouter(prefix='/inquiries',tags=['inquiries'],dependencies=[Depends(no_store)])
def result(db,user,row):svc.save(db);return svc.visible(db,user,row)
@router.get('')
def listing(q:str=Query('',max_length=300),year:int|None=Query(None,ge=1900,le=2200),limit:int=Query(100,ge=1,le=200),offset:int=Query(0,ge=0),db:Session=Depends(get_db),user:User=Depends(require_permission('inquiry.read'))):
 return [svc.visible(db,user,r) for r in svc.list_rows(db,user,q,year)[offset:offset+limit]]
@router.post('',status_code=201)
def create(payload:InquiryInput,db:Session=Depends(get_db),user:User=Depends(require_mutation_permission('inquiry.create'))):return result(db,user,svc.create(db,user,payload))
@router.get('/similar')
def similar(q:str=Query(...,min_length=1,max_length=300),year:int|None=Query(None,ge=1900,le=2200),limit:int=Query(20,ge=1,le=100),db:Session=Depends(get_db),user:User=Depends(require_permission('inquiry.read'))):
 scored=[(svc.lexical_score(q,title=r.question,body=r.draft),r) for r in svc.list_rows(db,user,year=year)];scored.sort(key=lambda v:(-v[0],v[1].inquiry_id))
 return {'method':'deterministic lexical similarity; no semantic accuracy claim','items':[{'score':score,**svc.visible(db,user,r)} for score,r in scored if score>0][:limit]}
@router.get('/sources')
def sources(source_type:str,q:str=Query('',max_length=300),limit:int=Query(50,ge=1,le=100),db:Session=Depends(get_db),user:User=Depends(require_permission('inquiry.read'))):
 if source_type not in svc.SOURCES:raise HTTPException(422,'unknown typed source')
 model,permission,fields=svc.SOURCES[source_type];svc.need(db,user,permission);rows=[]
 pk=list(model.__table__.primary_key.columns)[0]
 for row in db.scalars(select(model).order_by(pk)):
  try:snapshot=svc.source(db,user,source_type,getattr(row,pk.name))
  except HTTPException as exc:
   if exc.status_code in (403,404,409,422):continue
   raise
  if not q or svc.normalized(q).lower() in svc.normalized(snapshot['text']).lower():rows.append(snapshot)
  if len(rows)>=limit:break
 return rows
@router.get('/source/{source_type}/{key}')
def source_detail(source_type:str,key:str,db:Session=Depends(get_db),user:User=Depends(require_permission('inquiry.read'))):return svc.source(db,user,source_type,key)
@router.get('/export')
def export(format:Literal['csv','xlsx']='csv',year:int|None=Query(None,ge=1900,le=2200),db:Session=Depends(get_db),user:User=Depends(require_permission('inquiry.export'))):
 rows=svc.export_rows(db,user,year);raw,mime=svc.tabular(svc.HEADERS,rows,format);svc.write_audit(db,user_id=user.user_id,action='inquiry.export',entity_type='inquiries',after={'schema_version':svc.SCHEMA_VERSION,'format':format,'year':year,'authorized_rows':len(rows),'file_sha256':svc.sha256(raw).hexdigest()});svc.save(db);return Response(raw,media_type=mime,headers={'Content-Disposition':f'attachment; filename="inquiries.{format}"','Cache-Control':'no-store'})
@router.get('/import-template')
def import_template(format:Literal['csv','xlsx']='csv',db:Session=Depends(get_db),user:User=Depends(require_permission('inquiry.import'))):
 svc.need(db,user,'inquiry.read');raw,mime=svc.tabular(svc.HEADERS,[],format);return Response(raw,media_type=mime,headers={'Content-Disposition':f'attachment; filename="inquiries-template.{format}"','Cache-Control':'no-store'})
@router.post('/import',status_code=201)
def import_file(file:UploadFile=File(...),db:Session=Depends(get_db),user:User=Depends(require_permission('inquiry.import'))):
 value=svc.import_file(db,user,file);svc.save(db);return value
@router.get('/templates')
def templates(db:Session=Depends(get_db),user:User=Depends(require_permission('inquiry.read'))):
 svc.need(db,user,'template.read','document.read');return [svc.row_dict(t) for t in db.scalars(select(FormTemplate).where(FormTemplate.module_code=='inquiries',FormTemplate.status=='active'))]
@router.get('/{key}')
def detail(key:str,db:Session=Depends(get_db),user:User=Depends(require_permission('inquiry.read'))):return svc.visible(db,user,svc.get_inquiry(db,user,key))
@router.patch('/{key}')
def patch(key:str,payload:InquiryPatch,db:Session=Depends(get_db),user:User=Depends(require_mutation_permission('inquiry.update'))):return result(db,user,svc.patch(db,user,key,payload))
@router.delete('/{key}')
def delete(key:str,payload:Action,db:Session=Depends(get_db),user:User=Depends(require_mutation_permission('inquiry.admin'))):
 row=svc.get_inquiry(db,user,key,True);svc.check_version(row,payload.expected_version);svc.mutable(row);svc.bump(db,row,row.version,{'deleted':True});svc.audit(db,user,'delete',row,{'reason':payload.reason});svc.save(db);return {'deleted':True,'version':row.version}
@router.post('/{key}/evidence',status_code=201)
def evidence(key:str,payload:EvidenceInput,db:Session=Depends(get_db),user:User=Depends(require_mutation_permission('inquiry.update'))):
 row=svc.add_evidence(db,user,key,payload);svc.save(db);return svc.row_dict(row)
@router.delete('/{key}/evidence/{evidence_id}')
def delete_evidence(key:str,evidence_id:str,payload:Action,db:Session=Depends(get_db),user:User=Depends(require_mutation_permission('inquiry.update'))):
 svc.remove_evidence(db,user,key,evidence_id,payload);svc.save(db);return {'removed':True}
@router.post('/{key}/review')
def review(key:str,payload:Action,db:Session=Depends(get_db),user:User=Depends(require_mutation_permission('inquiry.review'))):return result(db,user,svc.action(db,user,key,payload,'review'))
@router.post('/{key}/approve')
def approve(key:str,payload:Action,db:Session=Depends(get_db),user:User=Depends(require_mutation_permission('inquiry.approve'))):return result(db,user,svc.action(db,user,key,payload,'approve'))
@router.post('/{key}/revisions',status_code=201)
def revision(key:str,payload:Action,db:Session=Depends(get_db),user:User=Depends(require_mutation_permission('inquiry.create'))):return result(db,user,svc.revision(db,user,key,payload))
@router.post('/{key}/ai-draft',status_code=201)
def generate(key:str,payload:Action,db:Session=Depends(get_db),user:User=Depends(require_permission('inquiry.create'))):
 row=svc.generate(db,user,key,payload);svc.save(db);return svc.row_dict(row)
@router.get('/{key}/candidates')
def candidates(key:str,db:Session=Depends(get_db),user:User=Depends(require_permission('inquiry.read'))):
 svc.get_inquiry(db,user,key);return [svc.row_dict(r) for r in db.scalars(select(InquiryCandidate).where(InquiryCandidate.inquiry_id==key).order_by(InquiryCandidate.generated_at.desc()))]
@router.post('/{key}/adopt-candidate')
def adopt(key:str,payload:CandidateAction,db:Session=Depends(get_db),user:User=Depends(require_mutation_permission('inquiry.update'))):return result(db,user,svc.adopt(db,user,key,payload))
@router.post('/{key}/render',status_code=201)
def render(key:str,payload:RenderInput,db:Session=Depends(get_db),user:User=Depends(require_mutation_permission('inquiry.export'))):
 row=svc.render(db,user,key,payload);svc.save(db);return svc.row_dict(row)
