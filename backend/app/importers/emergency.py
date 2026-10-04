from __future__ import annotations

from dataclasses import dataclass, asdict
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..audit import write_audit
from ..models import (
    EmergencyCase,
    EmergencyCrewAssignment,
    EmergencyImportBatch,
    EmergencyPatient,
    Employee,
)
from .common import find_completed_run, finish_run, get_or_create_source_file, new_import_run
from .ooxml import SheetRow, read_sheet

SOURCE_KIND = "emergency_reporting_xlsm"
IMPORT_TYPE = "legacy_emergency_xlsm"
CASE_SHEET = "CSV_事案台帳"
PATIENT_SHEET = "CSV_救護者台帳"
CREW_SHEET = "CSV_出動隊員"

REQUIRED = {
    CASE_SHEET: {"覚知年月", "署所ｺｰﾄﾞ", "出場番号"},
    PATIENT_SHEET: {"覚知年月", "署所ｺｰﾄﾞ", "出場番号", "救護者番号"},
    CREW_SHEET: {"覚知年月", "署所ｺｰﾄﾞ", "出場番号", "隊員種別", "隊員ｺｰﾄﾞ"},
}


@dataclass
class EmergencyImportSummary:
    status: str
    import_run_id: str
    source_sha256: str
    cases_inserted: int
    cases_updated: int
    cases_skipped: int
    patients_inserted: int
    patients_updated: int
    patients_skipped: int
    crew_inserted: int
    crew_updated: int
    crew_skipped: int
    unresolved_crew: int
    errors: int

    def safe_dict(self) -> dict:
        return asdict(self)


def norm(value: str | None) -> str:
    return (value or "").strip()


def _int_or_none(value: str | None) -> int | None:
    text = norm(value)
    if not text:
        return None
    try:
        number = float(text)
        return int(number) if number.is_integer() else None
    except ValueError:
        return None


def _excel_date(value: str | None) -> date | None:
    text = norm(value)
    if not text:
        return None
    try:
        serial = float(text)
        if serial <= 0:
            return None
        return (datetime(1899, 12, 30) + timedelta(days=serial)).date()
    except ValueError:
        pass
    for fmt in ("%Y/%m/%d", "%Y-%m-%d", "%Y.%m.%d"):
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    return None


def _excel_time(value: str | None) -> time | None:
    text = norm(value)
    if not text:
        return None
    try:
        serial = float(text)
        seconds = int(round((serial % 1) * 86400)) % 86400
        return time(seconds // 3600, (seconds % 3600) // 60, seconds % 60)
    except ValueError:
        pass
    for fmt in ("%H:%M:%S", "%H:%M"):
        try:
            return datetime.strptime(text, fmt).time()
        except ValueError:
            continue
    return None


def _case_key(row: dict[str, str]) -> str:
    parts = [norm(row.get("覚知年月")), norm(row.get("署所ｺｰﾄﾞ")), norm(row.get("出場番号"))]
    if any(not x for x in parts):
        raise ValueError("case key is incomplete")
    return "|".join(parts)


def _raw_by_header(row: SheetRow, headers: dict[str, str]) -> dict[str, str]:
    # Headers are expected unique in the audited emergency sheets. If a duplicate ever
    # appears, retain the Excel column in the key rather than losing data.
    out: dict[str, str] = {}
    seen: set[str] = set()
    for col, value in row.by_column.items():
        header = headers.get(col, "").strip() or col
        key = header if header not in seen else f"{col}:{header}"
        seen.add(header)
        out[key] = value
    return out


def _changed(obj, values: dict) -> bool:
    changed = False
    for field, value in values.items():
        if getattr(obj, field) != value:
            setattr(obj, field, value)
            changed = True
    return changed


def _validate_headers(headers: dict[str, str], sheet: str) -> None:
    present = set(headers.values())
    missing = REQUIRED[sheet] - present
    if missing:
        raise ValueError(f"{sheet}: missing required headers: {sorted(missing)}")


def import_emergency_workbook(
    db: Session,
    path: Path,
    *,
    started_by: str | None = None,
    force: bool = False,
) -> EmergencyImportSummary:
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
        return EmergencyImportSummary(
            status="already_imported",
            import_run_id=completed.import_run_id,
            source_sha256=source.sha256,
            cases_inserted=int(d.get("cases_inserted", 0)),
            cases_updated=int(d.get("cases_updated", 0)),
            cases_skipped=int(d.get("cases_skipped", 0)),
            patients_inserted=int(d.get("patients_inserted", 0)),
            patients_updated=int(d.get("patients_updated", 0)),
            patients_skipped=int(d.get("patients_skipped", 0)),
            crew_inserted=int(d.get("crew_inserted", 0)),
            crew_updated=int(d.get("crew_updated", 0)),
            crew_skipped=int(d.get("crew_skipped", 0)),
            unresolved_crew=int(d.get("unresolved_crew", 0)),
            errors=completed.error_count,
        )

    run = new_import_run(
        db, source_file_id=source.source_file_id, import_type=IMPORT_TYPE, started_by=started_by
    )
    db.commit()

    counts = {
        "cases_inserted": 0,
        "cases_updated": 0,
        "cases_skipped": 0,
        "patients_inserted": 0,
        "patients_updated": 0,
        "patients_skipped": 0,
        "crew_inserted": 0,
        "crew_updated": 0,
        "crew_skipped": 0,
        "unresolved_crew": 0,
    }
    errors = 0
    try:
        case_headers, case_rows = read_sheet(path, CASE_SHEET)
        patient_headers, patient_rows = read_sheet(path, PATIENT_SHEET)
        crew_headers, crew_rows = read_sheet(path, CREW_SHEET)
        _validate_headers(case_headers, CASE_SHEET)
        _validate_headers(patient_headers, PATIENT_SHEET)
        _validate_headers(crew_headers, CREW_SHEET)

        batch = EmergencyImportBatch(
            import_run_id=run.import_run_id,
            source_system="legacy_xlsm",
            status="running",
        )
        db.add(batch)
        db.flush()

        case_ids: dict[str, str] = {}
        for row in case_rows:
            h = row.by_header
            if not any(norm(h.get(k)) for k in ("覚知年月", "署所ｺｰﾄﾞ", "出場番号")):
                continue
            key = _case_key(h)
            values = {
                "call_month": norm(h.get("覚知年月")) or None,
                "station_code": norm(h.get("署所ｺｰﾄﾞ")) or None,
                "dispatch_number": norm(h.get("出場番号")) or None,
                "ambulance_code": norm(h.get("救急隊ｺｰﾄﾞ")) or None,
                "call_date": _excel_date(h.get("覚知年月日")),
                "call_time": _excel_time(h.get("覚知時間")),
                "dispatch_time": _excel_time(h.get("出場時間")),
                "scene_arrival_time": _excel_time(h.get("現場到着時間")),
                "leave_scene_time": _excel_time(h.get("引揚時間")),
                "return_station_time": _excel_time(h.get("帰署時間")),
                "incident_area_code": norm(h.get("出動地区ｺｰﾄﾞ")) or None,
                "incident_address": norm(h.get("出動地区住所")) or None,
                "activity_type": norm(h.get("活動種類")) or None,
                "incident_type": norm(h.get("事故種別ｺｰﾄﾞ")) or None,
                "incident_place": norm(h.get("発生場所")) or None,
                "dispatch_vehicle": norm(h.get("出動車両")) or None,
                "command_text": norm(h.get("指令内容")) or None,
                "cpr_wishes_none": norm(h.get("心肺蘇生希望なし")) or None,
                "raw_payload": _raw_by_header(row, case_headers),
            }
            case = db.scalar(select(EmergencyCase).where(EmergencyCase.source_case_key == key))
            if case is None:
                case = EmergencyCase(source_case_key=key, source_batch_id=batch.batch_id, **values)
                db.add(case)
                db.flush()
                counts["cases_inserted"] += 1
            elif _changed(case, values):
                case.source_batch_id = batch.batch_id
                case.version += 1
                case.updated_at = datetime.now(timezone.utc)
                counts["cases_updated"] += 1
            else:
                counts["cases_skipped"] += 1
            case_ids[key] = case.emergency_case_id

        for row in patient_rows:
            h = row.by_header
            if not any(norm(h.get(k)) for k in ("覚知年月", "署所ｺｰﾄﾞ", "出場番号", "救護者番号")):
                continue
            case_key = _case_key(h)
            case_id = case_ids.get(case_key)
            if case_id is None:
                existing_case = db.scalar(select(EmergencyCase).where(EmergencyCase.source_case_key == case_key))
                if existing_case:
                    case_id = existing_case.emergency_case_id
            if case_id is None:
                raise ValueError("patient references a missing emergency case")
            patient_number = _int_or_none(h.get("救護者番号"))
            if patient_number is None:
                raise ValueError("patient number is missing or invalid")
            values = {
                "sex": norm(h.get("性別")) or None,
                "age": _int_or_none(h.get("年令")),
                "age_class": norm(h.get("年令分類")) or None,
                "residence_class": norm(h.get("居住分類")) or None,
                "hospital_code": norm(h.get("病院ｺｰﾄﾞ")) or None,
                "hospital_category": norm(h.get("医療機関種別ｺｰﾄﾞ")) or None,
                "department_code": norm(h.get("診療科目ｺｰﾄﾞ")) or None,
                "severity_code": norm(h.get("傷病程度ｺｰﾄﾞ")) or None,
                "injury_class_major": norm(h.get("傷病分類_大分類")) or None,
                "injury_class_middle": norm(h.get("傷病分類_中分類")) or None,
                "injury_class_minor": norm(h.get("傷病分類_小分類")) or None,
                "resuscitation_code": norm(h.get("救急蘇生ｺｰﾄﾞ")) or None,
                "first_aid_flag": norm(h.get("応急処置ﾌﾗｸﾞ")) or None,
                "condition_text": norm(h.get("傷病者状態")) or None,
                "diagnosis_text": norm(h.get("傷病名")) or None,
                "symptoms_text": norm(h.get("症状")) or None,
                "medical_history_text": norm(h.get("病歴診療科目")) or None,
                "other_information_text": norm(h.get("その他情報")) or None,
                "team_urgency": norm(h.get("救急隊判断緊急度")) or None,
                "raw_payload": _raw_by_header(row, patient_headers),
            }
            patient = db.scalar(
                select(EmergencyPatient).where(
                    EmergencyPatient.emergency_case_id == case_id,
                    EmergencyPatient.patient_number == patient_number,
                )
            )
            if patient is None:
                db.add(EmergencyPatient(emergency_case_id=case_id, patient_number=patient_number, source_batch_id=batch.batch_id, **values))
                counts["patients_inserted"] += 1
            elif _changed(patient, values):
                patient.source_batch_id = batch.batch_id
                patient.version += 1
                patient.updated_at = datetime.now(timezone.utc)
                counts["patients_updated"] += 1
            else:
                counts["patients_skipped"] += 1

        employee_by_code = {
            e.employee_code: e.employee_id
            for e in db.scalars(select(Employee).where(Employee.employee_code.is_not(None))).all()
            if e.employee_code
        }
        for row in crew_rows:
            h = row.by_header
            if not any(norm(h.get(k)) for k in ("覚知年月", "署所ｺｰﾄﾞ", "出場番号", "隊員種別", "隊員ｺｰﾄﾞ")):
                continue
            case_key = _case_key(h)
            case_id = case_ids.get(case_key)
            if case_id is None:
                existing_case = db.scalar(select(EmergencyCase).where(EmergencyCase.source_case_key == case_key))
                if existing_case:
                    case_id = existing_case.emergency_case_id
            if case_id is None:
                raise ValueError("crew row references a missing emergency case")

            role = norm(h.get("隊員種別"))
            if not role:
                raise ValueError("crew role is missing")
            code = norm(h.get("隊員ｺｰﾄﾞ"))
            if code:
                record_key = f"{case_key}|{role}|{code}"
                identity_status = "complete"
            else:
                record_key = f"{source.sha256}|{CREW_SHEET}|{row.row_no}"
                identity_status = "missing_crew_code"
                counts["unresolved_crew"] += 1
            values = {
                "source_row_no": row.row_no,
                "source_identity_status": identity_status,
                "crew_role": role,
                "source_crew_code": code or None,
                "employee_id": employee_by_code.get(code) if code else None,
                "qualification": norm(h.get("隊員資格")) or None,
                "rank_name": norm(h.get("階級")) or None,
                "raw_payload": _raw_by_header(row, crew_headers),
            }
            assignment = db.scalar(
                select(EmergencyCrewAssignment).where(
                    EmergencyCrewAssignment.source_record_key == record_key
                )
            )
            if assignment is None:
                db.add(EmergencyCrewAssignment(emergency_case_id=case_id, source_record_key=record_key, source_batch_id=batch.batch_id, **values))
                counts["crew_inserted"] += 1
            elif _changed(assignment, {"emergency_case_id": case_id, **values}):
                assignment.source_batch_id = batch.batch_id
                counts["crew_updated"] += 1
            else:
                counts["crew_skipped"] += 1

        db.flush()
        batch.status = "completed"
        batch.completed_at = datetime.now(timezone.utc)

        total_inserted = counts["cases_inserted"] + counts["patients_inserted"] + counts["crew_inserted"]
        total_updated = counts["cases_updated"] + counts["patients_updated"] + counts["crew_updated"]
        total_skipped = counts["cases_skipped"] + counts["patients_skipped"] + counts["crew_skipped"]
        run = db.get(type(run), run.import_run_id)
        finish_run(
            run,
            status="completed",
            inserted=total_inserted,
            updated=total_updated,
            skipped=total_skipped,
            errors=0,
            details={**counts, "case_rows": len(case_rows), "patient_rows": len(patient_rows), "crew_rows": len(crew_rows)},
        )
        write_audit(
            db,
            user_id=started_by,
            action="emergency.import",
            entity_type="import_run",
            entity_id=run.import_run_id,
            after={
                "cases": len(case_rows),
                "patients": len(patient_rows),
                "crew": len(crew_rows),
                "unresolved_crew": counts["unresolved_crew"],
            },
        )
        db.commit()
    except Exception as exc:
        db.rollback()
        failed = db.get(type(run), run.import_run_id)
        if failed:
            finish_run(failed, status="failed", errors=max(errors, 1), details={"error_type": type(exc).__name__})
            db.commit()
        raise

    return EmergencyImportSummary(
        status="completed",
        import_run_id=run.import_run_id,
        source_sha256=source.sha256,
        errors=0,
        **counts,
    )