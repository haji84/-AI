from datetime import date
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy.orm import Session

from .. import hazardous_service as svc
from ..authz import require_mutation_permission, require_permission
from ..db import get_db
from ..hazardous_schemas import (InstallationInput, InstallationPatch, InstallationRetire,
                                 RecordAction, RecordInput, RecordPatch, RecordRevision)
from ..models import User


def no_store(response: Response):
    response.headers['Cache-Control'] = 'no-store'


router = APIRouter(prefix='/hazardous', tags=['hazardous'], dependencies=[Depends(no_store)])


@router.get('/installations')
def list_installations(q: str = Query('', max_length=300), building_id: UUID | None = None, status: str | None = None,
                       limit: int = Query(100, ge=1, le=1000), offset: int = Query(0, ge=0),
                       db: Session = Depends(get_db), user: User = Depends(require_permission('hazardous.read'))):
    return svc.list_installations(db, user, q, str(building_id) if building_id else None, status, limit, offset)


@router.get('/sources/{kind}')
def sources(kind: str, building_id: UUID | None = None, q: str = Query('', max_length=300),
            limit: int = Query(100, ge=1, le=200), offset: int = Query(0, ge=0),
            db: Session = Depends(get_db), user: User = Depends(require_permission('hazardous.read'))):
    return svc.source_choices(db, user, kind, str(building_id) if building_id else None, q, limit, offset)


@router.get('/deadlines')
def deadlines(due_before: date | None = None, limit: int = Query(100, ge=1, le=1000), offset: int = Query(0, ge=0),
              db: Session = Depends(get_db), user: User = Depends(require_permission('hazardous.read'))):
    return svc.deadlines(db, user, due_before, limit, offset)


def installation_result(db, row):
    result = svc.installation_dict(db, row)
    db.commit()
    return result


def record_result(db, user, result):
    parent, row = result
    data = svc.record_dict(db, user, parent, row)
    db.commit()
    return data


@router.post('/installations', status_code=201)
def create_installation(payload: InstallationInput, db: Session = Depends(get_db),
                        user: User = Depends(require_mutation_permission('hazardous.create'))):
    return installation_result(db, svc.create_installation(db, user, payload))


@router.get('/installations/{identity}')
def detail(identity: str, db: Session = Depends(get_db), user: User = Depends(require_permission('hazardous.read'))):
    return svc.detail(db, user, identity)


@router.patch('/installations/{identity}')
def patch_installation(identity: str, payload: InstallationPatch, db: Session = Depends(get_db),
                       user: User = Depends(require_mutation_permission('hazardous.update'))):
    return installation_result(db, svc.patch_installation(db, user, identity, payload))


@router.post('/installations/{identity}/retire')
def retire(identity: str, payload: InstallationRetire, db: Session = Depends(get_db),
           user: User = Depends(require_mutation_permission('hazardous.update'))):
    return installation_result(db, svc.patch_installation(db, user, identity, payload, retire=True))


@router.post('/installations/{identity}/records', status_code=201)
def create_record(identity: str, payload: RecordInput, db: Session = Depends(get_db),
                  user: User = Depends(require_mutation_permission('hazardous.create'))):
    return record_result(db, user, svc.create_record(db, user, identity, payload))


@router.patch('/installations/{identity}/records/{record_id}')
def patch_record(identity: str, record_id: str, payload: RecordPatch, db: Session = Depends(get_db),
                 user: User = Depends(require_mutation_permission('hazardous.update'))):
    return record_result(db, user, svc.patch_record(db, user, identity, record_id, payload))


@router.post('/installations/{identity}/records/{record_id}/confirm')
def confirm(identity: str, record_id: str, payload: RecordAction, db: Session = Depends(get_db),
            user: User = Depends(require_mutation_permission('hazardous.review'))):
    return record_result(db, user, svc.record_action(db, user, identity, record_id, payload, 'confirm'))


@router.post('/installations/{identity}/records/{record_id}/cancel')
def cancel(identity: str, record_id: str, payload: RecordAction, db: Session = Depends(get_db),
           user: User = Depends(require_mutation_permission('hazardous.update'))):
    return record_result(db, user, svc.record_action(db, user, identity, record_id, payload, 'cancel'))


@router.post('/installations/{identity}/records/{record_id}/revisions', status_code=201)
def revise(identity: str, record_id: str, payload: RecordRevision, db: Session = Depends(get_db),
           user: User = Depends(require_mutation_permission('hazardous.update'))):
    return record_result(db, user, svc.record_action(db, user, identity, record_id, payload, 'revisions'))
