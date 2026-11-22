"""Protected measurement APIs. Validation failures never echo submitted data."""
from collections import Counter
from dataclasses import asdict
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.routing import APIRoute
from sqlalchemy import select
from sqlalchemy.orm import Session
from starlette.exceptions import HTTPException as StarletteHTTPException

from .. import emergency_acceptance_service as service
from ..audit import write_audit
from ..authz import require_mutation_permission, require_permission
from ..db import get_db
from ..emergency_acceptance import evaluate_acceptance
from ..emergency_acceptance_api_schemas import CandidateCheck, ReviewEvaluation, SaveEvaluation
from ..emergency_acceptance_models import EmergencyAcceptanceEvaluation
from ..emergency_acceptance_schemas import EvaluationInput
from ..emergency_review_core import Observation, evaluate_confirmed_fields
from ..models import User
from ..settings import settings


MAX_BODY_BYTES = 2 * 1024 * 1024
PRIVATE_HEADERS = {'Cache-Control': 'no-store', 'Pragma': 'no-cache', 'X-Content-Type-Options': 'nosniff'}


class PrivateEvaluationRoute(APIRoute):
    def get_route_handler(self):
        original = super().get_route_handler()

        async def protected(request: Request):
            try:
                if request.method in {'POST', 'PUT', 'PATCH'}:
                    if request.headers.get('content-type', '').split(';')[0].strip().lower() != 'application/json':
                        raise HTTPException(415, '測定記録は所定の形式で送信してください。')
                    chunks, size = [], 0
                    async for chunk in request.stream():
                        size += len(chunk)
                        if size > MAX_BODY_BYTES:
                            raise HTTPException(413, '測定記録の容量が上限を超えています。')
                        chunks.append(chunk)
                    # Cache the bounded stream for FastAPI's normal JSON and schema parsing.
                    request._body = b''.join(chunks)
                response = await original(request)
            except RequestValidationError:
                response = JSONResponse(status_code=422, content={'detail': '入力形式を確認してください。未定義の項目や不正な値は保存しません。'})
            except StarletteHTTPException as error:
                detail = '測定記録の形式を確認してください。' if error.status_code == 400 else error.detail
                response = JSONResponse(status_code=error.status_code, content={'detail': detail}, headers=error.headers)
            except (RecursionError, UnicodeDecodeError):
                response = JSONResponse(status_code=422, content={'detail': '測定記録の形式を確認してください。'})
            response.headers.update(PRIVATE_HEADERS)
            return response

        return protected


router = APIRouter(prefix='/emergency/acceptance', tags=['emergency-acceptance'], route_class=PrivateEvaluationRoute)


def read_access(db: Session = Depends(get_db), user: User = Depends(require_permission('emergency.report.read'))):
    service.require_details(db, user)
    return user


def create_access(db: Session = Depends(get_db), user: User = Depends(require_mutation_permission('emergency.report.create'))):
    service.require_details(db, user)
    return user


def review_access(db: Session = Depends(get_db), user: User = Depends(require_mutation_permission('emergency.report.review'))):
    service.require_details(db, user)
    return user


@router.post('/preview')
def preview(payload: EvaluationInput, user: User = Depends(read_access)):
    service.allow_dataset(payload.dataset_kind)
    return evaluate_acceptance(payload)


@router.post('/evaluations', status_code=201)
def create(payload: SaveEvaluation, response: Response, db: Session = Depends(get_db), user: User = Depends(create_access)):
    row, created = service.save(db, user, payload)
    if not created:
        response.status_code = 200
    return service.output(db, row, user, include_measurement=True)


@router.get('/evaluations')
def listing(limit: int = Query(30, ge=1, le=100), offset: int = Query(0, ge=0),
            db: Session = Depends(get_db), user: User = Depends(read_access)):
    query = select(EmergencyAcceptanceEvaluation)
    if not settings.emergency_acceptance_internal_enabled:
        query = query.where(EmergencyAcceptanceEvaluation.dataset_kind == 'synthetic')
    rows = db.scalars(query.order_by(EmergencyAcceptanceEvaluation.created_at.desc(),
                                   EmergencyAcceptanceEvaluation.evaluation_id).offset(offset).limit(limit))
    return [service.output(db, row, user) for row in rows]


@router.get('/evaluations/{identity}')
def detail(identity: UUID, db: Session = Depends(get_db), user: User = Depends(read_access)):
    return service.output(db, service.get_evaluation(db, identity), user, include_measurement=True)


@router.post('/evaluations/{identity}/review')
def review(identity: UUID, payload: ReviewEvaluation, db: Session = Depends(get_db), user: User = Depends(review_access)):
    return service.output(db, service.review(db, user, identity, payload), user, include_measurement=True)


@router.post('/candidate-checks')
def candidate_checks(payload: CandidateCheck, db: Session = Depends(get_db), user: User = Depends(create_access)):
    fields = {name: Observation(item.state, item.value) for name, item in payload.fields.items()}
    findings = evaluate_confirmed_fields(fields)
    counts = {status: 0 for status in ('REVIEW_REQUIRED', 'NO_ISSUE_DETECTED', 'NOT_TESTED', 'NOT_APPLICABLE')}
    counts.update(Counter(item.status for item in findings))
    reading_counts = {state: 0 for state in ('confirmed', 'unconfirmed', 'unreadable', 'not_printed', 'unmapped')}
    reading_counts.update(Counter(item.state for item in fields.values()))
    write_audit(db, user_id=user.user_id, action='emergency.acceptance.candidate_check',
                entity_type='emergency_acceptance_evaluations', after={'counts': counts, 'reading_counts': reading_counts})
    db.commit()
    return {'findings': [asdict(item) for item in findings], 'counts': counts, 'reading_counts': reading_counts,
            'production_complete': False, 'submission_decision': 'NOT_PROVIDED',
            'rule_approval': 'PROVISIONAL_NOT_APPROVED'}


@router.get('/sample')
def sample(user: User = Depends(read_access)):
    # This is a product tutorial, always explicitly synthetic, with incomplete evidence.
    return EvaluationInput.model_validate({'dataset_kind': 'synthetic', 'reports': [
        {'report_id': '00000000-0000-4000-8000-000000000001', 'report_version': 1, 'cohort': 'baseline',
         'activity_kind': 'transport', 'document_kind': 'image_pdf', 'followup_complete': True,
         'corrected_after_submission': True, 'work_complete': True,
         'work': [{'worker_id': '00000000-0000-4000-8000-000000000011', 'stage': 'check',
                   'start_seconds': 0, 'end_seconds': 600}]},
        {'report_id': '00000000-0000-4000-8000-000000000002', 'report_version': 1, 'cohort': 'assisted',
         'activity_kind': 'transport', 'document_kind': 'image_pdf', 'followup_complete': False,
         'independent_review_complete': True,
         'opportunities': [{'opportunity_id': '00000000-0000-4000-8000-000000000021',
                            'error_id': '00000000-0000-4000-8000-000000000031', 'truth': 'error',
                            'decision': 'unchecked', 'read_state': 'unreadable', 'verified_read_state': 'unreadable'}]},
    ]}).model_dump(mode='json')
