from __future__ import annotations

from copy import deepcopy
import math


def geometry_points(geometry: dict) -> list[tuple[float, float]]:
    if not isinstance(geometry, dict):
        return []
    points = geometry.get("points")
    if isinstance(points, list):
        out = []
        for point in points:
            if isinstance(point, dict) and "x" in point and "y" in point:
                out.append((float(point["x"]), float(point["y"])))
            elif isinstance(point, (list, tuple)) and len(point) >= 2:
                out.append((float(point[0]), float(point[1])))
        if len(out) >= 3:
            return out

    bbox = geometry.get("bbox")
    if isinstance(bbox, list) and len(bbox) == 4:
        x, y, width, height = map(float, bbox)
        if width > 0 and height > 0:
            return [
                (x, y),
                (x + width, y),
                (x + width, y + height),
                (x, y + height),
            ]

    if all(k in geometry for k in ("x", "y", "width", "height")):
        x = float(geometry["x"])
        y = float(geometry["y"])
        width = float(geometry["width"])
        height = float(geometry["height"])
        if width > 0 and height > 0:
            return [
                (x, y),
                (x + width, y),
                (x + width, y + height),
                (x, y + height),
            ]

    if all(k in geometry for k in ("x1", "y1", "x2", "y2")):
        x1 = float(geometry["x1"])
        y1 = float(geometry["y1"])
        x2 = float(geometry["x2"])
        y2 = float(geometry["y2"])
        if x2 > x1 and y2 > y1:
            return [
                (x1, y1),
                (x2, y1),
                (x2, y2),
                (x1, y2),
            ]
    return []


def polygon_area_px2(points: list[tuple[float, float]]) -> float:
    if len(points) < 3:
        return 0.0
    area = 0.0
    for index, (x1, y1) in enumerate(points):
        x2, y2 = points[(index + 1) % len(points)]
        area += x1 * y2 - x2 * y1
    return abs(area) / 2.0


def polygon_perimeter_px(points: list[tuple[float, float]]) -> float:
    if len(points) < 2:
        return 0.0
    total = 0.0
    for index, (x1, y1) in enumerate(points):
        x2, y2 = points[(index + 1) % len(points)]
        total += math.hypot(x2 - x1, y2 - y1)
    return total


def canonical_page_dimensions(page_dimensions: dict) -> dict:
    if not isinstance(page_dimensions, dict):
        raise ValueError("page_dimensions must be an object")

    out = deepcopy(page_dimensions)
    for page_key, raw in list(out.items()):
        if not isinstance(raw, dict):
            raise ValueError(f"page_dimensions[{page_key}] must be an object")

        width = raw.get("width")
        height = raw.get("height")
        if width is not None and float(width) <= 0:
            raise ValueError(f"page_dimensions[{page_key}].width must be > 0")
        if height is not None and float(height) <= 0:
            raise ValueError(f"page_dimensions[{page_key}].height must be > 0")

        calibration = raw.get("calibration")
        if calibration in (None, {}):
            raw.pop("calibration", None)
            continue
        if not isinstance(calibration, dict):
            raise ValueError(f"page_dimensions[{page_key}].calibration must be an object")

        method = str(calibration.get("method") or "")
        if method != "two_point":
            raise ValueError(
                f"page_dimensions[{page_key}].calibration.method must be two_point"
            )
        point_a = calibration.get("point_a")
        point_b = calibration.get("point_b")
        if (
            not isinstance(point_a, (list, tuple))
            or not isinstance(point_b, (list, tuple))
            or len(point_a) < 2
            or len(point_b) < 2
        ):
            raise ValueError(
                f"page_dimensions[{page_key}].calibration requires point_a and point_b"
            )
        ax, ay = float(point_a[0]), float(point_a[1])
        bx, by = float(point_b[0]), float(point_b[1])
        pixel_distance = math.hypot(bx - ax, by - ay)
        if pixel_distance <= 0:
            raise ValueError(
                f"page_dimensions[{page_key}].calibration points must differ"
            )
        reference_length_m = float(calibration.get("reference_length_m") or 0)
        if reference_length_m <= 0:
            raise ValueError(
                f"page_dimensions[{page_key}].calibration.reference_length_m must be > 0"
            )
        meters_per_pixel = reference_length_m / pixel_distance
        raw["calibration"] = {
            "method": "two_point",
            "point_a": [ax, ay],
            "point_b": [bx, by],
            "reference_length_m": reference_length_m,
            "pixel_distance": pixel_distance,
            "meters_per_pixel": meters_per_pixel,
        }
    return out


def page_meters_per_pixel(page_dimensions: dict, page_no: int) -> float | None:
    page = page_dimensions.get(str(page_no))
    if page is None:
        page = page_dimensions.get(page_no)
    if not isinstance(page, dict):
        return None
    calibration = page.get("calibration")
    if not isinstance(calibration, dict):
        return None
    value = calibration.get("meters_per_pixel")
    if value in (None, ""):
        return None
    result = float(value)
    return result if result > 0 else None



def _bbox(points: list[tuple[float, float]]) -> tuple[float, float, float, float]:
    xs = [x for x, _ in points]
    ys = [y for _, y in points]
    return min(xs), min(ys), max(xs), max(ys)


def _point_on_segment(
    point: tuple[float, float],
    a: tuple[float, float],
    b: tuple[float, float],
    *,
    eps: float = 1e-9,
) -> bool:
    px, py = point
    ax, ay = a
    bx, by = b
    cross = (px - ax) * (by - ay) - (py - ay) * (bx - ax)
    if abs(cross) > eps:
        return False
    return (
        min(ax, bx) - eps <= px <= max(ax, bx) + eps
        and min(ay, by) - eps <= py <= max(ay, by) + eps
    )


def _point_in_polygon_strict(
    point: tuple[float, float],
    polygon: list[tuple[float, float]],
) -> bool:
    if len(polygon) < 3:
        return False
    for index, a in enumerate(polygon):
        b = polygon[(index + 1) % len(polygon)]
        if _point_on_segment(point, a, b):
            return False

    px, py = point
    inside = False
    j = len(polygon) - 1
    for i in range(len(polygon)):
        xi, yi = polygon[i]
        xj, yj = polygon[j]
        if (yi > py) != (yj > py):
            x_cross = (xj - xi) * (py - yi) / (yj - yi) + xi
            if px < x_cross:
                inside = not inside
        j = i
    return inside


def _orientation(
    a: tuple[float, float],
    b: tuple[float, float],
    c: tuple[float, float],
) -> float:
    return (
        (b[0] - a[0]) * (c[1] - a[1])
        - (b[1] - a[1]) * (c[0] - a[0])
    )


def _proper_segment_intersection(
    a1: tuple[float, float],
    a2: tuple[float, float],
    b1: tuple[float, float],
    b2: tuple[float, float],
    *,
    eps: float = 1e-9,
) -> bool:
    o1 = _orientation(a1, a2, b1)
    o2 = _orientation(a1, a2, b2)
    o3 = _orientation(b1, b2, a1)
    o4 = _orientation(b1, b2, a2)

    if abs(o1) <= eps or abs(o2) <= eps or abs(o3) <= eps or abs(o4) <= eps:
        return False
    return (o1 > 0) != (o2 > 0) and (o3 > 0) != (o4 > 0)


def polygons_have_interior_overlap(
    left: list[tuple[float, float]],
    right: list[tuple[float, float]],
) -> bool:
    if len(left) < 3 or len(right) < 3:
        return False

    lbox = _bbox(left)
    rbox = _bbox(right)
    if (
        lbox[2] <= rbox[0]
        or rbox[2] <= lbox[0]
        or lbox[3] <= rbox[1]
        or rbox[3] <= lbox[1]
    ):
        return False

    if left == right:
        return True

    for i, a1 in enumerate(left):
        a2 = left[(i + 1) % len(left)]
        for j, b1 in enumerate(right):
            b2 = right[(j + 1) % len(right)]
            if _proper_segment_intersection(a1, a2, b1, b2):
                return True

    if any(_point_in_polygon_strict(point, right) for point in left):
        return True
    if any(_point_in_polygon_strict(point, left) for point in right):
        return True

    left_center = (
        sum(x for x, _ in left) / len(left),
        sum(y for _, y in left) / len(left),
    )
    right_center = (
        sum(x for x, _ in right) / len(right),
        sum(y for _, y in right) / len(right),
    )
    return (
        _point_in_polygon_strict(left_center, right)
        or _point_in_polygon_strict(right_center, left)
    )



def canonical_area_targets(area_targets) -> list[dict]:
    if area_targets in (None, []):
        return []
    if not isinstance(area_targets, list):
        raise ValueError("area_targets must be a list")

    out = []
    seen = set()
    for index, raw in enumerate(area_targets):
        if not isinstance(raw, dict):
            raise ValueError(f"area_targets[{index}] must be an object")
        floor_number = raw.get("floor_number")
        if floor_number in (None, ""):
            raise ValueError(f"area_targets[{index}].floor_number is required")
        try:
            floor_number = int(floor_number)
        except (TypeError, ValueError) as exc:
            raise ValueError(
                f"area_targets[{index}].floor_number must be an integer"
            ) from exc

        target_area_m2 = float(raw.get("target_area_m2") or 0)
        if target_area_m2 <= 0:
            raise ValueError(
                f"area_targets[{index}].target_area_m2 must be > 0"
            )
        if floor_number in seen:
            raise ValueError(
                f"duplicate area target for floor_number: {floor_number}"
            )
        seen.add(floor_number)

        out.append(
            {
                "floor_number": floor_number,
                "target_area_m2": round(target_area_m2, 6),
                "label": raw.get("label"),
                "source": raw.get("source"),
                "note": raw.get("note"),
                "comparison_basis": "rooms_only",
            }
        )
    return sorted(out, key=lambda row: row["floor_number"])

def build_geometry_summary(elements: list[dict], area_targets: list[dict] | None = None) -> dict:
    regions = []
    for index, element in enumerate(elements):
        if not isinstance(element, dict):
            continue
        if str(element.get("element_type") or "") not in {"room", "zone"}:
            continue
        points = geometry_points(element.get("geometry") or {})
        if len(points) < 3:
            continue
        derived = element.get("derived_geometry") or {}
        area_px2 = derived.get("area_px2")
        if area_px2 is None:
            area_px2 = polygon_area_px2(points)
        regions.append(
            {
                "index": index,
                "client_ref": element.get("client_ref"),
                "label": element.get("label"),
                "element_type": element.get("element_type"),
                "page_no": int(element.get("page_no", 1) or 1),
                "floor_number": element.get("floor_number"),
                "points": points,
                "area_px2": float(area_px2),
                "area_m2": (
                    float(derived["area_m2"])
                    if derived.get("area_m2") is not None
                    else None
                ),
            }
        )

    floors: dict[str, dict] = {}
    for region in regions:
        floor_key = (
            str(region["floor_number"])
            if region["floor_number"] is not None
            else "unassigned"
        )
        row = floors.setdefault(
            floor_key,
            {
                "floor_number": region["floor_number"],
                "region_count": 0,
                "room_count": 0,
                "zone_count": 0,
                "area_px2_total": 0.0,
                "area_m2_total": 0.0,
                "room_area_px2_total": 0.0,
                "room_area_m2_total": 0.0,
                "zone_area_px2_total": 0.0,
                "zone_area_m2_total": 0.0,
                "calibrated_region_count": 0,
                "calibrated_room_count": 0,
                "uncalibrated_room_count": 0,
                "calibrated_zone_count": 0,
                "uncalibrated_zone_count": 0,
                "uncalibrated_region_count": 0,
                "metric_area_complete": True,
            },
        )
        row["region_count"] += 1
        if region["element_type"] == "room":
            row["room_count"] += 1
            row["room_area_px2_total"] += region["area_px2"]
        else:
            row["zone_count"] += 1
            row["zone_area_px2_total"] += region["area_px2"]
        row["area_px2_total"] += region["area_px2"]
        if region["area_m2"] is None:
            row["uncalibrated_region_count"] += 1
            row["metric_area_complete"] = False
            if region["element_type"] == "room":
                row["uncalibrated_room_count"] += 1
            else:
                row["uncalibrated_zone_count"] += 1
        else:
            row["calibrated_region_count"] += 1
            row["area_m2_total"] += region["area_m2"]
            if region["element_type"] == "room":
                row["calibrated_room_count"] += 1
                row["room_area_m2_total"] += region["area_m2"]
            else:
                row["calibrated_zone_count"] += 1
                row["zone_area_m2_total"] += region["area_m2"]

    for row in floors.values():
        row["area_px2_total"] = round(row["area_px2_total"], 6)
        row["room_area_px2_total"] = round(row["room_area_px2_total"], 6)
        row["zone_area_px2_total"] = round(row["zone_area_px2_total"], 6)
        row["area_m2_total"] = (
            round(row["area_m2_total"], 6)
            if row["calibrated_region_count"] > 0
            else None
        )
        row["room_area_m2_total"] = (
            round(row["room_area_m2_total"], 6)
            if row["calibrated_room_count"] > 0
            else None
        )
        row["zone_area_m2_total"] = (
            round(row["zone_area_m2_total"], 6)
            if row["zone_count"] > 0
            and row["uncalibrated_zone_count"] == 0
            else None
        )
        if row["region_count"] == 0:
            row["metric_area_complete"] = False

    overlaps = []
    for left_index, left in enumerate(regions):
        for right in regions[left_index + 1 :]:
            if left["page_no"] != right["page_no"]:
                continue
            if (
                left["floor_number"] is not None
                and right["floor_number"] is not None
                and left["floor_number"] != right["floor_number"]
            ):
                continue
            if not polygons_have_interior_overlap(
                left["points"],
                right["points"],
            ):
                continue
            overlaps.append(
                {
                    "page_no": left["page_no"],
                    "floor_number": (
                        left["floor_number"]
                        if left["floor_number"] == right["floor_number"]
                        else None
                    ),
                    "left_ref": left["client_ref"],
                    "left_label": left["label"],
                    "left_type": left["element_type"],
                    "right_ref": right["client_ref"],
                    "right_label": right["label"],
                    "right_type": right["element_type"],
                    "warning": "interior_overlap",
                }
            )

    canonical_targets = canonical_area_targets(area_targets)
    floor_by_number = {
        row["floor_number"]: row
        for row in floors.values()
        if row["floor_number"] is not None
    }
    comparisons = []
    for target in canonical_targets:
        floor = floor_by_number.get(target["floor_number"])
        if floor is None:
            comparisons.append(
                {
                    **target,
                    "status": "missing_floor_annotation",
                    "measured_room_area_m2": None,
                    "difference_m2": None,
                    "difference_pct": None,
                }
            )
            continue

        room_metric_complete = bool(
            floor["room_count"] > 0
            and floor["uncalibrated_room_count"] == 0
            and floor["room_area_m2_total"] is not None
        )
        if not room_metric_complete:
            comparisons.append(
                {
                    **target,
                    "status": "room_area_uncalibrated",
                    "measured_room_area_m2": floor["room_area_m2_total"],
                    "difference_m2": None,
                    "difference_pct": None,
                }
            )
            continue

        measured = float(floor["room_area_m2_total"])
        target_value = float(target["target_area_m2"])
        difference = measured - target_value
        comparisons.append(
            {
                **target,
                "status": "comparable",
                "measured_room_area_m2": round(measured, 6),
                "difference_m2": round(difference, 6),
                "difference_pct": round(
                    difference / target_value * 100.0,
                    6,
                ),
            }
        )

    return {
        "summary_version": "drawing-geometry-summary-v1",
        "region_count": len(regions),
        "floor_summaries": sorted(
            floors.values(),
            key=lambda row: (
                row["floor_number"] is None,
                row["floor_number"]
                if row["floor_number"] is not None
                else 10**9,
            ),
        ),
        "overlap_warning_count": len(overlaps),
        "overlap_warnings": overlaps,
        "area_targets": canonical_targets,
        "area_target_comparisons": comparisons,
        "note": (
            "Floor totals are sums of annotated room/zone regions, not "
            "building-code floor-area determinations. Overlap warnings "
            "indicate likely double-counting and require Human review."
        ),
    }

def apply_geometry_metrics(payload: dict, page_dimensions: dict) -> tuple[dict, dict]:
    if not isinstance(payload, dict):
        raise ValueError("annotation payload must be an object")
    canonical_dimensions = canonical_page_dimensions(page_dimensions)
    result = deepcopy(payload)

    elements = result.get("elements", [])
    if not isinstance(elements, list):
        raise ValueError("elements must be a list")

    for element in elements:
        if not isinstance(element, dict):
            continue
        points = geometry_points(element.get("geometry") or {})
        if len(points) < 3:
            element.pop("derived_geometry", None)
            continue

        area_px2 = polygon_area_px2(points)
        perimeter_px = polygon_perimeter_px(points)
        page_no = int(element.get("page_no", 1) or 1)
        meters_per_pixel = page_meters_per_pixel(
            canonical_dimensions,
            page_no,
        )
        area_m2 = (
            area_px2 * meters_per_pixel * meters_per_pixel
            if meters_per_pixel is not None
            else None
        )
        perimeter_m = (
            perimeter_px * meters_per_pixel
            if meters_per_pixel is not None
            else None
        )
        element["derived_geometry"] = {
            "area_px2": round(area_px2, 6),
            "perimeter_px": round(perimeter_px, 6),
            "area_m2": round(area_m2, 6) if area_m2 is not None else None,
            "perimeter_m": (
                round(perimeter_m, 6)
                if perimeter_m is not None
                else None
            ),
            "calibration_status": (
                "calibrated"
                if meters_per_pixel is not None
                else "uncalibrated"
            ),
            "meters_per_pixel": meters_per_pixel,
            "calculation": "polygon_shoelace_v1",
        }

    result["area_targets"] = canonical_area_targets(
        result.get("area_targets")
    )
    result["geometry_summary"] = build_geometry_summary(
        elements,
        result["area_targets"],
    )
    return result, canonical_dimensions
