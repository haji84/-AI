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


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def postgres_args(database_url: str) -> tuple[list[str], dict[str, str]]:
    url = make_url(database_url)
    args: list[str] = []
    if url.host:
        args += ["-h", url.host]
    if url.port:
        args += ["-p", str(url.port)]
    if url.username:
        args += ["-U", url.username]
    if url.database:
        args += [url.database]
    env = os.environ.copy()
    if url.password:
        env["PGPASSWORD"] = url.password
    return args, env


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
    args = p.parse_args()

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    folder = args.destination.resolve() / f"fire-ai-backup-{stamp}"
    folder.mkdir(parents=True, exist_ok=False)

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

    manifest = {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "database_kind": db_kind,
        "database_file": dump.name,
        "database_sha256": sha256(dump),
        "storage_file": storage_archive.name,
        "storage_sha256": sha256(storage_archive),
    }
    (folder / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"backup": str(folder), "database_kind": db_kind}, ensure_ascii=False))


if __name__ == "__main__":
    main()