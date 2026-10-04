from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from ..audit import write_audit
from ..authz import require_permission
from ..db import get_db
from ..models import ChangeRequest, Document, ExtensionDeployment, ExtensionIntake, FeatureFlag, ModuleDefinition, User
from ..schemas import (
    ChangeRequestApprove, ChangeRequestCreate, ChangeRequestOut, ChangeRequestReview,
    ExtensionDeploymentCreate, ExtensionDeploymentOut, ExtensionIntakeCreate, ExtensionIntakeOut, FeatureFlagOut, FeatureFlagPatch, ModuleOut,
)

router = APIRouter(prefix="/extensions", tags=["extensions"])


def _cr_out(row: ChangeRequest) -> ChangeRequestOut:
    return ChangeRequestOut(
        change_request_id=row.change_request_id, title=row.title, request_text=row.request_text,
        target_module=row.target_module, target_surface=row.target_surface, status=row.status,
        risk_level=row.risk_level, analysis=row.analysis or {}, proposed_changes=row.proposed_changes or {},
        acceptance_criteria=row.acceptance_criteria or [], sandbox_result=row.sandbox_result or {}, version=row.version,
    )


@router.get("/modules", response_model=list[ModuleOut])
def list_modules(db: Session = Depends(get_db), user: User = Depends(require_permission("extension.read"))):
    rows = db.scalars(select(ModuleDefinition).order_by(ModuleDefinition.code)).all()
    return [ModuleOut(module_id=r.module_id, code=r.code, name=r.name, version=r.version, status=r.status, manifest=r.manifest or {}) for r in rows]


@router.post("/intakes", response_model=ExtensionIntakeOut, status_code=201)
def create_intake(payload: ExtensionIntakeCreate, db: Session = Depends(get_db), user: User = Depends(require_permission("extension.create"))):
    if not db.get(Document, payload.source_document_id):
        raise HTTPException(status_code=404, detail="source document not found")
    row = ExtensionIntake(source_document_id=payload.source_document_id, requested_goal=payload.requested_goal,
                          target_module=payload.target_module, submitted_by=user.user_id)
    db.add(row); db.flush()
    write_audit(db, user_id=user.user_id, action="extension.intake.create", entity_type="extension_intake",
                entity_id=row.extension_intake_id, after={"source_document_id": row.source_document_id, "target_module": row.target_module, "status": row.status})
    db.commit(); db.refresh(row)
    return ExtensionIntakeOut(**{k: getattr(row, k) for k in ExtensionIntakeOut.model_fields})


@router.post("/change-requests", response_model=ChangeRequestOut, status_code=201)
def create_change_request(payload: ChangeRequestCreate, db: Session = Depends(get_db), user: User = Depends(require_permission("extension.create"))):
    row = ChangeRequest(title=payload.title, request_text=payload.request_text, target_module=payload.target_module,
                        target_surface=payload.target_surface, requester_id=user.user_id)
    db.add(row); db.flush()
    write_audit(db, user_id=user.user_id, action="change_request.create", entity_type="change_request",
                entity_id=row.change_request_id, after={"title": row.title, "target_module": row.target_module, "status": row.status})
    db.commit(); db.refresh(row)
    return _cr_out(row)


@router.get("/change-requests/{change_request_id}", response_model=ChangeRequestOut)
def get_change_request(change_request_id: str, db: Session = Depends(get_db), user: User = Depends(require_permission("extension.read"))):
    row = db.get(ChangeRequest, change_request_id)
    if not row: raise HTTPException(status_code=404, detail="change request not found")
    return _cr_out(row)


@router.post("/change-requests/{change_request_id}/review", response_model=ChangeRequestOut)
def review_change_request(change_request_id: str, payload: ChangeRequestReview, db: Session = Depends(get_db), user: User = Depends(require_permission("extension.review"))):
    row = db.get(ChangeRequest, change_request_id)
    if not row: raise HTTPException(status_code=404, detail="change request not found")
    before = {"status": row.status, "version": row.version}
    result = db.execute(update(ChangeRequest).where(ChangeRequest.change_request_id == change_request_id,
                                                     ChangeRequest.version == payload.expected_version)
                        .values(status="reviewed", risk_level=payload.risk_level, analysis=payload.analysis,
                                proposed_changes=payload.proposed_changes, acceptance_criteria=payload.acceptance_criteria,
                                sandbox_result=payload.sandbox_result, version=payload.expected_version+1,
                                updated_at=datetime.now(timezone.utc)))
    if result.rowcount != 1:
        db.rollback(); raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="change request was updated by another user")
    row = db.get(ChangeRequest, change_request_id)
    write_audit(db, user_id=user.user_id, action="change_request.review", entity_type="change_request", entity_id=change_request_id,
                before=before, after={"status": row.status, "risk_level": row.risk_level, "version": row.version})
    db.commit(); db.refresh(row)
    return _cr_out(row)


@router.post("/change-requests/{change_request_id}/approve", response_model=ChangeRequestOut)
def approve_change_request(change_request_id: str, payload: ChangeRequestApprove, db: Session = Depends(get_db), user: User = Depends(require_permission("extension.apply"))):
    row = db.get(ChangeRequest, change_request_id)
    if not row: raise HTTPException(status_code=404, detail="change request not found")
    if row.status != "reviewed": raise HTTPException(status_code=409, detail="change request must be reviewed before approval")
    result = db.execute(update(ChangeRequest).where(ChangeRequest.change_request_id == change_request_id,
                                                     ChangeRequest.version == payload.expected_version)
                        .values(status="approved", approved_by=user.user_id, approved_at=datetime.now(timezone.utc),
                                version=payload.expected_version+1, updated_at=datetime.now(timezone.utc)))
    if result.rowcount != 1:
        db.rollback(); raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="change request was updated by another user")
    row = db.get(ChangeRequest, change_request_id)
    write_audit(db, user_id=user.user_id, action="change_request.approve", entity_type="change_request", entity_id=change_request_id,
                after={"status": row.status, "version": row.version})
    db.commit(); db.refresh(row)
    return _cr_out(row)


@router.get("/feature-flags", response_model=list[FeatureFlagOut])
def list_feature_flags(db: Session = Depends(get_db), user: User = Depends(require_permission("extension.read"))):
    rows = db.scalars(select(FeatureFlag).order_by(FeatureFlag.key)).all()
    return [FeatureFlagOut(feature_flag_id=r.feature_flag_id, key=r.key, module_code=r.module_code,
                           enabled=r.enabled, config=r.config or {}, version=r.version) for r in rows]


@router.patch("/feature-flags/{flag_key}", response_model=FeatureFlagOut)
def patch_feature_flag(flag_key: str, payload: FeatureFlagPatch, db: Session = Depends(get_db), user: User = Depends(require_permission("extension.apply"))):
    row = db.scalar(select(FeatureFlag).where(FeatureFlag.key == flag_key))
    if not row: raise HTTPException(status_code=404, detail="feature flag not found")
    values = {"enabled": payload.enabled, "version": payload.expected_version + 1,
              "updated_by": user.user_id, "updated_at": datetime.now(timezone.utc)}
    if payload.config is not None: values["config"] = payload.config
    result = db.execute(update(FeatureFlag).where(FeatureFlag.key == flag_key, FeatureFlag.version == payload.expected_version).values(**values))
    if result.rowcount != 1:
        db.rollback(); raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="feature flag was updated by another user")
    row = db.scalar(select(FeatureFlag).where(FeatureFlag.key == flag_key))
    write_audit(db, user_id=user.user_id, action="feature_flag.update", entity_type="feature_flag", entity_id=row.feature_flag_id,
                after={"key": row.key, "enabled": row.enabled, "version": row.version})
    db.commit(); db.refresh(row)
    return FeatureFlagOut(feature_flag_id=row.feature_flag_id, key=row.key, module_code=row.module_code,
                          enabled=row.enabled, config=row.config or {}, version=row.version)


def _deployment_out(r: ExtensionDeployment) -> ExtensionDeploymentOut:
    return ExtensionDeploymentOut(extension_deployment_id=r.extension_deployment_id, change_request_id=r.change_request_id,
        module_code=r.module_code, release_version=r.release_version, previous_version=r.previous_version,
        migration_version=r.migration_version, feature_flag_key=r.feature_flag_key, status=r.status,
        rollback_of=r.rollback_of, evidence=r.evidence or {})


@router.post("/change-requests/{change_request_id}/deployments", response_model=ExtensionDeploymentOut, status_code=201)
def record_deployment(change_request_id: str, payload: ExtensionDeploymentCreate, db: Session = Depends(get_db), user: User = Depends(require_permission("extension.apply"))):
    cr = db.get(ChangeRequest, change_request_id)
    if not cr: raise HTTPException(status_code=404, detail="change request not found")
    if cr.status != "approved": raise HTTPException(status_code=409, detail="change request must be approved before deployment")
    row = ExtensionDeployment(change_request_id=change_request_id, module_code=payload.module_code,
        release_version=payload.release_version, previous_version=payload.previous_version,
        migration_version=payload.migration_version, feature_flag_key=payload.feature_flag_key,
        evidence=payload.evidence, applied_by=user.user_id)
    db.add(row); db.flush()
    write_audit(db, user_id=user.user_id, action="extension.deploy", entity_type="extension_deployment", entity_id=row.extension_deployment_id,
                after={"change_request_id": change_request_id, "module_code": row.module_code, "release_version": row.release_version,
                       "migration_version": row.migration_version, "feature_flag_key": row.feature_flag_key})
    db.commit(); db.refresh(row)
    return _deployment_out(row)


@router.post("/deployments/{deployment_id}/rollback", response_model=ExtensionDeploymentOut)
def rollback_deployment(deployment_id: str, db: Session = Depends(get_db), user: User = Depends(require_permission("extension.apply"))):
    original = db.get(ExtensionDeployment, deployment_id)
    if not original: raise HTTPException(status_code=404, detail="deployment not found")
    if original.status != "applied": raise HTTPException(status_code=409, detail="deployment is not active")
    original.status = "rolled_back"
    rollback = ExtensionDeployment(change_request_id=original.change_request_id, module_code=original.module_code,
        release_version=original.previous_version or original.release_version, previous_version=original.release_version,
        migration_version=None, feature_flag_key=original.feature_flag_key, status="rollback_applied",
        rollback_of=original.extension_deployment_id, evidence={"reason":"manual rollback"}, applied_by=user.user_id)
    if original.feature_flag_key:
        flag = db.scalar(select(FeatureFlag).where(FeatureFlag.key == original.feature_flag_key))
        if flag:
            flag.enabled = False; flag.version += 1; flag.updated_by = user.user_id; flag.updated_at = datetime.now(timezone.utc)
    db.add(rollback); db.flush()
    write_audit(db, user_id=user.user_id, action="extension.rollback", entity_type="extension_deployment", entity_id=rollback.extension_deployment_id,
                after={"rollback_of": original.extension_deployment_id, "module_code": original.module_code,
                       "feature_flag_key": original.feature_flag_key})
    db.commit(); db.refresh(rollback)
    return _deployment_out(rollback)