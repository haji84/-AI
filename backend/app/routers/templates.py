from datetime import date
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..audit import write_audit
from ..authz import require_permission
from ..db import get_db
from ..models import Document, FormTemplate, User
from ..schemas import FormTemplateCreate, FormTemplateOut

router = APIRouter(prefix="/templates", tags=["templates"])


def parse_date(v: str | None):
    return date.fromisoformat(v) if v else None


def out(t: FormTemplate) -> FormTemplateOut:
    return FormTemplateOut(
        form_template_id=t.form_template_id, template_code=t.template_code, name=t.name, module_code=t.module_code,
        document_id=t.document_id, version_label=t.version_label, issuer=t.issuer,
        effective_from=t.effective_from.isoformat() if t.effective_from else None,
        effective_to=t.effective_to.isoformat() if t.effective_to else None,
        field_mapping=t.field_mapping or {}, print_settings=t.print_settings or {},
        modification_policy=t.modification_policy, status=t.status,
    )


@router.post("", response_model=FormTemplateOut, status_code=201)
def register_template(payload: FormTemplateCreate, db: Session = Depends(get_db), user: User = Depends(require_permission("template.manage"))):
    doc = db.get(Document, payload.document_id)
    if not doc: raise HTTPException(status_code=404, detail="source document not found")
    exists = db.scalar(select(FormTemplate).where(FormTemplate.template_code == payload.template_code,
                                                   FormTemplate.version_label == payload.version_label))
    if exists: raise HTTPException(status_code=409, detail="template version already exists")
    row = FormTemplate(template_code=payload.template_code, name=payload.name, module_code=payload.module_code,
                       document_id=payload.document_id, version_label=payload.version_label, issuer=payload.issuer,
                       effective_from=parse_date(payload.effective_from), effective_to=parse_date(payload.effective_to),
                       field_mapping=payload.field_mapping, print_settings=payload.print_settings,
                       modification_policy=payload.modification_policy, created_by=user.user_id)
    db.add(row); db.flush()
    write_audit(db, user_id=user.user_id, action="template.register", entity_type="form_template", entity_id=row.form_template_id,
                after={"template_code": row.template_code, "version_label": row.version_label,
                       "document_id": row.document_id, "source_sha256": doc.sha256, "modification_policy": row.modification_policy})
    db.commit(); db.refresh(row)
    return out(row)


@router.get("/{template_code}/latest", response_model=FormTemplateOut)
def latest_template(template_code: str, on_date: str | None = None, db: Session = Depends(get_db), user: User = Depends(require_permission("template.read"))):
    target = parse_date(on_date) or date.today()
    rows = db.scalars(select(FormTemplate).where(FormTemplate.template_code == template_code,
                                                  FormTemplate.status == "active").order_by(FormTemplate.effective_from.desc())).all()
    for row in rows:
        if (row.effective_from is None or row.effective_from <= target) and (row.effective_to is None or target <= row.effective_to):
            return out(row)
    raise HTTPException(status_code=404, detail="no effective template found")