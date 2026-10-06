# Task 2 — Shared incident/dispatch and fleet

Read RUN_B_CONTRACT.md and AGENTS.md. Baseline main240703a9 / PR40 is merged; code in this workspace includes it. No native git remote is available; root handles GitHub refresh/PR/merge.

Implement a usable operational domain in the existing application. Do not stop at scaffolding.

## Exact scope

Shared incident/dispatch: fire/rescue/emergency_support/watch/storm/other incidents; emergency link to existing EmergencyCase; fire-investigation link to existing FireInvestigationCase. A link references source IDs; don't duplicate address/call time/number from linked source. Non-linked incidents own their source fields. Dispatch unit/vehicle/crew (existing Employee)/times/activity/report/allowance candidate/official Human approval/counts/monthly/yearly/CSV-XLSX.
Fleet: shared vehicle registry; operational trips/odometer/fuel/fuel receipts-and-issues/inspection/vehicle inspection/repair/fault/cost/next inspection/next service/deadline warnings/use history/incident-dispatch links. Decimal amount/liters; odometer consistency; immutable or optimistic versioned histories; no silent stock underflow or negative mileage. No externally fetched legal rates or invented financial allowance policy. Configure approved allowance rates, store draft calculation, explicit Human approval only.

## Interfaces

New files backend/app/operations_models.py, operations_schemas.py, operations_service.py, routers/operations.py; router prefix /operations; vehicle PK vehicle_id, incident PK incident_id, dispatch PK dispatch_id. Register router in main. Migration039 provisional; parent rechecks and renumbers.
Existing app.db.Base/get_db, authz.require_permission/permission_codes, audit.write_audit, models.uuid_str/now_utc, Employee.employee_id, EmergencyCase.emergency_case_id, FireInvestigationCase.fire_investigation_case_id (verify actual property in models), Document.document_id. Reuse existing code; no common-core redesign or tenant implementation.
Use unique linking constraints so one source case isn't copied into several incidents. Parent-case/vehicle row locks plus expected_version; SQL-backed constraints for money/mileage/range/relationships. Preserve source facts separately from candidate allowance/review.

RBAC operational incident.read/create/update/review/approve/admin and fleet.read/create/update/review/approve/admin as needed. Existing seed_rbac/role registry additive; aggregate-only exports separate sensitive crew detail read gate. Audit writes/approve/cancel/import/export. Refuse user IDs/body fields that pretend to choose tenant DB.
Same shell /ui/, shared header/session/auth permissions. New frontend/operations.js modal, usable CRUD/dispatch/vehicle/trip/fuel/service/actions/reviews/alerts/stats/import/export with escaped text, zero preserved, stale-write message. No separate app.
Connect existing search via permission-filtered operational case/fleet source IDs; source lineage in aggregates to authorized detail readers only. Register operations and fleet modules without duplicating emergency_reporting or fire_investigation.

## Tests / deliverable

Synthetic end-to-end CRUD, unique source links, shared Employee/Vehicle/Document FKs, inactive employee checks, backend RBAC denies, stale version409, audit, allowance Human gate, actual imports/exports, source-preserving linked incidents, search privacy, odometer/fuel validations, inspection/repair deadline warnings, same-shell surface/JS syntax.
Run focused tests (expected red before implementation), all backend tests, parser and frontend checks. No real data or dependency installation necessary. You may edit own domain and minimal main/RBAC/module/search/index registration. Do not modify emergency or Run A foundation semantics. Do not spawn any subagents, reviewers or helpers; root handles independent review.
Make local git commits if useful; no GitHub writes. Return report path + short status/commit/test count/concerns. Full report docs/completion/task-2-report.md: exact delivered coverage, true remaining items, file list, API/permission/DB relationships, import/export/output, test commands/results, external acceptance, and interface points. Never classify missing code as External Gate.
