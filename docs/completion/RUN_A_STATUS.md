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
