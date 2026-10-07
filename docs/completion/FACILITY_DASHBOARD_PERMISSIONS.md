# Facility dashboard source permissions

Bounded repair against `c1b684c5`, implementing specification sections 7 and 36.

`GET /facilities/{building_id}/dashboard` still requires `facility.read`. It now independently checks current `inspection.read` and `submission.read` before querying those sources. Restricted inspection counts, latest inspection date, and submission statuses are `null`; restricted submission IDs, statuses, dates, legacy filing values and record existence are not disclosed. A facility-only dashboard has identical source fields whether protected records exist or not. Authorized zero counts and empty submission states retain their existing meaning.

The facility detail loader reads current permissions and skips inspection, submission, installed-equipment and drawing-analysis endpoints without their respective read permissions. Restricted sections display an explicit unavailable message rather than a zero count or no-record claim. The existing shared-session guard clears source state and rejects delayed responses when permissions or the session change. No role grants, business mutations, migrations or source records are changed.

## Verification evidence

- API red/green: four failures on the original code reproduced leaked counts, dates, submission states and failure to recheck changed permissions. The five final API cases pass, including independently authorized sources, real zero, direct endpoint denial, same-session rights loss and inspection of SQL to ensure no protected source queries occur.
- Node red/green: the original shell fetched forbidden source endpoints and failed to open a facility. Three actual-shell/session-guard tests pass after repair, including partial rights and a delayed inspection response followed by rights loss and a restricted session.
- Focused run: 11 passed, 1 skipped. The skip is the new CI-only Chromium journey. JavaScript syntax and `git diff --check` pass.
- Independent review found no bugs or regressions in this bounded repair. Its separate focused API/Node run passed all eight tests and `git diff --check` passed. The reviewer verified that existing shared-session checks clear cached state and reject delayed responses after source rights change.
- Full backend suite: 687 passed, 91 skipped, 287 warnings in 179.38 seconds. Warnings concern existing Starlette/httpx usage, SQLite foreign-key-cycle teardown, and Pillow deprecations. Changed Python files compile; all 49 unchanged migration files parse; frontend JavaScript syntax and diff whitespace checks pass.
- Real Chromium is intentionally unrun locally. `test_facility_dashboard_browser.py` exercises a facility-only login, authorized source display, rights loss, clearing of cached records, and a restricted fresh login. It must run in the administration-browser CI job. Local Node/SQLite evidence does not replace Chromium or PostgreSQL CI.

Final integration is based on PR68 and retains `hideWorkQueue` and `mainNavigationGeneration` checks before/after permission and source reads and in stale-error handling. The dedicated Chromium test is included in the workflow. Independent integration review found no regression; 44 targeted checks passed and the full integrated suite passed **751 tests with 93 skips** in 200.04 seconds. The authority guard still rejects revoked access; the shell quietly drops its superseded navigation while keeping private state cleared. Actual Chromium/PostgreSQL acceptance still requires the exact-head CI result.
