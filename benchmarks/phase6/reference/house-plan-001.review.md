# House Plan 001 Geometry Human Review

Source: `平面図-1024x745.jpg`  
Source SHA-256: `2df43a8f5cebe48f2a55ae8968714319ca05491088d98a1e6038fd0b10aa26b6`  
Reference: `benchmarks/phase6/reference/house-plan-001.reference.json`

## Status

Current Reference status: `pending_human_acceptance`

The 12 room/zone polygons below are a Draft prepared from the supplied 1024x745 drawing. They must be visually reviewed and corrected before `reference_status` can become `human_accepted`.

| Label | Use | Geometry quality | Review focus |
|---|---|---|---|
| UB | bathroom | strict_wall_bounded | wall faces / door-side boundary |
| トイレ | toilet | strict_wall_bounded | lower wall / hall opening |
| 洗面脱衣室 | washroom_dressing | strict_wall_bounded | south door opening boundary |
| 玄関 | entrance | circulation_approx | south boundary into hall |
| ホール | hall | circulation_approx | irregular circulation shape |
| WIC | walk_in_closet | strict_wall_bounded | doorway edge |
| 主寝室 | bedroom | strict_wall_bounded | closet line is inside room |
| タタミコーナー | tatami_area | open_plan_approx | open boundary toward L |
| L | living | open_plan_approx | functional-zone boundary |
| D | dining | open_plan_approx | functional-zone boundary |
| K | kitchen | open_plan_approx | east service-space boundary |
| P | pantry | service_area_approx | pantry/refrigerator-space split |

## Human acceptance checklist

1. Confirm each label and use code.
2. Correct polygon points where the Draft crosses a wall or excludes a room area.
3. Pay particular attention to open-plan L/D/K/Tatami boundaries. These are functional zones, not physical walls.
4. Confirm whether `P` should be treated as Pantry and whether the adjacent refrigerator space belongs inside or outside that zone.
5. Confirm that the source image really represents 1F and that all 12 regions belong to page/floor 1.
6. After corrections, set:
   - `reference_status: human_accepted`
   - `human_gate.accepted: true`
   - `human_gate.acceptance_note`
   - `human_gate.accepted_by`
   - `human_gate.accepted_at`

Until then, `benchmark_drawing_analysis.py` rejects this Reference.
