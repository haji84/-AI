#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import inspect
import json
import os
import shutil
import sqlite3
import subprocess
import tarfile
from pathlib import Path

from sqlalchemy.engine import make_url


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
        args += ["-d", url.database]
    env = os.environ.copy()
    if url.password:
        env["PGPASSWORD"] = url.password
    return args, env


def verify_manifest(folder: Path) -> dict:
    manifest = json.loads((folder / "manifest.json").read_text(encoding="utf-8"))
    db_file = folder / manifest["database_file"]
    storage_file = folder / manifest["storage_file"]
    if sha256(db_file) != manifest["database_sha256"]:
        raise SystemExit("database backup checksum mismatch")
    if sha256(storage_file) != manifest["storage_sha256"]:
        raise SystemExit("storage backup checksum mismatch")
    return manifest


def restore_sqlite(source: Path, database_url: str) -> None:
    url = make_url(database_url)
    target_path = Path(url.database or "")
    target_path.parent.mkdir(parents=True, exist_ok=True)
    src = sqlite3.connect(source)
    dst = sqlite3.connect(target_path)
    try:
        src.backup(dst)
    finally:
        dst.close()
        src.close()


def main() -> None:
    p = argparse.ArgumentParser(description="Restore into an explicitly supplied target. Never overwrites the current DB implicitly.")
    p.add_argument("backup", type=Path)
    p.add_argument("--target-database-url", required=True)
    p.add_argument("--target-storage-root", type=Path, required=True)
    p.add_argument("--confirm-restore", action="store_true")
    args = p.parse_args()
    if not args.confirm_restore:
        raise SystemExit("restore requires --confirm-restore")

    folder = args.backup.resolve()
    manifest = verify_manifest(folder)
    db_file = folder / manifest["database_file"]

    if args.target_database_url.startswith("postgresql"):
        if manifest["database_kind"] != "postgresql":
            raise SystemExit("backup database kind does not match PostgreSQL target")
        pg_args, env = postgres_args(args.target_database_url)
        cmd = ["pg_restore", "--clean", "--if-exists", "--no-owner", *pg_args, str(db_file)]
        subprocess.run(cmd, env=env, check=True)
    elif args.target_database_url.startswith("sqlite"):
        if not manifest["database_kind"].startswith("sqlite"):
            raise SystemExit("backup database kind does not match SQLite target")
        restore_sqlite(db_file, args.target_database_url)
    else:
        raise SystemExit("unsupported target database URL")

    target_storage = args.target_storage_root.resolve()
    if target_storage.exists():
        shutil.rmtree(target_storage)
    target_storage.parent.mkdir(parents=True, exist_ok=True)
    with tarfile.open(folder / manifest["storage_file"], "r:gz") as tf:
        members = tf.getmembers()
        for member in members:
            rel = Path(member.name)
            if rel.is_absolute() or ".." in rel.parts or (rel.parts and rel.parts[0] != "storage"):
                raise SystemExit("unsafe storage archive path")
            if member.issym() or member.islnk():
                raise SystemExit("storage archive links are not allowed")
        supports_filter = "filter" in inspect.signature(tf.extract).parameters
        for member in members:
            if supports_filter:
                tf.extract(member, target_storage.parent, filter="data")
            else:
                tf.extract(member, target_storage.parent)
    extracted = target_storage.parent / "storage"
    if not extracted.exists():
        target_storage.mkdir(parents=True, exist_ok=True)
    elif extracted != target_storage:
        if target_storage.exists():
            shutil.rmtree(target_storage)
        extracted.rename(target_storage)
    print(json.dumps({"restored": True, "database_kind": manifest["database_kind"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()