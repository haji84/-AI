from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from .. import hazardous_evaluation_service as service
from ..authz import require_mutation_permission, require_permission
from ..db import get_db
from ..hazardous_evaluation_schemas import EvaluationInput, EvaluationReview
from ..models import User
from .hazardous import no_store

router = APIRouter(prefix='/hazardous', tags=['hazardous-evaluations'], dependencies=[Depends(no_store)])


@router.post('/installations/{identity}/evaluations', status_code=201)
def create(identity: str, payload: EvaluationInput, db: Session = Depends(get_db),
    user: User = Depends(require_mutation_permission('hazardous.create'))):
    row = service.create(db, user, identity, payload)
    result = service.output(db, user, row)
    db.commit()
    return result


@router.get('/installations/{identity}/evaluations')
def listing(identity: str, limit: int = Query(100, ge=1, le=200), offset: int = Query(0, ge=0),
    db: Session = Depends(get_db), user: User = Depends(require_permission('hazardous.read'))):
    return service.listing(db, user, identity, limit, offset)


@router.get('/evaluations/{identity}')
def detail(identity: str, db: Session = Depends(get_db),
    user: User = Depends(require_permission('hazardous.read'))):
    return service.detail(db, user, identity)


@router.post('/evaluations/{identity}/review')
def review(identity: str, payload: EvaluationReview, db: Session = Depends(get_db),
    user: User = Depends(require_mutation_permission('hazardous.review'))):
    row = service.review(db, user, identity, payload)
    result = service.output(db, user, row)
    db.commit()
    return result
