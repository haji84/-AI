# Personal Work Queue Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Show a useful permission-aware work list after login, with links to existing records and honest personal relationships, without duplicating business state.

**Architecture:** A read-only aggregation endpoint consumes existing assets, fleet, corrective-action and inquiry sources. A home panel in the existing authenticated shell renders its source pointers; the existing shared-session guard and module detail screens remain authoritative. No new database table, migration, worker process or automatic business decision is introduced.

**Tech Stack:** Existing FastAPI, SQLAlchemy, Pydantic, PostgreSQL/SQLite test fixtures, plain JavaScript and Chromium CI.

**Spec:** `docs/SPECIFICATION.md` sections 5, 7–9, 36, 40, 43, 45, 47–48, 53–55. Base: `c1b684c5c38fc52fe908d2116a21a16ef48dcb34`.

## Global Constraints

- 権限のないModuleの件数や内容を表示しない。
- Cardは元Recordへのpointerを持つ。Dashboardが正式データを複製しない。
- AI停止時にもCRUD/受付/検索を継続できる。
- 救急個人情報は専用RBACで保護する。
- Existing originals, audit, Human approval and tenant isolation remain unchanged.
- Workforce/statistics source changes belong to separate recovery work; no adapter is added for them in this slice.
- No legal thresholds, distributed workers, deployments, credentials or production access are created.

## Review Focus

1. A permitted inquiry containing a forbidden underlying source must reveal neither title, source ID nor count; test transitive source authorization before aggregation/pagination.
2. Creator is not assignee: test `created_by_me` separately from the actual `borrowed_by_me` employee relationship; never return an invented assignment.
3. Hidden/closed/disabled source records must not remain as cached tasks; test source status/version updates and module flags on every refresh.
4. One Japan business date must drive all due calculations; test timezone boundary, overdue/today/upcoming and nullable due dates.
5. Account/session/permission change or newer navigation must discard delayed data and clear the home panel; test real SharedSession code and actual browser behavior.

## Shared API contract

`GET /work-queue` requires the existing authenticated current user. Query: `scope=all|related` (default `all`), `as_of` optional date (default existing Asia/Tokyo business date), `days` integer 0–30 (default 30; matches the existing fleet alert horizon), `limit` 1–100 (default 50), `offset` >=0 (default 0).

Response:

```json
{
  "schema_version": "work-queue-v1",
  "as_of": "2026-10-07", "through": "2026-11-06", "business_timezone": "Asia/Tokyo",
  "scope": "all", "limit": 50, "offset": 0, "total": 0,
  "counts": {}, "items": []
}
```

Each item contains `key`, `module`, `kind`, `title`, `source_type`, `source_id`, `source_version`, `status`, nullable `due_on`, `overdue`, `relationships` (subset of `created_by_me`, `borrowed_by_me`, `available_to_my_role`, `shared_deadline`), `required_permissions`, `navigation` and `provenance`.

`navigation` is a closed contract: `{surface:"asset",id:asset_id}`, `{surface:"vehicle",id:vehicle_id}`, `{surface:"violation",id:case_id}`, or `{surface:"inquiry",id:inquiry_id}`. No arbitrary URL or executable code comes from the server. `provenance` includes `source_api`, `as_of` and source/parent record versions when applicable. No original text, patient fields, borrower names or other unnecessary business payloads are copied into cards.

Ordering is deterministic: overdue first, then due date (undated items last), then module/kind/source ID/key. Permission/source/flag/relationship filters happen before counts and pagination. `total` and `counts` describe only that authorized filtered result. `scope=related` includes only creator/borrower relations, not general role work.

Providers:

- `operational_assets`: reuse `assets_service.alerts(db,user,as_of,days)`, require `asset.read`; loan-return items additionally require `asset.borrower.read`. Fetch the corresponding source versions. Loan borrower relation compares `AssetLoan.borrower_employee_id` to authenticated `User.employee_id`; omit inactive parents/closed loans. Navigate to `assetsDetail(asset_id)`.
- `fleet`: reuse `operations_service.alerts(db,as_of)`; require `fleet.read`, preserve its recorded-date/mileage/fault semantics and restrict dated results to the requested horizon. Use Vehicle/VehicleService versions. Navigate to `operationsVehicleDetail(vehicle_id)`.
- `violations`: active-case, non-completed/non-cancelled corrective actions due through the requested horizon; require `violation.read`, reuse canonical visible/redaction behavior, preserve source action/case IDs and versions. Creator is only a creator relation. Navigate to `violationDetail(case_id)`.
- `inquiries`: reuse `inquiries_service.list_rows`/authorization before exposing data. Include own non-approved drafts, draft work actionable with `inquiry.review`, and reviewed work actionable with `inquiry.approve`; require `inquiry.read` and transitive source rights. No invented due date. Navigate to `inquiryDetail(inquiry_id)`.

Honor seeded source `module.*.enabled` flags; absent flags retain current seed-compatible enabled defaults. `module.work_queue.enabled=false` disables this endpoint without changing underlying module services. The slice does not claim global module-disable enforcement or general assignee support.

## Task 1: Source aggregation and authorization

**Files:** create `backend/app/work_queue.py`, `backend/app/work_queue_schemas.py`, `backend/app/routers/work_queue.py`, `backend/tests/test_work_queue.py`, and focused PostgreSQL coverage if needed. Do not edit main.py, module_seed.py, shared schemas, or existing business services without lead coordination.

**Interfaces:** produce the GET contract above and exported `router`. Reuse existing service functions and source models; no business writes. Expected auth/session and audit writes are distinct from task data.

- [x] Add failing API tests for mixed authorized/forbidden providers and transitive inquiry rights; verify expected missing-endpoint failure.
- [x] Implement exact source pointers/versions, relationship filters, flags, dates, stable order and pagination.
- [x] Test overdue/today/future/closed states, own-vs-other borrower/creator, empty/no-permission response, repeated refresh and source mutation, no extra business records.
- [x] Run targeted tests, then the existing suite on the integrated branch. Record RED/GREEN evidence and local limitations.

## Task 2: Shared-shell home panel and browser acceptance

**Files:** create `frontend/work-queue.js`, `backend/tests/test_work_queue_browser_state.py`, `backend/tests/test_work_queue_browser.py`. Lead owns index.html and CI wiring.

**Interfaces:** export `openWorkQueue()`, `hideWorkQueue()`, `clearWorkQueue()` and `initWorkQueue()` for the lead's shell wiring. Use `$`, `esc`, `api` and existing module globals. Lead provides `<section id="workQueuePanel" class="hidden"></section>` within the main pane and `#workQueueBtn` in the header.

- [x] Add failing UI state tests for loading/empty/error, relation labels, escaped text, pagination, deterministic navigation and delayed response cancellation.
- [x] Implement the inline home panel (not a modal that blocks existing navigation), labels for creator/borrower/role/shared deadlines, dates, refresh, scope and source links. Do not label created records as assigned work.
- [x] Clear state/DOM on shared-session invalidation; prevent an older request from reappearing after hide/newer refresh. Preserve errors rather than claiming zero work when the request failed.
- [x] Add real Chromium journey: limited user login → permitted cards only → specific source detail → close/back → source update reflected → session/permission change clears queue. Synthetic data only.
- [x] Verify JavaScript syntax and UI state tests; actual Chromium runs in authorized GitHub CI, not a denied local browser route.

## Task 3: Lead integration, evidence and delivery

**Files:** lead only modifies `backend/app/main.py`, `backend/app/module_seed.py`, `frontend/index.html`, `.github/workflows/project-checks.yml`, and narrow completion evidence/docs.

- [x] Integrate reviewed backend/frontend commits into the isolated integration worktree; register router/module flag.
- [x] Add header/home panel/script/reset wiring. Login shows the queue after existing initialization; facility detail hides the panel. Source links reuse existing detail screens and permission revalidation.
- [x] Run full backend, migration parser and all JS syntax checks, plus independent branch review.
- [ ] Create draft PR and monitor its exact head through PostgreSQL and actual Chromium CI; fix only evidenced failures.
- [ ] Report tested source, artifact/readiness and remaining provider/assignment gaps. Obtain specific merge approval at the integration milestone; no deployment is implied.

## Scope accounting

This completes a usable first §36 work-list flow. General assignment, workforce/statistics, other providers and whole §54/§53 acceptance remain separately tracked internal work, not External Gates. Existing release RC and stranded work are preserved.
