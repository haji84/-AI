"""Personnel source intake never bypasses the administration Human gates."""
from uuid import UUID
from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy import select
from sqlalchemy.orm import Session
from ..db import get_db
from ..authz import require_permission
from ..personnel_intake_models import PersonnelDocumentProposal
from ..personnel_intake_schemas import NoticeCreate, NoticePatch, NoticeDecision
from .. import personnel_intake_service as svc

router = APIRouter(prefix='/personnel-intake', tags=['personnel intake'])


@router.get('/proposals')
def list_proposals(response: Response, limit: int = Query(100, ge=1, le=200), offset: int = Query(0, ge=0),
    db: Session = Depends(get_db), actor=Depends(require_permission('personnel.read'))):
    svc.need(db, actor, 'document.read'); response.headers['Cache-Control'] = 'no-store'
    rows = db.scalars(select(PersonnelDocumentProposal).order_by(PersonnelDocumentProposal.created_at.desc(),
        PersonnelDocumentProposal.proposal_id).limit(limit).offset(offset)).all()
    # All notices share this explicit personnel/document boundary; individual
    # original authorization is still rechecked for each returned source.
    return [svc.output(svc.get(db, actor, row.proposal_id)) for row in rows]


@router.post('/proposals', status_code=201)
def create_proposal(payload: NoticeCreate, response: Response, db: Session = Depends(get_db),
    actor=Depends(require_permission('personnel.manage'))):
    response.headers['Cache-Control'] = 'no-store'
    return svc.create(db, actor, payload.document_id)


@router.get('/proposals/{key}')
def get_proposal(key: UUID, response: Response, db: Session = Depends(get_db), actor=Depends(require_permission('personnel.read'))):
    response.headers['Cache-Control'] = 'no-store'
    return svc.output(svc.get(db, actor, key))


@router.patch('/proposals/{key}')
def revise_proposal(key: UUID, payload: NoticePatch, db: Session = Depends(get_db), actor=Depends(require_permission('personnel.manage'))):
    return svc.patch(db, actor, key, payload)


@router.post('/proposals/{key}/review')
def review_proposal(key: UUID, payload: NoticeDecision, db: Session = Depends(get_db), actor=Depends(require_permission('personnel.manage'))):
    return svc.decision(db, actor, key, payload, 'review')


@router.post('/proposals/{key}/apply')
def apply_proposal(key: UUID, payload: NoticeDecision, db: Session = Depends(get_db), actor=Depends(require_permission('personnel.manage'))):
    return svc.decision(db, actor, key, payload, 'apply')


@router.post('/proposals/{key}/reject')
def reject_proposal(key: UUID, payload: NoticeDecision, db: Session = Depends(get_db), actor=Depends(require_permission('personnel.manage'))):
    return svc.decision(db, actor, key, payload, 'reject')
