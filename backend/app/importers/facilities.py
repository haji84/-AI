from __future__ import annotations

from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..audit import write_audit
from ..models import Facility, LegacyFacilitySourceRow
from .common import find_completed_run, finish_run, get_or_create_source_file, new_import_run
from .ooxml import read_sheet
from .facility_normalization import normalize_facility_from_raw

SOURCE_KIND = "inspection_ledger_xlsm"
IMPORT_TYPE = "legacy_facilities"
SHEET = "DB保存"


@dataclass
class ImportSummary:
    status: str
    import_run_id: str
    source_sha256: str
    inserted: int
    updated: int
    skipped: int
    errors: int
    source_rows: int

    def safe_dict(self) -> dict:
        return asdict(self)


def _clean(value: str | None) -> str | None:
    text = (value or "").strip()
    return text or None


def import_facility_workbook(
    db: Session,
    path: Path,
    *,
    started_by: str | None = None,
    force: bool = False,
) -> ImportSummary:
    path = path.resolve()
    if not path.exists():
        raise FileNotFoundError(path)

    source, _ = get_or_create_source_file(
        db, path=path, source_kind=SOURCE_KIND, imported_by=started_by
    )
    db.commit()

    completed = find_completed_run(db, source.source_file_id, IMPORT_TYPE)
    if completed and not force:
        d = completed.details or {}
        return ImportSummary(
            status="already_imported",
            import_run_id=completed.import_run_id,
            source_sha256=source.sha256,
            inserted=completed.inserted_count,
            updated=completed.updated_count,
            skipped=completed.skipped_count,
            errors=completed.error_count,
            source_rows=int(d.get("source_rows", 0)),
        )

    run = new_import_run(
        db, source_file_id=source.source_file_id, import_type=IMPORT_TYPE, started_by=started_by
    )
    db.commit()

    inserted = updated = skipped = errors = 0
    source_rows = 0
    try:
        headers, rows = read_sheet(path, SHEET, header_row=2)
        required = {"C": "名称1メイショウ", "G": "整理番号セイリバンゴウ", "I": "所在地ショザイチ", "IP": "内部キー"}
        header_errors = {
            col: {"expected": expected, "actual": headers.get(col)}
            for col, expected in required.items()
            if headers.get(col) != expected
        }
        if header_errors:
            raise ValueError(f"legacy facility header mismatch: {header_errors}")

        for row in rows:
            # Empty tail rows/formula artifacts are not business records.
            name = _clean(row.by_column.get("C"))
            legacy_key = _clean(row.by_column.get("IP"))
            if not name and not legacy_key:
                continue
            source_rows += 1
            if not name or not legacy_key:
                errors += 1
                continue

            typed = {
                "legacy_category_key": _clean(row.by_column.get("A")),
                "legacy_serial_no": _clean(row.by_column.get("G")),
                "legacy_global_serial": _clean(row.by_column.get("HZ")),
                "name": name,
                "phone": _clean(row.by_column.get("D")),
                "address": _clean(row.by_column.get("I")),
            }
            facility = db.scalar(select(Facility).where(Facility.legacy_internal_key == legacy_key))
            if facility is None:
                facility = Facility(legacy_internal_key=legacy_key, **typed)
                db.add(facility)
                db.flush()
                inserted += 1
            else:
                changed = False
                for field, value in typed.items():
                    if getattr(facility, field) != value:
                        setattr(facility, field, value)
                        changed = True
                if changed:
                    facility.version += 1
                    facility.updated_at = datetime.now(timezone.utc)
                    updated += 1
                else:
                    skipped += 1

            raw = {col: value for col, value in row.by_column.items() if value != ""}
            normalize_facility_from_raw(db, facility, raw)
            source_row = db.scalar(
                select(LegacyFacilitySourceRow).where(
                    LegacyFacilitySourceRow.source_file_id == source.source_file_id,
                    LegacyFacilitySourceRow.source_sheet == SHEET,
                    LegacyFacilitySourceRow.source_row_no == row.row_no,
                )
            )
            if source_row is None:
                db.add(
                    LegacyFacilitySourceRow(
                        source_file_id=source.source_file_id,
                        building_id=facility.building_id,
                        legacy_internal_key=legacy_key,
                        source_sheet=SHEET,
                        source_row_no=row.row_no,
                        raw_payload=raw,
                    )
                )
            else:
                source_row.building_id = facility.building_id
                source_row.legacy_internal_key = legacy_key
                source_row.raw_payload = raw

        if errors:
            raise ValueError(f"{errors} legacy facility rows missing required name/internal key")

        run = db.get(type(run), run.import_run_id)
        finish_run(
            run,
            status="completed",
            inserted=inserted,
            updated=updated,
            skipped=skipped,
            errors=0,
            details={"source_rows": source_rows, "sheet": SHEET},
        )
        write_audit(
            db,
            user_id=started_by,
            action="facility.import",
            entity_type="import_run",
            entity_id=run.import_run_id,
            after={"inserted": inserted, "updated": updated, "skipped": skipped, "source_rows": source_rows},
        )
        db.commit()
    except Exception as exc:
        db.rollback()
        failed = db.get(type(run), run.import_run_id)
        if failed:
            finish_run(failed, status="failed", errors=max(errors, 1), details={"error_type": type(exc).__name__})
            db.commit()
        raise

    return ImportSummary(
        status="completed",
        import_run_id=run.import_run_id,
        source_sha256=source.sha256,
        inserted=inserted,
        updated=updated,
        skipped=skipped,
        errors=0,
        source_rows=source_rows,
    )