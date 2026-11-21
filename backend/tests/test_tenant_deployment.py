import pytest
from uuid import uuid4


def environment_values(content):
    import shlex
    values = {}
    for line in content.splitlines():
        if not line.strip() or line.lstrip().startswith('#'):
            continue
        key, value = line.split('=', 1)
        parts = shlex.split(value)
        values[key] = parts[0] if parts else ''
    return values


def parameters():
    return dict(slug='alpha', tenant_id=str(uuid4()), host='alpha.fire.internal',
                port=8101, release_id='release-20261006')


def test_department_configuration_has_separate_paths_users_db_and_lifecycle():
    from app.tenant_deployment import render_department
    first = render_department(**parameters())
    second_args = parameters();second_args.update(slug='beta', host='beta.fire.internal', port=8102)
    second = render_department(**second_args)
    assert 'User=fireai_alpha' in first['fire-ai-alpha.service']
    assert '/var/lib/fire-ai/alpha/storage' in first['alpha.env']
    assert '/var/backups/fire-ai/alpha' in first['backup-alpha.env']
    assert 'fi_alpha_app' in first['alpha.env']
    assert 'fi_alpha_owner' in first['migration-alpha.env']
    assert 'REVOKE ALL ON DATABASE fi_alpha FROM PUBLIC' in first['00-create-alpha.sql']
    assert 'REVOKE INSERT, UPDATE, DELETE ON tenant_identity' in first['01-grants-alpha.sql']
    assert 'REVOKE UPDATE, DELETE ON audit_logs' in first['01-grants-alpha.sql']
    assert 'REVOKE UPDATE, DELETE ON correction_events' in first['01-grants-alpha.sql']
    assert 'ReadWritePaths=/var/lib/fire-ai/alpha' in first['fire-ai-alpha.service']
    assert '/var/lib/fire-ai/beta' not in first['fire-ai-alpha.service']
    assert '127.0.0.1:8101' in first['nginx-alpha.conf']
    assert '127.0.0.1:8102' in second['nginx-beta.conf']
    assert 'FIRE_AI_TENANT_ID=' in first['alpha.env']
    assert 'FIRE_AI_PRODUCTION_MODE=true' in first['alpha.env']
    assert 'OnCalendar=*-*-* 03:00:00 Asia/Tokyo' in first['fire-ai-alpha-backup.timer']
    assert '--slug alpha --release-id release-20261006' in first['fire-ai-alpha-backup.service']
    assert '/etc/fire-ai/backup-alpha.env' in first['fire-ai-alpha-backup.service']
    assert 'User=root' in first['fire-ai-alpha-backup.service']
    assert 'FIRE_AI_BACKUP_WRITER_UNITS=' in first['backup-alpha.env']
    assert 'FIRE_AI_BACKUP_ENCRYPTION_REQUIRED=true' in first['backup-alpha.env']
    assert 'FIRE_AI_BACKUP_RECIPIENT_PUBLIC_KEY=/etc/fire-ai/keys/alpha-backup-recipient.pem' in first['backup-alpha.env']
    assert 'ReadOnlyPaths=/etc/fire-ai/keys/alpha-backup-recipient.pem' in first['fire-ai-alpha-backup.service']


@pytest.mark.parametrize('field,value', [('slug','alpha; DROP DATABASE'),('slug','../beta'),
    ('host','alpha; malicious'), ('host','*'),('port',80),('release_id','../main'),('tenant_id','invalid')])
def test_generator_rejects_injection_or_ambiguous_target(field,value):
    from app.tenant_deployment import render_department
    args = parameters();args[field] = value
    with pytest.raises(ValueError): render_department(**args)


def test_optional_audit_is_off_by_default_without_an_uninstalled_backup_dependency():
    import json
    from app.tenant_deployment import render_department
    assets = render_department(**parameters())
    for name in ('alpha.env', 'migration-alpha.env', 'backup-alpha.env'):
        values = environment_values(assets[name])
        assert values['FIRE_AI_EMERGENCY_AUDIT_ENABLED'] == 'false'
        assert values['FIRE_AI_EMERGENCY_AUDIT_INTERNAL_ENABLED'] == 'false'
        assert values['FIRE_AI_EMERGENCY_AUDIT_AI_MODEL'] == ''
    assert 'fire-ai-alpha-emergency-audit-worker.service' not in assets
    assert json.loads(environment_values(assets['backup-alpha.env'])['FIRE_AI_BACKUP_WRITER_UNITS']) == []
    assert 'emergency-audit' not in assets['fire-ai-alpha.service']


def test_enabled_audit_generates_isolated_worker_and_api_temp_areas_without_secrets_or_model_downloads():
    import json
    from app.tenant_deployment import render_department
    args = parameters(); assets = render_department(**args, emergency_audit=True)
    values = environment_values(assets['alpha.env'])
    assert values['FIRE_AI_EMERGENCY_AUDIT_ENABLED'] == 'true'
    assert values['FIRE_AI_EMERGENCY_AUDIT_INTERNAL_ENABLED'] == 'false'
    assert values['FIRE_AI_EMERGENCY_AUDIT_KEY_FILE'] == '/etc/fire-ai/keys/alpha-emergency-audit/audit.key'
    assert values['FIRE_AI_EMERGENCY_AUDIT_NATIVE_MANIFEST'] == '/etc/fire-ai/alpha-emergency-audit-native.json'
    assert values['FIRE_AI_EMERGENCY_AUDIT_OCR_LANGUAGE'] == 'jpn+eng'
    assert values['FIRE_AI_EMERGENCY_AUDIT_AI_MODEL'] == ''
    assert values['FIRE_AI_EMERGENCY_AUDIT_AI_PORT'] == '11434'
    assert values['FIRE_AI_EMERGENCY_AUDIT_WORKER_TIMEOUT'] == '600'
    assert json.loads(environment_values(assets['backup-alpha.env'])['FIRE_AI_BACKUP_WRITER_UNITS']) == [
        'fire-ai-alpha-emergency-audit-worker.service']
    worker = assets['fire-ai-alpha-emergency-audit-worker.service']; api = assets['fire-ai-alpha.service']
    assert 'User=fireai_alpha\nGroup=fireai_alpha' in worker
    assert 'WorkingDirectory=/opt/fire-ai/releases/release-20261006' in worker
    assert 'EnvironmentFile=/etc/fire-ai/alpha.env' in worker
    assert 'RuntimeDirectory=fire-ai-alpha-emergency-audit-worker\nRuntimeDirectoryMode=0700' in worker
    assert 'Environment=TMPDIR=/run/fire-ai-alpha-emergency-audit-worker' in worker
    assert 'ReadWritePaths=/var/lib/fire-ai/alpha /run/fire-ai-alpha-emergency-audit-worker' in worker
    assert 'ExecStartPre=/opt/fire-ai/instances/alpha/venv/bin/python /opt/fire-ai/releases/release-20261006/scripts/check_emergency_audit_host.py' in worker
    assert 'ExecStart=/opt/fire-ai/instances/alpha/venv/bin/python /opt/fire-ai/releases/release-20261006/scripts/run_emergency_audit_worker.py' in worker
    assert 'KillMode=control-group' in worker and 'UMask=0077' in worker
    assert 'RuntimeDirectory=fire-ai-alpha-emergency-audit-api\nRuntimeDirectoryMode=0700' in api
    assert 'Environment=TMPDIR=/run/fire-ai-alpha-emergency-audit-api' in api
    assert 'check_emergency_audit_host.py' not in api  # OCR readiness must not block ordinary CRUD startup.
    assert '--initialize-key' not in worker
    assert 'download' not in worker and 'ollama pull' not in worker
    assert not any(name.endswith(('.key', '.pem', '.traineddata', '.gguf')) for name in assets)
    second_args = parameters(); second_args.update(slug='beta', host='beta.fire.internal', port=8102)
    second = render_department(**second_args, emergency_audit=True)
    assert 'alpha' not in second['fire-ai-beta-emergency-audit-worker.service']
    assert 'beta' not in worker


@pytest.mark.parametrize('enabled,worker_active', [(False, False), (True, False), (True, True)])
def test_generated_optional_writer_list_obeys_real_backup_stop_and_restore_contract(tmp_path, enabled, worker_active):
    import json
    from app.scheduled_backup import run_scheduled_backup
    from app.tenant_deployment import render_department
    args = parameters(); assets = render_department(**args, emergency_audit=enabled)
    writers = json.loads(environment_values(assets['backup-alpha.env'])['FIRE_AI_BACKUP_WRITER_UNITS'])
    app = 'fire-ai-alpha.service'; worker = 'fire-ai-alpha-emergency-audit-worker.service'
    active = {app, worker} if worker_active else {app}
    initial = active.copy(); operations = []
    def control(action, unit):
        # A registered-but-uninstalled worker fails in actual systemd_control.
        # Default generated deployment must never refer to such a unit.
        assert unit in assets
        operations.append((action, unit))
        if action == 'is-active': return unit in active
        if action == 'stop': active.discard(unit)
        if action == 'start': active.add(unit)
        return True
    def backup():
        assert active == set()
        operations.append(('backup', None))
        return 'synthetic-backup-complete'
    result = run_scheduled_backup(slug='alpha', tenant_id=args['tenant_id'], lock_path=tmp_path / 'backup.lock',
        writer_units=writers, control=control, backup=backup)
    assert result == 'synthetic-backup-complete' and active == initial
    assert (('stop', worker) in operations) is enabled
    assert (('start', worker) in operations) is worker_active
    if enabled:
        assert operations.index(('stop', worker)) < operations.index(('stop', app)) < operations.index(('backup', None))


@pytest.mark.parametrize('value', ['false', 'true', 1, None])
def test_optional_audit_requires_an_explicit_boolean(value):
    from app.tenant_deployment import render_department
    with pytest.raises(ValueError):
        render_department(**parameters(), emergency_audit=value)


@pytest.mark.parametrize('enabled', [False, True])
def test_generation_cli_explicit_audit_flag_writes_only_reviewable_assets(tmp_path, monkeypatch, capsys, enabled):
    import importlib.util
    import sys
    from pathlib import Path
    path = Path(__file__).resolve().parents[2] / 'scripts' / 'generate_department_config.py'
    spec = importlib.util.spec_from_file_location('synthetic_department_generation', path)
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    args = parameters(); destination = tmp_path / 'reviewable'
    command = [str(path), '--slug', args['slug'], '--tenant-id', args['tenant_id'], '--host', args['host'],
        '--port', str(args['port']), '--release-id', args['release_id'], '--output', str(destination)]
    if enabled: command.append('--emergency-audit')
    monkeypatch.setattr(sys, 'argv', command)
    module.main()
    values = environment_values((destination / 'alpha.env').read_text())
    assert values['FIRE_AI_EMERGENCY_AUDIT_ENABLED'] == str(enabled).lower()
    assert values['FIRE_AI_EMERGENCY_AUDIT_INTERNAL_ENABLED'] == 'false'
    assert (destination / 'fire-ai-alpha-emergency-audit-worker.service').exists() is enabled
    assert all(file.stat().st_mode & 0o777 == 0o600 for file in destination.iterdir())
    assert not list(destination.rglob('*.key')) and not list(destination.rglob('*.traineddata'))
    assert 'no server was modified' in capsys.readouterr().out


def test_postgresql_dedicated_roles_deny_other_database_and_identity_mutation(tmp_path):
    import os
    url = os.environ.get('FIRE_AI_TEST_POSTGRES_URL')
    if not url: pytest.skip('PostgreSQL role service is exercised in CI')
    from pathlib import Path
    from sqlalchemy import create_engine, text
    from sqlalchemy.engine import make_url
    from sqlalchemy.exc import DBAPIError
    from app.migrations import apply_migrations, split_sql
    from app.settings import Settings
    from app.tenant import initialize_tenant, validate_runtime_binding, TenantBoundaryError
    from app.tenant_deployment import render_department
    slugs = ['t' + uuid4().hex[:10] for _ in range(2)]
    admin = create_engine(make_url(url).set(database='postgres'), isolation_level='AUTOCOMMIT')
    engines = []
    try:
        for slug in slugs:
            tenant_id = str(uuid4());password = uuid4().hex
            assets = render_department(slug=slug, tenant_id=tenant_id, host='alpha.test', port=8101, release_id='test-release')
            with admin.connect() as connection:
                for statement in split_sql(assets['00-create-' + slug + '.sql']): connection.exec_driver_sql(statement)
                for suffix in ['owner', 'app']:
                    connection.exec_driver_sql(f"ALTER ROLE fi_{slug}_{suffix} PASSWORD '{password}'")
            owner_url = make_url(url).set(database='fi_' + slug, username='fi_' + slug + '_owner', password=password)
            apply_migrations(owner_url.render_as_string(hide_password=False), Path(__file__).resolve().parents[2] / 'db' / 'migrations')
            owner_engine = create_engine(owner_url);engines.append(owner_engine)
            cfg = Settings(_env_file=None, production_mode=True, tenant_id=tenant_id,
                database_url=owner_url.render_as_string(hide_password=False), cookie_secure=True,
                trusted_hosts=['alpha.test'], storage_root=str(tmp_path / slug))
            initialize_tenant(owner_engine, cfg, 'Synthetic role department')
            with pytest.raises(TenantBoundaryError): validate_runtime_binding(owner_engine, cfg)
            with owner_engine.begin() as connection:
                for statement in split_sql(assets['01-grants-' + slug + '.sql']): connection.exec_driver_sql(statement)
            app_url = owner_url.set(username='fi_' + slug + '_app')
            app_engine = create_engine(app_url);engines.append(app_engine)
            assert validate_runtime_binding(app_engine, cfg)['tenant_id'] == tenant_id
            with app_engine.begin() as connection:
                assert connection.execute(text('SELECT COUNT(*) FROM employees')).scalar_one() == 0
            for statement in ['UPDATE tenant_identity SET name = \'changed\'', 'DELETE FROM audit_logs', "UPDATE learning_artifacts SET task='ocr'", "DELETE FROM learning_transitions", "UPDATE learning_evaluation_sets SET cases='[]'::json", "UPDATE learning_corrections SET input_text='changed'", "UPDATE correction_events SET text='changed'", 'DELETE FROM correction_events', 'TRUNCATE tenant_identity']:
                with pytest.raises(DBAPIError):
                    with app_engine.begin() as connection: connection.exec_driver_sql(statement)
            if slug == slugs[1]:
                other = create_engine(app_url.set(database='fi_' + slugs[0]));engines.append(other)
                with pytest.raises(DBAPIError):
                    with other.connect(): pass
    finally:
        for engine in engines: engine.dispose()
        with admin.connect() as connection:
            for slug in slugs:
                connection.exec_driver_sql(f'DROP DATABASE IF EXISTS fi_{slug} WITH (FORCE)')
                for suffix in ['app', 'owner']:
                    connection.exec_driver_sql(f'DROP ROLE IF EXISTS fi_{slug}_{suffix}')
        admin.dispose()
