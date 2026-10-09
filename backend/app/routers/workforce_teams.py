from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.routing import APIRoute
from fastapi.exceptions import RequestValidationError
from fastapi.exception_handlers import request_validation_exception_handler
from sqlalchemy import select
from sqlalchemy.orm import Session
from ..authz import require_permission, require_mutation_permission
from ..db import get_db
from ..models import User
from ..workforce_models import WorkforceTeam, WorkforceTeamMembership, WorkforceTeamChange
from ..workforce_team_schemas import TeamCreate, TeamPatch, MembershipCreate, MembershipPatch
from .. import workforce_teams as service
from .. import workforce_service as common


class PrivateTeamRoute(APIRoute):
    def get_route_handler(self):
        original=super().get_route_handler()
        async def handler(request):
            try:response=await original(request)
            except RequestValidationError as error:
                response=await request_validation_exception_handler(request,error)
            except HTTPException as error:
                error.headers={**(error.headers or {}),'Cache-Control':'no-store'};raise
            response.headers['Cache-Control']='no-store';return response
        return handler


router=APIRouter(prefix='/teams',tags=['workforce teams'],route_class=PrivateTeamRoute)


@router.get('')
def teams(offset:int=Query(0,ge=0),limit:int=Query(100,ge=1,le=1000),db:Session=Depends(get_db),user:User=Depends(require_permission('workforce.read'))):
    service.authority(db,user)
    rows=db.scalars(select(WorkforceTeam).order_by(WorkforceTeam.code,WorkforceTeam.team_id).offset(offset).limit(limit)).all()
    data={'items':[common.row_dict(team) for team in rows],'offset':offset,'limit':limit,'formal_crew_assignment':False}
    db.expire_all();service.authority(db,user)
    if any(service.row(db,WorkforceTeam,item['team_id']).version!=item['version'] for item in data['items']):raise HTTPException(409,'Team changed; reload')
    return data


@router.post('',status_code=201)
def create(payload:TeamCreate,db:Session=Depends(get_db),user:User=Depends(require_mutation_permission('workforce.admin'))):
    team=service.create(db,user,payload);data=common.row_dict(team);service.authority(db,user,True);common.save(db);return data


@router.patch('/{key}')
def patch(key:str,payload:TeamPatch,db:Session=Depends(get_db),user:User=Depends(require_mutation_permission('workforce.admin'))):
    team=service.patch(db,user,key,payload);data=common.row_dict(team);service.authority(db,user,True);common.save(db);return data


@router.get('/{key}/members')
def members(key:str,offset:int=Query(0,ge=0),limit:int=Query(100,ge=1,le=1000),db:Session=Depends(get_db),user:User=Depends(require_permission('workforce.read'))):
    service.authority(db,user);team=service.row(db,WorkforceTeam,key)
    rows=db.scalars(select(WorkforceTeamMembership).where(WorkforceTeamMembership.team_id==team.team_id)
        .order_by(WorkforceTeamMembership.valid_from,WorkforceTeamMembership.membership_id).offset(offset).limit(limit)).all()
    data={'team':common.row_dict(team),'items':[service.membership_payload(db,team,member) for member in rows],
          'offset':offset,'limit':limit,'formal_crew_assignment':False}
    db.expire_all();service.authority(db,user);fresh_team=service.row(db,WorkforceTeam,key)
    if fresh_team.version!=data['team']['version']:raise HTTPException(409,'Team changed; reload')
    for item in data['items']:
        fresh=service.row(db,WorkforceTeamMembership,item['membership_id'])
        if service.membership_payload(db,fresh_team,fresh)!=item:raise HTTPException(409,'Team membership source changed; reload')
    return data


@router.post('/{key}/members',status_code=201)
def add_member(key:str,payload:MembershipCreate,db:Session=Depends(get_db),user:User=Depends(require_mutation_permission('workforce.admin'))):
    team,member=service.add_member(db,user,key,payload)
    data={'team_version':team.version,'membership':service.membership_payload(db,team,member),'formal_crew_assignment':False}
    service.authority(db,user,True)
    common.save(db);return data


@router.get('/{key}/history')
def history(key:str,offset:int=Query(0,ge=0),limit:int=Query(100,ge=1,le=1000),db:Session=Depends(get_db),user:User=Depends(require_permission('workforce.read'))):
    service.authority(db,user);team=service.row(db,WorkforceTeam,key)
    rows=db.scalars(select(WorkforceTeamChange).where(WorkforceTeamChange.team_id==team.team_id)
        .order_by(WorkforceTeamChange.created_at,WorkforceTeamChange.change_id).offset(offset).limit(limit)).all()
    data={'team_id':team.team_id,'items':[common.row_dict(change) for change in rows],'offset':offset,'limit':limit}
    db.expire_all();service.authority(db,user)
    return data


@router.patch('/{key}/members/{member_key}')
def patch_member(key:str,member_key:str,payload:MembershipPatch,db:Session=Depends(get_db),user:User=Depends(require_mutation_permission('workforce.admin'))):
    team,member=service.patch_member(db,user,key,member_key,payload)
    data={'team_version':team.version,'membership':service.membership_payload(db,team,member),'formal_crew_assignment':False}
    service.authority(db,user,True)
    common.save(db);return data
