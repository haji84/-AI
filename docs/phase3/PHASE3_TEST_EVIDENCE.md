# Phase 3 Test Evidence

更新日: 2026-10-05

## Automated tests

- backend pytest: 30 passed
- frontend JavaScript syntax: PASS (`node --check`)

Covered behavior includes:
- inspection/finding workflow
- stale-write conflict rejection
- submission receipt and original-document link
- official number digits-only API validation
- official number digits-only PostgreSQL CHECK definition
- submission-type browser alias
- submission stale-write rejection
- fire manager / fire plan specialized data
- prevention RBAC boundary
- legacy date parsing and raw-text preservation
- legacy manager name does not falsely claim submission evidence
- legacy dashboard states

## Real legacy workbook verification

Input: supplied operational inspection ledger. No business row values or personal information were printed to evidence.

First import:
- facilities: 611
- facility details: 611
- facility contacts: 611
- facility floors: 1,434
- legacy fire-management records: 70
- legacy fire-management rows containing filing/source text: 65
- legacy fire-plan records: 54
- legacy equipment-report records with actual report/result field values: 1
- legacy guidance records: 579

Forced second import:
- facilities inserted: 0
- facilities updated: 0
- facilities skipped: 611
- normalized Phase 3 record counts remained unchanged

This confirms idempotency for the tested development import path.

## Not executed

- approved LAN PostgreSQL migration 001-006
- real PostgreSQL backup/restore after migration 006
- HTTPS from production LAN clients
- two physical clients editing the same record concurrently