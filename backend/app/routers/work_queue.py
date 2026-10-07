from datetime import date
from typing import Literal

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy.orm import Session

from ..authz import current_user
from ..db import get_db
from ..models import User
from ..work_queue import list_work_queue
from ..work_queue_schemas import WorkQueueResponse

router = APIRouter(prefix='/work-queue', tags=['work_queue'])


@router.get('', response_model=WorkQueueResponse)
def work_queue(response: Response, scope: Literal['all', 'related'] = 'all',
               as_of: date | None = None, days: int = Query(30, ge=0, le=30),
               limit: int = Query(50, ge=1, le=100), offset: int = Query(0, ge=0),
               db: Session = Depends(get_db), user: User = Depends(current_user)):
    response.headers['Cache-Control'] = 'no-store'
    return list_work_queue(db, user, as_of=as_of, days=days, scope=scope, limit=limit, offset=offset)
