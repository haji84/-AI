from __future__ import annotations


APPROXIMATE_GEOMETRY_QUALITIES = {
    "circulation_approx",
    "open_plan_approx",
    "service_area_approx",
}


def _code(prefix: str, *parts) -> str:
    clean = [
        str(part).strip().replace(" ", "_")
        for part in parts
        if part not in (None, "")
    ]
    return ":".join([prefix, *clean]) if clean else prefix


def build_annotation_review_preflight(payload: dict) -> dict:
    if not isinstance(payload, dict):
        raise ValueError("annotation payload must be an object")

    elements = payload.get("elements", [])
    if not isinstance(elements, list):
        raise ValueError("elements must be a list")

    blockers: list[dict] = []
    warnings: list[dict] = []
    infos: list[dict] = []
    seen_refs: set[str] = set()

    for index, element in enumerate(elements):
        if not isinstance(element, dict):
            blockers.append(
                {
                    "code": _code("invalid_element", index),
                    "message": f"elements[{index}] is not an object",
                }
            )
            continue

        element_type = str(element.get("element_type") or "")
        if element_type not in {"room", "zone"}:
            continue

        client_ref = str(
            element.get("client_ref") or f"index-{index}"
        ).strip()
        if client_ref in seen_refs:
            blockers.append(
                {
                    "code": _code("duplicate_client_ref", client_ref),
                    "message": (
                        f"区画ID {client_ref} が重複しています。"
                    ),
                    "client_ref": client_ref,
                }
            )
        seen_refs.add(client_ref)

        label = str(element.get("label") or "").strip()
        extracted = element.get("extracted_data") or {}
        use_name = (
            str(extracted.get("use_name") or "").strip()
            if isinstance(extracted, dict)
            else ""
        )
        if not label and not use_name:
            blockers.append(
                {
                    "code": _code("missing_label_or_use", client_ref),
                    "message": (
                        f"{client_ref} に区画名または用途がありません。"
                    ),
                    "client_ref": client_ref,
                }
            )

        geometry = element.get("geometry") or {}
        points = geometry.get("points")
        if not isinstance(points, list) or len(points) < 3:
            blockers.append(
                {
                    "code": _code("invalid_polygon", client_ref),
                    "message": (
                        f"{label or client_ref} のポリゴンが3頂点未満です。"
                    ),
                    "client_ref": client_ref,
                }
            )

        if element.get("floor_number") in (None, ""):
            warnings.append(
                {
                    "code": _code("floor_unassigned", client_ref),
                    "message": (
                        f"{label or client_ref} の階が未設定です。"
                    ),
                    "client_ref": client_ref,
                }
            )

        meta = element.get("reference_meta") or {}
        if isinstance(meta, dict):
            quality = str(meta.get("geometry_quality") or "")
            status = str(meta.get("human_review_status") or "")
            if (
                quality in APPROXIMATE_GEOMETRY_QUALITIES
                and status != "reviewed"
            ):
                warnings.append(
                    {
                        "code": _code(
                            "approximate_geometry",
                            client_ref,
                        ),
                        "message": (
                            f"{label or client_ref} は {quality} の近似境界です。"
                            "Humanで境界を確認してください。"
                        ),
                        "client_ref": client_ref,
                        "geometry_quality": quality,
                    }
                )

    summary = payload.get("geometry_summary") or {}
    overlaps = summary.get("overlap_warnings") or []
    if isinstance(overlaps, list):
        for index, overlap in enumerate(overlaps):
            if not isinstance(overlap, dict):
                continue
            left = overlap.get("left_ref") or overlap.get("left_label")
            right = overlap.get("right_ref") or overlap.get("right_label")
            warnings.append(
                {
                    "code": _code(
                        "interior_overlap",
                        left or index,
                        right,
                    ),
                    "message": (
                        f"{overlap.get('left_label') or left or '区画A'} と "
                        f"{overlap.get('right_label') or right or '区画B'} "
                        "が内部で重なっています。"
                    ),
                    "page_no": overlap.get("page_no"),
                    "floor_number": overlap.get("floor_number"),
                }
            )

    comparisons = summary.get("area_target_comparisons") or []
    if isinstance(comparisons, list):
        for row in comparisons:
            if not isinstance(row, dict):
                continue
            floor = row.get("floor_number")
            status = row.get("status")
            if status == "room_area_uncalibrated":
                warnings.append(
                    {
                        "code": _code(
                            "area_target_uncalibrated",
                            floor,
                        ),
                        "message": (
                            f"{floor}階は既知床面積ターゲットがありますが、"
                            "room区画の縮尺校正が未完です。"
                        ),
                        "floor_number": floor,
                    }
                )
            elif status == "missing_floor_annotation":
                warnings.append(
                    {
                        "code": _code(
                            "area_target_missing_floor",
                            floor,
                        ),
                        "message": (
                            f"{floor}階の既知床面積ターゲットがありますが、"
                            "対応するroom区画がありません。"
                        ),
                        "floor_number": floor,
                    }
                )
            elif status == "comparable":
                infos.append(
                    {
                        "code": _code(
                            "area_target_comparison",
                            floor,
                        ),
                        "message": (
                            f"{floor}階 room合計と既知面積の差は "
                            f"{row.get('difference_m2')}㎡ "
                            f"({row.get('difference_pct')}%) です。"
                        ),
                        "floor_number": floor,
                        "target_area_m2": row.get("target_area_m2"),
                        "measured_room_area_m2":
                            row.get("measured_room_area_m2"),
                        "difference_m2": row.get("difference_m2"),
                        "difference_pct": row.get("difference_pct"),
                    }
                )

    warning_codes = [str(x["code"]) for x in warnings]
    blocker_codes = [str(x["code"]) for x in blockers]
    return {
        "preflight_format":
            "fire-ai-drawing-annotation-review-preflight-v1",
        "ready_for_review": not blockers,
        "acknowledgement_required": bool(warnings),
        "blocker_count": len(blockers),
        "warning_count": len(warnings),
        "info_count": len(infos),
        "blocker_codes": blocker_codes,
        "warning_codes": warning_codes,
        "blockers": blockers,
        "warnings": warnings,
        "infos": infos,
        "geometry_summary": summary,
        "note": (
            "Warnings require explicit Human acknowledgement but do not "
            "automatically reject the Reference. Blockers must be corrected."
        ),
    }


def mark_reference_elements_reviewed(
    payload: dict,
    *,
    reviewed_at: str,
) -> dict:
    if not isinstance(payload, dict):
        raise ValueError("annotation payload must be an object")

    elements = payload.get("elements", [])
    if not isinstance(elements, list):
        return payload

    for element in elements:
        if not isinstance(element, dict):
            continue
        if str(element.get("element_type") or "") not in {
            "room",
            "zone",
        }:
            continue
        meta = element.get("reference_meta")
        if not isinstance(meta, dict):
            continue
        meta["human_review_status"] = "reviewed"
        meta["human_reviewed_at"] = reviewed_at
    return payload
