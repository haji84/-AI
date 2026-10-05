from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from ..audit import write_audit
from ..authz import require_permission
from ..db import get_db
from ..legal_structure import PARSER_VERSION
from ..legal_structure_service import structure_legal_version
from ..models import (
    LegalJurisdiction,
    LegalProfile,
    LegalProfileJurisdiction,
    LegalSource,
    LegalSourceDocument,
    LegalSourceDocumentVersion,
    User,
)
from ..schemas import (
    LegalJurisdictionCreate,
    LegalJurisdictionOut,
    LegalProfileCreate,
    LegalProfileJurisdictionCreate,
    LegalProfileOut,
    LegalSourceCreate,
    LegalSourceDocumentOut,
    LegalSourceDocumentVersionOut,
    LegalSourceOut,
    LegalStructureRebuildRequest,
    LegalStructureRebuildOut,
)

router = APIRouter(prefix="/legal-sources", tags=["legal-sources"])


def _document_out(row: LegalSourceDocument) -> LegalSourceDocumentOut:
    return LegalSourceDocumentOut(
        legal_source_document_id=row.legal_source_document_id,
        legal_source_id=row.legal_source_id,
        external_id=row.external_id,
        document_type=row.document_type,
        title=row.title,
        document_number=row.document_number,
        current_status=row.current_status,
        source_url=row.source_url,
    )


def _document_version_out(row: LegalSourceDocumentVersion) -> LegalSourceDocumentVersionOut:
    return LegalSourceDocumentVersionOut(
        legal_source_document_version_id=row.legal_source_document_version_id,
        legal_source_document_id=row.legal_source_document_id,
        version_label=row.version_label,
        effective_from=row.effective_from.isoformat() if row.effective_from else None,
        effective_to=row.effective_to.isoformat() if row.effective_to else None,
        source_current_date=row.source_current_date.isoformat() if row.source_current_date else None,
        source_url=row.source_url,
        sha256=row.sha256,
        structure_status=row.structure_status,
        structure_parser_version=row.structure_parser_version,
        provision_count=row.provision_count,
    )


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


@router.get("/documents", response_model=list[LegalSourceDocumentOut])
def list_legal_documents(
    source_id: str | None = None,
    q: str | None = None,
    document_type: str | None = None,
    offset: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("legal_source.read")),
):
    stmt = select(LegalSourceDocument)
    if source_id:
        stmt = stmt.where(LegalSourceDocument.legal_source_id == source_id)
    if document_type:
        stmt = stmt.where(LegalSourceDocument.document_type == document_type)
    if q:
        needle = f"%{q}%"
        stmt = stmt.where(
            or_(
                LegalSourceDocument.title.ilike(needle),
                LegalSourceDocument.document_number.ilike(needle),
                LegalSourceDocument.external_id.ilike(needle),
            )
        )
    rows = db.scalars(
        stmt.order_by(LegalSourceDocument.title)
        .offset(max(0, offset))
        .limit(max(1, min(limit, 500)))
    ).all()
    return [_document_out(x) for x in rows]


@router.get("/documents/{document_id}/versions", response_model=list[LegalSourceDocumentVersionOut])
def list_legal_document_versions(
    document_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("legal_source.read")),
):
    if not db.get(LegalSourceDocument, document_id):
        raise HTTPException(status_code=404, detail="legal source document not found")
    rows = db.scalars(
        select(LegalSourceDocumentVersion)
        .where(LegalSourceDocumentVersion.legal_source_document_id == document_id)
        .order_by(LegalSourceDocumentVersion.retrieved_at.desc())
    ).all()
    return [_document_version_out(x) for x in rows]


@router.post(
    "/document-versions/{version_id}/restructure",
    response_model=LegalStructureRebuildOut,
)
def restructure_legal_document_version(
    version_id: str,
    payload: LegalStructureRebuildRequest,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("legal_source.manage")),
):
    version = db.get(LegalSourceDocumentVersion, version_id)
    if not version:
        raise HTTPException(status_code=404, detail="legal source document version not found")

    if payload.expected_sha256 and version.sha256 != payload.expected_sha256:
        raise HTTPException(
            status_code=409,
            detail={
                "message": "legal source version SHA-256 does not match expected value",
                "current_sha256": version.sha256,
            },
        )

    already_current = (
        version.structure_status == "structured"
        and version.structure_parser_version == PARSER_VERSION
    )
    if already_current and not payload.force:
        return LegalStructureRebuildOut(
            changed=False,
            result={
                "version_id": version.legal_source_document_version_id,
                "status": version.structure_status,
                "parser_version": version.structure_parser_version,
                "count": version.provision_count or 0,
                "note": "already structured with current parser",
            },
        )

    before = {
        "structure_status": version.structure_status,
        "structure_parser_version": version.structure_parser_version,
        "provision_count": version.provision_count,
    }
    result = structure_legal_version(db, version)
    write_audit(
        db,
        user_id=user.user_id,
        action="legal_source.restructure",
        entity_type="legal_source_document_version",
        entity_id=version.legal_source_document_version_id,
        before=before,
        after=result,
    )
    db.commit()
    return LegalStructureRebuildOut(changed=True, result=result)
