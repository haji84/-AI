# Tenant operational completion implementation plan

Goal: implement the user's approved common-code, database/service/originals/backup-per-fire-department deployment.
Spec: docs/architecture/TENANT_ISOLATION_DECISION.md; user's 2026-10-06 approval supersedes proposed status.
Execution: inline; existing authorized small-PR/test/CI/main-merge process. No routine approval pauses.
Shared contract: common app.db.Base/SessionLocal, settings, storage root and Employee remain authoritative; Run B owns operational modules.

## Task 1 — tenant identity and fail-closed runtime
- Add app.tenant with TenantIdentity singleton, initialize_tenant(engine, settings, name, adopt_existing=False) and validate_binding(engine, settings).
- Add append-only migration after current 038; no automatic association of existing production data with a tenant.
- Settings: production_mode, tenant_id, trusted_hosts. Production requires PostgreSQL, valid tenant UUID, Secure cookie, absolute original root and explicit exact hosts.
- Initialize DB/storage binding through an explicit CLI, immutable after initialization; reject wrong DB/root, unmarked existing records/root unless adoption explicitly requested.
- Check before startup and HTTP request; ignore client-supplied tenant selectors; reject unknown Host.
- Tests: absent/wrong DB identity, wrong storage, read-only validation, explicit legacy adoption, two independent DB users/data/cookies, unknown Host, concurrent initialization identity uniqueness.
- Run full suite and migration parsing; review; PR/CI/merge.

## Task 2 — tenant lifecycle, backup/restore and deployment
- Add tenant_id to backups only after validating DB/storage identity; reject mislabeled source.
- Restore preflight compares manifest tenant against initialized target DB/root before writing. Legacy backups stay dev-only by default; never silently relabel production data.
- Add per-instance systemd/nginx/environment templates and provisioning commands with dedicated DB role/database/service account/ACL.
- Test cross-tenant restore refusal with target unchanged, valid round trip, no alternate CLI target bypass and no original/backup overlap.
- Add PostgreSQL service CI: actual complete migration execution/idempotency, ORM column contract, tenant cross-role connection denial and recovery verification.
- PR/CI/merge; correct actual failures instead of reducing gates.

## Task 3 — common organization and assignment administration
- Dedicated OrganizationUnit and dated EmployeeAssignment history using existing immutable Employee IDs.
- Explicit assignment-role rules; no AI permission mutation; effective-date permissions and disabled/terminated employee session refusal.
- Staff/account/organization/history management APIs with dedicated RBAC, optimistic locking, audits; browser UI.
- Tests: transfer/end date, stale update, no cross-department membership via separate DB boundary, account/employee separation, unauthorized administration, audit preservation.
- PR/CI/merge and publish contract for Run B workforce integration.

## Task 4 — operational artifacts and re-audit
- Complete setup/server/update/backup/restore/admin/user/config/DB/migration/permissions/security/test/limitations/release reports using actual code and results.
- Separate implemented runtime boundaries from external LAN/Unix ACL/official Human benchmark acceptance.
- Continue independently implementable Run A gaps; avoid reimplementing Run B.
- Stop only at a genuinely needed external credential/environment/Human formal decision; never claim system complete with missing evidence.

Review focus: configuration points to wrong tenant; unmarked legacy dataset; request Host or cookie crosses boundary; restore replaces mismatched target; organization transfer changes active permissions without rewriting history.
