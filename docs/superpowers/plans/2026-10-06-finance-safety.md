# Finance authority and shared-PC safety

Spec: docs/SPECIFICATION.md chapters7,26,27,43,45. Canonical prerequisite: main7b320db (PR53), common mutation guard; no finance reimplementation.

Task1: reproduce queued session, permission, employee and password revocation; require the shared transaction account lock and fresh originating session/permission validation on all financial POST/PATCH endpoints. Preserve existing Human, Decimal, provenance, CAS and ledger checks.

Task2: reproduce authorization-loss, successful read-permission-loss and late-response retention in the actual finance JavaScript. Clear modal/drafts/cache/permissions on authentication/authorization/identity loss; discard responses from earlier state generations; cover downloads too. Keep finance.read and contract.read separately authorized.

Task3: focused and full tests, one fresh branch review, one TDD repair pass, exact-head PostgreSQL/Chromium CI, PR merge and main Green. Record actual evidence; do not infer production acceptance.

Review Focus: lock order against financial advisory and row locks; secondary permissions after lock; originating session reuse; mixed finance/contract-only rights; Promise.all late responses; export/attachment links; revoked-read state and pending form handlers; no loss of approved ledger or Human source binding.
