# Phase 1 LAN Deployment Profile

## Target

One approved server hosts the web API and PostgreSQL access. Client PCs use only a browser. Excel/JUST Calc/VBA are not runtime dependencies.

```text
Client browsers
    -> HTTPS reverse proxy
        -> FastAPI (localhost only)
            -> PostgreSQL
            -> shared storage mount
```

## Shared folder rule

The shared folder is not the database. It stores originals and backups only.

Recommended layout:

```text
/srv/fire-ai/storage/
  originals/
  imports/
  backups/
```

The server service account performs file writes. Browsers upload through the API so clients do not concurrently rewrite the same files.

## Required production controls

1. PostgreSQL is reachable only from the application server or an explicitly approved administration host.
2. HTTPS is used on the LAN. The certificate should come from the organization's trusted internal CA when available.
3. `FIRE_AI_COOKIE_SECURE=true` when HTTPS is enabled.
4. Use a dedicated non-interactive service account.
5. `.env`, TLS private keys and database credentials are ACL-restricted.
6. Original PDF/photo/audio/import files are stored under the server-controlled storage root and included in backup.
7. Audit logs remain in the database and are not deletable through ordinary application roles.
8. Firewall restricts access to the intended LAN segments.
9. Server clock synchronization is required because timestamps are audit evidence.
10. Client browsers must not receive direct PostgreSQL credentials.

## Example Linux service

Reference files:

- `deploy/systemd/fire-ai.service`
- `deploy/nginx/fire-ai.conf`

The exact hostname, certificate paths, network ranges, service user and mounted share must be changed for the real environment. They are intentionally not guessed in source control.

## Windows server fallback

See `deploy/windows/README.md`. The client model remains unchanged: browser only.

## Migration

```bash
PYTHONPATH=backend FIRE_AI_DATABASE_URL='postgresql+psycopg://...' python scripts/migrate_database.py
PYTHONPATH=backend FIRE_AI_DATABASE_URL='postgresql+psycopg://...' python scripts/seed_rbac.py
```

Then create the first administrator:

```bash
cd backend
python -m app.bootstrap --username admin --display-name 管理者
```

## Legacy import

```bash
PYTHONPATH=backend FIRE_AI_DATABASE_URL='postgresql+psycopg://...' \
FIRE_AI_STORAGE_ROOT='/srv/fire-ai/storage' \
python scripts/import_facilities.py '/path/to/★新査察台帳システム.xlsm'

PYTHONPATH=backend FIRE_AI_DATABASE_URL='postgresql+psycopg://...' \
FIRE_AI_STORAGE_ROOT='/srv/fire-ai/storage' \
python scripts/import_emergency_xlsm.py '/path/to/救急報告関係.xlsm'
```

The import tools print counts/hashes only and do not print names, addresses, patient details or other PII.

## Backup

```bash
PYTHONPATH=backend python scripts/backup_phase1.py --destination /srv/fire-ai/backups
```

PostgreSQL production backup requires `pg_dump`. Restore uses `pg_restore` and always requires an explicit target plus `--confirm-restore`.

## Recovery drill

Restore to a separate test database and a separate storage directory. Never use the production target for a routine drill.

```bash
PYTHONPATH=backend python scripts/restore_phase1.py /backup/folder \
  --target-database-url 'postgresql+psycopg://.../fire_ai_restore_test' \
  --target-storage-root /srv/fire-ai/restore-test-storage \
  --confirm-restore

PYTHONPATH=backend python scripts/verify_restored_database.py \
  --database-url 'postgresql+psycopg://.../fire_ai_restore_test'
```