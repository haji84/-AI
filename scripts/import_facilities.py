#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path

from app.db import SessionLocal
from app.importers.facilities import import_facility_workbook


def main() -> None:
    p = argparse.ArgumentParser(description="Import the legacy inspection ledger into the Phase 1 DB.")
    p.add_argument("workbook", type=Path)
    p.add_argument("--started-by", help="app_users.user_id for audit attribution")
    p.add_argument("--force", action="store_true", help="reprocess an already imported identical source file")
    args = p.parse_args()
    with SessionLocal() as db:
        result = import_facility_workbook(db, args.workbook, started_by=args.started_by, force=args.force)
    print(json.dumps(result.safe_dict(), ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()