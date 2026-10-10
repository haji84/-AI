# Failed authentication audit Implementation Plan

> For agentic workers: use test-driven-development and independent final code review.

Goal: persist minimal failed-login audit without recording supplied credentials or attributing an attacker to a known account.
Architecture: reuse the current tenant-bound Session, account_change_lock and write_audit. Commit an unauthenticated auth.login_failed event before the unchanged generic401; no schema or permission change.
Tech Stack: existing FastAPI, SQLAlchemy, pytest, PostgreSQL CI.
Spec: docs/SPECIFICATION.md §8/43.1 and Issue91; explicit user authorization for ordinary autonomous development.

## Constraints and review focus

No operational data, credentials, username/IP, new grants or dependency. No session/cookie/last_login on failure. Existing successful login, inactive employee boundary, account lock and tenant binding stay intact. Audit persistence errors fail closed; they must not falsely report a durably recorded event.

## Task 1: existing auth flow

Files: backend/app/routers/auth.py; backend/tests/test_authentication_audit.py; docs/completion/AUTHENTICATION_AUDIT_VERIFICATION_20261010.md.
Interface: login(payload,response,db) keeps the existing API. Failed event: user_id=None, entity_id=None, action=auth.login_failed, entity_type=user, success=False, no input metadata.

- [ ] Write parametrized unknown/inactive/unavailable/wrong-password failures and check durable exactly-one event, identical401, no Set-Cookie/session/last_login change or input data.
- [ ] Run tests on unmodified login; verify missing event RED.
- [ ] Minimal audit insertion and transaction commit before401.
- [ ] Run focused and auth/personnel/password/tenant regression; include audit-write failure rollback and successful login preservation.
- [ ] Independent review; fix material defects with RED/GREEN.
- [ ] Publish exact tree on isolated branch, PR, full exact-head CI; conflicts/conditions recheck before merge; independent main CI and evidence update.

## Integration task

Reconcile user-authorized additive security/HA/development requirements, preserving historical evidence. PR89 main CI is verified37891928869 SUCCESS; carry D21 forward. Expanded chapter42 is Partial until HA/Vault/restore contract is implemented and verified. Old Completed count is historical. Record this audit's limits and all unexecuted acceptance.
