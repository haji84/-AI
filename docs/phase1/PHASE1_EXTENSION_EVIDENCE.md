# Phase 1 Extension Foundation Evidence

Date: 2026-10-04

## Implemented
- migration 004: extensibility/templates/contracts
- Module Registry and seeded modules
- Feature Flag with optimistic version
- Extension Intake
- Import Adapter definition Schema
- Human Change Request create/review/approve
- review-before-approval enforcement
- Deployment evidence record
- manual Rollback record + Feature Flag disable
- official Form Template registry using original Document
- contract counterparty/case/change/document foundation
- contract edit optimistic lock
- contract approval separated by permission
- Phase 2 facility search/list API
- Phase 2 browser preview `/ui/`

## Automated tests
`pytest`: 13 passed

Covered new behavior includes:
- facility search/list
- Change Request cannot be approved before review
- official form template keeps original document reference
- contract stale-write rejection
- explicit contract approval
- Module Registry seed
- deployment/rollback audit path and Feature Flag disable
- browser preview served

## Real legacy verification after extension changes
The existing importers were rerun against the supplied operational workbooks using temporary local storage/SQLite test-only verification. No row values were printed.

Counts:
- facilities: 611
- facility source rows: 611
- emergency cases: 2,958
- emergency patients: 2,950
- emergency crew: 8,981
- unresolved crew identity: 66

Forced re-import remained idempotent.

## Migration parser
`004_extensibility_templates_contracts.sql`: 25 DDL/DML statements parsed successfully by the current migration splitter.

## Not yet truthfully executed
Actual approved-host PostgreSQL migration, pg_dump/pg_restore, HTTPS/LAN two-PC test and concurrent browser E2E remain host-dependent. They must not be marked PASS until run on the real deployment host.