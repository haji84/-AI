from __future__ import annotations

from sqlalchemy import select

from app.db import SessionLocal
from app.importers.facility_normalization import normalize_facility_from_raw
from app.models import Facility, LegacyFacilitySourceRow


def main() -> None:
    normalized = 0
    with SessionLocal() as db:
        sources = db.scalars(
            select(LegacyFacilitySourceRow).order_by(LegacyFacilitySourceRow.created_at)
        ).all()
        latest: dict[str, LegacyFacilitySourceRow] = {}
        for source in sources:
            latest[source.building_id] = source
        for building_id, source in latest.items():
            facility = db.get(Facility, building_id)
            if not facility:
                continue
            normalize_facility_from_raw(db, facility, source.raw_payload or {})
            normalized += 1
        db.commit()
    print({"normalized_facilities": normalized})


if __name__ == "__main__":
    main()