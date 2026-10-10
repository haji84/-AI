# Failed authentication audit — Issue 91

Base: canonical main `847d793` (PR 89). This bounded slice implements the failed-login evidence requirement added to specification §43.1; it does not complete chapter 43 or the system.

## Behavior and privacy

`POST /auth/login` reuses the existing tenant-bound request database, personnel/account transaction lock and append-only audit mechanism. Unknown username, incorrect password, inactive account and unavailable employee all persist one `auth.login_failed` event before the unchanged generic HTTP 401 response.

The event has `success=false`, `user_id=null`, `entity_id=null`, `entity_type=user`. Supplied username, password, cookie/token, IP/header content and internal rejection reason are not recorded. A known account is not attributed as the actor of an unauthenticated attempt. No session, response cookie or last-login change is created on rejection. Successful login retains its current audit/session behavior.

If audit persistence fails, the request fails closed with a generic HTTP 500; it does not claim successful durable recording, issue a session or reveal the storage exception. Request-session cleanup rolls back the failed transaction. No migration, new dependency, role/grant or authentication policy is introduced.

## Executed local evidence

Environment: Python 3.12, isolated file-backed SQLite engines, real FastAPI HTTP requests and SQLAlchemy transactions, synthetic records only.

- Before implementation: `python -m pytest backend/tests/test_authentication_audit.py -q` produced **7 failed, 1 passed**, 2.77 s. The failure conditions returned 401 but persisted zero audit events; the injected audit-storage-failure case still returned 401 because no audit write was attempted. Successful authentication already passed.
- After the four-line implementation, focused authentication/personnel/password/bootstrap/tenant/authorization regression produced **68 passed, 27 skipped**, 24.77 s. Command: `python -m pytest backend/tests/test_authentication_audit.py backend/tests/test_personnel.py backend/tests/test_password_expiry.py backend/tests/test_bootstrap_security.py backend/tests/test_tenant_boundary.py backend/tests/test_human_authorization.py -q`.
- Dedicated final test file: **8 passed, 2 skipped**, 2.98 s. The two skips explicitly cover the PostgreSQL lock-lifecycle test's SQLite fixture variant and the native PostgreSQL variant when its CI database URL is absent.

The dedicated tests verify durable exactly-one evidence from a fresh database session for each rejection reason, anonymous empty metadata, repeated individual events, unchanged last login/no session/cookie, successful login preservation, injected storage failure with rollback, and two separately bound department databases. A wrong Host returns 421 before any failed-login audit write to the other department.

The native PostgreSQL test uses the established isolated migrated-database fixture. During audit insertion, a separate database connection must fail to acquire the personnel advisory transaction lock; after the rejected request commits, it must acquire that lock and observe the durable event. This is actual database locking evidence only when the PostgreSQL test executes; SQLite is not credited as a substitute.

One existing dependency deprecation warning was reported: Starlette's installed TestClient warns about using httpx. No dependency change is made in this slice.

## Remaining acceptance

Full exact-head PostgreSQL/browser CI, independent review, protected PR merge and independent main CI remain required for main implementation credit. Local full-suite results are to be appended after execution. No actual deployment/TLS/OS ACL, MFA, rate limiting, intrusion containment, backup encryption, HA or Owner Recovery Vault acceptance is claimed. Anonymous failure events support observation of failed attempts; this slice does not implement detection thresholds, identity/IP correlation or denial-of-service protection.

Every rejected attempt now writes audit while holding the existing global account lock. A flood can grow audit storage and contend with administration/login; retention, bounded admission/rate limiting and monitoring remain unfinished. This change does not establish attack-ready operation.

Independent review: no Critical/Important blocking finding; independently rerun dedicated8 passed/2 skipped, diff check clean. PostgreSQL advisory-lock acceptance remains exact CI-only.
