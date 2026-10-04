#!/usr/bin/env python3
"""PII-safe Phase 1 import verification using a temporary SQLite database.

This never prints source row values. The temporary DB/storage are deleted on success/failure.
SQLite here validates import/idempotency behavior only; PostgreSQL remains the production target.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import tempfile
from pathlib import Path


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("facility_workbook", type=Path)
    p.add_argument("emergency_workbook", type=Path)
    args = p.parse_args()

    root = Path(tempfile.mkdtemp(prefix="fire-ai-phase1-verify-"))
    db_path = root / "verify.sqlite3"
    storage = root / "storage"
    os.environ["FIRE_AI_DATABASE_URL"] = f"sqlite+pysqlite:///{db_path}"
    os.environ["FIRE_AI_STORAGE_ROOT"] = str(storage)

    try:
        from sqlalchemy import func, select
        from app.db import Base, SessionLocal, engine
        from app.importers.emergency import import_emergency_workbook
        from app.importers.facilities import import_facility_workbook
        from app.models import (
            EmergencyCase,
            EmergencyCrewAssignment,
            EmergencyPatient,
            Facility,
            LegacyFacilitySourceRow,
        )

        Base.metadata.create_all(engine)
        with SessionLocal() as db:
            f1 = import_facility_workbook(db, args.facility_workbook)
            f2 = import_facility_workbook(db, args.facility_workbook, force=True)
            e1 = import_emergency_workbook(db, args.emergency_workbook)
            e2 = import_emergency_workbook(db, args.emergency_workbook, force=True)
            counts = {
                "facilities": db.scalar(select(func.count()).select_from(Facility)),
                "facility_source_rows": db.scalar(select(func.count()).select_from(LegacyFacilitySourceRow)),
                "emergency_cases": db.scalar(select(func.count()).select_from(EmergencyCase)),
                "emergency_patients": db.scalar(select(func.count()).select_from(EmergencyPatient)),
                "emergency_crew": db.scalar(select(func.count()).select_from(EmergencyCrewAssignment)),
            }

        assert f2.inserted == 0 and f2.updated == 0 and f2.skipped == f1.source_rows
        assert e2.cases_inserted == 0 and e2.cases_updated == 0 and e2.cases_skipped == counts["emergency_cases"]
        assert e2.patients_inserted == 0 and e2.patients_updated == 0 and e2.patients_skipped == counts["emergency_patients"]
        assert e2.crew_inserted == 0 and e2.crew_updated == 0 and e2.crew_skipped == counts["emergency_crew"]
        print(json.dumps({"ok": True, "counts": counts, "unresolved_crew": e1.unresolved_crew}, ensure_ascii=False, sort_keys=True))
    finally:
        shutil.rmtree(root, ignore_errors=True)


if __name__ == "__main__":
    main()