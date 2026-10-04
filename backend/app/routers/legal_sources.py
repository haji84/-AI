from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..audit import write_audit
from ..authz import require_permission
from ..db import get_db
from ..models import (
    LegalJurisdiction,
    LegalProfile,
    LegalProfileJurisdiction,
    LegalSource,
    User,
)
from ..schemas import (
    LegalJurisdictionCreate,
    LegalJurisdictionOut,
    LegalProfileCreate,
    LegalProfileJurisdictionCreate,
    LegalProfileOut,
    LegalSourceCreate,
    LegalSourceOut,
)

router = APIRouter(prefix="/legal-sources", tags=["legal-sources"])


def _jurisdiction_out(row: LegalJurisdiction) -> LegalJurisdictionOut:
    return LegalJurisdictionOut(
        jurisdiction_id=row.jurisdiction_id,
        code=row.code,
        name=row.name,
        jurisdiction_type=row.jurisdiction_type,
        parent_jurisdiction_id=row.parent_jurisdiction_id,
        official_base_url=row.official_base_url,
        active=row.active,
    )


def _profile_out(row: LegalProfile) -> LegalProfileOut:
    return LegalProfileOut(
        legal_profile_id=row.legal_profile_id,
        code=row.code,
        name=row.name,
        fire_department_name=row.fire_department_name,
        active=row.active,
    )


def _source_out(row: LegalSource) -> LegalSourceOut:
    return LegalSourceOut(
        legal_source_id=row.legal_source_id,
        legal_profile_id=row.legal_profile_id,
        jurisdiction_id=row.jurisdiction_id,
        source_code=row.source_code,
        name=row.name,
        source_type=row.source_type,
        adapter_type=row.adapter_type,
        base_url=row.base_url,
        index_url=row.index_url,
        update_mode=row.update_mode,
        content_scope=row.content_scope,
        sync_frequency=row.sync_frequency,
        trust_level=row.trust_level,
        enabled=row.enabled,
        coverage_status=row.coverage_status,
        expected_document_count=row.expected_document_count,
        captured_document_count=row.captured_document_count,
        stale_after_hours=row.stale_after_hours,
    )


@router.get("/jurisdictions", response_model=list[LegalJurisdictionOut])
def list_jurisdictions(
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("legal_source.read")),
):
    return [_jurisdiction_out(x) for x in db.scalars(select(LegalJurisdiction).order_by(LegalJurisdiction.name)).all()]


@router.post("/jurisdictions", response_model=LegalJurisdictionOut, status_code=201)
def create_jurisdiction(
    payload: LegalJurisdictionCreate,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("legal_source.manage")),
):
    if db.scalar(select(LegalJurisdiction).where(LegalJurisdiction.code == payload.code)):
        raise HTTPException(status_code=409, detail="jurisdiction code already exists")
    if payload.parent_jurisdiction_id and not db.get(LegalJurisdiction, payload.parent_jurisdiction_id):
        raise HTTPException(status_code=422, detail="parent jurisdiction not found")
    row = LegalJurisdiction(**payload.model_dump())
    db.add(row)
    db.flush()
    write_audit(
        db,
        user_id=user.user_id,
        action="legal_source.jurisdiction.create",
        entity_type="legal_jurisdiction",
        entity_id=row.jurisdiction_id,
        after=_jurisdiction_out(row).model_dump(mode="json"),
    )
    db.commit()
    return _jurisdiction_out(row)


@router.get("/profiles", response_model=list[LegalProfileOut])
def list_profiles(
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("legal_source.read")),
):
    return [_profile_out(x) for x in db.scalars(select(LegalProfile).order_by(LegalProfile.name)).all()]


@router.post("/profiles", response_model=LegalProfileOut, status_code=201)
def create_profile(
    payload: LegalProfileCreate,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("legal_source.manage")),
):
    if db.scalar(select(LegalProfile).where(LegalProfile.code == payload.code)):
        raise HTTPException(status_code=409, detail="legal profile code already exists")
    row = LegalProfile(**payload.model_dump(), created_by=user.user_id)
    db.add(row)
    db.flush()
    write_audit(
        db,
        user_id=user.user_id,
        action="legal_source.profile.create",
        entity_type="legal_profile",
        entity_id=row.legal_profile_id,
        after=_profile_out(row).model_dump(mode="json"),
    )
    db.commit()
    return _profile_out(row)


@router.post("/profiles/{profile_id}/jurisdictions", status_code=204)
def attach_jurisdiction(
    profile_id: str,
    payload: LegalProfileJurisdictionCreate,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("legal_source.manage")),
):
    if not db.get(LegalProfile, profile_id):
        raise HTTPException(status_code=404, detail="legal profile not found")
    if not db.get(LegalJurisdiction, payload.jurisdiction_id):
        raise HTTPException(status_code=422, detail="jurisdiction not found")
    existing = db.get(LegalProfileJurisdiction, (profile_id, payload.jurisdiction_id))
    if existing:
        existing.applicability = payload.applicability
        existing.priority = payload.priority
    else:
        db.add(
            LegalProfileJurisdiction(
                legal_profile_id=profile_id,
                jurisdiction_id=payload.jurisdiction_id,
                applicability=payload.applicability,
                priority=payload.priority,
            )
        )
    write_audit(
        db,
        user_id=user.user_id,
        action="legal_source.profile_jurisdiction.attach",
        entity_type="legal_profile",
        entity_id=profile_id,
        after=payload.model_dump(mode="json"),
    )
    db.commit()
    return None


@router.get("/sources", response_model=list[LegalSourceOut])
def list_sources(
    profile_id: str | None = None,
    jurisdiction_id: str | None = None,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("legal_source.read")),
):
    stmt = select(LegalSource).order_by(LegalSource.name)
    if profile_id:
        stmt = stmt.where(LegalSource.legal_profile_id == profile_id)
    if jurisdiction_id:
        stmt = stmt.where(LegalSource.jurisdiction_id == jurisdiction_id)
    return [_source_out(x) for x in db.scalars(stmt).all()]


@router.post("/sources", response_model=LegalSourceOut, status_code=201)
def create_source(
    payload: LegalSourceCreate,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("legal_source.manage")),
):
    if not db.get(LegalJurisdiction, payload.jurisdiction_id):
        raise HTTPException(status_code=422, detail="jurisdiction not found")
    if payload.legal_profile_id and not db.get(LegalProfile, payload.legal_profile_id):
        raise HTTPException(status_code=422, detail="legal profile not found")
    duplicate = db.scalar(
        select(LegalSource).where(
            LegalSource.jurisdiction_id == payload.jurisdiction_id,
            LegalSource.source_code == payload.source_code,
        )
    )
    if duplicate:
        raise HTTPException(status_code=409, detail="source code already exists in jurisdiction")
    row = LegalSource(**payload.model_dump())
    db.add(row)
    db.flush()
    write_audit(
        db,
        user_id=user.user_id,
        action="legal_source.create",
        entity_type="legal_source",
        entity_id=row.legal_source_id,
        after=_source_out(row).model_dump(mode="json"),
    )
    db.commit()
    return _source_out(row)
