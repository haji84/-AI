#!/usr/bin/env python3
"""PII-safe Phase 2 facility normalization verification."""
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
    args = p.parse_args()
    root = Path(tempfile.mkdtemp(prefix="fire-ai-phase2-verify-"))
    os.environ["FIRE_AI_DATABASE_URL"] = f"sqlite+pysqlite:///{root / 'verify.sqlite3'}"
    os.environ["FIRE_AI_STORAGE_ROOT"] = str(root / "storage")
    try:
        from sqlalchemy import func, select
        from app.db import Base, SessionLocal, engine
        from app.importers.facilities import import_facility_workbook
        from app.models import Facility, FacilityContact, FacilityDetail, FacilityFloor, LegacyFacilitySourceRow

        Base.metadata.create_all(engine)
        with SessionLocal() as db:
            first = import_facility_workbook(db, args.facility_workbook)
            second = import_facility_workbook(db, args.facility_workbook, force=True)
            counts = {
                "facilities": db.scalar(select(func.count()).select_from(Facility)),
                "facility_details": db.scalar(select(func.count()).select_from(FacilityDetail)),
                "facility_contacts": db.scalar(select(func.count()).select_from(FacilityContact)),
                "facility_floors": db.scalar(select(func.count()).select_from(FacilityFloor)),
                "legacy_source_rows": db.scalar(select(func.count()).select_from(LegacyFacilitySourceRow)),
            }
        assert counts["facilities"] == 611
        assert counts["facility_details"] == 611
        assert counts["facility_contacts"] == 611
        assert counts["legacy_source_rows"] == 611
        assert counts["facility_floors"] > 0
        assert second.inserted == 0 and second.updated == 0 and second.skipped == first.source_rows
        print(json.dumps({"ok": True, "counts": counts}, ensure_ascii=False, sort_keys=True))
    finally:
        shutil.rmtree(root, ignore_errors=True)


if __name__ == "__main__":
    main()