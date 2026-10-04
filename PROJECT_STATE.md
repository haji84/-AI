# PROJECT_STATE

更新日: 2026-10-05

## Current Phase

Phase 3 inspection + submission core is code-complete and verified in the development environment.
The formal approved-host PostgreSQL/TLS/two-client gate remains unexecuted.

## Phase 0-2 retained
- legacy inspection ledger audited and mapped
- common auth/RBAC/audit/optimistic locking/extensibility foundation
- emergency reporting import foundation
- facility browser/detail/create/edit/abolish/restore/history
- 611 facilities normalized to 611 details, 611 contacts, 1,434 floor rows

## Phase 3 completed in code
- inspections and findings
- submission type master
- receipt/update workflow
- original document linkage
- digits-only official number
- equipment inspection report / fire manager / fire plan specialized records
- facility dashboard
- Phase 3 browser workflow
- legacy Phase 3 normalization with raw evidence preservation

## Verification
- backend tests: 30 passed
- frontend JavaScript syntax: PASS
- real legacy facility workbook import: PASS
- forced second import idempotency: PASS
- legacy Phase 3 counts: manager 70, manager-with-filing-text 65, fire-plan 54, equipment-report-value 1, guidance 579

## Formal Host Gate remaining
1. approved LAN PostgreSQL host
2. migrations 001-006 on host
3. PostgreSQL backup/restore test
4. HTTPS client access
5. two physical clients concurrent edit E2E

## Next
Phase 4: document intake/OCR/content classification and AI-assisted extraction/difference review, while keeping formal reflection behind Human Gate.