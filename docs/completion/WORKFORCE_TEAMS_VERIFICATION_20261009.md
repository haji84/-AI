# Canonical workforce teams and explicit dated membership

## Canonical dependency and internal status

Canonical accepted maincc9e676d14fe0439abc69b8ab2be9034e450ffbb/tree155ed4e71d40311256b049e77b7adf6042a44803 contains accepted PR86 source, PR87 protected search and PR88 checkout. PR88 exactCI37888019576 SUCCESS backend1424/99 skipped/794.23s, browser75/780.79s; independentmainCI37889200619 SUCCESS backend1424/99 skipped/806.95s, browser75/761.35s, parser/JS. Main artifact11597408712 SHA256b4d962d85ca02244e2a563dcc620a4efa8ebe5cd74f835b4f12da75cbd114769, D20. This teams delta is not yet accepted main. Chapters25/45/48/54 remain Partial; no canonical ten-flow E2E or release credit. Later pending statements are historical checkpoints, superseded by this accepted prefix.

Specification25 and actual models/services/routers/frontend plus Run B status confirm team support was absent. SQL058 adds only canonical organization teams and dated EmployeeAssignment memberships; inventory currently ends at057 on main. Fresh remote migration/PR/permission/shared-file comparison is required before publishing.

## Implemented boundary

Existing workforce.read+personnel.read protect individual team reads; workforce.admin+personnel.read protect reasoned Human mutations. No grant or role policy changes. Current module/originating session/password/permissions are checked before records and again before private response/commit. Success, HTTP errors and validation errors use no-store.

Membership requires selected assignment_id and expected_assignment_version, parent expected_team_version and explicit dates fitting that canonical primary assignment in the team's organization. Team and source locks prevent duplicate active overlap; every member change advances parent version. Captured source stays immutable. Assignment revision/inactivation marks historical membership unavailable. Human can explicitly inactivate an old membership and create a new captured assignment revision for the same period, retaining both histories. No delete, automatic roster, dispatch crew or salary decision.

Same-shell team/create/change/member/history controls retain view ownership and one pending Human mutation; reasons and explicit versions are sent once. Canonical assignment options are read through the existing authorized personnel API; role IDs are not displayed or used as grants. Current roots remain separate by department DB/runtime/original/backup.

## Verification

- Actual HTTP RED: missing team route404, then first two tests PASS.
- Validation no-store RED4, then dedicated validation handler preserves normal422 and no-store.
- Assignment changed after Human selection: actual incorrect201 with new title/version reproduced; explicit expected assignment version now gives409 with no membership.
- Same-period source revision and duplicate team-code constraints produced IntegrityErrors; revision uniqueness preserves archived source and flush conflicts now rollback to private-free409.
- Team and Node focused final: **18 passed / 2 native PostgreSQL skipped,21.80s**. Includes Human CAS, interval/overlap/strict fields, current permission/session/module release checks and actual UI duplicate/obsolete-auth writes. Skips receive no native acceptance credit.
- Earlier combined team plus existing checkout/Human/statistics/source/search state: **95 passed / 2 native skipped,27.92s**; this preceded the latest assignment-version/history fixes. Diff/JS/Python syntax PASS.
- Isolated actual full application bootstrap: team→member→canonical personnel versioned change→historical membership unavailable **PASS** before adding expected_assignment_version; must rerun the updated payload before acceptance. This HTTP exercise is not Chromium.
- Updated isolated actual full bootstrap with required expected_assignment_version: team→member→personnel CAS change→unavailable historical member→Human inactivation→same-period fresh assignment revision→both immutable histories **PASS**. This supersedes the earlier bootstrap payload; it is still HTTP, not Chromium.
- SQL parser: **56 migration files PASS**, SQL058 has5 statements. No PostgreSQL execution locally.
- Three native PostgreSQL cases use a freshly fully migrated database and require [201,409] for concurrent same-parent-version memberships, plus immutable history and unchanged UserRole/roster counts. Actual Chromium journey uses real team/member/admin APIs, expected versions, stale409 and changed-source UI, without fabricated responses. Its new file is explicitly added to the browser CI command. Both native executions remain pending.

Independent review, exact remote tree parity, full exact-head CI, merge and independent main CI are required. Remaining teams-to-roster/dispatch/work-results, balance/crew UX, overtime/allowance and institution policy reconciliation remain internal; real institution decisions/production acceptance remain Human External only.

## Independent review repair — protected change history

Shared error recovery delta dac2039 defines the existing workforce error formatting as a reusable cancelled-aware helper; actual assignment-fetch failure now displays the personnel-service message instead of a ReferenceError. Root related Node29PASS/6.16s; independent team Node5PASS/1.20s; no Critical/Important in the bounded delta. Migration058 parser9 statements PASS after protected history repair. Fresh team/checkout/Human related suite46PASS/3 native PG skipped/26.03s; native skips remain unexecuted.

Independent focused review at2dbdc32 found one Important: generic audit.read alone could read new team reasons and assignment snapshot prose after individual permissions were removed. Root reproduced that exact audit-only response with the previous full common-audit projection (**RED1,8.10s**). Teams now persist complete before/after/name/reason/source evidence in a dedicated protected WorkforceTeamChange record/API/UI, and publish only opaque IDs, versions, active state and hashes to shared audit. Existing personnel/workforce audit policy is untouched. SQL058 includes an append-only PostgreSQL trigger rejecting UPDATE and DELETE of these history records; its native test remains unexecuted locally.

Private history requires current workforce.read+personnel.read and module/session rechecks after payload. Current module503 clears the private workforce surface; obsolete errors preserve newer view ownership. Independent original review was42 passed/2 PG skips38.13s. Current related team API/Node/checkout/Human suite: **46 passed/3 native PG skips35.75s**; syntax/diff PASS. This includes private-free audit-only, retained original names/reasons and after-payload permission revocation. Fresh focused protected-history/audit rerun is pending; final repair review and actual PG/Chromium exact/main acceptance remain required.

Fresh protected-history/audit rerun: **3 passed,7.75s**. Independent repair review atca29a566/tree994c71bd: **46 passed/3 native PG skips27.17s**, diff/JS syntax PASS, Important closed and no new Critical/Important. Native PostgreSQL/Chromium remains unexecuted for this slice. PR87 protected search exactCI37885361278 succeeded backend1417/99 skips815.86s and Chrome75/801.10s; it merged asmain70953bab88116318cf9f69342be39361c75da4d8/tree3a81c1b7b7aac271019f83cdc79b2b72e4dfd228. Independent mainCI37886725333 is pending; search/checkout/teams acceptance must remain ordered.
