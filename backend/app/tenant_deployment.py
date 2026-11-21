"""Render reviewable per-department server assets; never operate a live server."""
import json
import re
from uuid import UUID


def render_department(*, slug, tenant_id, host, port, release_id, emergency_audit=False):
    if type(emergency_audit) is not bool:
        raise ValueError('emergency_audit must be an explicit boolean')
    if not re.fullmatch(r'[a-z][a-z0-9_]{0,15}', slug):
        raise ValueError('slug must be a short lowercase server identifier')
    if not re.fullmatch(r'[a-z0-9](?:[a-z0-9.-]{0,251}[a-z0-9])?', host) or '..' in host:
        raise ValueError('host must be an exact lowercase DNS name or IPv4 address')
    if not isinstance(port, int) or not 1024 <= port <= 65535:
        raise ValueError('Use an unprivileged dedicated loopback port')
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._-]{0,79}', release_id) or release_id in {'.', '..'}:
        raise ValueError('Invalid immutable release identifier')
    tenant_id = str(UUID(tenant_id))
    database, owner, application = 'fi_' + slug, 'fi_' + slug + '_owner', 'fi_' + slug + '_app'
    code = '/opt/fire-ai/releases/' + release_id
    instance = '/opt/fire-ai/instances/' + slug
    storage = '/var/lib/fire-ai/' + slug + '/storage'
    backup = '/var/backups/fire-ai/' + slug
    audit_worker_name = 'fire-ai-' + slug + '-emergency-audit-worker.service'
    audit_worker_runtime = 'fire-ai-' + slug + '-emergency-audit-worker'
    audit_api_runtime = 'fire-ai-' + slug + '-emergency-audit-api'
    audit_key = '/etc/fire-ai/keys/' + slug + '-emergency-audit/audit.key' if emergency_audit else ''
    audit_manifest = '/etc/fire-ai/' + slug + '-emergency-audit-native.json' if emergency_audit else ''
    common = f'''FIRE_AI_PRODUCTION_MODE=true
FIRE_AI_TENANT_ID={tenant_id}
FIRE_AI_TRUSTED_HOSTS='{json.dumps([host])}'
FIRE_AI_COOKIE_SECURE=true
# Human optional password-age policy,1..3650days; unset means explicit scheduling.
# FIRE_AI_PASSWORD_MAX_AGE_DAYS=
FIRE_AI_STORAGE_ROOT={storage}
# Optional Linux-server report audit. Generated settings never authorize real-data use.
FIRE_AI_EMERGENCY_AUDIT_ENABLED={str(emergency_audit).lower()}
FIRE_AI_EMERGENCY_AUDIT_INTERNAL_ENABLED=false
FIRE_AI_EMERGENCY_AUDIT_KEY_FILE={audit_key}
FIRE_AI_EMERGENCY_AUDIT_NATIVE_MANIFEST={audit_manifest}
FIRE_AI_EMERGENCY_AUDIT_OCR_LANGUAGE=jpn+eng
# A local model is separately provisioned and reviewed; empty means NOT_CONFIGURED.
FIRE_AI_EMERGENCY_AUDIT_AI_MODEL=
FIRE_AI_EMERGENCY_AUDIT_AI_PORT=11434
FIRE_AI_EMERGENCY_AUDIT_WORKER_TIMEOUT=600
'''
    runtime = common + f'FIRE_AI_DATABASE_URL=postgresql+psycopg://{application}:REPLACE_WITH_URLENCODED_PASSWORD@127.0.0.1:5432/{database}\n'
    migration = common + f'FIRE_AI_DATABASE_URL=postgresql+psycopg://{owner}:REPLACE_WITH_URLENCODED_PASSWORD@127.0.0.1:5432/{database}\n'
    cluster = f'''-- Run as cluster administrator; this file never changes another database.
CREATE ROLE {owner} LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOBYPASSRLS;
CREATE ROLE {application} LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOBYPASSRLS;
CREATE DATABASE {database} OWNER {owner};
REVOKE ALL ON DATABASE {database} FROM PUBLIC;
GRANT CONNECT ON DATABASE {database} TO {owner}, {application};
-- Set passwords interactively using psql's \\password; do not store them in SQL/history.
'''
    grants = f'''-- Connect to {database} as its owner, AFTER every migration.
REVOKE CREATE ON SCHEMA public FROM PUBLIC;
GRANT USAGE ON SCHEMA public TO {application};
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO {application};
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO {application};
REVOKE INSERT, UPDATE, DELETE ON tenant_identity FROM {application};
REVOKE INSERT, UPDATE, DELETE ON schema_migrations FROM {application};
REVOKE UPDATE, DELETE ON audit_logs FROM {application};
REVOKE UPDATE, DELETE ON correction_events FROM {application};
REVOKE UPDATE, DELETE ON learning_artifacts, learning_evaluations, learning_transitions FROM {application};
REVOKE UPDATE, DELETE ON learning_corrections, learning_evaluation_sets FROM {application};
GRANT UPDATE(review_status, reviewed_by, reason, version) ON learning_corrections, learning_evaluation_sets TO {application};
-- No role membership from application to owner; no DDL/TRUNCATE privileges.
'''
    api_audit_temp = f'''Environment=TMPDIR=/run/{audit_api_runtime}
RuntimeDirectory={audit_api_runtime}
RuntimeDirectoryMode=0700
KillMode=control-group
''' if emergency_audit else ''
    api_write_paths = f'/var/lib/fire-ai/{slug}' + (f' /run/{audit_api_runtime}' if emergency_audit else '')
    service = f'''[Unit]
Description=Fire AI department {slug}
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=fireai_{slug}
Group=fireai_{slug}
WorkingDirectory={code}
EnvironmentFile=/etc/fire-ai/{slug}.env
{api_audit_temp}ExecStart={instance}/venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port {port} --workers 2 --proxy-headers --forwarded-allow-ips=127.0.0.1
Restart=on-failure
RestartSec=5
TimeoutStopSec=60
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=strict
ProtectHome=true
ReadWritePaths={api_write_paths}
UMask=0077

[Install]
WantedBy=multi-user.target
'''
    audit_worker = f'''[Unit]
Description=Fire AI private emergency report worker for department {slug}
After=network-online.target fire-ai-{slug}.service
Wants=network-online.target

[Service]
Type=simple
User=fireai_{slug}
Group=fireai_{slug}
WorkingDirectory={code}
EnvironmentFile=/etc/fire-ai/{slug}.env
Environment=TMPDIR=/run/{audit_worker_runtime}
RuntimeDirectory={audit_worker_runtime}
RuntimeDirectoryMode=0700
ExecStartPre={instance}/venv/bin/python {code}/scripts/check_emergency_audit_host.py
ExecStart={instance}/venv/bin/python {code}/scripts/run_emergency_audit_worker.py
Restart=on-failure
RestartSec=5
TimeoutStopSec=30
KillMode=control-group
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=strict
ProtectHome=true
ReadWritePaths=/var/lib/fire-ai/{slug} /run/{audit_worker_runtime}
UMask=0077

[Install]
WantedBy=multi-user.target
'''
    nginx = f'''server {{
    listen 443 ssl;
    server_name {host};
    ssl_certificate /etc/fire-ai/tls/{slug}.crt;
    ssl_certificate_key /etc/fire-ai/tls/{slug}.key;
    ssl_protocols TLSv1.2 TLSv1.3;
    client_max_body_size 200m;
    add_header X-Content-Type-Options nosniff always;
    add_header X-Frame-Options DENY always;
    add_header Referrer-Policy no-referrer always;
    location / {{
        proxy_pass http://127.0.0.1:{port};
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-Proto https;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_read_timeout 120s;
    }}
}}
server {{
    listen 80;
    server_name {host};
    return 301 https://{host}$request_uri;
}}
'''
    backup_service = f"""[Unit]
Description=Fire AI paired backup for department {slug}
After=network-online.target

[Service]
Type=oneshot
User=root
WorkingDirectory={code}
EnvironmentFile=/etc/fire-ai/backup-{slug}.env
ExecStart={instance}/venv/bin/python {code}/scripts/scheduled_department_backup.py --slug {slug} --release-id {release_id}
ReadOnlyPaths=/etc/fire-ai/keys/{slug}-backup-recipient.pem
UMask=0077
TimeoutStartSec=infinity
"""
    backup_timer = f"""[Unit]
Description=Daily Fire AI paired backup for department {slug}

[Timer]
OnCalendar=*-*-* 03:00:00 Asia/Tokyo
Persistent=true
Unit=fire-ai-{slug}-backup.service

[Install]
WantedBy=timers.target
"""
    layout = f'''# Generated server assets for {slug}

Department UUID: `{tenant_id}`. Release: `{release_id}`.
These files are a reviewable configuration package. No server is provisioned by generation.

Paths: code `{code}`, dedicated venv `{instance}/venv`, storage `{storage}`, backups `{backup}`.
Create OS account `fireai_{slug}`. Storage owner is that account, mode0700. Backup owner is root, mode0700.
Code and venv are root-owned, readable/executable but unwritable by the service. Environment files are root-owned mode0600.
Review DNS `{host}`, TLS certificate, port `{port}`, capacity and PostgreSQL access before installing.

1. Install `00-create-{slug}.sql` as cluster admin; use psql `\\password {owner}` and `\\password {application}` to set separate passwords interactively.
2. Put URL-encoded credentials in migration/runtime env files. Never commit edited files. Keep migration credentials out of the runtime environment.
3. Build dedicated venv from common release backend. Load migration env, run `scripts/migrate_database.py`, then `scripts/initialize_tenant.py --name '<department name>'`.
4. Apply `01-grants-{slug}.sql` as owner. Load runtime env and bootstrap the human administrator interactively. Install service/nginx and approved TLS certificate.
5. Verify matching DB/root UUID, another department DB CONNECT denial, identity mutation/audit alteration denial, other OS account storage/backup denial, health, RBAC, Human Gate and two-PC conflict.
6. Human review and enrollment must place this department's X25519 public recipient at `/etc/fire-ai/keys/{slug}-backup-recipient.pem`, separate from data/backups; never place the private key on this host as part of generation. Install the generated department backup service/timer only after registering every writer in `FIRE_AI_BACKUP_WRITER_UNITS` (JSON list of own `fire-ai-{slug}-*.service`/`.timer` units). Required encryption fails closed if the recipient is unavailable. The root orchestrator stops timers/writers/app, runs the bound backup under PostgreSQL maintenance exclusion, then restores previous activity. It never deletes backups. Verify free space and test failure alerts.
7. Recovery private-key custody, revocation and emergency access require Human approval. For an approved recovery STOP all writers, retain current DB+storage backup, set `FIRE_AI_BACKUP_PRIVATE_KEY` only in the protected recovery environment, load migration env and run `scripts/restore_phase1.py <backup-folder> --target-database-env FIRE_AI_DATABASE_URL --target-storage-root {storage} --confirm-restore --confirm-writers-stopped --expected-release-id {release_id} --decryption-private-key-env FIRE_AI_BACKUP_PRIVATE_KEY`.
8. Reapply `01-grants-{slug}.sql` as target owner; restored table/schema ACLs must fit target roles. Validate restored code release against manifest, migration list, counts, original hashes, audit and login before restart. DB and filesystem are not one transaction; failure keeps service stopped.
9. Update one department at a time: clone rehearsal, stopped-writer backup, migration as owner, reapply grants, build its new venv, switch its service WorkingDirectory/release, acceptance, restart. Never switch all services by replacing shared code.
10. Same-department relocation preserves UUID and paired DB/storage. New department generates new UUID and separate resources. Never overwrite another department identity.
'''
    if emergency_audit:
        layout += f'''
## Optional private emergency report audit (Linux server)

The explicit `--emergency-audit` generation option includes `{audit_worker_name}` and registers it in this package's backup writer list. This creates reviewable files only; it does not install or start anything. `FIRE_AI_EMERGENCY_AUDIT_INTERNAL_ENABLED` remains false, and no local AI model is selected.

Before enabling the worker, provision the approved native OCR/jpn+eng distribution and root-owned manifest `{audit_manifest}`. Create the private parent directory `/etc/fire-ai/keys/{slug}-emergency-audit` for `fireai_{slug}`, mode0700. Explicitly initialize the absent key using the protected department runtime environment and `scripts/check_emergency_audit_host.py --initialize-key`; generation never creates a key. Keep this AES key and its recovery copy outside storage and ordinary backups. No unit downloads a package, language or model.

Install the generated API and worker units together. Their private mode0700 temporary areas `/run/{audit_api_runtime}` and `/run/{audit_worker_runtime}` are separate; verify that `/run` is tmpfs. Worker `ExecStartPre` verifies the approved native manifest, key and private temporary area. Ordinary API startup does not depend on OCR/model readiness. Review `docs/emergency/AUDIT_OPERATIONS.md`, run synthetic acceptance and verify worker heartbeat before allowing report processing. Real-data activation requires separate local operational acceptance.

The backup writer list includes `{audit_worker_name}` because it writes the DB and encrypted storage. Install that unit before scheduling backup. Preserve and merge every existing department writer/timer when updating `backup-{slug}.env`; do not replace an existing writer inventory with the generated initial list. An installed but inactive worker is stopped and remains inactive after backup; a previously active worker is restarted. A missing registered unit fails backup closed. The default package without `--emergency-audit` has no such registration or dependency.

For each release, update both the API and worker release/venv references under stopped-writer backup and acceptance. Do not remove a worker's backup registration while it can still run. To disable and remove it, first stop/disable the worker and report intake, set the audit flags false, then remove the stopped unit from the writer inventory. Preserve the existing AES key for stored history and recovery. Keep API/worker settings and the backup writer inventory together in the deployment review.
'''
    else:
        layout += '''
## Optional private emergency report audit

Audit flags are false by default, no audit worker unit is generated, and backup has no dependency on an uninstalled optional worker. To prepare the Linux-server audit configuration, regenerate for the same department UUID/release with `--emergency-audit` into a new review directory, then follow `docs/emergency/AUDIT_OPERATIONS.md`. Review and merge existing credentials, settings and writer inventory; never overwrite a live environment file with generated placeholders. Key creation, OCR/model provisioning, real-data activation and server operations remain separate explicit administrator steps.
'''
    writers = json.dumps([audit_worker_name] if emergency_audit else [])
    assets = {slug + '.env': runtime, 'migration-' + slug + '.env': migration,
            'backup-' + slug + '.env': runtime + 'FIRE_AI_BACKUP_DESTINATION=' + backup + "\nFIRE_AI_BACKUP_WRITER_UNITS='" + writers + "'\nFIRE_AI_BACKUP_ENCRYPTION_REQUIRED=true\nFIRE_AI_BACKUP_RECIPIENT_PUBLIC_KEY=/etc/fire-ai/keys/" + slug + '-backup-recipient.pem\n',
            'fire-ai-' + slug + '-backup.service': backup_service,
            'fire-ai-' + slug + '-backup.timer': backup_timer,
            '00-create-' + slug + '.sql': cluster, '01-grants-' + slug + '.sql': grants,
            'fire-ai-' + slug + '.service': service, 'nginx-' + slug + '.conf': nginx,
            'README.md': layout}
    if emergency_audit:
        assets[audit_worker_name] = audit_worker
    return assets
