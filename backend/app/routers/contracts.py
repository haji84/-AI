from datetime import date, datetime, timezone
from decimal import Decimal
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import update
from sqlalchemy.orm import Session

from ..audit import write_audit
from ..authz import require_permission
from ..db import get_db
from ..models import ContractCase, ContractCounterparty, User
from ..schemas import ContractCounterpartyCreate, ContractCounterpartyOut, ContractCreate, ContractOut, ContractPatch, ContractStateChange

router = APIRouter(prefix="/contracts", tags=["contracts"])


def d(v): return date.fromisoformat(v) if v else None

def out(c: ContractCase) -> ContractOut:
    return ContractOut(contract_case_id=c.contract_case_id, contract_no=c.contract_no, title=c.title,
        counterparty_id=c.counterparty_id, contract_method=c.contract_method,
        amount=float(c.amount) if c.amount is not None else None, currency=c.currency,
        start_date=c.start_date.isoformat() if c.start_date else None, end_date=c.end_date.isoformat() if c.end_date else None,
        status=c.status, version=c.version)

@router.post("/counterparties", response_model=ContractCounterpartyOut, status_code=201)
def create_counterparty(payload: ContractCounterpartyCreate, db: Session = Depends(get_db), user: User = Depends(require_permission("contract.create"))):
    row = ContractCounterparty(**payload.model_dump())
    db.add(row); db.flush();
    write_audit(db, user_id=user.user_id, action="contract.counterparty.create", entity_type="contract_counterparty", entity_id=row.counterparty_id, after={"name": row.name})
    db.commit(); db.refresh(row)
    return ContractCounterpartyOut(counterparty_id=row.counterparty_id, name=row.name, registration_no=row.registration_no,
                                   address=row.address, contact=row.contact, active=row.active, version=row.version)

@router.post("", response_model=ContractOut, status_code=201)
def create_contract(payload: ContractCreate, db: Session = Depends(get_db), user: User = Depends(require_permission("contract.create"))):
    if payload.counterparty_id and not db.get(ContractCounterparty, payload.counterparty_id): raise HTTPException(status_code=404, detail="counterparty not found")
    row=ContractCase(contract_no=payload.contract_no,title=payload.title,counterparty_id=payload.counterparty_id,
                     contract_method=payload.contract_method,amount=Decimal(str(payload.amount)) if payload.amount is not None else None,
                     currency=payload.currency,start_date=d(payload.start_date),end_date=d(payload.end_date),created_by=user.user_id)
    db.add(row); db.flush(); write_audit(db,user_id=user.user_id,action="contract.create",entity_type="contract",entity_id=row.contract_case_id,after={"title":row.title,"status":row.status,"version":row.version}); db.commit(); db.refresh(row); return out(row)

@router.get("/{contract_case_id}", response_model=ContractOut)
def get_contract(contract_case_id: str, db: Session=Depends(get_db), user: User=Depends(require_permission("contract.read"))):
    row=db.get(ContractCase,contract_case_id)
    if not row: raise HTTPException(status_code=404,detail="contract not found")
    return out(row)

@router.patch("/{contract_case_id}", response_model=ContractOut)
def patch_contract(contract_case_id: str,payload:ContractPatch,db:Session=Depends(get_db),user:User=Depends(require_permission("contract.update"))):
    row=db.get(ContractCase,contract_case_id)
    if not row: raise HTTPException(status_code=404,detail="contract not found")
    before={"title":row.title,"amount":float(row.amount) if row.amount is not None else None,"status":row.status,"version":row.version}
    vals={}
    for k,v in payload.model_dump(exclude={"expected_version"},exclude_unset=True).items():
        if k in ("start_date","end_date"): v=d(v)
        if k=="amount" and v is not None: v=Decimal(str(v))
        vals[k]=v
    if not vals: return out(row)
    vals.update(version=payload.expected_version+1,updated_at=datetime.now(timezone.utc))
    result=db.execute(update(ContractCase).where(ContractCase.contract_case_id==contract_case_id,ContractCase.version==payload.expected_version).values(**vals))
    if result.rowcount!=1: db.rollback(); raise HTTPException(status_code=status.HTTP_409_CONFLICT,detail="contract was updated by another user")
    row=db.get(ContractCase,contract_case_id); write_audit(db,user_id=user.user_id,action="contract.update",entity_type="contract",entity_id=contract_case_id,before=before,after={"title":row.title,"amount":float(row.amount) if row.amount is not None else None,"status":row.status,"version":row.version}); db.commit(); db.refresh(row); return out(row)

@router.post("/{contract_case_id}/approve", response_model=ContractOut)
def approve_contract(contract_case_id:str,payload:ContractStateChange,db:Session=Depends(get_db),user:User=Depends(require_permission("contract.approve"))):
    result=db.execute(update(ContractCase).where(ContractCase.contract_case_id==contract_case_id,ContractCase.version==payload.expected_version).values(status="approved",approved_by=user.user_id,approved_at=datetime.now(timezone.utc),version=payload.expected_version+1,updated_at=datetime.now(timezone.utc)))
    if result.rowcount!=1: db.rollback(); raise HTTPException(status_code=status.HTTP_409_CONFLICT,detail="contract was updated by another user")
    row=db.get(ContractCase,contract_case_id); write_audit(db,user_id=user.user_id,action="contract.approve",entity_type="contract",entity_id=contract_case_id,after={"status":row.status,"version":row.version}); db.commit(); db.refresh(row); return out(row)