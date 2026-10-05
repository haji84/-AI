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

    return result, canonical_dimensions
