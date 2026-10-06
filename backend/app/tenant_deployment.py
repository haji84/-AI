"""Render reviewable per-department server assets; never operate a live server."""
import json
import re
from uuid import UUID


def render_department(*, slug, tenant_id, host, port, release_id):
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
    common = f'''FIRE_AI_PRODUCTION_MODE=true
FIRE_AI_TENANT_ID={tenant_id}
FIRE_AI_TRUSTED_HOSTS='{json.dumps([host])}'
FIRE_AI_COOKIE_SECURE=true
FIRE_AI_STORAGE_ROOT={storage}
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
REVOKE UPDATE, DELETE ON learning_artifacts, learning_evaluations, learning_transitions FROM {application};
REVOKE UPDATE, DELETE ON learning_corrections, learning_evaluation_sets FROM {application};
GRANT UPDATE(review_status, reviewed_by, reason, version) ON learning_corrections, learning_evaluation_sets TO {application};
-- No role membership from application to owner; no DDL/TRUNCATE privileges.
'''
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
ExecStart={instance}/venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port {port} --workers 2 --proxy-headers --forwarded-allow-ips=127.0.0.1
Restart=on-failure
RestartSec=5
TimeoutStopSec=60
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=strict
ProtectHome=true
ReadWritePaths=/var/lib/fire-ai/{slug}
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
6. Install the generated department backup service/timer only after registering every writer in `FIRE_AI_BACKUP_WRITER_UNITS` (JSON list of own `fire-ai-{slug}-*.service`/`.timer` units). The root orchestrator stops timers/writers/app, runs the bound backup under PostgreSQL maintenance exclusion, then restores previous activity. It never deletes backups. Verify free space and test failure alerts. For manual backup STOP this service AND all CLI/sync writers, load `backup-{slug}.env`, run `scripts/backup_phase1.py --destination {backup} --release-id {release_id} --confirm-writers-stopped`.
7. For recovery STOP all writers, retain current DB+storage backup, load migration env and run `scripts/restore_phase1.py <backup-folder> --target-database-env FIRE_AI_DATABASE_URL --target-storage-root {storage} --confirm-restore --confirm-writers-stopped --expected-release-id {release_id}`.
8. Reapply `01-grants-{slug}.sql` as target owner; restored table/schema ACLs must fit target roles. Validate restored code release against manifest, migration list, counts, original hashes, audit and login before restart. DB and filesystem are not one transaction; failure keeps service stopped.
9. Update one department at a time: clone rehearsal, stopped-writer backup, migration as owner, reapply grants, build its new venv, switch its service WorkingDirectory/release, acceptance, restart. Never switch all services by replacing shared code.
10. Same-department relocation preserves UUID and paired DB/storage. New department generates new UUID and separate resources. Never overwrite another department identity.
'''
    return {slug + '.env': runtime, 'migration-' + slug + '.env': migration,
            'backup-' + slug + '.env': runtime + 'FIRE_AI_BACKUP_DESTINATION=' + backup + '\nFIRE_AI_BACKUP_WRITER_UNITS=\'[]\'\n',
            'fire-ai-' + slug + '-backup.service': backup_service,
            'fire-ai-' + slug + '-backup.timer': backup_timer,
            '00-create-' + slug + '.sql': cluster, '01-grants-' + slug + '.sql': grants,
            'fire-ai-' + slug + '.service': service, 'nginx-' + slug + '.conf': nginx,
            'README.md': layout}
