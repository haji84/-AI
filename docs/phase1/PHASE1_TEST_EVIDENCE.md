# Phase 1 Test Evidence

Date: 2026-10-04

## Backend automated tests

Command:

```bash
cd backend
pytest -q
```

Result:

```text
6 passed
```

Coverage includes health, login/RBAC, facility CRUD, optimistic locking, file SHA-256, role separation, abolish/restore version locking and migration splitter behavior.

## Real facility workbook import

PII-safe verification result:

```text
facilities: 611
legacy source rows preserved: 611
first import: inserted 611
forced re-import: inserted 0, updated 0, skipped 611
```

No names or addresses are printed by the verification tool.

## Real emergency workbook import

PII-safe verification result:

```text
cases: 2,958
patients: 2,950
crew: 8,981
unresolved crew code: 66
```

Forced identical-file re-import:

```text
cases: inserted 0, updated 0, skipped 2,958
patients: inserted 0, updated 0, skipped 2,950
crew: inserted 0, updated 0, skipped 8,981
```

No patient/person values are printed by the verification tool.

## Recovery drill

Using a temporary SQLite database strictly as a behavior-test substitute:

1. Imported both real legacy workbooks.
2. Archived the two source workbooks under test storage.
3. Created DB + storage backup with checksum manifest.
4. Restored to a separate DB and separate storage root.
5. Verified required tables and row counts.

Result:

```text
facilities: 611
emergency_cases: 2,958
emergency_patients: 2,950
emergency_crew_assignments: 8,981
archived source files restored: 2
PASS
```

## PostgreSQL limitation

No PostgreSQL server, `pg_dump` or `pg_restore` is available in the current execution environment. Therefore PostgreSQL integration is not falsely reported as passed.

Prepared host-side verification:
- `scripts/check_phase1_host.py`
- `scripts/migrate_database.py`
- `scripts/verify_postgres_phase1.py`
- `scripts/backup_phase1.py`
- `scripts/restore_phase1.py`
- `scripts/verify_restored_database.py`

These must be executed on an approved PostgreSQL verification host before formal Phase 1 exit.