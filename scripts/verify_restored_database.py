#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json

from sqlalchemy import create_engine, inspect, text

REQUIRED_TABLES = {
    "employees", "app_users", "roles", "permissions", "audit_logs", "facilities",
    "source_files", "import_runs", "documents", "emergency_cases", "emergency_patients",
    "emergency_crew_assignments", "legacy_facility_source_rows",
}


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--database-url", required=True)
    args = p.parse_args()
    engine = create_engine(args.database_url, pool_pre_ping=True, future=True)
    with engine.connect() as conn:
        conn.execute(text("SELECT 1"))
        tables = set(inspect(conn).get_table_names())
        missing = sorted(REQUIRED_TABLES - tables)
        counts = {}
        for table in ("facilities", "emergency_cases", "emergency_patients", "emergency_crew_assignments"):
            if table in tables:
                counts[table] = int(conn.execute(text(f"SELECT count(*) FROM {table}")).scalar_one())
    if missing:
        raise SystemExit(f"restore verification failed; missing tables: {missing}")
    print(json.dumps({"ok": True, "counts": counts}, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()