#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import sqlite3
import subprocess
import tarfile
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy.engine import make_url

from app.settings import settings
from app.backup_contract import binding, dump_identity, postgres_args, record_admin_audit
from app.tenant import TenantBoundaryError


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def backup_sqlite(database_url: str, dest: Path) -> None:
    url = make_url(database_url)
    source = Path(url.database or "")
    if not source.exists():
        raise FileNotFoundError(source)
    src = sqlite3.connect(source)
    target = sqlite3.connect(dest)
    try:
        src.backup(target)
    finally:
        target.close()
        src.close()


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--database-url", default=settings.database_url)
    p.add_argument("--storage-root", type=Path, default=Path(settings.storage_root))
    p.add_argument("--destination", type=Path, required=True)
    p.add_argument("--confirm-writers-stopped", action="store_true")
    p.add_argument("--release-id")
    args = p.parse_args()
    tenant_id = settings.tenant_id
    migrations = []
    if tenant_id or settings.production_mode or args.database_url.startswith("postgresql"):
        if not tenant_id or not args.confirm_writers_stopped or not args.release_id:
            raise SystemExit("department backup requires configured UUID, --confirm-writers-stopped and --release-id")
        try:
            migrations = binding(args.database_url, args.storage_root, tenant_id)
        except TenantBoundaryError as exc:
            raise SystemExit(str(exc)) from None
    storage_root = args.storage_root.resolve()
    destination = args.destination.resolve()
    if destination == storage_root or destination.is_relative_to(storage_root):
        raise SystemExit("backup destination must be outside originals")

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    folder = args.destination.resolve() / f"fire-ai-backup-{stamp}"
    folder.mkdir(parents=True, exist_ok=False, mode=0o700)

    if tenant_id:
        record_admin_audit(args.database_url, tenant_id, 'tenant.backup.started',
                           {'release_id': args.release_id, 'backup': folder.name, 'writers_stopped': True})
    if args.database_url.startswith("postgresql"):
        dump = folder / "database.dump"
        pg_args, env = postgres_args(args.database_url)
        cmd = ["pg_dump", "--format=custom", "--no-owner", "--file", str(dump), *pg_args]
        subprocess.run(cmd, env=env, check=True)
        db_kind = "postgresql"
    elif args.database_url.startswith("sqlite"):
        dump = folder / "database.sqlite3"
        backup_sqlite(args.database_url, dump)
        db_kind = "sqlite-test-only"
    else:
        raise SystemExit("unsupported database URL")

    storage_archive = folder / "storage.tar.gz"
    storage_root = args.storage_root.resolve()
    with tarfile.open(storage_archive, "w:gz") as tf:
        if storage_root.exists():
            tf.add(storage_root, arcname="storage", recursive=True)

    if tenant_id:
        try:
            if dump_identity(dump, db_kind) != tenant_id:
                raise TenantBoundaryError("Dump belongs to another department")
        except TenantBoundaryError as exc:
            raise SystemExit(str(exc)) from None
    manifest = {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "database_kind": db_kind,
        "database_file": dump.name,
        "database_sha256": sha256(dump),
        "storage_file": storage_archive.name,
        "storage_sha256": sha256(storage_archive),
    }
    if tenant_id:
        manifest.update(tenant_id=tenant_id, release_id=args.release_id,
                        consistency="writers-stopped", migrations=migrations, format_version=2)
    (folder / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"backup": str(folder), "database_kind": db_kind}, ensure_ascii=False))


if __name__ == "__main__":
    main()