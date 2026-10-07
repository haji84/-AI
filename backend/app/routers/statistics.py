"""Observed statistics never accept client evidence, source values or tenant selectors."""
from typing import Literal
from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy import select
from sqlalchemy.orm import Session
from ..authz import current_user, permission_codes
from ..db import get_db
from ..models import User
from ..settings import settings
from ..statistics_schemas import StatisticsQuery, ConfirmStatistics, ReplaceStatistics, MetricKey
from ..statistics_sources import DEFINITIONS, QUERY_VERSION, required_permissions
from ..statistics_models import StatisticsReport, StatisticsEvidence, StatisticsHistory
from .. import statistics_service as service
from .. import statistics_reports as reports
from .. import statistics_exports as exports
from ..statistics_drilldown import drilldown

router = APIRouter(prefix='/statistics', tags=['observed statistics'])


def no_store(response):
    response.headers['Cache-Control'] = 'no-store'


@router.get('/metrics')
def metrics(response:Response, db:Session=Depends(get_db), user:User=Depends(current_user)):
    no_store(response)
    identity=service.preflight(db,user,{'statistics.read'})
    with service.final_session(identity,{'statistics.read'}) as final:
        permissions=permission_codes(final,identity.user_id)
        return {'query_version':QUERY_VERSION,'business_timezone':settings.statistics_business_timezone,'coverage_status':'unknown',
                'metrics':[{**definition,'available':required_permissions([key]).issubset(permissions)} for key,definition in DEFINITIONS.items()]}


@router.post('/query')
def query(payload:StatisticsQuery,response:Response,db:Session=Depends(get_db),user:User=Depends(current_user)):
    no_store(response)
    return service.query_statistics(db,user,payload)


@router.post('/reports',status_code=201)
def save_report(payload:StatisticsQuery,response:Response,db:Session=Depends(get_db),user:User=Depends(current_user)):
    no_store(response)
    return reports.create_report(db,user,payload)


@router.get('/reports')
def list_reports(response:Response,limit:int=Query(50,ge=1,le=200),offset:int=Query(0,ge=0),db:Session=Depends(get_db),user:User=Depends(current_user)):
    no_store(response)
    identity=service.preflight(db,user,{'statistics.read'})
    with service.final_session(identity,{'statistics.read'}) as final:
        permissions=permission_codes(final,identity.user_id)
        # A mixed report is either wholly visible or absent, before counting/pagination.
        rows=[row for row in final.scalars(select(StatisticsReport).order_by(StatisticsReport.created_at,StatisticsReport.report_id)) if reports.report_codes(row).issubset(permissions)]
        data={'items':[reports.public_report(row) for row in rows[offset:offset+limit]],'total':len(rows),'limit':limit,'offset':offset}
        service.audit_statistics(final,identity,'list');final.commit()
        return data


@router.get('/reports/{key}')
def report(key:str,response:Response,db:Session=Depends(get_db),user:User=Depends(current_user)):
    no_store(response)
    identity=service.preflight(db,user,{'statistics.read'})
    with service.final_session(identity,{'statistics.read'}) as final:
        row=reports.get_report(final,key)
        service.authorize(final,identity,reports.report_codes(row))
        data=reports.public_report(row)
        service.audit_statistics(final,identity,'read',report_id=row.report_id,version=row.version,metric_keys=row.metric_keys);final.commit()
        return data


@router.get('/reports/{key}/history')
def history(key:str,response:Response,limit:int=Query(50,ge=1,le=200),offset:int=Query(0,ge=0),db:Session=Depends(get_db),user:User=Depends(current_user)):
    no_store(response)
    identity=service.preflight(db,user,{'statistics.read'})
    with service.final_session(identity,{'statistics.read'}) as final:
        row=reports.get_report(final,key);service.authorize(final,identity,reports.report_codes(row))
        rows=list(final.scalars(select(StatisticsHistory).where(StatisticsHistory.report_id==row.report_id).order_by(StatisticsHistory.version)))
        result={'items':[{'action':item.action,'version':item.version,'occurred_at':reports.public_lifecycle_time(item.occurred_at)} for item in rows[offset:offset+limit]],'total':len(rows),'limit':limit,'offset':offset}
        service.audit_statistics(final,identity,'history',report_id=row.report_id,version=row.version,metric_keys=row.metric_keys);final.commit()
        return result


@router.post('/reports/{key}/confirm')
def confirm(key:str,payload:ConfirmStatistics,response:Response,db:Session=Depends(get_db),user:User=Depends(current_user)):
    no_store(response)
    return reports.transition(db,user,key,payload)


@router.post('/reports/{key}/replacements',status_code=201)
def replace(key:str,payload:ReplaceStatistics,response:Response,db:Session=Depends(get_db),user:User=Depends(current_user)):
    no_store(response)
    return reports.transition(db,user,key,payload,replacement=True)


@router.get('/reports/{key}/export')
def export(key:str,format:Literal['csv','xlsx']='csv',db:Session=Depends(get_db),user:User=Depends(current_user)):
    identity=service.preflight(db,user,{'statistics.read','statistics.export'})
    with service.final_session(identity,{'statistics.read','statistics.export'}) as final:
        row=reports.get_report(final,key);codes=reports.report_codes(row,'statistics.export',export=True)
        service.authorize(final,identity,codes)
        prepared=reports.public_report(row)
    content,mime=exports.render_export(prepared,format)
    # Byte generation can take time. Rights and originating session are checked again afterward.
    with service.final_session(identity,codes) as final:
        current=reports.get_report(final,key)
        if current.version!=prepared['version']:
            raise HTTPException(409,'Statistics lifecycle changed during export; retry')
        service.audit_statistics(final,identity,'export',report_id=current.report_id,version=current.version,metric_keys=current.metric_keys,format=format);final.commit()
    return Response(content,media_type=mime,headers={'Cache-Control':'no-store','Content-Disposition':f'attachment; filename="statistics-{key}.{format}"'})


@router.get('/reports/{key}/drilldown')
def source_pointers(key:str,metric_key:MetricKey,response:Response,limit:int=Query(50,ge=1,le=200),offset:int=Query(0,ge=0),db:Session=Depends(get_db),user:User=Depends(current_user)):
    no_store(response)
    identity=service.preflight(db,user,{'statistics.read'})
    with service.final_session(identity,{'statistics.read'}) as final:
        row=reports.get_report(final,key);service.authorize(final,identity,reports.report_codes(row))
        data=drilldown(final,row,final.get(StatisticsEvidence,row.report_id),metric_key,permission_codes(final,identity.user_id),limit,offset)
        service.audit_statistics(final,identity,'drilldown',report_id=row.report_id,version=row.version,metric_keys=[metric_key]);final.commit()
        return data
