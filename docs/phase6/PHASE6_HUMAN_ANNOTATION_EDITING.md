# Phase 6 Human Annotation Editing and Area Calculation

Updated: 2026-10-06

## Goal

Allow a Human reviewer to correct AI/manual drawing polygons directly and keep geometry-derived measurements synchronized automatically.

## Editing

Draft annotations support:

- add a new `room`
- add a new arbitrary `zone`
- select an existing region
- drag polygon vertices
- add a vertex
- delete a selected vertex while preserving at least 3 vertices
- correct label
- correct use code
- correct floor number

Reviewed annotations remain immutable through the ordinary Draft edit endpoint.

## Area calculation

The browser calculates area immediately for feedback.

The backend is authoritative and recalculates every saved/reviewed element using polygon shoelace geometry.

Stored per element in `derived_geometry`:

- `area_px2`
- `perimeter_px`
- `area_m2`
- `perimeter_m`
- `calibration_status`
- `meters_per_pixel`
- `calculation=polygon_shoelace_v1`

A client-supplied `derived_geometry` value is never trusted. The backend overwrites it.

## Scale calibration

Square meters require page calibration.

Calibration method v1:

1. Human selects two points on a known drawing dimension.
2. Human enters the real-world distance in meters.
3. System computes:

```
pixel_distance = distance(point_a, point_b)
meters_per_pixel = reference_length_m / pixel_distance
area_m2 = polygon_area_px2 * meters_per_pixel^2
```

Calibration is stored per page inside `page_dimensions[page].calibration`.

If a page is not calibrated:

- px² remains available
- m² remains null
- UI explicitly says the square-meter value is unresolved

This prevents an image or scan from silently inventing metric area from pixel size alone.

## Multi-page drawings

Each region keeps `page_no`.

Each page keeps its own:

- preview dimensions
- calibration
- meters-per-pixel value

A scale from page 1 is never automatically reused on page 2.

## Human Reference gate

Both `room` and `zone` require a label or use code before Human review.

Geometry edits and scale changes update the saved Reference SHA and therefore invalidate stale downstream Benchmark evidence naturally.
