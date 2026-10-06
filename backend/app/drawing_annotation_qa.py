from __future__ import annotations

from typing import Any


def _text(value: Any) -> str:
    return str(value or "").strip()


def _region_label(element: dict) -> str:
    extracted = element.get("extracted_data")
    use_name = _text(extracted.get("use_name")) if isinstance(extracted, dict) else ""
    return _text(element.get("label")) or use_name


def _is_open_plan_approximation(element: dict) -> bool:
    extracted = element.get("extracted_data")
    if not isinstance(extracted, dict):
        return False
    return bool(
        extracted.get("open_plan_approximation") is True
        or _text(extracted.get("approximation")).lower() == "open_plan"
        or _text(extracted.get("geometry_basis")).lower() == "open_plan_approximation"
    )


def build_annotation_qa(
    *,
    status: str,
    payload: dict | None,
    page_dimensions: dict | None,
) -> dict:
    body = payload if isinstance(payload, dict) else {}
    elements = body.get("elements") if isinstance(body.get("elements"), list) else []
    summary = body.get("geometry_summary") if isinstance(body.get("geometry_summary"), dict) else {}
    page_meta = page_dimensions if isinstance(page_dimensions, dict) else {}

    regions = [
        element
        for element in elements
        if isinstance(element, dict)
        and _text(element.get("element_type")) in {"room", "zone"}
    ]
    rooms = [x for x in regions if _text(x.get("element_type")) == "room"]
    zones = [x for x in regions if _text(x.get("element_type")) == "zone"]

    missing_labels = []
    open_plan = []
    used_pages = set()
    for index, element in enumerate(regions):
        page_no = int(element.get("page_no") or 1)
        used_pages.add(page_no)
        if not _region_label(element):
            missing_labels.append(
                {
                    "index": index,
                    "client_ref": element.get("client_ref"),
                    "element_type": element.get("element_type"),
                    "page_no": page_no,
                }
            )
        if _is_open_plan_approximation(element):
            open_plan.append(
                {
                    "index": index,
                    "client_ref": element.get("client_ref"),
                    "label": _region_label(element) or None,
                    "page_no": page_no,
                    "floor_number": element.get("floor_number"),
                }
            )

    uncalibrated_pages = []
    for page_no in sorted(used_pages):
        page = page_meta.get(str(page_no)) or page_meta.get(page_no) or {}
        calibration = page.get("calibration") if isinstance(page, dict) else None
        meters_per_pixel = calibration.get("meters_per_pixel") if isinstance(calibration, dict) else None
        try:
            calibrated = float(meters_per_pixel) > 0
        except (TypeError, ValueError):
            calibrated = False
        if not calibrated:
            uncalibrated_pages.append(page_no)

    overlaps = summary.get("overlap_warnings")
    if not isinstance(overlaps, list):
        overlaps = []

    comparisons = summary.get("area_target_comparisons")
    if not isinstance(comparisons, list):
        comparisons = []

    blockers = []
    warnings = []

    if not regions:
        blockers.append(
            {
                "code": "no_regions",
                "message": "確認対象のroom/zone区画がありません。",
            }
        )
    if missing_labels:
        blockers.append(
            {
                "code": "missing_label_or_usage",
                "message": "ラベルまたは用途が未入力の区画があります。",
                "count": len(missing_labels),
            }
        )
    if overlaps:
        blockers.append(
            {
                "code": "overlap_warning",
                "message": "内部が重なる区画があります。二重計上の可能性をHuman確認してください。",
                "count": len(overlaps),
            }
        )
    if uncalibrated_pages:
        warnings.append(
            {
                "code": "uncalibrated_pages",
                "message": "実寸校正されていないページがあります。Geometry確認は可能ですが㎡比較は未完です。",
                "pages": uncalibrated_pages,
            }
        )
    if open_plan:
        warnings.append(
            {
                "code": "open_plan_approximation",
                "message": "open-plan近似として明示された区画があります。境界の妥当性をHuman確認してください。",
                "count": len(open_plan),
            }
        )

    non_comparable_targets = [
        x for x in comparisons
        if isinstance(x, dict) and _text(x.get("status")) != "comparable"
    ]
    if non_comparable_targets:
        warnings.append(
            {
                "code": "floor_area_comparison_incomplete",
                "message": "既知床面積との比較が未完の階があります。",
                "count": len(non_comparable_targets),
            }
        )

    reference_reviewable = not blockers
    reviewed_reference = status == "reviewed" and reference_reviewable
    area_comparison_ready = reviewed_reference and not uncalibrated_pages and not non_comparable_targets

    return {
        "qa_format": "fire-ai-drawing-annotation-qa-v1",
        "status": status,
        "counts": {
            "region_count": len(regions),
            "room_count": len(rooms),
            "zone_count": len(zones),
            "overlap_warning_count": len(overlaps),
            "missing_label_or_usage_count": len(missing_labels),
            "open_plan_approximation_count": len(open_plan),
            "uncalibrated_page_count": len(uncalibrated_pages),
        },
        "floor_summaries": summary.get("floor_summaries") if isinstance(summary.get("floor_summaries"), list) else [],
        "area_target_comparisons": comparisons,
        "overlap_warnings": overlaps,
        "uncalibrated_pages": uncalibrated_pages,
        "missing_label_or_usage": missing_labels,
        "open_plan_approximations": open_plan,
        "reference_reviewable": reference_reviewable,
        "reviewed_reference_ready": reviewed_reference,
        "area_comparison_ready": area_comparison_ready,
        "blockers": blockers,
        "warnings": warnings,
        "policy": (
            "QA is a Human review aid. It does not convert Draft evidence into Reference, "
            "does not auto-accept a Benchmark, and does not make a statutory floor-area determination."
        ),
    }
