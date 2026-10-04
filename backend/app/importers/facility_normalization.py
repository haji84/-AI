from __future__ import annotations

import re
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from ..models import (
    EquipmentInspectionReport,
    Facility,
    FacilityContact,
    FacilityDetail,
    FacilityFloor,
    FireManagementAssignment,
    FirePlan,
    GuidanceRecord,
    InspectionReportingProfile,
)

_NUM_RE = re.compile(r"[-+]?\d+(?:\.\d+)?")


def _text(raw: dict, col: str) -> str | None:
    value = str(raw.get(col, "") or "").strip()
    return value or None


def _integer(raw: dict, col: str) -> int | None:
    value = _text(raw, col)
    if not value:
        return None
    value = value.replace(",", "")
    m = _NUM_RE.search(value)
    if not m:
        return None
    try:
        return int(Decimal(m.group(0)))
    except (InvalidOperation, ValueError):
        return None


def _decimal(raw: dict, col: str) -> Decimal | None:
    value = _text(raw, col)
    if not value:
        return None
    value = value.replace(",", "")
    m = _NUM_RE.search(value)
    if not m:
        return None
    try:
        return Decimal(m.group(0)).quantize(Decimal("0.01"))
    except InvalidOperation:
        return None




def _legacy_date_text(value: str | None) -> tuple[date | None, str | None]:
    raw = (value or "").strip()
    if not raw:
        return None, None
    # Excel serial dates in the legacy workbook.
    if re.fullmatch(r"\d+(?:\.0+)?", raw):
        try:
            serial = int(float(raw))
            if 1 <= serial <= 100000:
                return date(1899, 12, 30) + timedelta(days=serial), raw
        except (ValueError, OverflowError):
            pass
    # Gregorian date embedded in free text.
    m = re.search(r"(20\d{2})[./-](\d{1,2})[./-](\d{1,2})", raw)
    if m:
        try:
            return date(int(m.group(1)), int(m.group(2)), int(m.group(3))), raw
        except ValueError:
            pass
    # Japanese era date embedded in free text.
    m = re.search(r"([RrHhSs])\s*(\d{1,2})[.年/](\d{1,2})[.月/](\d{1,2})", raw)
    if m:
        base = {"R": 2018, "H": 1988, "S": 1925}[m.group(1).upper()]
        try:
            return date(base + int(m.group(2)), int(m.group(3)), int(m.group(4))), raw
        except ValueError:
            pass
    return None, raw


def _legacy_decimal_text(value: str | None) -> Decimal | None:
    raw = (value or "").strip().replace(",", "")
    if not raw:
        return None
    m = _NUM_RE.search(raw)
    if not m:
        return None
    try:
        return Decimal(m.group(0)).quantize(Decimal("0.01"))
    except InvalidOperation:
        return None


def normalize_facility_from_raw(db: Session, facility: Facility, raw: dict) -> None:
    """Normalize only Phase-0 confirmed fields. Unresolved columns stay raw/read-only."""
    now = datetime.now(timezone.utc)

    # Confirmed scalar legacy columns that also belong on the facility row.
    facility.phone = _text(raw, "D")
    facility.legacy_serial_no = _text(raw, "G")
    facility.legacy_global_serial = _text(raw, "HZ")

    detail = db.get(FacilityDetail, facility.building_id)
    if detail is None:
        detail = FacilityDetail(building_id=facility.building_id)
        db.add(detail)
    detail.legacy_book_type = _text(raw, "E")
    detail.content_as_of = _text(raw, "F")
    detail.classification_code = _text(raw, "H")
    detail.classification_detail_1 = _text(raw, "HX")
    detail.classification_detail_2 = _text(raw, "HY")
    detail.zoning = _text(raw, "R")
    detail.article8_partition = _text(raw, "S")
    detail.structure = _text(raw, "T")
    detail.above_ground_floors = _integer(raw, "U")
    detail.basement_floors = _integer(raw, "V")
    detail.building_area = _decimal(raw, "W")
    detail.total_floor_area = _decimal(raw, "X")
    detail.updated_at = now

    contact = db.get(FacilityContact, facility.building_id)
    if contact is None:
        contact = FacilityContact(building_id=facility.building_id)
        db.add(contact)
    contact.representative_address = _text(raw, "J")
    contact.representative_title = _text(raw, "K")
    contact.representative_name = _text(raw, "L")
    contact.representative_phone = _text(raw, "M")
    contact.updated_at = now

    floor_label_cols = ["Y", "Z", "AA", "AB", "AC", "AD", "AE"]
    floor_area_cols = ["AF", "AG", "AH", "AI", "AJ", "AK", "AL"]
    use_cols = ["AN", "AO", "AP", "AQ", "AR", "AS", "AT"]
    occupancy_cols = ["AU", "AV", "AW", "AX", "AY", "AZ", "BA"]
    employee_cols = ["BC", "BD", "BE", "BF", "BG", "BH", "BI"]
    window_cols = ["BK", "BL", "BM", "BN", "BO", "BP", "BQ"]
    curtain_cols = ["BR", "BS", "BT", "BU", "BV", "BW", "BX"]
    carpet_cols = ["BY", "BZ", "CA", "CB", "CC", "CD", "CE"]
    plywood_cols = ["CF", "CG", "CH", "CI", "CJ", "CK", "CL"]

    new_floors: list[dict] = []
    for idx in range(7):
        values = {
            "floor_number": idx + 1,
            "floor_label": _text(raw, floor_label_cols[idx]) or f"{idx + 1}階",
            "floor_area": _decimal(raw, floor_area_cols[idx]),
            "use_name": _text(raw, use_cols[idx]),
            "occupancy_count": _integer(raw, occupancy_cols[idx]),
            "employee_count": _integer(raw, employee_cols[idx]),
            "windowless_status": _text(raw, window_cols[idx]),
            "curtain_status": _text(raw, curtain_cols[idx]),
            "carpet_status": _text(raw, carpet_cols[idx]),
            "plywood_status": _text(raw, plywood_cols[idx]),
        }
        meaningful = any(
            values[k] not in (None, "", f"{idx + 1}階")
            for k in values
            if k not in {"floor_number"}
        )
        if meaningful:
            new_floors.append(values)

    db.execute(delete(FacilityFloor).where(FacilityFloor.building_id == facility.building_id))
    for values in new_floors:
        db.add(FacilityFloor(building_id=facility.building_id, **values))

    detail.occupancy_total = sum(x["occupancy_count"] or 0 for x in new_floors) if new_floors else _integer(raw, "BB")
    detail.employee_total = sum(x["employee_count"] or 0 for x in new_floors) if new_floors else _integer(raw, "BJ")
    facility.updated_at = now

    # Phase 3 legacy normalization. These records preserve source text and only
    # promote dates when a deterministic parser succeeds. Missing source documents
    # are never treated as proof of a formal submission.
    profile = db.get(InspectionReportingProfile, facility.building_id)
    if profile is None:
        profile = InspectionReportingProfile(building_id=facility.building_id)
        db.add(profile)
    due_date, due_raw = _legacy_date_text(_text(raw, "IT"))
    profile.report_cycle_years = _legacy_decimal_text(_text(raw, "IS"))
    profile.next_due_date = due_date
    profile.raw_cycle_text = _text(raw, "IS")
    profile.raw_next_due_text = due_raw
    profile.updated_at = now

    db.execute(delete(FireManagementAssignment).where(
        FireManagementAssignment.building_id == facility.building_id,
        FireManagementAssignment.source_kind == "legacy",
    ))
    db.execute(delete(FirePlan).where(
        FirePlan.building_id == facility.building_id,
        FirePlan.source_kind == "legacy",
    ))
    manager_slots = [("HC", "HD", "HE", "HF"), ("HG", "HH", "HI", "HJ"), ("HK", "HL", "HM", "HN")]
    for slot, (name_col, title_col, appointment_col, plan_col) in enumerate(manager_slots, start=1):
        name = _text(raw, name_col)
        title = _text(raw, title_col)
        appointment_date, appointment_raw = _legacy_date_text(_text(raw, appointment_col))
        plan_date, plan_raw = _legacy_date_text(_text(raw, plan_col))
        if name or title or appointment_raw:
            db.add(FireManagementAssignment(
                building_id=facility.building_id,
                manager_name=name,
                manager_title=title,
                appointment_submitted_at=appointment_date,
                status="legacy_recorded",
                source_kind="legacy",
                legacy_slot=slot,
                raw_submission_text=appointment_raw,
            ))
        if plan_raw:
            db.add(FirePlan(
                building_id=facility.building_id,
                submitted_at=plan_date,
                status="legacy_recorded",
                source_kind="legacy",
                legacy_slot=slot,
                raw_submission_text=plan_raw,
            ))

    db.execute(delete(EquipmentInspectionReport).where(
        EquipmentInspectionReport.building_id == facility.building_id,
        EquipmentInspectionReport.source_kind == "legacy",
    ))
    equipment_name_cols = ["CN", "CW", "DF", "DO", "DX", "EG", "EP"]
    result_cols = ["IU", "IW", "IY", "JA", "JC", "JE", "JG"]
    report_cols = ["IV", "IX", "IZ", "JB", "JD", "JF", "JH"]
    for idx in range(7):
        equipment_label = _text(raw, equipment_name_cols[idx])
        result_date, result_raw = _legacy_date_text(_text(raw, result_cols[idx]))
        report_date, report_raw = _legacy_date_text(_text(raw, report_cols[idx]))
        if result_raw or report_raw:
            db.add(EquipmentInspectionReport(
                building_id=facility.building_id,
                equipment_label=equipment_label,
                inspection_date=result_date,
                submitted_at=report_date,
                result_summary=None,
                next_due_at=profile.next_due_date,
                source_kind="legacy",
                raw_result_text=result_raw,
                raw_report_text=report_raw,
            ))
    for label, result_col, report_col in [
        ("自家発", "JI", "JJ"), ("蓄電池", "JK", "JL"), ("専用受電", "JM", "JN")
    ]:
        result_date, result_raw = _legacy_date_text(_text(raw, result_col))
        report_date, report_raw = _legacy_date_text(_text(raw, report_col))
        if result_raw or report_raw:
            db.add(EquipmentInspectionReport(
                building_id=facility.building_id, equipment_label=label,
                inspection_date=result_date, submitted_at=report_date,
                next_due_at=profile.next_due_date, source_kind="legacy",
                raw_result_text=result_raw, raw_report_text=report_raw,
            ))

    db.execute(delete(GuidanceRecord).where(
        GuidanceRecord.building_id == facility.building_id,
        GuidanceRecord.source_kind == "legacy",
    ))
    # JO..SH are 76 groups of subject / issued text / content. Convert Excel
    # column names to numeric indices so we do not hard-code 228 names.
    def _col_no(col: str) -> int:
        n = 0
        for ch in col:
            n = n * 26 + (ord(ch) - 64)
        return n
    def _col_name(n: int) -> str:
        out = ""
        while n:
            n, r = divmod(n - 1, 26)
            out = chr(65 + r) + out
        return out
    start = _col_no("JO")
    for slot in range(1, 77):
        subject_col = _col_name(start + (slot - 1) * 3)
        issued_col = _col_name(start + (slot - 1) * 3 + 1)
        content_col = _col_name(start + (slot - 1) * 3 + 2)
        subject = _text(raw, subject_col)
        issued_at, issued_raw = _legacy_date_text(_text(raw, issued_col))
        content = _text(raw, content_col)
        if subject or issued_raw or content:
            db.add(GuidanceRecord(
                building_id=facility.building_id, subject=subject, issued_at=issued_at,
                content=content, legacy_slot=slot, source_kind="legacy", raw_issued_text=issued_raw,
            ))