"""Department-bound backup preflight. No destructive operation is performed here."""
import json
import os
import re
import sqlite3
import subprocess
from pathlib import Path
from types import SimpleNamespace
from uuid import UUID

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import make_url
from .tenant import TenantBoundaryError, validate_binding


def postgres_args(database_url, restore=False):
    url = make_url(database_url)
    args = []
    for flag, value in (('-h', url.host), ('-p', url.port), ('-U', url.username)):
        if value is not None:
            args += [flag, str(value)]
    if url.database:
        args += (['-d', url.database] if restore else [url.database])
    env = os.environ.copy()
    if url.password is not None:
        env['PGPASSWORD'] = url.password
    supported = {'sslmode': 'PGSSLMODE', 'sslrootcert': 'PGSSLROOTCERT',
                 'sslcert': 'PGSSLCERT', 'sslkey': 'PGSSLKEY',
                 'connect_timeout': 'PGCONNECT_TIMEOUT', 'channel_binding': 'PGCHANNELBINDING',
                 'application_name': 'PGAPPNAME', 'target_session_attrs': 'PGTARGETSESSIONATTRS'}
    for name, value in url.query.items():
        if name not in supported or not isinstance(value, str):
            raise TenantBoundaryError('Unsupported PostgreSQL backup connection option')
        env[supported[name]] = value
    return args, env


def binding(database_url, storage_root, tenant_id):
    if database_url.startswith('sqlite'):
        path = Path(make_url(database_url).database or '')
        if not path.is_file():
            raise TenantBoundaryError('Department database must already be initialized')
    engine = create_engine(database_url)
    try:
        validate_binding(engine, SimpleNamespace(tenant_id=tenant_id, storage_root=str(storage_root), production_mode=True))
        with engine.connect() as connection:
            migrations = []
            if 'schema_migrations' in inspect(connection).get_table_names():
                migrations = list(connection.execute(text('SELECT version FROM schema_migrations ORDER BY version')).scalars())
        return migrations
    finally:
        engine.dispose()


def dump_identity(source, database_kind):
    if database_kind == 'sqlite-test-only':
        try:
            with sqlite3.connect(source.resolve().as_uri() + '?mode=ro', uri=True) as db:
                rows = db.execute('SELECT singleton_id, tenant_id FROM tenant_identity').fetchall()
        except sqlite3.Error:
            raise TenantBoundaryError('Backup database identity unavailable') from None
    else:
        result = subprocess.run(['pg_restore', '--data-only', '--table=tenant_identity', '--file=-', str(source)],
                                check=True, text=True, capture_output=True)
        # pg_dump custom archives preserve a COPY section with explicit column names.
        matches = re.findall(r'COPY public\.tenant_identity \(([^\n]+)\) FROM stdin;\n(.*?)\n\\\.', result.stdout, re.S)
        if len(matches) != 1:
            raise TenantBoundaryError('Backup database identity unavailable')
        columns, body = matches[0]
        columns = [column.strip().strip('"') for column in columns.split(',')]
        if 'singleton_id' not in columns or 'tenant_id' not in columns:
            raise TenantBoundaryError('Backup database identity unavailable')
        rows = []
        for line in body.splitlines():
            values = line.split('\t')
            if len(values) != len(columns):
                raise TenantBoundaryError('Invalid backup database identity')
            rows.append((values[columns.index('singleton_id')], values[columns.index('tenant_id')]))
    if len(rows) != 1 or str(rows[0][0]) != '1':
        raise TenantBoundaryError('Invalid backup database identity')
    try:
        return str(UUID(rows[0][1]))
    except (ValueError, TypeError):
        raise TenantBoundaryError('Invalid backup database identity') from None


def verify_restore_department(manifest, source, staged, database_url, target_storage, expected_id):
    try:
        expected_id = str(UUID(expected_id))
        if manifest.get('tenant_id') != expected_id or manifest.get('consistency') != 'writers-stopped':
            raise TenantBoundaryError('Backup belongs to another department or lacks consistency evidence')
        if not manifest.get('release_id') or not isinstance(manifest.get('migrations'), list):
            raise TenantBoundaryError('Backup release/migration evidence missing')
        if dump_identity(source, manifest['database_kind']) != expected_id:
            raise TenantBoundaryError('Backup database belongs to another department')
        marker = staged / 'tenant-identity.json'
        if json.loads(marker.read_text(encoding='utf-8'))['tenant_id'] != expected_id:
            raise TenantBoundaryError('Backup originals belong to another department')
        binding(database_url, target_storage, expected_id)
    except (OSError, ValueError, KeyError, TypeError, subprocess.CalledProcessError):
        raise TenantBoundaryError('Department backup identity could not be verified') from None


def record_admin_audit(database_url, tenant_id, action, details):
    from .models import AuditLog
    engine = create_engine(database_url)
    try:
        with engine.begin() as connection:
            connection.execute(AuditLog.__table__.insert().values(
                user_id=None, entity_type='tenant', entity_id=tenant_id, action=action,
                after_data=details, success=True, ai_used=False))
    finally:
        engine.dispose()
