"""PII-free outputs for a *candidate-only* emergency report review core.

This module NEVER reads PDFs, logs records, updates official source records,
changes clinical decisions, or claims current-rule approval. Only explicit
human-confirmed observations can produce a rule finding; lack of print is not
proof of a blank input field. This is a bounded slice, not a deployed checker.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Mapping


ObservationState = Literal["confirmed", "unconfirmed", "unreadable", "not_printed", "unmapped"]
CheckStatus = Literal["REVIEW_REQUIRED", "NO_ISSUE_DETECTED", "NOT_TESTED", "NOT_APPLICABLE"]
Scalar = str | int | float | bool | None


@dataclass(frozen=True)
class Observation:
    state: ObservationState
    value: Scalar = None

    def __post_init__(self) -> None:
        if self.state not in {"confirmed", "unconfirmed", "unreadable", "not_printed", "unmapped"}:
            raise ValueError("invalid observation state")
        if self.state != "confirmed" and self.value is not None:
            raise ValueError("unverified observations cannot carry values")
        if self.value is not None and not isinstance(self.value, (str, int, float, bool)):
            raise TypeError("unsupported observation value")


@dataclass(frozen=True)
class CheckFinding:
    rule_id: str
    status: CheckStatus
    message: str
    fields: tuple[str, ...]
    source_reference: str
    rule_approval: str = "PROVISIONAL_NOT_APPROVED"


def confirmed(value: Scalar) -> Observation:
    """Use None or an empty string only when the blank was actually checked."""
    return Observation("confirmed", value)


def _read(values: Mapping[str, Observation], name: str) -> tuple[bool, Scalar]:
    item = values.get(name)
    if isinstance(item, Observation) and item.state == "confirmed":
        return True, item.value
    return False, None


def _blank(value: Scalar) -> bool:
    return value is None or (isinstance(value, str) and not value.strip())


def _finding(rule: str, status: CheckStatus, message: str, fields: tuple[str, ...], source: str) -> CheckFinding:
    # Deliberately does not include input values, names, dates or PDF snippets.
    return CheckFinding(rule, status, message, fields, source)


def _bool(value: Scalar) -> bool | None:
    return value if type(value) is bool else None


def _category(value: Scalar) -> str | None:
    return value.strip() if isinstance(value, str) else None


def _numeric(value: Scalar) -> float | None:
    if type(value) not in (int, float):
        return None
    try:
        amount = float(value)
    except (ValueError, OverflowError):
        return None
    if amount != amount or amount in (float("inf"), float("-inf")):
        return None
    return amount


# Age bands are for the LOCAL guide's urgency threshold (p17), not general
# medical normal ranges, and MUST NOT be derived from an age-in-years integer
# for newborns/infants without the underlying days/months and confirmation.
_RED_RANGES = {
    "newborn": {"pulse": (100, 150), "respirations": (30, 50), "systolic": (70, None)},
    "infant": {"pulse": (80, 120), "respirations": (20, 30), "systolic": (80, None)},
    "toddler": {"pulse": (60, 110), "respirations": (20, 30), "systolic": (80, None)},
    "age_7_plus": {"pulse": (50, 120), "respirations": (10, 30), "systolic": (90, 200)},
}


def _red_trigger(metric: str, amount: float, age_band: str | None) -> bool | None:
    if metric == "spo2":
        return amount < 90 if 0 <= amount <= 100 else None
    if metric == "jcs":
        return amount >= 100 if amount >= 0 and amount.is_integer() else None
    if age_band not in _RED_RANGES:
        return None
    bounds = _RED_RANGES[age_band][metric]
    low, high = bounds
    if metric in ("pulse", "respirations") and (amount < 0 or not amount.is_integer()):
        return None
    if metric == "systolic" and amount <= 0:
        return None
    return amount < low or (high is not None and amount >= high)


def evaluate_confirmed_fields(values: Mapping[str, Observation]) -> tuple[CheckFinding, ...]:
    """Return non-authoritative suggestions with *no individual values*.

    Required keys are documentation-defined normalized fields, not raw OCR:
      transported: bool; transfer_transport: bool; urgency: '緊急（赤）'/'準緊急（黄）';
      place_major: str; place_minor: str/blank; occurrence_floor: str/blank;
      form_version: 'new'/'old'; incident_type_first/second: str;
      vital_phase: 'initial'; age_band: newborn/infant/toddler/age_7_plus;
      pulse/respirations/systolic/spo2/jcs: numeric values.

    Unknown, unreadable, non-printed, or unconfirmed inputs yield NOT_TESTED.
    These candidate checks must be mapped to the approved form/rule version
    before production use. 'NO_ISSUE_DETECTED' is not a compliance certificate.
    """
    if not isinstance(values, Mapping):
        raise TypeError("confirmed fields mapping required")
    results: list[CheckFinding] = []
    has_transport, transported_raw = _read(values, "transported")
    transported = _bool(transported_raw) if has_transport else None
    has_urgency, urgency_raw = _read(values, "urgency")
    urgency = _category(urgency_raw) if has_urgency else None
    has_transfer, transfer_raw = _read(values, "transfer_transport")
    transfer = _bool(transfer_raw) if has_transfer else None

    # Nontransport MUST short-circuit transfer and physiological red logic.
    if transported is None or not has_urgency or (has_urgency and urgency is None and not _blank(urgency_raw)):
        status = "NOT_TESTED"
    elif transported:
        status = "NOT_APPLICABLE"
    else:
        status = "NO_ISSUE_DETECTED" if _blank(urgency_raw) else "REVIEW_REQUIRED"
    results.append(_finding("ER-NONTRANSPORT-URGENCY", status,
        "不搬送時は緊急度を入力しない。印刷されない欄は未検査扱い。",
        ("transported", "urgency"), "全国版p9／利用者提示の現行運用"))

    if transported is None or transfer is None or not has_urgency or (has_urgency and urgency is None and not _blank(urgency_raw)):
        status = "NOT_TESTED" if transported is not False else "NOT_APPLICABLE"
    elif transported is False or transfer is False:
        status = "NOT_APPLICABLE"
    else:
        status = "NO_ISSUE_DETECTED" if urgency == "準緊急（黄）" else "REVIEW_REQUIRED"
    results.append(_finding("ER-TRANSFER-URGENCY", status,
        "転院搬送は準緊急（黄）。転院区分は正式コードで確認する。",
        ("transported", "transfer_transport", "urgency"), "全国版p14・地域版p17"))

    have_place, place_raw = _read(values, "place_major")
    place = _category(place_raw) if have_place else None
    for rule_id, field, msg in (
        ("ER-PLACE-MINOR", "place_minor", "住宅は小分類まで選択し、住宅以外は中分類までとする。"),
        ("ER-PLACE-FLOOR", "occurrence_floor", "発生階層は住宅の場合のみ入力し、住宅以外は空欄とする。"),
    ):
        has_field, data = _read(values, field)
        if not have_place or place not in {"住宅", "公衆出入場所", "仕事場", "道路", "その他"} or not has_field:
            status = "NOT_TESTED"
        elif place == "住宅":
            # National p10: residence must use minor category. Floor may be
            # recorded at residence but the cited text does not make it mandatory.
            if field == "place_minor":
                status = "REVIEW_REQUIRED" if _blank(data) else "NO_ISSUE_DETECTED"
            else:
                status = "NOT_APPLICABLE"
        else:
            status = "NO_ISSUE_DETECTED" if _blank(data) else "REVIEW_REQUIRED"
        results.append(_finding(rule_id, status, msg, ("place_major", field), "全国版p10・地域版p14"))

    have_form, form_raw = _read(values, "form_version")
    form = _category(form_raw) if have_form else None
    a_ready, a = _read(values, "incident_type_first")
    b_ready, b = _read(values, "incident_type_second")
    if not have_form or form not in ("new", "old"):
        status = "NOT_TESTED"
    elif form == "old":
        status = "NOT_APPLICABLE"
    elif not a_ready or not b_ready or not isinstance(a, str) or not isinstance(b, str) or not a.strip() or not b.strip():
        status = "NOT_TESTED"
    else:
        status = "NO_ISSUE_DETECTED" if a.strip() == b.strip() else "REVIEW_REQUIRED"
    results.append(_finding("ER-FORM-ACCIDENT-TWO", status,
        "新様式に指定された事故種別2欄の一致を確認。別台帳同士は比較対象外。",
        ("form_version", "incident_type_first", "incident_type_second"), "利用者提示の新様式運用（欄位置未照合）"))

    # All vital thresholds are *red urgency triggers* from local p17, never
    # asserted to be general 'normal ranges'. No automatic patient diagnosis.
    phase_ok, phase_raw = _read(values, "vital_phase")
    band_ok, band_raw = _read(values, "age_band")
    band = _category(band_raw) if band_ok else None
    for metric in ("pulse", "respirations", "systolic", "spo2", "jcs"):
        ready, reading = _read(values, metric)
        num = _numeric(reading) if ready else None
        if transported is False or (transported is True and transfer is True):
            status = "NOT_APPLICABLE"
        elif transported is None or transfer is None or not has_urgency or urgency not in ("緊急（赤）", "準緊急（黄）"):
            status = "NOT_TESTED"
        elif not phase_ok or phase_raw != "initial" or num is None:
            status = "NOT_TESTED"
        else:
            trigger = _red_trigger(metric, num, band)
            if trigger is None:
                status = "NOT_TESTED"
            elif trigger and urgency == "準緊急（黄）":
                status = "REVIEW_REQUIRED"
            else:
                status = "NO_ISSUE_DETECTED"
        fields = ("transported", "transfer_transport", "urgency", "vital_phase", "age_band", metric)
        results.append(_finding(f"ER-RED-TRIGGER-{metric.upper()}", status,
            "年齢別の緊急（赤）基準と選択緊急度の整合性候補。正常値判定ではない。",
            fields, "地域版p17（参考資料、正式採用未確認）"))
    return tuple(results)
