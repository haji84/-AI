# Completion Run B — integration handoff (live)

Status: IN PROGRESS; not the final completion handoff.
Latest inspected main: 027e1d025ea9947ca7ae2d0a015a943c297466f6. Run B PR40/42/46/55 merged; Run A personnel, legal, maintenance/backup and Human-gated learning foundations preserved. Canonical PR59 financial authority/shared-PC fixes are being adopted; main CI37513897759 is Green (backend566 passed/14 declared skips, actual Chromium7 passed).
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

## Operational assets — Task 3 merged

Local implementation7a6bb633 plus fix2493c877; independent re-review PASS, latest-main adaptation/publication/CI/merge pending. Module operational_assets, router app.routers.assets, /assets, /ui/assets.js in the shared shell. Unmerged migration renamed042_run_b_operational_assets.sql after canonical Run A041; pre-PR main refresh remains required.
Tables: operational_assets, asset_locations, asset_lots, asset_balances, asset_loans, asset_movements, asset_services, asset_import_previews. SKU/lot separation, composite lot/asset and loan lineage FKs; common Facility.building_id, Employee.employee_id, Document.document_id and Task2 Vehicle/Incident IDs reused.
Permissions: asset.read/create/update/review/approve/admin/import/export and asset.borrower.read/manage; linked source permissions remain necessary. Stock is version-bound/locked/idempotent; disposal and service dates require Human review and approval with source versions and Document SHA binding. Imports cannot insert reviewed/official signatures. Date lineage is occurred_on versus created_at; no historical-as-of stock reconstruction claim.
Configuration: FIRE_AI_ASSET_BUSINESS_TIMEZONE defaults Asia/Tokyo; report as_of cannot alter actual issue expiry enforcement. No background process or paid AI dependency. Declared tzdata>=2025.2,<2027 supports hosts without an OS timezone database; isolated fresh import verified with PYTHONTZPATH empty. Existing CLI bootstrap registers emergency/operations/assets and canonical personnel models before SQLite create_all; PostgreSQL migrations and tenant boundaries preserved.
Integration tests: test_run_b_assets.py, fixround1 focused26 passed/1 explicit local PG skip; full308 passed/5 local PG skips; independent re-review PASS. Latest-main adaptation focused72 passed/4 explicit PostgreSQL/browser skips;42 migration parser/schema and JS/compile/diff success; stable full adaptation run pending. Actual PostgreSQL042 stock locks and test_assets_browser.py Chromium workflow execute in project CI after publication; production/Human acceptance is unclaimed. Exact API/coverage/limits: docs/completion/task-3-report.md. Subsequent statistics/dashboard/template adapters use asset/lot/location/movement/loan/service IDs and permission-aware services.

Task3 latest-main adaptation67221ef independently passed specification/security review; stable full323 passed with6 PostgreSQL and2 browser local skips, focused72/4. PR46 is published but unmerged. Main00f128cd PR45 adds signed-legal dependencies; assets is re-adapting canonical dependency file before refreshed CI/merge. Initial PR46 CI37481145661 executed PostgreSQL042 and actual assets/admin Chromium successfully. Latest-main45 adaptation25067d25 stable full349 passed/8 local skips; refreshed-head review/CI remain pending.

Task3 final integration: PR46 merged mainc4e692ed; migration042. Refreshed-head CI37482188445 SUCCESS: actual PostgreSQL backend355 passed, with2 browser cases skipped only in that job; separate actual Chromium job2 passed18.22s, covering administration and assets. Independent latest-main reviews PASS; canonical personnel/legal/tenant guards retained. Later common statistics/dashboard/template adapters remain internal Run B work.

Merged-main assets CI37482634204 SUCCESS: backend355 passed/2 browser-only skips118.44s; separate actual Chromium2 passed16.07s. Both jobs green on authoritative mainc4e692ed; migration042 verified.

Run A PR47/main7fb4ba0d supplies scheduled department backups and runtime maintenance exclusion. Run B uses these canonical get_db/startup/tenant/maintenance guards unchanged; finance adaptation is in progress.

## Finance integration preparation — unmerged

Task4 uses common ContractCase/Counterparty/Document/Change masters and adds fiscal policies/accounts, procurement candidates/events, reviewed financial proposals/amendments, immutable journal, import previews and rendered-form lineage. Proposed migration044 follows canonical learning043; numbering must be refreshed before publication. Router `/finance` and shared `/ui/finance.js` use existing session/RBAC/audit/tenant boundaries. Exact decimal adapters retain native PostgreSQL NUMERIC and legacy response compatibility; formal balances change only after explicit Human approval. Source versions and Document hashes are bound at review and rechecked before approval.

These are implementation interfaces awaiting independent review, actual CI and merge, not completed-module evidence. Task4 report records verification boundaries. Canonical52 learning integration stays intact; shared audio transcription is internal Task8/Task10 work, and common statistics/dashboard adapters remain scheduled.

Run A54 password expiry integration supersedes the preceding finance baseline: preserve canonical auth/session/password-policy and browser self-renewal surfaces, append finance hooks only. Its Migration045 means unmerged finance moves to046. Pre-adaptation408-pass local evidence does not establish final adapted-source/PG/browser success. Pending PR53 workforce foundations will be reused subject to latest-main and residual behavioral audit, with no duplicated workforce/employee master.

### Finance prepared interfaces (verification pending)

- New tables: finance_years, finance_accounts, finance_contract_profiles, finance_candidates, finance_contract_amendments, finance_import_previews, finance_procurement_events, finance_proposals, finance_journal, finance_rendered_forms. Append-only unmerged Migration046 follows canonical045; pending workforce044 is not replaced.
- Relationships: fiscal accounts→FinanceYear/parent account; profile→common ContractCase uniquely; candidate/proposal/event/amendment→common contract/vendor/Document; journal→approved proposal/account and reversal lineage; rendered forms→proposal/common FormTemplate/output Document. Common User IDs record creators/reviewers/approvers; no second contract/vendor master.
- Router: app.routers.finance `/finance`; exact contracts/vendor adapters and compatible legacy `/contracts` guards; unified search adapters for budget/procurement; shared `/ui/finance.js`. Bootstrap imports mapped finance models before fresh SQLite initialization; existing PostgreSQL runner applies046.
- Permissions: finance.read/create/update/review/approve/admin/import/export, plus existing contract.read/create/update/approve, document.read/create, template.read, search.use at source operations. Restricted reversal evidence is redacted; rendering requires transitive original-source authorization.
- Processes/configuration/dependencies: no finance background process, paid dependency or separate tenancy setting. Existing SQLAlchemy, openpyxl, common original-template renderer, server DB/storage/session and canonical password policy remain. ExactMoney uses native PostgreSQL NUMERIC(18,2) and fresh SQLite canonical decimal text; legacy SQLite numeric-affinity writes reject detected precision loss rather than claiming reconstruction.
- Integration tests: test_run_b_finance.py and test_finance_browser.py; existing administration/assets/learning/password browser coverage retained. Required actual PG CI includes distinct evidence locks, source refresh, payments/races/replay/immutable journal; actual Chromium verifies stage identity and exact balance workflow.
- Shared connections: common Documents/SHA, ContractCase/vendor/change history, form templates, source permissions, audit, search, bootstrap/module registry; later statistics/dashboard and common audio-intake adapters remain internal Run B integration.

Checkpointbc597a9 independent review found four defects; fixround1 addresses entity picker IDs, reversal source confidentiality/rendering, all standalone Evidence Document locks, and unambiguous reversible CSV/XLSX apostrophe encoding. Ten targeted regressions passed. Adapted-source full test and scoped independent re-review/actual CI/merge remain pending; no finance completion is asserted.

Latest-main PR56 Human role/exact rule/timed acting grants supersedes the finance046 publication baseline. Preserve canonical authz/personnel/authorization models, session renewal and browser flows; finance uses canonical permission_codes unchanged. Unmerged finance moves to048 after actual maximum047. First PR55 browser CI5passed is actual evidence; its PostgreSQL migration failed on split function bodies, so refreshed compatible-SQL CI and merge remain required. No runner/historical-migration weakening is permitted.

Main57 supplies canonical complete-statement SQL preflight, PostgreSQL function/dollar-quote support and no_parameters execution. All seven files are retained exactly. Finance048 independently avoids driver-dependent %ROWTYPE declarations by using RECORD with unchanged SELECT INTO/guards; native test calls the same runner execution option. Refreshed PR55 actual browser6passed; native CI exposed driver conversion and duplicate synthetic originals, now fixed in ea48ba3. Native Document uniqueness remains unchanged. Another actual CI must pass before finance can be merged/completed.

Native trigger namespace correction (fix4): finance_account_identity_guard resolves year and parent from quoted TG_TABLE_SCHEMA with parameterized UUIDs; absence uses primary-key null checks because dynamic EXECUTE does not set FOUND. Native tests cover quoted owning schema, pg_catalog-only callers and conflicting same-name shadow policies/parents. Guard behavior/payment races remain; this corrects the sole remaining failure in actual native CI (511passed/1failed/8skipped), not a second financial data source or tenant selector. Reviewed-head full CI is still pending.

Task4 merged proof: PR55/main0feb62e6, Migration048. CI37506769584 allGreen (backend513 passed/8 opt-in skips; separate actual Chromium6 passed). Finance source interfaces above now exist in main. Shared statistics/dashboard/audio remain internal later tasks; this is still a live, unfinished handoff.

Merged-main CI37507500474 SUCCESS on0feb62e6: backend513 passed/8 opt-in skips/227 warnings in250.04s; separate actual Chromium6 passed in59.69s. Both jobs Green on authoritative main; finance bounded integration verified. Remaining Run B internal tasks continue.

## Canonical workforce reuse boundary

PR53/main7b320db supplies app.workforce_models/schemas/service, routers.workforce `/workforce`, `/ui/workforce.js`, shared registration/search/PC hooks and immutable historical Migration044. Tables: workforce_shift_types, workforce_employee_qualifications, workforce_staffing_rules, workforce_roster_entries, workforce_leave_entries, workforce_attendance, workforce_time_entries, workforce_import_previews. Common Employee/OrganizationUnit/EmployeeAssignment/Document IDs remain authoritative; no separate personnel master. Permissions: workforce.read/create/update/review/approve/admin/import/export/aggregate plus source gates. Canonical authz.require_mutation_permission is retained. Core browser/PG/safety tests live in test_run_b_workforce.py and test_workforce_{browser,browser_state,concurrency,safety}. This existing slice remains Partial; Task5 extends the verified residuals, and Task11 closes queued-session/shared-PC integration across modules. No new background process or paid dependency. Main browser synchronization repair is pending actual CI.

Canonical workforce browser repair PR58/main386582ce adopted exactly; mainCI37511281181 backend546 passed/14 skips and real Chromium7 passed, both Green. No duplicate workforce implementation or parallel browser fix retained. Task5 residual functionality and shared session integration still require completion.

## Task6 inquiry integration — pending review and merge

Local inquiry product with reviewed security and UI corrections extends the existing shared app with `/inquiries` and `/ui/inquiries.js`, module registration and fresh bootstrap. Append-only Migration050 (renumbered after canonical main049_violation_correction.sql; provisional until pre-PR refresh) adds inquiries, inquiry_evidence, inquiry_candidates and inquiry_rendered_forms. Evidence references existing source UUIDs and optional common Document; rendered forms reference common FormTemplate and Document; creators/reviewers/approvers reference app_users. Approved inquiry revisions link the original inquiry ID. No additional personnel, incident or document master is created.

Permissions: inquiry.read/create/update/review/approve/admin/import/export plus cumulative underlying source permissions. Typed adapters cover Document/personnel/emergency/facility/contracts/finance/incident/vehicle/assets/workforce/legal/fire. Answer prose and numbers, candidates, search/counts, originals and rendered outputs retain source confidentiality. Generic audits contain IDs/state/version/counts and change/source hashes, with raw content retained behind inquiry/source access. Human review and approval require fresh evidence and originating session; candidates remain separate.

PC surface supplies source selection, exact quotes/numeric claims, editing, review/approval, revisions, year/lexical search, CSV/XLSX exchange and original-template rendering. Local-model adapter is optional in-process; deterministic evidence extraction is labeled. There is no new background worker, paid dependency or external endpoint. Model work and import decoding precede short canonical mutation decisions. DOCX/XLSX/PDF use existing original renderer; mapped Excel text remains exact literal strings and unmapped formulas remain unchanged.

Tests: test_run_b_inquiries.py, test_inquiries_browser_state.py and test_inquiries_browser.py; native PostgreSQL and actual Chromium CI are wired. Latest corrective focused run67 passed/2 environment skips and actual audit-only regression1 passed. Historical full-suite coverage is explicitly pre-delta. Independent Spec/Quality review, final-head full/native/browser CI and main merge remain internal gates. Evidence provenance and source Document guards connect existing download/search/intake/finance consumers; canonical PR59 finance authority/shared-PC changes are preserved.

Canonical PR60/main027e1d violations/corrective-evidence code is retained. Main CI37520767373 is Green (backend605 passed/18 declared skips; actual Chromium8 passed). Shared hooks preserve these modules and add inquiry as the ninth browser workflow. PR61 initial native/backend596 passed but browser adoption race failed; source-readiness correction and latest-main rebase are under independent review. No canonical Migration049 was edited.
