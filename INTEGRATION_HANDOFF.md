# Completion Run B — integration handoff (live)

Status: IN PROGRESS; not the final completion handoff.
Baseline: main89e87e1739add38d2e5de7afac195c14e58b6a4f (Run A PR41/43 and Run B PR40/42 merged).
Detailed remaining scope: docs/completion/RUN_B_STATUS.md.

## Added module surface

Existing module emergency_reporting is extended; no parallel application or duplicated Case/Patient/Employee/Document master.
- Models in app.emergency_models; loaded by registered emergency router.
- Tables: emergency_treatments; emergency_report_drafts.
- Existing table emergency_clinical_flags gets optimistic version and unique candidate_fingerprint columns.
- Migration 038; append-only relative to baseline 001–037, re-number if main advances.
- Relationships: treatments.patient -> emergency_patients; treatment.source_document -> documents; treatment.created_by -> app_users; report.case -> emergency_cases; report creators/reviewers -> app_users. Existing crew.employee -> employees remains authoritative.

## API and permissions

router app.routers.emergency, /emergency:
- cases list/detail/create/update: emergency.case.read/create/update.
- patients list/create/update: emergency.patient.read/create/update; parent-case read on listing/creation.
- crew list/create: emergency.crew.read/manage; common employee required.
- treatments list/create: emergency.patient.read/update; source Document requires document.read.
- clinical candidates: emergency.clinical.generate + emergency.patient.read.
- candidate review: emergency.clinical.review + emergency.patient.read; expected_version and unchanged evidence required.
- report snapshots create/list/review: emergency.report.create/read/review plus case/patient/crew read.
- input checks: case/patient/crew read.
- clinical-statistics: emergency.report.read; aggregate counts only; no individual IDs/text.
- audited workbook import: emergency.import; reuses app.importers.emergency.

Permissions added by existing seed_rbac; new emergency_editor and emergency_reviewer roles.
Existing emergency_reporter remains aggregate-only; no patient privilege added.
Existing audited importer now locks and refreshes existing parent Case and Patient rows, matching operational lock order; original mapping is unchanged.
Existing main /emergency/reports/summary and /export + emergency.report.export are retained, not reimplemented.

## Frontend

Existing /ui/ header has emergency module button; /ui/emergency.js uses shared session/api/escaping/modal styles.
Uses main /auth/permissions. Main /ui/emergency.html remains the aggregate/output screen.
No smartphone-specific scope or external frontend package.
Case search joins existing search registry, requires emergency.case.read, excludes patient fields.

## AI / review / audit

No LLM inference added. Deterministic CPA/allergy candidates store rule version, source field snapshots, patient version, treatment IDs and provenance hash.
CPR/chest compression records only suggest CPA; Human must review evidence.
Unknown/negated free text is not assigned a fabricated diagnosis.
Candidates never mutate the patient diagnosis or source payload.
Confirmed flags with changed evidence are excluded from clinical counts; old evidence remains intact.
Reports capture source snapshots; Human review rejects changed evidence and reviewed reports are immutable.
Write/import/review/statistics actions use existing write_audit.

## Configuration, workers, dependencies

No new background process; no new package dependency.
Uses existing FIRE_AI_DATABASE_URL, FIRE_AI_STORAGE_ROOT and server session configuration.
Re-run existing scripts/seed_rbac.py after deployment; apply new migration using existing migration runner.
Tenant routing/isolation uses Run A's canonical server-selected DB/service and storage-identity contract from PR41. Task2 integration regressions exercise that boundary; actual tenant deployment/acceptance remains a separate operational gate.

## Integration tests

backend/tests/test_run_b_emergency.py: operational CRUD/version conflict, candidate separation/Human review/stale evidence, negation, checks, source immutability, report snapshot, shared employee, audited workbook idempotency, RBAC privacy, case search, UI wiring.
Existing test_emergency_reports.py and all prior tests must remain green.
Migration parser and frontend JavaScript syntax are required. Production PostgreSQL migration and actual browser acceptance are still required.

## Known limitations / connection points

- Structured report forms, official template export, CSV mapping, code-name masters and full date/day-offset validation remain internal backlog.
- Case/patient deletion/retirement and treatment/report editing UI are not implemented in this slice.
- Text candidate rules are intentionally conservative and not a clinical classifier.
- Clinical candidates have database-unique source fingerprints; parent-case/patient row locks serialize PostgreSQL clinical/record/report operations. Actual PostgreSQL concurrent-client acceptance remains required.
- Run A's tenant boundary is available in main89e87e17; actual deployment acceptance remains coordinated; the common temporal OrganizationUnit/EmployeeAssignment contract is now available in PR44.
- Task2 implements shared Incident/Dispatch and operational fleet; assets, budgets/contracts execution, inquiries/statistics/dashboard remain Run B backlog.
- Full Run B completion and system release are not declared.

## Operations and fleet — Task 2 merged

PR42 merged main89e87e17 after refreshed-head CI37470033732 success and independent spec/quality reviews PASS. Local full282 passed with4 explicit PostgreSQL skips; CI runs actual PostgreSQL. Exact contracts and limitations: docs/completion/task-2-report.md.
Modules operations/fleet; router app.routers.operations, prefix /operations; frontend /ui/operations.js in the same header/session/search shell.
Tables: operation_incidents, operation_vehicles, operation_allowance_rates, operation_dispatches, operation_dispatch_crew, operation_vehicle_trips, operation_fuel_entries, operation_vehicle_services, operation_import_previews.
Append-only Migration040 follows canonical Run A tenant-identity039. Historical001–038 are unchanged; the original Task2 provisional039 allocation is superseded.
Relationships: incident uniquely links existing EmergencyCase or FireInvestigationCase; dispatch references incident/shared vehicle; crew/driver reference Employee; dispatch/trip/fuel/service reference Document; creators/reviewers/approvers reference existing User. Trip/dispatch vehicle and repair/fault vehicle matching have composite FKs. No linked address/date/number copy.
Permissions: incident/fleet read/create/update/review/approve/admin/aggregate/import/export, plus incident.crew.read/manage; original source read permissions remain separately required. Existing seed_rbac and module/search registration are additive.
Human gate: configured approved rates/rounding -> allowance candidate -> dispatch review -> approval; cancellation preserves approved decision and excludes it from current totals. Service deadlines and explicit fault resolution apply only through Human approval.
Imports: actual CSV/XLSX preview with file SHA/uploader/expiry/schema validation, explicit version-bound confirmation and atomic rechecks. No official decisions imported. Exports are formula-safe operational data, not invented official layouts.
Background process/dependencies: none added; existing SQLAlchemy/session/audit/RBAC/storage and openpyxl reused. Deployment re-runs RBAC seed and existing migration runner.
Integration tests: backend/tests/test_run_b_operations.py (31 tests), test_run_b_operations_tenant_integration.py (5 local cases +1 optional PostgreSQL case), and canonical test_tenant_boundary.py. Historical PR41 focused52/full263 passed with2 local PostgreSQL skips; latest PR43 focused40/full282 passed with4 local skips. Parser40 migrations passed. Actual local PostgreSQL concurrency/browser acceptance is not claimed.
Run A connection: get_db/authz/Employee/Document/source-case IDs, no client tenant selector; effective-dated organization/history is available in PR44; actual tenant deployment acceptance remains coordinated. Subsequent Run B statistics/dashboard/templates adapters consume vehicle_id/incident_id/dispatch_id and /operations statistics/history services.

Task2 fixround1: permission-filtered mutation responses, complete mixed-source export columns, and separate fuel purchase expense/issue valuation implemented;31 focused and242 full tests passed. Scoped independent re-review passed.

Task2 latest-main adaptation: exact Run A PR41 snapshot preserves startup, HTTP Host/storage/DB guards, BoundSession and initializer. Operational integration tests use two synthetic server-bound databases and an optional PostgreSQL source-lock/stale-approval check; test evidence and local skips are recorded in task-2-report.md. Fresh-base PR42 CI37470033732 is successful; no real-browser result is inferred from CI.

Canonical PR43 integration retains validate_runtime_binding startup, department-bound backup/restore and isolated deployment generation. PR42 fresh-base CI37470033732 succeeded, including PostgreSQL migration/locking/tenant tests. Main push CI37470396667 SUCCESS; actual deployed LAN/browser acceptance remains unverified.

Merged-main evidence: workflow37470396667 job112292064798 reports286 passed,168 warnings,88.90s; no skipped tests in CI. This includes the4 PostgreSQL tests skipped in the local SQLite-only environment.

## Operational assets — Task 3 review candidate

Local implementation7a6bb633 plus fix2493c877; independent re-review PASS, latest-main adaptation/publication/CI/merge pending. Module operational_assets, router app.routers.assets, /assets, /ui/assets.js in the shared shell. Unmerged migration renamed042_run_b_operational_assets.sql after canonical Run A041; pre-PR main refresh remains required.
Tables: operational_assets, asset_locations, asset_lots, asset_balances, asset_loans, asset_movements, asset_services, asset_import_previews. SKU/lot separation, composite lot/asset and loan lineage FKs; common Facility.building_id, Employee.employee_id, Document.document_id and Task2 Vehicle/Incident IDs reused.
Permissions: asset.read/create/update/review/approve/admin/import/export and asset.borrower.read/manage; linked source permissions remain necessary. Stock is version-bound/locked/idempotent; disposal and service dates require Human review and approval with source versions and Document SHA binding. Imports cannot insert reviewed/official signatures. Date lineage is occurred_on versus created_at; no historical-as-of stock reconstruction claim.
Configuration: FIRE_AI_ASSET_BUSINESS_TIMEZONE defaults Asia/Tokyo; report as_of cannot alter actual issue expiry enforcement. No background process or paid AI dependency. Declared tzdata>=2025.2,<2027 supports hosts without an OS timezone database; isolated fresh import verified with PYTHONTZPATH empty. Existing CLI bootstrap registers emergency/operations/assets and canonical personnel models before SQLite create_all; PostgreSQL migrations and tenant boundaries preserved.
Integration tests: test_run_b_assets.py, fixround1 focused26 passed/1 explicit local PG skip; full308 passed/5 local PG skips; independent re-review PASS. Latest-main adaptation focused72 passed/4 explicit PostgreSQL/browser skips;42 migration parser/schema and JS/compile/diff success; stable full adaptation run pending. Actual PostgreSQL042 stock locks and test_assets_browser.py Chromium workflow execute in project CI after publication; production/Human acceptance is unclaimed. Exact API/coverage/limits: docs/completion/task-3-report.md. Subsequent statistics/dashboard/template adapters use asset/lot/location/movement/loan/service IDs and permission-aware services.

Task3 latest-main adaptation67221ef independently passed specification/security review; stable full323 passed with6 PostgreSQL and2 browser local skips, focused72/4. PR46 is published but unmerged. Main00f128cd PR45 adds signed-legal dependencies; assets is re-adapting canonical dependency file before refreshed CI/merge. Initial PR46 CI37481145661 executed PostgreSQL042 and actual assets/admin Chromium successfully. Latest-main45 adaptation25067d25 stable full349 passed/8 local skips; refreshed-head review/CI remain pending.
