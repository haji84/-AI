from __future__ import annotations

import hashlib
import json
import mimetypes
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from ..audit import write_audit
from ..authz import require_permission
from ..db import get_db
from ..models import (
    Document,
    FireEvidenceSnapshot,
    FireInvestigationAIManifest,
    FireInvestigationCase,
    FireReportDraft,
    FireReportExport,
    FormTemplate,
    User,
)
from ..official_form_renderer import (
    TemplateRenderError,
    flatten_values,
    render_template,
    sha256_file,
)
from ..schemas import (
    FireReportExportCreate,
    FireReportExportOut,
    FireReportExportVerify,
)
from ..settings import settings

router = APIRouter(prefix="/fire-investigations", tags=["fire-report-exports"])


def _out(row: FireReportExport) -> FireReportExportOut:
    return FireReportExportOut(
        fire_report_export_id=row.fire_report_export_id,
        fire_report_draft_id=row.fire_report_draft_id,
        form_template_id=row.form_template_id,
        template_document_id=row.template_document_id,
        template_sha256=row.template_sha256,
        report_draft_version=row.report_draft_version,
        request_sha256=row.request_sha256,
        output_format=row.output_format,
        field_values=row.field_values or {},
        render_manifest=row.render_manifest or {},
        output_document_id=row.output_document_id,
        status=row.status,
        error_detail=row.error_detail,
        created_at=row.created_at.isoformat(),
    )


def _root() -> Path:
    root = Path(settings.storage_root).resolve()
    root.mkdir(parents=True, exist_ok=True)
    return root


def _managed_path(storage_path: str) -> Path:
    root = _root()
    path = (root / storage_path).resolve()
    if path != root and root not in path.parents:
        raise HTTPException(status_code=409, detail="template document path escapes managed storage")
    return path


def _validate_template(
    template: FormTemplate,
    *,
    case: FireInvestigationCase,
) -> None:
    if template.status != "active":
        raise HTTPException(status_code=409, detail="form template is not active")
    if not template.module_code.startswith("fire_investigation"):
        raise HTTPException(
            status_code=409,
            detail="form template is not registered for the fire investigation module",
        )
    if template.modification_policy != "fill_only":
        raise HTTPException(
            status_code=409,
            detail="formal fire report output requires fill_only template policy",
        )
    target_date = (
        case.occurred_at.date()
        if case.occurred_at
        else datetime.now(timezone.utc).date()
    )
    if template.effective_from and template.effective_from > target_date:
        raise HTTPException(status_code=409, detail="form template is not effective for the case date")
    if template.effective_to and template.effective_to < target_date:
        raise HTTPException(status_code=409, detail="form template expired before the case date")


def _build_field_values(
    case: FireInvestigationCase,
    report: FireReportDraft,
    snapshot: FireEvidenceSnapshot | None,
) -> dict:
    nested = {
        "case": {
            "case_number": case.case_number,
            "title": case.title,
            "occurred_at": case.occurred_at.isoformat() if case.occurred_at else None,
            "location_text": case.location_text,
            "official_cause_text": case.official_cause_text,
            "status": case.status,
        },
        "report": {
            "report_type": report.report_type,
            "narrative_text": report.narrative_text,
            "structured_content": report.structured_content or {},
            "status": report.status,
            "version": report.version,
        },
        "snapshot": {
            "snapshot_sha256": snapshot.snapshot_sha256 if snapshot else None,
            "case_version": snapshot.case_version if snapshot else None,
            "photo_annotation_count": len(snapshot.photo_annotation_ids or []) if snapshot else 0,
            "transcript_segment_count": len(snapshot.transcript_segment_ids or []) if snapshot else 0,
            "statement_count": len(snapshot.statement_draft_ids or []) if snapshot else 0,
            "timeline_event_count": len(snapshot.timeline_event_ids or []) if snapshot else 0,
        },
    }
    values = flatten_values(nested)
    values.update({
        "case_number": case.case_number,
        "title": case.title,
        "occurred_at": case.occurred_at.isoformat() if case.occurred_at else None,
        "location_text": case.location_text,
        "official_cause_text": case.official_cause_text,
        "report_type": report.report_type,
        "narrative_text": report.narrative_text,
    })
    return values


def _request_hash(
    *,
    report: FireReportDraft,
    template: FormTemplate,
    template_sha256: str,
    values: dict,
) -> str:
    payload = {
        "report_draft_id": report.fire_report_draft_id,
        "report_version": report.version,
        "form_template_id": template.form_template_id,
        "template_document_id": template.document_id,
        "template_sha256": template_sha256,
        "field_mapping": template.field_mapping or {},
        "values": values,
    }
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


@router.get("/report-drafts/{draft_id}/exports", response_model=list[FireReportExportOut])
def list_report_exports(
    draft_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("fire_investigation.read")),
):
    if not db.get(FireReportDraft, draft_id):
        raise HTTPException(status_code=404, detail="report draft not found")
    rows = db.scalars(
        select(FireReportExport)
        .where(FireReportExport.fire_report_draft_id == draft_id)
        .order_by(FireReportExport.created_at.desc())
    ).all()
    return [_out(x) for x in rows]


@router.post(
    "/report-drafts/{draft_id}/render-form",
    response_model=FireReportExportOut,
    status_code=201,
)
def render_report_form(
    draft_id: str,
    payload: FireReportExportCreate,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("fire_investigation.approve")),
):
    report = db.get(FireReportDraft, draft_id)
    if not report:
        raise HTTPException(status_code=404, detail="report draft not found")
    if report.version != payload.expected_report_version:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="report draft version changed")
    if report.status != "approved":
        raise HTTPException(status_code=409, detail="only approved report drafts can be rendered as formal output")
    if not report.form_template_id:
        raise HTTPException(status_code=409, detail="approved report draft has no registered form template")

    case = db.get(FireInvestigationCase, report.fire_investigation_case_id)
    if not case:
        raise HTTPException(status_code=409, detail="report case not found")
    template = db.get(FormTemplate, report.form_template_id)
    if not template:
        raise HTTPException(status_code=409, detail="form template not found")
    _validate_template(template, case=case)

    if report.ai_generated:
        if not report.fire_evidence_snapshot_id or not report.source_manifest_id:
            raise HTTPException(status_code=409, detail="AI report provenance is incomplete")
        snapshot = db.get(FireEvidenceSnapshot, report.fire_evidence_snapshot_id)
        manifest = db.get(FireInvestigationAIManifest, report.source_manifest_id)
        if not snapshot or not manifest or manifest.manifest_type != "report_draft":
            raise HTTPException(status_code=409, detail="AI report provenance is invalid")
    else:
        snapshot = db.get(FireEvidenceSnapshot, report.fire_evidence_snapshot_id) if report.fire_evidence_snapshot_id else None

    source_doc = db.get(Document, template.document_id)
    if not source_doc:
        raise HTTPException(status_code=409, detail="template source document not found")
    source_path = _managed_path(source_doc.storage_path)
    if not source_path.exists():
        raise HTTPException(status_code=409, detail="template source file is missing from managed storage")
    actual_template_hash = sha256_file(source_path)
    if actual_template_hash != source_doc.sha256:
        raise HTTPException(status_code=409, detail="template source file SHA-256 no longer matches registered original")

    values = _build_field_values(case, report, snapshot)
    request_sha = _request_hash(
        report=report,
        template=template,
        template_sha256=actual_template_hash,
        values=values,
    )
    existing = db.scalar(
        select(FireReportExport).where(FireReportExport.request_sha256 == request_sha)
    )
    if existing:
        return _out(existing)

    suffix = source_path.suffix.lower()
    if suffix not in {".docx", ".xlsx", ".xlsm", ".pdf"}:
        raise HTTPException(status_code=422, detail=f"unsupported formal template format: {suffix or '(none)'}")

    now = datetime.now(timezone.utc)
    folder = _root() / "generated" / "fire_reports" / f"{now:%Y}" / f"{now:%m}"
    folder.mkdir(parents=True, exist_ok=True)
    destination = folder / f"{draft_id}-{request_sha[:12]}{suffix}"

    try:
        manifest = render_template(
            source_path,
            destination,
            template.field_mapping or {},
            values,
        )
    except TemplateRenderError as exc:
        destination.unlink(missing_ok=True)
        failed = FireReportExport(
            fire_report_draft_id=draft_id,
            form_template_id=template.form_template_id,
            template_document_id=source_doc.document_id,
            template_sha256=actual_template_hash,
            report_draft_version=report.version,
            request_sha256=request_sha,
            output_format=suffix.lstrip("."),
            field_values=values,
            render_manifest={},
            status="failed",
            error_detail=str(exc),
            created_by=user.user_id,
        )
        db.add(failed)
        db.commit()
        raise HTTPException(status_code=422, detail=f"formal template render failed: {exc}") from exc

    output_sha = sha256_file(destination)
    rel = str(destination.relative_to(_root()))
    mime_type = mimetypes.guess_type(destination.name)[0] or "application/octet-stream"
    output_doc = Document(
        building_id=case.building_id,
        storage_path=rel,
        original_filename=f"{source_path.stem}_{case.case_number or case.fire_investigation_case_id}{suffix}",
        sha256=output_sha,
        size_bytes=destination.stat().st_size,
        mime_type=mime_type,
        document_type="fire_investigation_form_output",
        created_by=user.user_id,
    )
    db.add(output_doc)
    db.flush()

    manifest = {
        **manifest,
        "template_document_id": source_doc.document_id,
        "template_sha256": actual_template_hash,
        "output_sha256": output_sha,
        "form_template_id": template.form_template_id,
        "form_template_version": template.version_label,
        "modification_policy": template.modification_policy,
    }
    row = FireReportExport(
        fire_report_draft_id=draft_id,
        form_template_id=template.form_template_id,
        template_document_id=source_doc.document_id,
        template_sha256=actual_template_hash,
        report_draft_version=report.version,
        request_sha256=request_sha,
        output_format=suffix.lstrip("."),
        field_values=values,
        render_manifest=manifest,
        output_document_id=output_doc.document_id,
        status="rendered",
        created_by=user.user_id,
    )
    db.add(row)
    db.flush()
    write_audit(
        db,
        user_id=user.user_id,
        action="fire_investigation.report_form.render",
        entity_type="fire_report_export",
        entity_id=row.fire_report_export_id,
        after={
            "report_draft_id": draft_id,
            "form_template_id": template.form_template_id,
            "template_sha256": actual_template_hash,
            "output_document_id": output_doc.document_id,
            "output_sha256": output_sha,
            "status": "rendered",
        },
    )
    db.commit()
    return _out(row)


@router.post(
    "/report-exports/{export_id}/verify",
    response_model=FireReportExportOut,
)
def verify_report_export(
    export_id: str,
    payload: FireReportExportVerify,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("fire_investigation.approve")),
):
    row = db.get(FireReportExport, export_id)
    if not row:
        raise HTTPException(status_code=404, detail="report export not found")
    if row.status != "rendered":
        raise HTTPException(status_code=409, detail="only rendered output can be verified")

    report = db.get(FireReportDraft, row.fire_report_draft_id)
    if not report or report.status != "approved":
        raise HTTPException(status_code=409, detail="source report draft is not approved")
    case = db.get(FireInvestigationCase, report.fire_investigation_case_id)
    if not case:
        raise HTTPException(status_code=409, detail="report case not found")
    if case.version != payload.expected_case_version:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="case version changed before output verification")

    output_doc = db.get(Document, row.output_document_id) if row.output_document_id else None
    if not output_doc:
        raise HTTPException(status_code=409, detail="rendered output document is missing")
    output_path = _managed_path(output_doc.storage_path)
    if not output_path.exists() or sha256_file(output_path) != output_doc.sha256:
        raise HTTPException(status_code=409, detail="rendered output file failed SHA-256 verification")

    if report.report_type == "fire_investigation_report":
        result = db.execute(
            update(FireInvestigationCase)
            .where(
                FireInvestigationCase.fire_investigation_case_id == case.fire_investigation_case_id,
                FireInvestigationCase.version == payload.expected_case_version,
            )
            .values(
                final_report_document_id=output_doc.document_id,
                version=payload.expected_case_version + 1,
                updated_by=user.user_id,
                updated_at=datetime.now(timezone.utc),
            )
        )
        if result.rowcount != 1:
            db.rollback()
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="case version changed during output verification")

    row.status = "verified"
    row.verified_by = user.user_id
    row.verified_at = datetime.now(timezone.utc)
    write_audit(
        db,
        user_id=user.user_id,
        action="fire_investigation.report_form.verify",
        entity_type="fire_report_export",
        entity_id=row.fire_report_export_id,
        after={
            "output_document_id": output_doc.document_id,
            "output_sha256": output_doc.sha256,
            "status": "verified",
            "case_final_report_linked": report.report_type == "fire_investigation_report",
        },
    )
    db.commit()
    return _out(row)
