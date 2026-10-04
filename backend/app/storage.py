from __future__ import annotations
import hashlib
import shutil
import uuid
from datetime import datetime
from pathlib import Path
from fastapi import UploadFile
from .settings import settings

def _root() -> Path:
    p=Path(settings.storage_root).resolve()
    p.mkdir(parents=True, exist_ok=True)
    return p

def store_upload(upload: UploadFile) -> tuple[str,str,int]:
    now=datetime.now()
    folder=_root()/"originals"/f"{now:%Y}"/f"{now:%m}"
    folder.mkdir(parents=True, exist_ok=True)
    suffix=Path(upload.filename or '').suffix.lower()
    if len(suffix)>10 or not all(ch.isalnum() or ch=='.' for ch in suffix): suffix=''
    dest=folder/f"{uuid.uuid4()}{suffix}"
    h=hashlib.sha256(); size=0
    with dest.open('wb') as out:
        while True:
            chunk=upload.file.read(1024*1024)
            if not chunk: break
            h.update(chunk); size += len(chunk); out.write(chunk)
    rel=str(dest.relative_to(_root()))
    return rel,h.hexdigest(),size