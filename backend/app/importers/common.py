from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import shutil

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import ImportRun, SourceFile
from ..settings import settings
from .ooxml import file_sha256


def get_or_create_source_file(
    db: Session,
    *,
    path: Path,
    source_kind: str,
    imported_by: str | None,
) -> tuple[SourceFile, bool]:
    digest = file_sha256(path)
    existing = db.scalar(
        select(SourceFile).where(SourceFile.source_kind == source_kind, SourceFile.sha256 == digest)
    )
    root = Path(settings.storage_root).resolve()
    if existing:
        stored = Path(existing.storage_path) if existing.storage_path else None
        archived = stored if stored and stored.is_absolute() else (root / stored if stored else None)
        if archived is None or not archived.exists():
            now = datetime.now(timezone.utc)
            archive_dir = root / "imports" / source_kind / f"{now:%Y}" / f"{now:%m}"
            archive_dir.mkdir(parents=True, exist_ok=True)
            suffix = path.suffix.lower() if len(path.suffix) <= 10 else ""
            archived = archive_dir / f"{digest}{suffix}"
            if not archived.exists():
                shutil.copy2(path, archived)
            existing.storage_path = str(archived.relative_to(root))
            db.flush()
        return existing, False
    now = datetime.now(timezone.utc)
    archive_dir = root / "imports" / source_kind / f"{now:%Y}" / f"{now:%m}"
    archive_dir.mkdir(parents=True, exist_ok=True)
    suffix = path.suffix.lower() if len(path.suffix) <= 10 else ""
    archived = archive_dir / f"{digest}{suffix}"
    if not archived.exists():
        shutil.copy2(path, archived)
    source = SourceFile(
        source_kind=source_kind,
        original_filename=path.name,
        storage_path=str(archived.relative_to(root)),
        sha256=digest,
        size_bytes=path.stat().st_size,
        imported_by=imported_by,
    )
    db.add(source)
    db.flush()
    return source, True


def find_completed_run(db: Session, source_file_id: str, import_type: str) -> ImportRun | None:
    return db.scalar(
        select(ImportRun)
        .where(
            ImportRun.source_file_id == source_file_id,
            ImportRun.import_type == import_type,
            ImportRun.status == "completed",
        )
        .order_by(ImportRun.started_at.desc())
    )


def new_import_run(
    db: Session,
    *,
    source_file_id: str,
    import_type: str,
    started_by: str | None,
) -> ImportRun:
    run = ImportRun(
        source_file_id=source_file_id,
        import_type=import_type,
        status="running",
        started_by=started_by,
    )
    db.add(run)
    db.flush()
    return run


def finish_run(
    run: ImportRun,
    *,
    status: str,
    inserted: int = 0,
    updated: int = 0,
    skipped: int = 0,
    errors: int = 0,
    details: dict | None = None,
) -> None:
    run.status = status
    run.completed_at = datetime.now(timezone.utc)
    run.inserted_count = inserted
    run.updated_count = updated
    run.skipped_count = skipped
    run.error_count = errors
    run.details = details or {}
