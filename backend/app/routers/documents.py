from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy.orm import Session
from ..db import get_db
from ..models import Document, Facility, User
from ..schemas import DocumentOut
from ..authz import require_permission
from ..audit import write_audit
from ..storage import store_upload

router=APIRouter(prefix="/documents", tags=["documents"])

@router.post("/upload", response_model=DocumentOut, status_code=201)
def upload_document(
    file: UploadFile = File(...),
    building_id: str | None = Form(default=None),
    document_type: str | None = Form(default=None),
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("document.create")),
):
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
def get_document(document_id: str, db: Session = Depends(get_db), user: User = Depends(require_permission("document.read"))):
    doc=db.get(Document,document_id)
    if not doc: raise HTTPException(status_code=404,detail="document not found")
    return DocumentOut(document_id=doc.document_id, building_id=doc.building_id,
                       original_filename=doc.original_filename, sha256=doc.sha256,
                       size_bytes=doc.size_bytes, mime_type=doc.mime_type,
                       document_type=doc.document_type)