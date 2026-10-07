# Observed Statistics Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development. Steps use checkbox syntax for tracking.

**Goal:** Query distinct existing emergency, incident/dispatch and vehicle-operation measures for selected dates, preserve immutable observed snapshots, record Human confirmation and export generic CSV/XLSX.

**Architecture:** Code-owned metric adapters select canonical records once for values and private source evidence. A fresh department-bound read-only snapshot transaction captures observations; a fresh ordinary transaction rechecks the originating session and source permissions before returning or persisting them. No operational records or second business ledger are introduced.

**Tech Stack:** Existing FastAPI, SQLAlchemy BoundSession, PostgreSQL16, SQLite development fixtures, Decimal, ZoneInfo, shared JavaScript shell and openpyxl.

**Spec:** `docs/SPECIFICATION.md` §§5,7,8,34,47,54 and `docs/completion/task-7-brief.md`. Implementation base: `71754c593066cd2720178372fcf0c8c4620aab50`.

## Global Constraints

- One server-selected headquarters DB/runtime/storage; no client tenant selector or global-engine fallback.
- Source records and Human decisions remain authoritative. Preserve stranded source/checkpoints; this is new main-based implementation, not recovered code.
- Dates are explicit inclusive start/end dates. Server-owned `FIRE_AI_STATISTICS_BUSINESS_TIMEZONE` defaults visibly to `Asia/Tokyo`; clients cannot override it. Pin the zone and resolved UTC interval in every snapshot. DATE fields remain dates.
- Timestamp queries use `[local start midnight converted to UTC, next local midnight after end converted to UTC)`. Confirmation reuses pinned bounds after configuration changes.
- Operations' current API/import normalizes aware timestamps before SQLite storage; unsupported direct/legacy admission lineage remains an explicit limitation. SQLite fire timestamps lose offset information and must be excluded as ambiguous, never reinterpreted. PostgreSQL timestamps are recorded instants, not proof of the original operator's timezone intent.
- `coverage_status=unknown` remains unknown after confirmation. An observed zero is not evidence of historical completeness. Money, fiscal totals, staff/fleet census, comparisons, coverage declarations and official templates remain unavailable/out of this slice.
- Add statistics.read/record/export only to the existing HQ-local system_admin convention. Other role memberships and source permissions remain unchanged. No service-owner or Recovery Vault access is introduced.
- No production deployment, actual data transmission, local Chromium execution or changes to existing statistics endpoint semantics.
- Migration051 remains reserved;053 belongs to vehicle assignments. Reserve054 only after the fresh remote check; never amend historical SQL.

## Review Focus

- Several patients, crew or trips must not multiply their parent incident count; metric membership, dependencies and exclusions must match each definition.
- Aggregate-only users must not receive source/patient/employee IDs or private evidence hashes through any response, failure, audit or export.
- Midnight, timezone-representation and inclusive-end boundaries must not silently shift records; ambiguous source timestamps stay visible as uncertainty.
- Concurrent source changes must not produce a mixed capture; later inserted/moved/undated records must invalidate confirmation when applicable.
- Session/rights loss after capture or byte preparation must block release, and old async UI results must not reappear after navigation/logout.

## Task 1: Source selection and guarded query

**Files:** new statistics_schemas.py, statistics_sources.py, statistics_service.py, routers/statistics.py; focused source/API tests; settings.py only for the named timezone.

**Interfaces:**
- GET `/statistics/metrics`: versioned definitions and current availability.
- POST `/statistics/query`: strict `{start_date,end_date,metric_keys}`; no values, evidence, timezone, SQL, permissions or tenant accepted.
- Keys: `emergency.cases`, `emergency.patient_records`, `operations.incidents`, `operations.dispatches`, `operations.approved_dispatches`, `fleet.trips`, `fleet.distance_km`.
- Public result: pinned period, metric definitions/units/date bases, exact observed values, unknown coverage, exclusion summaries and limitations. Private capture separately retains canonical row/dependency sets and fingerprints. Any public checksum covers only the safe public projection.
- Emergency source gate: emergency.report.read; operations: incident.aggregate; fleet: fleet.aggregate. statistics.read is additional. Drilldown separately requires the original target's detail/sensitive rights.

- [ ] Fail tests for case/patient separation, active incident population versus dispatches under all date-matched parents, trip IDs and exact Decimal distance, exclusions and consistent fingerprints.
- [ ] Fail tests for Japanese local boundaries, equivalent JST/UTC instants, DATE preservation, end overflow, configuration changes, rejected overrides and SQLite fire ambiguity.
- [ ] Implement the same selected sets for values/provenance/drilldown. Retain undated/ambiguous exclusion sets and link/date dependencies privately; do not copy legacy broad source-ID lists.
- [ ] Capture through a fresh same-engine BoundSession configured before its first SQL. Do not call committing routers, authentication helpers, account locks or writes inside capture. Close it before final authorization.
- [ ] Revalidate the server-derived session digest, account/employee/password, command gate and complete source capability union in a fresh READ COMMITTED/read-write session before protected release.
- [ ] Run source, authorization and existing-domain regressions; commit the independently testable query foundation.

## Task 2: Immutable snapshots and Human confirmation

**Files:** statistics_models.py, statistics_reports.py, additive migration054, router additions; PostgreSQL concurrency/tenant tests.

**Interfaces:** POST `/statistics/reports` recaptures a strict query; GET list/detail/history uses complete current report authorization; POST `/{id}/confirm` takes expected_version, Human acknowledgement and review note; POST `/{id}/replacements` takes expected_version and reason and recaptures the same pinned query.

- [ ] Fail tests for immutable payload/evidence, current rights after capture, complete-report list filtering before totals/pagination, and no aggregate identity/hash disclosure.
- [ ] Store immutable public snapshot and private evidence separately. Track saved/confirmed lifecycle/version and append-only history. Confirmation changes neither values nor coverage and is not managerial or official approval.
- [ ] Use one database-enforced successor per predecessor, a new replacement identity and atomic predecessor version/history update. Preserve old snapshots and prior confirmation facts.
- [ ] Recompute full selected/excluded/dependency sets before confirmation; compare evidence excluding capture time. Inserted matches, moved dates and new patients must be detected. Clearly state capture-time freshness, not a freeze of domain writers through commit.
- [ ] Prove repeatable-read before BoundSession's maintenance SQL, maintenance rejection, pooled option cleanup, final read-write isolation and two-HQ factory isolation on PostgreSQL.
- [ ] Prove single-winner confirmation/replacement and rejection of SQL payload/history mutation. Run full backend tests; commit reviewed persistence.

## Task 3: Shared UI, source navigation and generic exports

**Files:** new frontend/statistics.js and Node/Chromium tests; lead-owned index/main/bootstrap/module/RBAC/CI wiring; focused export tests and Japanese usage/evidence docs.

- [ ] Fail tests for exact frozen CSV/XLSX values after source changes, safe text in all cells/metadata, current lifecycle version, source export permissions and post-preparation revocation.
- [ ] GET saved report export requires statistics.export plus statistics.read and each selected source's aggregate/export rights. Label every output `汎用統計出力（正式様式ではありません）`; exclude private provenance and unnecessary confirmation prose. Do not promise byte-identical XLSX regeneration.
- [ ] Add explicit date selectors, visible business timezone, metric definitions/availability/unknown coverage, frozen save/confirm/history/replacement and download in the same shell. No fiscal/currency/headcount inference or official-template claim.
- [ ] Add separately authorized paginated drilldown pointers; never return internal dependency IDs as aggregate data. Preserve existing source navigation ownership.
- [ ] Test repeated/interrupted/late/session-changed UI actions with actual source helpers. Write real-API Chromium scenarios; execute them only in authorized exact-head CI.
- [ ] Run independent whole-slice review, full backend/PostgreSQL/browser gates, migration parser and JavaScript checks. Publish draft PR; report its concrete new merge scope before integration. Keep §34 Partial until remaining adapters and acceptance exist.

## Verification References

Use the installed SQLAlchemy version's Engine execution-options contract and PostgreSQL16 snapshot guarantees; prove behavior with repository-specific tests rather than assuming option cleanup.

- [SQLAlchemy PostgreSQL transaction options](https://docs.sqlalchemy.org/en/20/dialects/postgresql.html#transaction-isolation-level)
- [PostgreSQL16 transaction isolation](https://www.postgresql.org/docs/16/transaction-iso.html)

## Plan self-review, 2026-10-07

The approved bounded scope and transaction contract were checked against the canonical specification and source admission paths. Migration 054 is reserved by the lead after a fresh remote-main check; 051 and vehicle-owned 053 stay untouched. Statistics source code, persistence and tests belong to the backend worker; shared wiring, UI and publication belong to the lead. PostgreSQL acceptance is authored for CI because this workspace has no PostgreSQL service. No general source permissions or legacy endpoint semantics are changed.

## Backend implementation progress

The backend query, selectors, immutable reports/history, separate authorized source navigation and generic exports are implemented with recorded failing tests. Migration 054 is additive and independent. Focused source/API/parser verification passes; real PostgreSQL transaction, maintenance, queued authority, immutable SQL and concurrency tests are authored and await CI. See `docs/completion/observed-statistics-backend-evidence.md` for actual local results and limitations. Shared-shell/RBAC/bootstrap wiring and publication remain lead-owned.
