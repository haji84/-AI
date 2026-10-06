from __future__ import annotations

from .drawing_annotation_geometry import geometry_points


REGION_TYPES = {"room", "zone"}
APPROX_GEOMETRY_QUALITIES = {
    "open_plan_approx",
    "circulation_approx",
    "service_area_approx",
    "approx",
}


def build_annotation_qa(
    *,
    payload: dict,
    page_dimensions: dict,
    status: str,
) -> dict:
    elements = payload.get("elements") if isinstance(payload, dict) else []
    if not isinstance(elements, list):
        elements = []

    regions = []
    unlabeled = []
    missing_use = []
    unassigned_floor = []
    invalid_geometry = []
    approximate = []
    used_pages: set[int] = set()

    for index, element in enumerate(elements):
        if not isinstance(element, dict):
            continue
        element_type = str(element.get("element_type") or "")
        if element_type not in REGION_TYPES:
            continue

        ref = str(element.get("client_ref") or f"index:{index}")
        label = str(element.get("label") or "").strip()
        extracted = element.get("extracted_data") or {}
        use_name = (
            str(extracted.get("use_name") or "").strip()
            if isinstance(extracted, dict)
            else ""
        )
        page_no = int(element.get("page_no", 1) or 1)
        used_pages.add(page_no)
        points = geometry_points(element.get("geometry") or {})
        floor_number = element.get("floor_number")
        meta = element.get("reference_meta") or {}
        quality = (
            str(meta.get("geometry_quality") or "").strip()
            if isinstance(meta, dict)
            else ""
        )

        row = {
            "client_ref": ref,
            "label": label or None,
            "use_name": use_name or None,
            "element_type": element_type,
            "page_no": page_no,
            "floor_number": floor_number,
            "geometry_quality": quality or None,
            "area_px2": (element.get("derived_geometry") or {}).get("area_px2"),
            "area_m2": (element.get("derived_geometry") or {}).get("area_m2"),
        }
        regions.append(row)

        if not label and not use_name:
            unlabeled.append(row)
        if not use_name:
            missing_use.append(row)
        if floor_number is None:
            unassigned_floor.append(row)
        if len(points) < 3:
            invalid_geometry.append(row)
        if quality in APPROX_GEOMETRY_QUALITIES:
            approximate.append(row)

    uncalibrated_pages = []
    for page_no in sorted(used_pages):
        raw = (
            page_dimensions.get(str(page_no))
            if isinstance(page_dimensions, dict)
            else None
        )
        if raw is None and isinstance(page_dimensions, dict):
            raw = page_dimensions.get(page_no)
        calibration = raw.get("calibration") if isinstance(raw, dict) else None
        meters_per_pixel = (
            calibration.get("meters_per_pixel")
            if isinstance(calibration, dict)
            else None
        )
        if not meters_per_pixel:
            uncalibrated_pages.append(page_no)

    summary = (
        payload.get("geometry_summary")
        if isinstance(payload, dict)
        and isinstance(payload.get("geometry_summary"), dict)
        else {}
    )
    overlaps = summary.get("overlap_warnings") or []
    target_comparisons = summary.get("area_target_comparisons") or []

    target_attention = []
    target_ready = 0
    for row in target_comparisons:
        if not isinstance(row, dict):
            continue
        status_value = row.get("status")
        if status_value == "comparable":
            target_ready += 1
            target_attention.append(
                {
                    "floor_number": row.get("floor_number"),
                    "label": row.get("label"),
                    "status": status_value,
                    "target_area_m2": row.get("target_area_m2"),
                    "measured_room_area_m2": row.get("measured_room_area_m2"),
                    "difference_m2": row.get("difference_m2"),
                    "difference_pct": row.get("difference_pct"),
                    "requires_human_judgment": True,
                }
            )
        elif status_value:
            target_attention.append(
                {
                    "floor_number": row.get("floor_number"),
                    "label": row.get("label"),
                    "status": status_value,
                    "target_area_m2": row.get("target_area_m2"),
                    "measured_room_area_m2": row.get("measured_room_area_m2"),
                    "difference_m2": None,
                    "difference_pct": None,
                    "requires_human_judgment": True,
                }
            )

    blockers = []
    warnings = []
    if not regions:
        blockers.append(
            {
                "code": "no_regions",
                "message": "Human Referenceにroom/zone区画がありません。",
            }
        )
    if invalid_geometry:
        blockers.append(
            {
                "code": "invalid_geometry",
                "message": f"有効なポリゴンでない区画が{len(invalid_geometry)}件あります。",
            }
        )
    if unlabeled:
        blockers.append(
            {
                "code": "missing_label_or_use",
                "message": f"名称/用途の両方が未入力の区画が{len(unlabeled)}件あります。",
            }
        )
    if unassigned_floor:
        warnings.append(
            {
                "code": "unassigned_floor",
                "message": f"階が未設定の区画が{len(unassigned_floor)}件あります。",
            }
        )
    if uncalibrated_pages:
        warnings.append(
            {
                "code": "uncalibrated_pages",
                "message": (
                    "㎡計算用の縮尺校正が未設定のページ: "
                    + ", ".join(str(x) for x in uncalibrated_pages)
                ),
            }
        )
    if overlaps:
        warnings.append(
            {
                "code": "interior_overlap",
                "message": f"内部重複の可能性がある区画ペアが{len(overlaps)}件あります。",
            }
        )
    if approximate:
        warnings.append(
            {
                "code": "approximate_regions",
                "message": f"近似境界としてHuman確認が必要な区画が{len(approximate)}件あります。",
            }
        )
    if target_attention:
        warnings.append(
            {
                "code": "floor_area_target_review",
                "message": (
                    "Human床面積ターゲットとの比較があります。"
                    "差の許容可否はHuman判断が必要です。"
                ),
            }
        )

    geometry_review_ready = not blockers and bool(regions)
    metric_area_review_ready = bool(
        geometry_review_ready
        and not uncalibrated_pages
        and all(
            region.get("area_m2") is not None
            for region in regions
        )
    )

    return {
        "qa_format": "drawing-annotation-qa-v1",
        "annotation_status": status,
        "region_count": len(regions),
        "room_count": sum(1 for x in regions if x["element_type"] == "room"),
        "zone_count": sum(1 for x in regions if x["element_type"] == "zone"),
        "used_pages": sorted(used_pages),
        "uncalibrated_pages": uncalibrated_pages,
        "geometry_review_ready": geometry_review_ready,
        "metric_area_review_ready": metric_area_review_ready,
        "blockers": blockers,
        "warnings": warnings,
        "details": {
            "unlabeled_regions": unlabeled,
            "missing_use_regions": missing_use,
            "unassigned_floor_regions": unassigned_floor,
            "invalid_geometry_regions": invalid_geometry,
            "approximate_regions": approximate,
            "overlap_warnings": overlaps,
            "area_target_comparisons": target_attention,
            "comparable_area_target_count": target_ready,
        },
        "policy": {
            "automatic_acceptance": False,
            "area_difference_threshold": None,
            "overlap_auto_reject": False,
            "human_review_required": True,
        },
    }
