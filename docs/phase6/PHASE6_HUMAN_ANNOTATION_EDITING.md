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


## Floor / region summary

Every save/review also rebuilds a server-authoritative `geometry_summary`.

The summary includes:

- total annotated region count
- per-floor region count
- per-floor room count
- per-floor arbitrary-zone count
- per-floor annotated area total in px²
- per-floor annotated area total in m² when calibrated
- calibrated / uncalibrated region counts
- `metric_area_complete`
- interior-overlap warnings

The browser recalculates the same summary immediately while vertices are edited, but the backend overwrites the client summary on save/review.

### Overlap warning policy

Two regions are warned only when their interiors overlap.

Normal shared boundaries between adjacent rooms are not warnings.

Regions on different pages are never compared.

Regions with two explicit different floor numbers are not treated as overlapping even if their drawing coordinates happen to coincide.

Overlap warnings are review aids. They do not automatically reject the Annotation because some intentional arbitrary zones may overlap other regions.

### Important meaning of totals

`area_m2_total` is the sum of annotated room/zone polygons.

It is **not** automatically the statutory or architectural floor-area determination.

Walls, shafts, voids, open-plan functional zones, intentionally overlapping arbitrary zones, and incomplete Annotation coverage can make the annotated sum differ from a formal floor area.

The UI therefore labels it as an annotated-region total and keeps overlap warnings visible for Human review.


## Human floor-area targets

A reviewer can optionally register a known floor area in square meters for each floor.

Example:

```json
{
  "floor_number": 1,
  "target_area_m2": 78.66,
  "label": "1階",
  "source": "printed_area_table",
  "comparison_basis": "rooms_only"
}
```

Rules:

- at most one target per floor
- target area must be greater than 0
- targets are Human evidence, not derived values
- arbitrary `zone` polygons are excluded from the target comparison
- the comparison uses the sum of calibrated `room` polygons only
- if any room on the floor is uncalibrated, difference m² / % remains unresolved
- if no room Annotation exists for the target floor, the target is marked `missing_floor_annotation`

Reference Draft import can derive targets from:

`source_observations.floor_area_m2`

For example, the supplied house-plan-001 values:

- 1F = 78.66 m²
- 2F = 33.44 m²

are imported automatically as floor targets.

The comparison is an Annotation consistency check only. It does not certify the statutory floor area.
