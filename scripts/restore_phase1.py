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
import tempfile
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
    allowed_db_files = {"postgresql": "database.dump", "sqlite-test-only": "database.sqlite3"}
    if manifest.get("database_file") != allowed_db_files.get(manifest.get("database_kind")):
        raise SystemExit("invalid database backup filename/kind")
    if manifest.get("storage_file") != "storage.tar.gz":
        raise SystemExit("invalid storage backup filename")
    db_file = folder / manifest["database_file"]
    storage_file = folder / manifest["storage_file"]
    if db_file.is_symlink() or storage_file.is_symlink():
        raise SystemExit("backup file links are not allowed")
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

    target_storage = args.target_storage_root.resolve()
    if target_storage == Path(target_storage.anchor):
        raise SystemExit("storage target must not be a filesystem root")
    if folder == target_storage or folder.is_relative_to(target_storage) or target_storage.is_relative_to(folder):
        raise SystemExit("backup and target storage must be separate")
    if args.target_storage_root.is_symlink() or (target_storage.exists() and not target_storage.is_dir()):
        raise SystemExit("storage target must be a directory, not a link or file")
    is_postgres = args.target_database_url.startswith("postgresql")
    is_sqlite = args.target_database_url.startswith("sqlite")
    if not is_postgres and not is_sqlite:
        raise SystemExit("unsupported target database URL")
    if is_postgres and manifest["database_kind"] != "postgresql":
        raise SystemExit("backup database kind does not match PostgreSQL target")
    if is_sqlite:
        if manifest["database_kind"] != "sqlite-test-only":
            raise SystemExit("backup database kind does not match SQLite target")
        target_db = Path(make_url(args.target_database_url).database or "").resolve()
        if target_db == db_file.resolve() or target_db.is_relative_to(folder):
            raise SystemExit("target database must not overwrite backup")
        if target_db.is_relative_to(target_storage):
            raise SystemExit("target database must be outside replaced storage")

    # Validate and stage every byte before touching the target DB or storage.
    # Extraction never uses a neighbor named 'storage'.
    target_storage.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".fire-ai-restore-", dir=target_storage.parent) as staging_dir:
        staged = Path(staging_dir) / "storage"
        staged.mkdir()
        with tarfile.open(folder / manifest["storage_file"], "r:gz") as tf:
            members = tf.getmembers()
            for member in members:
                rel = Path(member.name)
                if rel.is_absolute() or ".." in rel.parts or not rel.parts or rel.parts[0] != "storage":
                    raise SystemExit("unsafe storage archive path")
                if not (member.isdir() or member.isfile()):
                    raise SystemExit("storage archive links and special files are not allowed")
            for member in members:
                dest = staged.joinpath(*Path(member.name).parts[1:])
                if member.isdir():
                    dest.mkdir(parents=True, exist_ok=True)
                else:
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    with tf.extractfile(member) as source, dest.open("wb") as output:
                        shutil.copyfileobj(source, output)
        if is_postgres:
            pg_args, env = postgres_args(args.target_database_url)
            cmd = ["pg_restore", "--exit-on-error", "--single-transaction", "--clean", "--if-exists", "--no-owner", *pg_args, str(db_file)]
            subprocess.run(cmd, env=env, check=True)
        else:
            restore_sqlite(db_file, args.target_database_url)
        # Keep old files until the staged directory can replace them.
        previous = Path(staging_dir) / "previous"
        if target_storage.exists():
            target_storage.rename(previous)
        try:
            staged.rename(target_storage)
        except OSError:
            if previous.exists():
                previous.rename(target_storage)
            raise
    print(json.dumps({"restored": True, "database_kind": manifest["database_kind"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()