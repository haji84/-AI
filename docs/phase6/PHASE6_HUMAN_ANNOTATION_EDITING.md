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


## Boundary snapping

Draft Annotation editing supports optional boundary snapping.

Policy:

- snapping is enabled by default
- Human can toggle snapping ON/OFF
- display-space threshold is approximately 10px
- the threshold is converted into drawing-coordinate units from the current SVG viewport
- only regions on the current page are considered
- the actively edited region is excluded from its own snap targets
- candidate snap targets:
  - vertices of other `room` / `zone` polygons
  - nearest projected point on edges of other `room` / `zone` polygons
- exact nearby vertices take precedence over edges when distances are equal
- new-region point placement uses the same snap engine
- vertex dragging uses the same snap engine
- a visible snap indicator shows the selected target type and region label
- snapping changes only the coordinate selected by the Human editor; backend area/summary recalculation remains authoritative

Why:

- reduce tiny gaps between adjacent rooms
- reduce accidental small overlaps
- make shared boundaries easier to align
- improve downstream area totals and Geometry Benchmark quality without auto-changing Human intent

Snapping is a UI aid, not an automatic topology correction. It never moves an entire region or silently changes saved Geometry after the Human releases the pointer.


## Undo / Redo and unsaved-change protection

Draft Human Annotation editing keeps a bounded local edit history.

Tracked persistent edits:

- room/zone metadata correction
- vertex drag
- vertex add
- vertex delete
- room/zone add
- room/zone delete
- page scale calibration
- page scale calibration removal
- known floor-area target add/update
- known floor-area target removal

Behavior:

- maximum retained Undo depth: 50 snapshots
- one vertex-drag gesture creates one history checkpoint, not one checkpoint per pointer-move event
- a new edit after Undo clears the Redo stack
- Undo/Redo restores Annotation payload and page-dimension calibration together
- restored Geometry immediately rebuilds local area/perimeter/floor summaries
- saving a Draft establishes a new saved checkpoint and clears Undo/Redo history
- the UI shows `未保存` or `保存済み`
- keyboard shortcuts:
  - Ctrl/Command + Z: Undo
  - Ctrl/Command + Shift + Z: Redo
  - Ctrl/Command + Y: Redo
- text fields keep their native browser Undo behavior because global shortcuts are not intercepted while an input/textarea/select has focus

Unsaved-change protection:

- closing the Drawing workspace asks before discarding unsaved Annotation edits
- switching to another Annotation asks before discarding unsaved edits
- opening a different Drawing workspace asks before discarding unsaved edits
- importing another Human Reference Draft asks before discarding unsaved edits
- browser/tab close uses `beforeunload` while unsaved edits exist

The Undo/Redo stack is a UI editing aid only. The backend remains authoritative after save and recomputes derived Geometry/area evidence from the submitted Annotation.


## Reviewed Annotation revision workflow

A reviewed Human Annotation remains immutable evidence.

When a reviewed Annotation needs correction:

1. choose `修正版Draftを作る`
2. optionally record a revision note
3. the backend creates a new Draft Annotation
4. Geometry, calibration, area targets, equipment/fact candidates, and derived evidence are copied
5. the backend recalculates Geometry-derived evidence
6. the new Draft can use the ordinary editing tools:
   - vertex drag
   - vertex add/remove
   - room/zone add/remove
   - calibration
   - area target correction
   - snapping
   - Undo/Redo
7. the old reviewed Annotation remains unchanged and exportable as its original Human Reference evidence
8. the revision requires a new explicit Human review before it becomes benchmark truth

Revision provenance is stored in `payload.revision_history[]`:

- source Annotation ID
- source Annotation version
- source reviewed timestamp
- revision note
- revision creation timestamp

Rules:

- only a `reviewed` Annotation can create a revision Draft
- optimistic version matching is required
- a Draft cannot recursively create another revision Draft
- the copied revision always starts at `status=draft`
- prior review state is never inherited
- creating/editing a revision never mutates the source Annotation
- after the revision is reviewed, both old and new References remain immutable evidence; Baseline readiness selects the latest reviewed Reference and reports multiple reviewed References as a warning
