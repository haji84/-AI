# Phase 1 Implementation

## Goal

Build a non-AI operational foundation that remains usable when AI services are unavailable and supports multiple concurrent browser users over the LAN.

## Implemented

### Database / identity
- PostgreSQL migrations 001-003
- SQLAlchemy UUID models aligned with PostgreSQL `uuid`
- employee and login-account separation
- roles / permissions / user-role / role-permission
- server-side session tokens stored as SHA-256 hashes
- Argon2 password hashing

### RBAC
Seeded role policy:
- `system_admin`
- `prevention_editor`
- `emergency_reporter`
- `emergency_detail_viewer`
- `auditor`

`emergency_reporter` can see aggregate reports but does not automatically receive case/patient/crew detail permissions.

### Concurrency / lifecycle
- record version optimistic locking
- stale update returns HTTP 409
- facility abolish and restore are explicit version-checked operations
- audit logs record important mutations

### Files
- originals stored under server-controlled storage root
- SHA-256 hashes preserved
- imported legacy source workbooks are archived under `imports/`
- clients do not directly rewrite the database or shared files

### Facility migration
`import_facilities.py`:
- reads `DB保存` OOXML directly
- validates required legacy headers
- upserts by unique legacy internal key
- maps core typed columns needed for Phase 1
- preserves every non-empty source column in `legacy_facility_source_rows.raw_payload`
- same source hash is idempotent

### Emergency migration
`import_emergency_xlsm.py`:
- reads `CSV_事案台帳`, `CSV_救護者台帳`, `CSV_出動隊員` directly
- normalizes case/patient/crew rows
- preserves every source field in raw payload
- converts Excel serial date/time values for indexed typed fields
- uses audited business keys
- preserves blank crew-code rows with fallback identities
- same source hash is idempotent

### Backup / restore
- PostgreSQL production path uses `pg_dump`/`pg_restore`
- storage root is archived with the DB backup
- manifest includes SHA-256 for DB and storage archive
- restore always requires an explicit target and confirmation flag
- verification checks required tables and key row counts

### Deployment
Reference deployment artifacts are under `deploy/` and `docs/phase1/LAN_DEPLOYMENT.md`.

## Not claimed as executed

The current build environment does not provide a real PostgreSQL server or PostgreSQL CLI backup tools. PostgreSQL-specific migration, UUID/JSONB and pg_dump/pg_restore execution must be run on the deployment/verification host before closing Phase 1.