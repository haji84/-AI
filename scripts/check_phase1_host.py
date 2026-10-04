#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import shutil
import tempfile
from pathlib import Path

from sqlalchemy import create_engine, text

from app.settings import settings


def main() -> None:
    p = argparse.ArgumentParser(description="PII-free readiness check for the real Phase 1 LAN host.")
    p.add_argument("--database-url", default=settings.database_url)
    p.add_argument("--storage-root", type=Path, default=Path(settings.storage_root))
    args = p.parse_args()

    checks: dict[str, object] = {}
    checks["postgres_url"] = args.database_url.startswith("postgresql")
    checks["pg_dump"] = bool(shutil.which("pg_dump"))
    checks["pg_restore"] = bool(shutil.which("pg_restore"))

    try:
        engine = create_engine(args.database_url, pool_pre_ping=True, future=True)
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        engine.dispose()
        checks["database_connection"] = True
    except Exception as exc:
        checks["database_connection"] = False
        checks["database_error_type"] = type(exc).__name__

    try:
        args.storage_root.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(dir=args.storage_root, prefix="phase1-check-", delete=True) as f:
            f.write(b"ok")
            f.flush()
        checks["storage_writable"] = True
    except Exception as exc:
        checks["storage_writable"] = False
        checks["storage_error_type"] = type(exc).__name__

    ok = all(bool(checks.get(k)) for k in ("postgres_url", "pg_dump", "pg_restore", "database_connection", "storage_writable"))
    print(json.dumps({"ok": ok, "checks": checks}, ensure_ascii=False, sort_keys=True))
    raise SystemExit(0 if ok else 2)


if __name__ == "__main__":
    main()