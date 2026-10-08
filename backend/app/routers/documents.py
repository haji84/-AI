from pathlib import Path
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, Response
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session
from ..db import get_db
from ..models import Document, Facility, User
from ..schemas import DocumentOut
from ..authz import require_permission
from ..audit import write_audit
from ..storage import store_upload
from ..settings import settings

router=APIRouter(prefix="/documents", tags=["documents"])

@router.post("/upload", response_model=DocumentOut, status_code=201)
def upload_document(
    file: UploadFile = File(...),
    building_id: str | None = Form(default=None),
    document_type: str | None = Form(default=None),
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("document.create")),
):
    if document_type == 'personnel_notice':
        from ..inquiries_service import need
        need(db, user, 'personnel.manage', 'personnel.read')
    if building_id and not db.get(Facility, building_id):
        raise HTTPException(status_code=404, detail="facility not found")
    storage_path, digest, size=store_upload(file)
    doc=Document(building_id=building_id, storage_path=storage_path,
                 original_filename=file.filename or "unnamed", sha256=digest,
                 size_bytes=size, mime_type=file.content_type,
                 document_type=document_type, created_by=user.user_id)
    db.add(doc); db.flush()
    write_audit(db,user_id=user.user_id,action="document.upload",entity_type="document",
                entity_id=doc.document_id,after={"building_id":building_id,"sha256":digest,"size_bytes":size,"document_type":document_type})
    db.commit(); db.refresh(doc)
    return DocumentOut(document_id=doc.document_id, building_id=doc.building_id,
                       original_filename=doc.original_filename, sha256=doc.sha256,
                       size_bytes=doc.size_bytes, mime_type=doc.mime_type,
                       document_type=doc.document_type)

@router.get("/{document_id}", response_model=DocumentOut)
def get_document(document_id: str, response:Response, db: Session = Depends(get_db), user: User = Depends(require_permission("document.read"))):
    doc=db.get(Document,document_id)
    if not doc: raise HTTPException(status_code=404,detail="document not found")
    from ..inquiries_service import guard_document
    guard_document(db,user,doc)
    if doc.document_type in ('inquiry_import_original','inquiry_rendered_original','hazardous_evidence','personnel_notice'):response.headers['Cache-Control']='no-store'
    return DocumentOut(document_id=doc.document_id, building_id=doc.building_id,
                       original_filename=doc.original_filename, sha256=doc.sha256,
                       size_bytes=doc.size_bytes, mime_type=doc.mime_type,
                       document_type=doc.document_type)

@router.get("/{document_id}/download")
def download_document(
    document_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("document.read")),
):
    doc=db.get(Document,document_id)
    if not doc:
        raise HTTPException(status_code=404,detail="document not found")
    from ..inquiries_service import guard_document
    guard_document(db,user,doc)
    root=Path(settings.storage_root).resolve()
    path=(root/doc.storage_path).resolve()
    if path != root and root not in path.parents:
        raise HTTPException(status_code=409,detail="document path escapes managed storage")
    if not path.exists() or not path.is_file():
        raise HTTPException(status_code=404,detail="document file not found")
    return FileResponse(
        str(path),
        media_type=doc.mime_type or "application/octet-stream",
        filename=doc.original_filename,
        headers={'Cache-Control':'no-store'} if doc.document_type in ('inquiry_import_original','inquiry_rendered_original','hazardous_evidence','personnel_notice') else None,
    )

