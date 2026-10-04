#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import uuid
from pathlib import Path

from sqlalchemy import create_engine, inspect, text

from app.migrations import apply_migrations

REQUIRED_TABLES = {
    "employees", "app_users", "roles", "permissions", "user_roles", "role_permissions",
    "user_sessions", "audit_logs", "facilities", "documents", "source_files", "import_runs",
    "legacy_facility_source_rows", "emergency_import_batches", "emergency_cases",
    "emergency_patients", "emergency_crew_assignments", "emergency_clinical_flags",
}


def main() -> None:
    p = argparse.ArgumentParser(description="Run against an approved PostgreSQL verification database, not production.")
    p.add_argument("--database-url", required=True)
    p.add_argument("--confirm-test-database", action="store_true")
    p.add_argument("--migrations", type=Path, default=Path(__file__).resolve().parents[1] / "db" / "migrations")
    args = p.parse_args()
    if not args.confirm_test_database:
        raise SystemExit("requires --confirm-test-database")
    if not args.database_url.startswith("postgresql"):
        raise SystemExit("PostgreSQL URL required")

    applied = apply_migrations(args.database_url, args.migrations)
    engine = create_engine(args.database_url, pool_pre_ping=True, future=True)
    with engine.connect() as conn:
        tables = set(inspect(conn).get_table_names())
        missing = sorted(REQUIRED_TABLES - tables)
    if missing:
        raise SystemExit(f"missing tables after migration: {missing}")

    # Rollback-only smoke test proves PostgreSQL UUID/JSONB/schema and optimistic update SQL.
    connection = engine.connect()
    tx = connection.begin()
    try:
        building_id = str(uuid.uuid4())
        connection.execute(
            text("INSERT INTO facilities(building_id,name,status,version) VALUES (CAST(:id AS uuid),:name,'active',1)"),
            {"id": building_id, "name": "PHASE1_VERIFY_ONLY"},
        )
        first = connection.execute(
            text("UPDATE facilities SET name=:name,version=2 WHERE building_id=CAST(:id AS uuid) AND version=1"),
            {"id": building_id, "name": "PHASE1_VERIFY_UPDATED"},
        )
        stale = connection.execute(
            text("UPDATE facilities SET name=:name,version=2 WHERE building_id=CAST(:id AS uuid) AND version=1"),
            {"id": building_id, "name": "PHASE1_VERIFY_STALE"},
        )
        connection.execute(
            text("INSERT INTO audit_logs(action,entity_type,entity_id,after_data) VALUES ('verify','facility',:id,CAST(:payload AS jsonb))"),
            {"id": building_id, "payload": '{"phase":1,"pii":false}'},
        )
        assert first.rowcount == 1
        assert stale.rowcount == 0
    finally:
        tx.rollback()
        connection.close()
        engine.dispose()

    print(json.dumps({"ok": True, "applied_migrations": applied, "optimistic_lock": True, "required_tables": len(REQUIRED_TABLES)}, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()