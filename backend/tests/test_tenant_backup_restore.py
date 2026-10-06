import hashlib
import importlib.util
import json
import os
import sqlite3
import sys
from pathlib import Path
from uuid import uuid4

os.environ.setdefault('FIRE_AI_DATABASE_URL', 'sqlite+pysqlite:///:memory:')
import pytest
from sqlalchemy import create_engine
from app.db import Base
from app.settings import Settings
from app.tenant import initialize_tenant
from app import models


def script(name):
    path = Path(__file__).resolve().parents[2] / 'scripts' / (name + '.py')
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def department(root, tenant_id=None):
    root.mkdir()
    cfg = Settings(_env_file=None, tenant_id=tenant_id or str(uuid4()), trusted_hosts=['alpha.test'],
                   database_url='sqlite+pysqlite:///' + str(root / 'database.sqlite3'),
                   storage_root=str(root / 'originals'))
    engine = create_engine(cfg.database_url)
    Base.metadata.create_all(engine)
    initialize_tenant(engine, cfg, 'Synthetic department')
    (Path(cfg.storage_root) / 'evidence.pdf').write_bytes(b'synthetic original')
    engine.dispose()
    return cfg


def make_backup(monkeypatch, tmp_path, cfg):
    backup = script('backup_phase1')
    monkeypatch.setattr(backup, 'settings', cfg)
    monkeypatch.setattr(sys, 'argv', ['backup', '--destination', str(tmp_path / 'backups'),
                                    '--confirm-writers-stopped', '--release-id', 'test-release'])
    backup.main()
    return next((tmp_path / 'backups').iterdir())


def restore_into(monkeypatch, folder, cfg):
    restore = script('restore_phase1')
    monkeypatch.setattr(restore, 'settings', cfg)
    monkeypatch.setattr(sys, 'argv', ['restore', str(folder), '--target-database-url', cfg.database_url,
        '--target-storage-root', cfg.storage_root, '--confirm-restore', '--confirm-writers-stopped', '--expected-release-id', 'test-release'])
    restore.main()


def test_bound_backup_manifest_and_same_department_recovery(tmp_path, monkeypatch):
    source = department(tmp_path / 'source')
    folder = make_backup(monkeypatch, tmp_path, source)
    manifest = json.loads((folder / 'manifest.json').read_text())
    assert manifest['tenant_id'] == source.tenant_id
    assert manifest['release_id'] == 'test-release'
    assert manifest['consistency'] == 'writers-stopped'
    assert 'migrations' in manifest
    target = department(tmp_path / 'target', source.tenant_id)
    (Path(target.storage_root) / 'evidence.pdf').write_bytes(b'changed')
    restore_into(monkeypatch, folder, target)
    assert (Path(target.storage_root) / 'evidence.pdf').read_bytes() == b'synthetic original'


def test_other_department_recovery_changes_nothing(tmp_path, monkeypatch):
    source, target = department(tmp_path / 'source'), department(tmp_path / 'target')
    folder = make_backup(monkeypatch, tmp_path, source)
    database = Path(target.database_url.split('///', 1)[1])
    before = database.read_bytes()
    with pytest.raises(SystemExit): restore_into(monkeypatch, folder, target)
    assert database.read_bytes() == before
    assert (Path(target.storage_root) / 'evidence.pdf').read_bytes() == b'synthetic original'


def test_false_manifest_identity_cannot_override_dump_and_original_identity(tmp_path, monkeypatch):
    source, target = department(tmp_path / 'source'), department(tmp_path / 'target')
    folder = make_backup(monkeypatch, tmp_path, source)
    path = folder / 'manifest.json'
    manifest = json.loads(path.read_text());manifest['tenant_id'] = target.tenant_id
    path.write_text(json.dumps(manifest))
    database = Path(target.database_url.split('///', 1)[1]);before = database.read_bytes()
    with pytest.raises(SystemExit): restore_into(monkeypatch, folder, target)
    assert database.read_bytes() == before


def test_bound_backup_requires_writers_stopped_acknowledgement(tmp_path, monkeypatch):
    cfg = department(tmp_path / 'source');backup = script('backup_phase1')
    monkeypatch.setattr(backup, 'settings', cfg)
    monkeypatch.setattr(sys, 'argv', ['backup', '--destination', str(tmp_path / 'backups'), '--release-id', 'test-release'])
    with pytest.raises(SystemExit): backup.main()
    assert not (tmp_path / 'backups').exists()


def test_postgres_connection_preserves_tls_and_does_not_expose_password():
    from app.backup_contract import postgres_args
    args, env = postgres_args('postgresql+psycopg://user:secret@db.test:5432/alpha?sslmode=verify-full&sslrootcert=/etc/ca.crt')
    assert 'secret' not in ' '.join(args)
    assert env['PGPASSWORD'] == 'secret'
    assert env['PGSSLMODE'] == 'verify-full'
    assert env['PGSSLROOTCERT'] == '/etc/ca.crt'


def test_pg_dump_identity_rejects_multiple_or_wrong_rows(tmp_path, monkeypatch):
    from app.backup_contract import dump_identity
    from app.tenant import TenantBoundaryError
    import subprocess
    tenant_id = str(uuid4())
    copy = f'COPY public.tenant_identity (singleton_id, tenant_id, name) FROM stdin;\n1\t{tenant_id}\tSynthetic\n\\.\n'
    monkeypatch.setattr(subprocess, 'run', lambda *a, **k: subprocess.CompletedProcess(a, 0, stdout=copy))
    assert dump_identity(tmp_path / 'database.dump', 'postgresql') == tenant_id
    copy = copy.replace('1\t', '2\t')
    with pytest.raises(TenantBoundaryError): dump_identity(tmp_path / 'database.dump', 'postgresql')


def test_postgresql_bound_backup_restore(tmp_path, monkeypatch):
    url = os.environ.get('FIRE_AI_TEST_POSTGRES_URL')
    if not url:
        pytest.skip('PostgreSQL backup/restore service is exercised in CI')
    from sqlalchemy import text
    from sqlalchemy.engine import make_url
    from app.migrations import apply_migrations
    from app.tenant import validate_binding
    from app.backup_contract import dump_identity
    admin = create_engine(make_url(url).set(database='postgres'), isolation_level='AUTOCOMMIT')
    names = ['fi_backup_' + uuid4().hex[:16], 'fi_restore_' + uuid4().hex[:16]]
    engines = []
    try:
        with admin.connect() as connection:
            for name in names: connection.execute(text(f'CREATE DATABASE {name}'))
        configs = []
        tenant_id = str(uuid4())
        for index, name in enumerate(names):
            db_url = make_url(url).set(database=name).render_as_string(hide_password=False)
            apply_migrations(db_url, Path(__file__).resolve().parents[2] / 'db' / 'migrations')
            cfg = Settings(_env_file=None, production_mode=True, tenant_id=tenant_id,
                database_url=db_url, cookie_secure=True, trusted_hosts=['alpha.test'],
                storage_root=str(tmp_path / ('pg-originals-' + str(index))))
            engine = create_engine(db_url);engines.append(engine)
            initialize_tenant(engine, cfg, 'Synthetic PostgreSQL department');configs.append(cfg)
        source, target = configs
        (Path(source.storage_root) / 'evidence.pdf').write_bytes(b'pg original')
        folder = make_backup(monkeypatch, tmp_path, source)
        assert dump_identity(folder / 'database.dump', 'postgresql') == tenant_id
        restore_into(monkeypatch, folder, target)
        assert validate_binding(engines[1], target)['tenant_id'] == tenant_id
        assert (Path(target.storage_root) / 'evidence.pdf').read_bytes() == b'pg original'
    finally:
        for engine in engines: engine.dispose()
        with admin.connect() as connection:
            for name in names: connection.execute(text(f'DROP DATABASE IF EXISTS {name} WITH (FORCE)'))
        admin.dispose()


def test_restore_uses_explicit_environment_target_without_dsn_in_arguments(tmp_path, monkeypatch):
    source = department(tmp_path / 'source');folder = make_backup(monkeypatch, tmp_path, source)
    target = department(tmp_path / 'target', source.tenant_id);restore = script('restore_phase1')
    monkeypatch.setattr(restore, 'settings', target)
    monkeypatch.setenv('FIRE_AI_RECOVERY_DATABASE_URL', target.database_url)
    monkeypatch.setattr(sys, 'argv', ['restore', str(folder), '--target-database-env', 'FIRE_AI_RECOVERY_DATABASE_URL',
        '--target-storage-root', target.storage_root, '--confirm-restore', '--confirm-writers-stopped',
        '--expected-release-id', 'test-release'])
    restore.main()
    assert (Path(target.storage_root) / 'evidence.pdf').exists()


def test_restore_refuses_wrong_release_before_database_change(tmp_path, monkeypatch):
    source = department(tmp_path / 'source');folder = make_backup(monkeypatch, tmp_path, source)
    target = department(tmp_path / 'target', source.tenant_id);restore = script('restore_phase1')
    monkeypatch.setattr(restore, 'settings', target)
    monkeypatch.setattr(sys, 'argv', ['restore', str(folder), '--target-database-url', target.database_url,
        '--target-storage-root', target.storage_root, '--confirm-restore', '--confirm-writers-stopped',
        '--expected-release-id', 'other-release'])
    database = Path(target.database_url.split('///', 1)[1]);before = database.read_bytes()
    with pytest.raises(SystemExit, match="release"): restore.main()
    assert database.read_bytes() == before


def test_restore_preserves_target_service_ownership_with_private_permissions(tmp_path, monkeypatch):
    source = department(tmp_path / 'source');folder = make_backup(monkeypatch, tmp_path, source)
    target = department(tmp_path / 'target', source.tenant_id)
    owner = Path(target.storage_root).stat()
    calls = []
    real_chown = os.chown
    def chown(path, uid, gid):
        calls.append((Path(path).name, uid, gid))
        real_chown(path, uid, gid)
    monkeypatch.setattr(os, 'chown', chown)
    restore_into(monkeypatch, folder, target)
    assert ('evidence.pdf', owner.st_uid, owner.st_gid) in calls
    assert Path(target.storage_root).stat().st_mode & 0o777 == 0o700
    assert (Path(target.storage_root) / 'evidence.pdf').stat().st_mode & 0o777 == 0o600


def test_backup_and_restore_record_admin_audit_with_provenance(tmp_path, monkeypatch):
    source = department(tmp_path / 'source');folder = make_backup(monkeypatch, tmp_path, source)
    target = department(tmp_path / 'target', source.tenant_id)
    restore_into(monkeypatch, folder, target)
    with sqlite3.connect(Path(target.database_url.split('///', 1)[1])) as db:
        actions = dict(db.execute("SELECT action, after_data FROM audit_logs WHERE action IN ('tenant.backup.started','tenant.restore.completed')"))
    assert 'tenant.backup.started' in actions
    manifest = json.loads((folder / 'manifest.json').read_text())
    restored = json.loads(actions['tenant.restore.completed'])
    assert restored['database_sha256'] == manifest['database_sha256']
    assert restored['release_id'] == 'test-release'
