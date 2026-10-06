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
