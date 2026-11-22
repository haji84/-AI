"""No general Document, external model, or training worker access is added here."""
from uuid import UUID

from fastapi import APIRouter, Depends, Response
from sqlalchemy.orm import Session

from .. import emergency_training_service as svc
from ..authz import require_mutation_permission
from ..db import get_db
from ..emergency_audit_service import require_details
from ..emergency_training_schemas import RegisterDataset, RegisterFamily, RegisterTruth
from ..models import User
from .emergency_audit import PrivateAuditRoute, config_access, read_access

router = APIRouter(prefix='/emergency/audit', tags=['emergency-training'], route_class=PrivateAuditRoute)


def truth_access(db: Session = Depends(get_db),
                 user: User = Depends(require_mutation_permission('emergency.report.review'))):
    require_details(db, user)
    return user


@router.post('/training/families', status_code=201)
def register_family(payload: RegisterFamily, response: Response,
                    db: Session = Depends(get_db), user: User = Depends(config_access)):
    result, created = svc.register_family(db, user, payload)
    if not created:
        response.status_code = 200
    return result


@router.get('/training/families/{identity}')
def get_family(identity: UUID, db: Session = Depends(get_db), user: User = Depends(read_access)):
    return svc.family_output(db, user, str(identity))


@router.post('/revisions/{identity}/training-truth', status_code=201)
def register_truth(identity: UUID, payload: RegisterTruth, response: Response,
                   db: Session = Depends(get_db), user: User = Depends(truth_access)):
    row, created = svc.register_truth(db, user, str(identity), payload)
    if not created:
        response.status_code = 200
    return svc.truth_output(db, user, row)


@router.get('/training/truths/{identity}')
def get_truth(identity: UUID, db: Session = Depends(get_db), user: User = Depends(read_access)):
    return svc.truth_output(db, user, svc.truth_record(db, user, str(identity)))


@router.post('/training/datasets', status_code=201)
def register_dataset(payload: RegisterDataset, response: Response,
                     db: Session = Depends(get_db), user: User = Depends(config_access)):
    row, created = svc.register_dataset(db, user, payload)
    if not created:
        response.status_code = 200
    return svc.dataset_output(db, user, row)


@router.get('/training/datasets/{identity}')
def get_dataset(identity: UUID, db: Session = Depends(get_db), user: User = Depends(read_access)):
    return svc.dataset_output(db, user, svc.dataset_record(db, str(identity)))
