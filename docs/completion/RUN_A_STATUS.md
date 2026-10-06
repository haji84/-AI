# Completion Run A live ledger

Status: IN PROGRESS. Canonical audited base: main 240703a9f0fa752da7b282a25f60c234f309703d; CI 37448233992 SUCCESS.
User approved common code + per-department DB/application/originals/backups on 2026-10-06.
Multiple branches within one department share that department's DB. No cross-department record sharing.

Owned here: tenant identity/runtime/deployment/recovery, common employees/organizations/assignment history/auth/permission/audit administration, legal/drawing foundations and final operational package.
Run B owns remaining operational modules; PR40 is already integrated and is not reimplemented here.
Plan: docs/superpowers/plans/2026-10-06-tenant-operational-completion.md.

Task 1 implemented; final verification/review/PR CI pending. Migration039 follows main038; open PRs empty at preflight.
Evidence: first11 tests RED, then tenant core11 GREEN. Initializer audit RED→GREEN; fresh migration seed regression RED→GREEN. Local PostgreSQL test requires CI service; local16 boundary tests pass,1skip. Existing full-suite222 pass before added tests.
Formal architecture and department lifecycle: docs/architecture/TENANT_OPERATIONS.md.
Actual production DB/OS credentials and backup validation remain Partial; LAN/TLS/real restoration acceptance remains External Gate.
Ruling: database/service-per-tenant is now APPROVED, not a pending architecture choice. User approval is the authority.
Ruling: initializing a legacy nonempty unmarked DB/root requires explicit --adopt-existing-data; choosing a tenant is not inferred from old data.
Ruling: dev SQLite remains available to regression tests; production mode fails on SQLite. Actual production isolation is not inferred from SQLite tests.

Ruling: initial migration permission definitions are bootstrap metadata, not tenant business records; allow permissions-only seeded DB and empty unmapped tables. Every other nonempty table requires explicit adoption. Incorrect classification could associate legacy data, so regression includes Employee and unmapped records refusal.
Task1 audit records tenant.initialize/adoption in same DB transaction; idempotent re-run produces no duplicate operation audit.

Task1 local verification: `python -m pytest backend/tests -q` → 227 passed,1 skipped,139 warnings; migration parser39/39; compileall and diff whitespace clean.
Fresh whole-Slice review: no Critical/Important remaining; independently tenant16 pass1skip, Session guard and audit rollback verified.
Final: minor (deferred): simultaneous same-UUID initialization can reject a stale storage marker snapshot; retry succeeds. Provisioning must serialize initialization for one department; binding never silently changes.

Task1 complete: PR41 merged8323930e659e6818a1cf85ccebc02dc34abc4e5f; PR CI37465769671 SUCCESS228 passed; main CI37466019056 SUCCESS.
Task2 in progress: manifestUUID/release/migrations/offline acknowledgement, source dump+original marker+target identity preflight; explicit env DSN to avoid process arguments; target service ownership maintained; per-department deployment generator and guarded runtime DB roles.
Task2 RED→GREEN evidence: backup3 failures→matching recovery/mismatch refusal; deployment8 failures→8 pass; runtime validator missing→pass; explicit recovery env/release2 failures→pass; service ownership failure→pass.
Latest full suite before ownership change244 passed3 skipped139 warnings. Real PostgreSQL recovery/role tests execute in CI, never counted as local pass.
Ruling: migration/restore administrative connections use identity validation but application/API/normalCLI additionally forbid privileged DB roles and mutable identity/audit; otherwise migration could not initialize protected identity. Incorrect use of administrative credentials in runtime is rejected.
Ruling: tenant production restore requires an already identified target; disaster recovery initializes an empty same-UUID target before restore. This avoids guessing ownership of unmarked live data; it costs one explicit initialization step.
Ruling: legacy unbound SQLite restore remains dev-test-only for existing tests; PostgreSQL or bound/production restore requires UUID, stopped-writer acknowledgement and matching selected release.
Task2 admin audit RED→GREEN: tenant.backup.started is captured in dump; tenant.restore.completed stores source hashes/release provenance after successful DB/filesystem restore.
Task2 fresh review: no Critical/Important on generated deployment/documented recovery path. Focused42 passed3 skipped (PostgreSQL runs in CI).
Final: minor (deferred): runtime checks do not detect column-only grants or NOINHERIT membership allowing SET ROLE. Generated app roles have neither; deployment must retain generated no-membership/no-column-grant contract.
Final: minor (deferred): custom dump recovery CI exercise uses disposable administrator credentials; combined app-backup/owner-restore/grant-reapply exercise remains useful additional coverage.
Final: minor (deferred): manually supplied PostgreSQL database names could have connection-string interpretation in CLI tools; generated fi_<slug> names avoid this. Operational database naming must follow generated identifiers.
Task2 final local verification: full suite246 passed3 skipped139 warnings; compileall, frontendJS syntax and diff whitespace checks pass. PostgreSQL full migration/restore/role jobs remain CI-required before merge.

Task2 complete: PR43 merged0335b59edb268b49e7e35cafedc1966c0a901d08; PR CI37468087421 SUCCESS249 passed; main CI37468465476 SUCCESS.
Canonical refresh: RunB PR42 merged main89e87e1739add38d2e5de7afac195c14e58b6a4f; exact-head main CI37470396667 SUCCESS; no open PR at audit. Migration040 and operations router/UI retained.
Task3 in progress: human organization/staff/assignment/transfer history, date-effective roles, account lifecycle/password history/session revocation, audit API and browser admin UI. Migration041; fresh branch review pending.
Task3 RED→GREEN: missing personnel4 tests, account/password2 tests, grant-boundary/enddate/audit3 tests. Focused9 passed1skip; integrated full291 passed5skip168warnings. PostgreSQL exclusion test waits for CI.
Ruling: RunB disabledcrew test now disables a separate synthetic crew member, not the logged-in operator; expected authentication rejection is retained. Otherwise the test bypasses the new retirement safety contract.
Ruling: system_admin remains explicit permanent Human-granted role; temporal assignments cannot accidentally expire the only administrator. Other assignment roles additionally require account.manage.
Remaining independent work: password expiry, audit pagination, formal-spec remaining common and drawing/legal modules, operational/release package; do not declare project complete from this Slice.
Task3 fresh-context review: no Critical; Important organization/employee activation authority, role-bearing assignment validity authority and reset/login race fixed. Each regression first failed then passed. Login shares PostgreSQL transaction advisory lock with Human administration; CI includes actual blocked-login/reset interleaving.
Final: fixed history boundary too: current plus five previous distinct generations, no duplicate hash history rows. Fifth-generation reuse regression RED→GREEN.
Final: fixed account-only UI staff selector: narrow account.manage employee picker; personnel detail API remains personnel.read protected. Picker regression RED→GREEN.
Local Chromium blocked by managed Unix socket policy; no local browser pass claimed. Add separate real Chromium CI job, synthetic-only server/data, screenshot artifact. This runs before merge alongside PostgreSQL migrations and recovery.
Task3 publication verification: `/tmp/fire-ai-venv/bin/python -m pytest backend/tests -q` → 297 passed,6 skipped,168 warnings,104.55s. PostgreSQL + real browser are CI-required and not locally counted. JS/compile/diff checks pass.
Task3 complete: PR44 merged fb2c9900f9cfa7e61d12106581d5a1d1ab5f1056. PR exact-head CI37476117058 SUCCESS: backend302 passed1skip97.93s; real browser1 passed8.71s, screenshot artifact11419291797. main CI awaited independently. Open PRs none on refresh.
Task4 signed legal updates in progress; spec38 Missing verified against both unsigned collectors/importers. Plan docs/superpowers/plans/2026-10-06-signed-legal-updates.md. Formal approval remains Human-only.
Task3 main exact-head CI37476512786 SUCCESS (fb2c9900). Fresh open PR list empty, recent merges44/42/43/41 checked; root AGENTS only; PROJECT_STATE retained but code/migration/test audit supersedes stale phase header.
Task4 evidence: cryptography48.0.1 installed in test venv; initial dependency failure was not counted as TDD RED. After dependency setup13 module-missing failures→13 passes. Production e-Gov importer provenance/candidate regression RED→GREEN; no LegalRuleVersion created; second import is idempotent; invalid signature leaves originals/versions unchanged. Both collectors' missing signing argument RED→GREEN. Signed ZIP unsafe member RED→GREEN. Signed collector repeated output and replay-timestamp regressions RED→GREEN; latest18 focused tests pass before additional folder integration.
Ruling: unsigned legacy bundles remain only for unbound nonproduction development/acquisition workflows; bound or production import always requires detached signature + operator-installed trust. A signature present but invalid is never downgraded to unsigned.
Ruling: keep imported source versions as evidence and review_required candidates; a trusted collector signature does not mean Human has approved any legal Rule.
Task4 fresh branch review found3 Important and1 Minor. Corrections: preflight all Law XML before business writes, permit identical shared HTML payload identity but reject conflicting hashes, restrict every collector redirect/final retrieval to the initial approved HTTPS host, convert malformed signature IDs into bounded rejection. Five reproductions RED→GREEN; fresh focused24 tests pass. Folio processing verifies before dispatch and checks immutable DB audit receipts, never inbound JSON markers; idempotent receipt still rechecks revoked/tampered signatures.
Task4 full suite before review fix had no asserted failures at last progress; final full run is required after all fixes. No completed claim yet.
Task4 final-review fixes verified:24 focused pass, both production-equivalent importers included in25-pass integration. Redirect guard validates destinations before follow and final response URL; collectors preserve effective URL/retrieval policy. Source snapshot bound to UUID/host/adapter/jurisdiction/profile is rechecked inside write transaction. All malformed signatures convert to rejection; special files opened nonblocking before regular-file validation. Full321 passed6skip before the final source/provenance integration; latest final full run pending.
Task4 publication verification: full backend322 passed6skip168warnings133.60s after all fixes/source snapshot/provenance; focused25 pass3.07s. Compile/JS/diff checks pass. No new migration required: existing source-version JSON and append-only audit carry signatures/receipts. Actual PG/browser regression remains CI-required before merge.
