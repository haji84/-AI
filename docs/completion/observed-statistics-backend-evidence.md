# Observed statistics backend slice

This is a new implementation from main `71754c593066cd2720178372fcf0c8c4620aab50`. It does not recover or replace Run A work. This candidate supports at most Partial for canonical §34: it delivers only the approved observed-data slice.

## Delivered contract

The seven code-owned measures keep case, patient-record, incident, dispatch and trip grains separate. There is no combined grand total, historical completeness claim, fiscal or money inference, current workforce/vehicle census, prior-period comparison, coverage declaration or official-template output.

`/statistics/metrics` lists definitions and current source-permission availability. Strict query/save requests accept only inclusive `start_date`, `end_date` and distinct registered `metric_keys`. Values are exact decimal/count strings. Every observation preserves unknown coverage, including observed zero and Human-confirmed reports.

`FIRE_AI_STATISTICS_BUSINESS_TIMEZONE` is a validated IANA zone and visibly defaults to `Asia/Tokyo`. Snapshots pin selected dates, the business zone, resolved UTC start/exclusive end and date-basis version. Confirmation and replacement reuse those pinned bounds. Emergency DATE fields stay date comparisons.

SQLite operations timestamps are included only under the conservative current supported-path assumption, with exact successful `incident.create` / `operation_incidents` or `fleet.trip.create` / `operation_vehicle_trips` audit matches, a recorded actor and trip creator agreement. A historical actor need not remain active. Confirmed imports use the same admitted creation paths; import preview audit rows roll back. A creation audit contains no normalized timestamp or admission-schema version, and cannot certify later direct SQL edits. Rows lacking evidence remain excluded, even after an ordinary update. This can undercount legitimate restored/legacy records and is stated in the output. SQLite linked-fire timestamps lose original offset meaning and are excluded. PostgreSQL stored instants remain usable, with an explicit original-intent limitation. Unknown-date and ambiguous exclusions have the metric's grain and department-wide scope; their private evidence participates in freshness.

Saved reports keep immutable public snapshot, private evidence and append-only Human history. Confirmation means Human-confirmed, without changing values or coverage. Full source selection, dependency and exclusion sets are recaptured to detect inserted, moved, deleted or changed records. A replacement has a new identity and a database-unique predecessor; the predecessor lifecycle version/history is advanced atomically and earlier confirmation facts remain intact. Freshness is as of the coherent capture, not a promise that ordinary domain writers remain frozen until commit.

Generic CSV/XLSX exports use frozen values and one current lifecycle version, say `汎用統計出力（正式様式ではありません）`, and exclude private lineage and review prose. Every cell uses formula-safe text. Regenerated XLSX bytes are not promised to be identical.

## Boundaries

Only the selected request's verified database engine is reused. No request accepts a tenant selector. Preflight authentication transactions are closed before capture. A same-engine SQLAlchemy OptionEngine configures read-only REPEATABLE READ before BoundSession's first maintenance SELECT; using an Engine preserves existing runtime tenant validation. Capture closes before a fresh explicit READ COMMITTED/read-write final session. The originating session, active account/employee, password and complete command/source capability union are revalidated. Mutations use the existing canonical account-change guard only after capture. Exports revalidate after byte preparation and reject a concurrent lifecycle change.

Required new commands are `statistics.read`, `statistics.record`, `statistics.export`. Source aggregates remain `emergency.report.read`, `incident.aggregate`, `fleet.aggregate`; exports additionally require the respective existing source export right. Complete report authorization is applied before list totals/pagination. Aggregate projections and audits never contain source/person IDs or private hashes. The separate paginated drilldown emits only original-detail-authorized navigation pointers; it does not expose raw evidence.

The lead owns application/model/bootstrap/module/RBAC registration and the HQ-local system_admin-only seed. No source semantics, general-role grants, workforce code, historical SQL or vehicle assignment code is changed here. Additive migration `054_observed_statistics.sql` is independent of reserved 051 and vehicle-owned 053.

## Verification

Recorded RED precedes implementation: eight source tests failed for missing query/selectors, lifecycle/API tests failed on missing routes, migration existence failed before DDL, and additional regression tests failed for exact audit matching, explicit acknowledgement, a Connection-vs-Engine tenant-validation issue and command-gate existence lookup before their fixes.

Local focused/backend-parser result: **49 passed, 11 skipped**. Ten observed-statistics PostgreSQL cases and one parser PostgreSQL case are authored for exact-head CI and skipped locally because no PostgreSQL service/URL is available. Cases cover actual transaction state before/at the maintenance guard, pool reset, coherent source reads across an intervening writer, maintenance denial, concurrent confirmation/replacement, SQL immutability, post-capture revocation, an actual queued advisory-lock authority change, initialized two-HQ bindings and PostgreSQL instant boundaries. They are authored acceptance, not claimed local PostgreSQL execution.

The final default `PYTHONPATH=backend python -m pytest backend/tests -q` for implementation commit `ed2699ac64833919742c9b804f5ab256ff7d497a` completed **897 passed, 203 skipped, 287 warnings** in 319.74 seconds, exit 0. Warnings concern dependency deprecations and existing foreign-key drop ordering. No local Chromium ran. An independent reviewer found no substantive backend defects and independently verified **32 passed / 10 PostgreSQL skipped**, plus clean diff checks.

A final test-only review strengthened the PostgreSQL interleaving: the writer adds a patient under an already-read parent as well as a new parent/child, so a READ COMMITTED capture cannot hide its inconsistent rowset merely as an unknown-parent exclusion. This narrower follow-up changes no product code; the reviewer accepted it and its local PostgreSQL cases remain skipped. The lead owns registered-app/browser integration, final combined-suite verification and actual exact-head PostgreSQL/Chromium CI.
