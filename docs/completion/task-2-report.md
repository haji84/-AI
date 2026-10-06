# Task 2 report — shared incident/dispatch and operational fleet

Status: implemented locally against the Run B Task 2 brief on the existing isolated Work branch and adapted to canonical main0335b59e / Run A PR43. Root owns refreshed-base independent review, CI and publication; no GitHub writes were performed by this task owner. The original baseline was main240703a9 / PR40; its emergency slice is retained. Migration040 follows canonical039 without a local collision. No Run A foundation, emergency-domain or fire-investigation semantics were redesigned.

## Delivered coverage

| Requested capability | Delivered behavior |
| --- | --- |
| Shared incident registry | CRUD via create/read/versioned update and audited cancellation; fire/rescue/emergency_support/watch/storm/other supported. Lists have search and pagination. Cancelled incidents are immutable; active dispatches must be cancelled first. |
| Source-case links | Real `EmergencyCase.emergency_case_id` and `FireInvestigationCase.fire_investigation_case_id` FKs, each unique across incidents. Only one linked source may be selected. SQL constraints and strict schemas forbid copies of linked address, number and call/occurrence timestamps. Original source data is projected at read time under its own permission. Source links cannot be moved through a patch. |
| Dispatch | Incident-owned unit, shared vehicle, departure/arrival/return timestamps, activity, report and optional existing Document ID. Versioned edits apply only to drafts. Parent incident and linked source rows are locked; parent version is required when adding a dispatch. Reviewed/approved reports cannot be edited. |
| Shared crew | Shared Employee IDs, active-employee checks, per-dispatch employee uniqueness, roles, assignment/removal against dispatch expected_version. Separate crew read/manage gates. Employee picker uses the existing employee registry, without creating parallel personnel records. |
| Allowance | No seeded financial amount, externally fetched legal rate or implicit rounding policy. Human supplies amount, basis (per dispatch / per crew / per hour), explicit rounding mode and organizational approval reference. Rate is draft until explicit Human approval. Calculation stores a candidate amount and source/crew/rate/version evidence. Dispatch Human review and subsequent explicit approval are separate transitions. Changed sources reject stale approval. |
| Financial decision history | Approved numeric allowance and approver remain on the typed dispatch record when cancelled; cancellation has its own reason, actor and time. Cancelled records leave current official totals. Rate approval notes and report/service decision reasons are retained. |
| Counts and statistics | Monthly/yearly incident kinds, dispatch counts, approved dispatch counts and official allowance. Fleet monthly/yearly trip distance, fuel liters by receipt/issue/refuel, fuel purchase expense (receipts plus external refuels), separate informational issue valuation and approved service costs. Aggregate-only users receive no source IDs. Authorized detail readers receive permitted source incident/vehicle IDs. Undated incidents are not attributed to an invented month/year. |
| Shared vehicle registry | `vehicle_id` PK, unique code, name/registration/notes, versioned edit and activation/deactivation. Current odometer and fuel stock can change only through the operational history APIs, rather than arbitrary registry patches. |
| Trips and use history | Immutable trip entries with driver Employee / Document / dispatch links, full timezone-aware timestamps, start/end mileage, purpose. Start odometer must match current vehicle mileage; end cannot precede start; overlapping earlier use is refused. Linked dispatch must use the same vehicle, also enforced by a composite SQL FK. Vehicle lock and expected_version protect odometer updates. |
| Fuel | Immutable decimal liters/amount entries: receipt increases vehicle-allocated stock, issue consumes that stock, external refuel records purchase/use without changing allocated stock. Underflow, negative cost, nonpositive liters, stale version and numeric range overflow are rejected. Receipt Document IDs reuse the existing Document registry. This is explicitly allocated stock per vehicle, not an invented centralized depot ledger. |
| Fleet service | Inspection, vehicle inspection, repair, fault and service drafts, decimal cost, Document reference, candidate next inspection/service dates and mileage. Human review then approval; only approval applies dates to the vehicle. Approval requires expected vehicle version. Approved histories cannot be edited/cancelled. Draft/reviewed histories may be cancelled and replaced. |
| Fault resolution | Repair explicitly references the particular unresolved fault on the same vehicle. Human repair approval requires expected fault version and vehicle version, records typed resolution link/time and increments the fault version without changing its original description. Unrelated repairs never implicitly resolve faults. |
| Warnings | Configured inspection/service dates within 30 days or overdue, service mileage due, unresolved faults. Successfully resolved faults leave warning results while their records remain in history. No legal deadline is invented; dates/mileage come from Human-approved service records. |
| CSV/XLSX | Real import parser and exporter for incidents, dispatches, crew, vehicles, trips, fuel and services. Import templates specify exact schema columns plus parent ID/expected_version where needed. Aggregate-only summary exports are separate from sensitive crew/detail exports. Formula-like exported cells are escaped. CSV/XLSX columns are the union of permission-filtered row keys, so later linked source projections and restriction indicators are retained. |
| Import preview and confirmation | Upload executes the real invariant checks transactionally and rolls back all domain/audit draft writes; it persists only a bounded preview/provenance record and preview audit. Preview returns row count, sample, original file SHA256 and expiry. Explicit confirmation binds uploader, preview version and digest, rechecks current references/permissions/versions and applies all rows atomically. Repeated, expired, mismatched or concurrently stale confirmation is rejected. Official decision fields, tenant selectors and user-ID fields cannot be imported. |
| Search integration | Existing `/search` gains permission-filtered `operations` and `fleet` modules, uses real incident/vehicle IDs, and links to their shared modal. Original case facts participate only under original domain read gates. Crew data is excluded. Existing emergency_reporting and fire_investigation identities are preserved. |
| Same-shell PC UI | `frontend/operations.js` modal uses `/ui/` header, existing session, API helper, escaping and styles. Actual lists, search/pagination, incident/source selectors, dispatch/crew/rate forms, Human review/approval/cancellation, vehicle/trip/fuel/service/fault forms, use history, alerts, statistics, import template/preview/confirm and file-download exports. Explicit stale-write message and reload controls. Zero amounts/mileage are preserved. |
| Audit / security | Domain writes, Human decisions, cancellations, crew removal, previews, confirmed imports and exports use existing audit service in the same transaction. Server-side permission checks remain authoritative; private responses and downloads use no-store. Strict body models forbid tenant/database/user spoofing. |

## API and permission contract

All APIs use the existing session cookie and `/operations` prefix. No separate authentication app or tenant selector exists.

| API family | Gates / version contract |
| --- | --- |
| `GET/POST /incidents`, `GET/PATCH /incidents/{incident_id}` | `incident.read/create/update`; PATCH requires incident expected_version. Original case permission additionally required for linked writes. |
| `POST /incidents/{incident_id}/cancel` | `incident.admin` + read, reason and expected_version; no active dispatches. |
| `GET/POST /incidents/{incident_id}/dispatches`, `GET/PATCH /dispatches/{dispatch_id}` | incident read/create/update; adding dispatch requires parent expected_version, editing dispatch its own version. Original case detail gate applies. Shared vehicle selection additionally requires fleet.read. |
| `GET /employees`, `GET/POST /dispatches/{dispatch_id}/crew`, `POST /crew/{crew_id}/remove` | `incident.crew.read/manage` and incident read as appropriate; crew writes consume dispatch expected_version and invalidate any draft allowance calculation. |
| `GET/POST /allowance-rates`, `POST /allowance-rates/{rate_id}/approve` | incident.read; incident.admin for configuration; incident.approve for Human rate approval. No approved-rate editing API. |
| `POST /dispatches/{dispatch_id}/calculate`, `/review`, `/approve`, `/cancel` | incident update/review/approve/admin respectively, plus incident.read and incident.crew.read. Draft -> reviewed -> approved is explicit; cancellation retains the approved numeric decision. |
| `GET/POST /vehicles`, `GET/PATCH /vehicles/{vehicle_id}` | fleet read/create/update; registry changes require vehicle expected_version. Odometer/stock/deadlines are excluded from PATCH. |
| `POST /vehicles/{vehicle_id}/trips`, `/fuel`, `/services` | fleet.create + read and vehicle expected_version. Driver links require incident.crew.read, dispatch links require incident.read and original case gate, Document links require document.read. |
| `GET /vehicles/{vehicle_id}/history` | fleet.read; driver, dispatch and Document IDs are filtered by their additional read gates. |
| `POST /services/{service_id}/review`, `/approve`, `/cancel` | fleet.review/approve/admin + read and service expected_version. Approval also requires expected_vehicle_version; explicit repair resolution requires expected_fault_version. |
| `GET /statistics`, `/fleet-statistics` | incident.aggregate / fleet.aggregate. Year/month ranges validated; source lineage IDs appear only to authorized detail readers. |
| `GET /alerts` | fleet.read; optional `as_of` date for review. |
| `POST /import/{dataset}`, `POST /import-previews/{preview_id}/confirm` | domain.import/create/read plus referenced detail gates; crew import also requires crew read/manage. Confirmation cannot nominate another uploader. |
| `GET /import-template/{dataset}` | corresponding import permission. |
| `GET /export/{dataset}?format=csv|xlsx` | domain.export + detail read or aggregate; crew additionally requires crew read. Summary exports always strip lineage. |

Additive seeded roles: incident_editor, incident_reviewer, fleet_editor, fleet_reviewer and operations_reporter. Existing system_admin gains the additive permissions through its existing all-permissions policy. Original emergency/fire read access is composed separately, rather than inferred from incident access. Registry/rate administration remains gated by admin permission.

## Database and locking

Append-only migration `040_run_b_operations_fleet.sql`: nine new tables, fourteen DDL statements including indexes. It follows canonical Run A migration039 (`039_run_a_tenant_identity.sql`) from main8323930e / PR41. Only this Task2 migration was renumbered;001–038 are unchanged.

New tables: operation_incidents, operation_vehicles, operation_allowance_rates, operation_dispatches, operation_dispatch_crew, operation_vehicle_trips, operation_fuel_entries, operation_vehicle_services and operation_import_previews.

Reuse of verified model properties:

- Employee.employee_id -> crew and trip driver FKs; Employee.active is checked on new assignments.
- EmergencyCase.emergency_case_id / FireInvestigationCase.fire_investigation_case_id -> unique incident links. Linked facts remain solely in their original tables.
- Document.document_id -> dispatch/trip/fuel/service FKs; original Document properties were verified in tests (`original_filename`, `mime_type`, `size_bytes`).
- app_users.user_id -> provenance, reviewer, approver, cancelling actor and preview owner; callers never choose these actors in their body.

Database constraints cover kind/status choices, source-link exclusivity and no fact copying, unique source links/vehicle codes/dispatch employees, nonnegative money/mileage/stock, ordered time/date ranges, Human-gated approved states, and matching dispatch/vehicle and repair/fault/vehicle references. Production DDL uses UUID, timestamptz and fixed NUMERIC columns. API timestamps normalize to UTC before persistence, including SQLite regression execution.

Mutations combine parent incident/source-case or vehicle SELECT FOR UPDATE with SQL version-conditional UPDATE. Linked-source locks remain held through candidate review/approval commit; this closes the independent source-domain editor race. Trips/fuel are append-only through the API; service and financial decisions are versioned and approved snapshots cannot be edited. Service approvals lock the vehicle and explicitly resolved fault. Approval errors roll back all updates.

## Exchange details

Files must be UTF-8 CSV or XLSX. Maximum upload 5 MB, workbook expanded content 30 MB and 1000 nonempty data rows. Unknown/duplicate/empty headers and formulas are rejected. XLSX first sheet is the operational table. Cells are interpreted under the declared strict schema, not guessed from legacy labels. CSV templates include all accepted fields. Datetime cells should contain timezone-aware ISO strings. Money/liters accept up to two decimals; mileage accepts one decimal; excessive precision is rejected rather than silently rounded on input. Candidate hourly calculations use the explicitly approved rounding mode.

The persisted preview includes file SHA256, filename, uploader, validated source rows, timestamp, one-hour expiry and applied target IDs. Original uploaded bytes are not archived as a new Document; an existing Document ID can be supplied in supported rows. Preview confirmation uses server-stored rows, not caller-resubmitted row contents. CSV/XLSX exports are operational tabular extracts, not invented formal printed layouts or original-template reproductions.

## Validation evidence

TDD: first focused run showed eight expected missing-route / missing shared-shell failures. Additional tests were observed red for preview+confirm binding, source-case locking, typed cancellation retention, explicit rounding input, explicit fault resolution and mixed-offset timestamps before those changes were implemented. No real data, original operational files or external dependency installation was used.

| Command / check | Result |
| --- | --- |
| `cd backend && python -m pytest tests/test_run_b_operations.py -q` | **21 passed**, 19 warnings. Synthetic end-to-end source-preserving CRUD, RBAC, shared relationships, stale versions, Human gates, audits, import/export, privacy, stock/mileage/deadlines, fault resolution, SQL constraints, source locking and real JS form behavior. |
| `PYTHONPATH=backend python -m pytest backend/tests -q` from repository root | **232 passed**, 158 warnings, 79.60 seconds. Full project suite, including existing emergency/fire/drawing/legal/common tests. |
| Migration parser smoke using app.migrations.split_sql | **39 migration files passed**; provisional039 contains **14 statements**. |
| Existing shell inline scripts and every frontend/*.js with node --check | **Passed**, including operations.js. |
| `python -m compileall -q backend/app` | **Passed**. |
| `git diff --check` | **Passed** after staging exact task paths. |

The full suite was initially invoked from backend and failed collection of `test_phase6_annotation_qa.py` because that existing test imports `backend.app` and needs repository-root context. It was rerun with the CI-equivalent repository-root command above and passed. The warnings are the existing Starlette/httpx deprecation and existing fire_cause_candidates/fire_investigation_cases cyclic-table drop warnings in SQLite fixtures; there are no failing tests hidden in the passing result.

The frontend regression evaluates the actual field renderer/value parser and Human review form handler in Node with synthetic DOM/API surfaces. It proves zero preservation, escaping and the resulting POST/version/reason behavior. It is not a real-browser acceptance result.

## Remaining items / external acceptance

No known Task 2 implementation item is left as scaffolding or an internal Missing/Partial after this delivery. Actual root independent review may identify further fixes.

Unverified acceptance work remains explicit:

- Apply040 to the approved PostgreSQL environment and exercise true concurrent transactions. Local tests verify emitted source row locks and SQLite conflicts; the optional CI PostgreSQL regression asserts actual source locks and stale approval rejection. No locally available PostgreSQL server was exercised.
- Run the merged/deployed `/ui/` flow in a real PC browser. The supplied workspace has no usable browser CLI/Chromium runtime; syntax and executable synthetic UI checks passed, and no browser pass is claimed.
- Human organization acceptance of supplied allowance basis/rounding/rates, operational terminology and actual inspection/service dates; no rate or legal deadline has been inferred.
- Root's refreshed-main conflict/migration-number check, independent review, CI, PR and merge.

Run A integration boundary: this domain consumes the currently verified shared Employee/org/auth/RBAC/audit/Document IDs and server session. Canonical tenant execution from Run A main8323930e is preserved and consumed; common temporal personnel history is not recreated in this task, nor is any existing control weakened. The domain has no user-selectable database/tenant path. It does not invent legal output layouts; unavailable originals and formal-template acceptance remain with their existing renderer/owning tasks.

## Exact task file list

- backend/app/operations_models.py
- backend/app/operations_schemas.py
- backend/app/operations_service.py
- backend/app/routers/operations.py
- backend/app/main.py (router registration)
- backend/app/rbac_seed.py (additive permissions/roles)
- backend/app/module_seed.py (operations/fleet registrations)
- backend/app/routers/search.py (permission-filtered operations/fleet search)
- backend/tests/test_run_b_operations.py
- db/migrations/040_run_b_operations_fleet.sql (original provisional039 allocation superseded after PR41)
- frontend/operations.js
- frontend/index.html (header/session/search navigation registration)
- docs/completion/task-2-report.md

Root-owned future task briefs and EXISTING_INTERFACE_AUDIT.md were left unmodified and unstaged. No git remote/GitHub mutation was attempted.

## Independent review fix round 1

Base product commit: `1c12195440746e54599f7ac679cb5c9cb9ae823d`. This round addresses both confirmed P2 review findings and the fuel accounting metric clarification; no DB/schema/migration or source-domain semantic change is involved.

- Mutation results now dispatch through the same permission-aware Dispatch and fleet-history projections used by reads. Calculation, review, approval and cancellation responses strip Document IDs, including nested calculation/review snapshot links, when document.read is absent. Trip/fuel/service create results also use the shared history projection. The original DB links and evidence remain intact; permissions are not weakened and mutation authorization is unchanged.
- Tabular output uses the ordered union of all permission-filtered row keys instead of the first row's keys. A local incident followed by emergency/fire linked incidents retains later source projection columns in both CSV and XLSX. Revoking original case permission still removes source facts/IDs and preserves the source_restricted indication. No raw rows are used to synthesize export columns.
- Fleet monthly/yearly statistics and fleet-summary exports replace ambiguous fuel_cost with fuel_purchase_expense (receipt + external refuel amounts) and fuel_issue_valuation (issue amounts, informational). Positive issue values remain valid recorded facts and are never counted a second time as purchase expense. Existing rows and stock behavior are unchanged. The PC form and summary labels distinguish expense from issue valuation.

TDD evidence: all ten new cases first failed for the precise review findings while the original 21 focused cases passed. They cover four dispatch mutation transitions, three service transitions after Document read permission revocation, mixed-case CSV/XLSX exports with source permission revocation, and monthly/yearly/export purchase totals versus issue valuation. The response tests also assert that stored Document provenance and calculation evidence are preserved.

Runtime recovery initially returned a missing-pytest error from managed primary Python. An existing `/tmp/fire-ai-venv` contained the declared dependencies and was used for all round1 Python checks; no dependency installation, escalation or new dependency was performed by this task owner.

Round1 exact modified paths: backend/app/routers/operations.py, backend/app/operations_service.py, backend/tests/test_run_b_operations.py, frontend/operations.js and this report. Root-owned handoff/state/status docs and future briefs remain unstaged.

Round1 validation results:

| Command / check | Result |
| --- | --- |
| `cd backend && /tmp/fire-ai-venv/bin/python -m pytest tests/test_run_b_operations.py -q` | **31 passed**, 29 known warnings, 20.59 seconds. |
| `PYTHONPATH=backend /tmp/fire-ai-venv/bin/python -m pytest backend/tests -q` from repository root | **242 passed**, 168 known warnings, 89.86 seconds. Full suite run once after all three fixes were complete. |
| Migration parser smoke | **39 files passed**, unchanged provisional039 has **14 statements**. |
| Inline shared-shell and every frontend/*.js with node --check | **Passed**. |
| `/tmp/fire-ai-venv/bin/python -m compileall -q backend/app` | **Passed**. |
| `git diff --cached --check` | **Passed** for exact staged Task2 round1 paths. |

Both P2 findings and the accounting clarification are implemented and regression-tested locally. Root independent re-review/publication remains pending. Original external acceptance limitations remain unchanged: actual approved PostgreSQL concurrency/migration execution and real PC-browser acceptance are not claimed by these tests.


## Latest-main adaptation round 2 — Run A PR41

Canonical main: `8323930e659e6818a1cf85ccebc02dc34abc4e5f` (PR41). The parent supplied the exact refreshed15-file snapshot in `.superpowers/sdd/2026-10-06-run-b-completion/run-a-main-update.json`; these files were adopted verbatim except main.py's additive operations import/router and the Run B state section appended after the latest Run A PROJECT_STATE section. No tenant/auth/storage guard was redesigned or relaxed. Canonical CI PostgreSQL service, tenant migration039, tenant tests, initializer and operational documents are retained. Run B's provisional039 was renamed040; historical001–038 are unchanged. Earlier039/39-file parser evidence above records the allocation at the time of those runs, not the current migration order.

The new synthetic integration suite uses two separately initialized databases with the same source/Incident/Vehicle/Employee/Document IDs and username but distinct server-bound tenant UUIDs, hosts, storage roots and passwords. The real canonical middleware protects each application. It checks cookie/password rejection across databases; distinct linked source/Document/Employee facts; source search/export isolation; fuel/history/vehicle mutation isolation; strict body and import rejection of tenant/database/user selectors; unknown Host rejection; mismatched BoundSession and storage-marker rejection. The canonical selector contract is preserved: X-Tenant-ID and query selectors are ignored and cannot change the server's fixed database; body/import selectors are422. The startup test invokes the actual lifespan and confirms its binding check and registered operational HTTP route.

An additional test consumes the inherited FIRE_AI_TEST_POSTGRES_URL only when available. It creates a unique synthetic schema through schema_translate_map, exercises the production review service, retains its linked Case row lock while a second transaction attempts a source edit with a bounded250ms lock timeout, then commits review, changes the source and proves Human approval returns409 without official promotion or approval audit. Cleanup drops only that generated synthetic schema and leaves Run A's initialized public-schema tenant intact. Local absence of PostgreSQL skips this check; adding it does not establish a PostgreSQL pass. Root must verify the refreshed-base CI result.

Round2 TDD evidence: before adopting main, all five non-PostgreSQL integration cases failed on the missing canonical startup guard, tenant settings or migration allocation. The first post-adaptation run exposed two test-harness issues (new FastAPI included-router wrappers and the still-present old migration filename); the route check now uses actual HTTP and only old039B was removed. The corrected focused run passed52 tests and skipped2 unavailable local PostgreSQL checks. The optional PG check could not be observed red/green locally and is explicitly an unexecuted CI regression here. No financial policy or dependency was added.

Round2 validation results (after latest-main adoption and test fixes):

| Command / check | Result |
| --- | --- |
| `PYTHONPATH=backend /tmp/fire-ai-venv/bin/python -m pytest backend/tests/test_run_b_operations_tenant_integration.py backend/tests/test_run_b_operations.py backend/tests/test_tenant_boundary.py -q` | **52 passed, 2 skipped**, 30 known warnings, 22.87 seconds. Skips are the canonical PostgreSQL physical migration test and the added actual source-lock test; no FIRE_AI_TEST_POSTGRES_URL is available locally. |
| `PYTHONPATH=backend /tmp/fire-ai-venv/bin/python -m pytest backend/tests -q` | **263 passed, 2 skipped**, 168 known warnings, 97.96 seconds. Full suite includes the latest Run A tests. Warnings are existing Starlette/httpx, cyclic SQLite table-drop and Pillow deprecations. |
| Exact snapshot fidelity | **Passed**:13 files exact, main.py only additive operations registration, PROJECT_STATE retains exact canonical prefix with Run B appended afterward. |
| Migration parser and immutability smoke | **40 files passed**;040 has14 statements,039 is canonical tenant identity, old039B absent,001–038 byte-identical to local committed history. |
| Inline shell and all frontend JavaScript syntax; compileall backend/app, tenant initializer and added integration test | **Passed**. |
| Whitespace / staged path check | **Passed** for the exact adaptation paths; root-owned task-3/task-4 brief edits are excluded. |

Round2 paths: the15 exact canonical snapshot paths; old039B removal/new040B allocation; backend/tests/test_run_b_operations_tenant_integration.py; this report; INTEGRATION_HANDOFF.md; docs/completion/RUN_B_STATUS.md; docs/superpowers/plans/2026-10-06-run-b-completion.md. This adoption changes no operational service/model/schema/UI behavior. Full refreshed-base CI, independent review, merge, real browser and actual approved PostgreSQL/LAN acceptance remain parent-owned or external gates; earlier stale-base PR42 CI is not used as evidence for this adaptation.


## Latest-main adaptation — Run A PR43

Current canonical main: `0335b59edb268b49e7e35cafedc1966c0a901d08` (PR43), supplied as the exact14-file snapshot `.superpowers/sdd/2026-10-06-run-b-completion/run-a-main-43-update.json`. All14 source files were adopted verbatim except the existing operations import/router registration in main.py. This is a narrow parallel-integration adaptation, not a review defect fix. Run A's strengthened runtime privilege validation, dedicated department deployment configuration, bound backup/restore preflight and administrative audit/provenance controls remain intact. Operational service, models, schema and UI were not edited. Migration040 remains byte-identical; canonical maximum039 and historical001–039 were not changed.

The existing operational startup regression was updated from validate_binding to Run A's canonical validate_runtime_binding hook; it first failed on the old hook contract, then passed after exact adoption. Other two-DB/source, selector rejection, source-lock and stale-approval integration regressions are reused. Parent reports prior refreshed PR42 CI37468236318 succeeded including PostgreSQL before PR43 landed; that run does not establish acceptance of this new base. Fresh-base CI remains required.

Focused command: `PYTHONPATH=backend /tmp/fire-ai-venv/bin/python -m pytest backend/tests/test_run_b_operations_tenant_integration.py backend/tests/test_tenant_boundary.py backend/tests/test_tenant_deployment.py backend/tests/test_tenant_backup_restore.py -q`: **40 passed,4 skipped**, one known warning,24.06 seconds. The four skips require local PostgreSQL: operational source lock, canonical physical migration, dedicated runtime roles and physical bound backup/restore. No local PostgreSQL or browser result is claimed. Exact snapshot fidelity, parser40, byte immutability of all001–040, compileall and whitespace checks passed.

Only the14 snapshot paths, the existing operational integration test's hook update and this report belong to this commit. No helpers, external writes, new dependencies or new operational decisions were introduced.

Full latest-base command run once after adaptation: `PYTHONPATH=backend /tmp/fire-ai-venv/bin/python -m pytest backend/tests -q`: **282 passed,4 skipped**,168 existing warnings,125.50 seconds. All added Run A tests were included; the same four locally unavailable PostgreSQL checks are skipped. Warnings remain the known Starlette/httpx, cyclic SQLite table-drop and Pillow deprecations. Exact16-path staging and staged whitespace checks passed; root-owned task-3 brief changes are excluded. Ready for refreshed-base review/CI; production/LAN/browser acceptance remains unchanged.
