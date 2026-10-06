import pytest
from uuid import uuid4


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


@pytest.mark.parametrize('field,value', [('slug','alpha; DROP DATABASE'),('slug','../beta'),
    ('host','alpha; malicious'), ('host','*'),('port',80),('release_id','../main'),('tenant_id','invalid')])
def test_generator_rejects_injection_or_ambiguous_target(field,value):
    from app.tenant_deployment import render_department
    args = parameters();args[field] = value
    with pytest.raises(ValueError): render_department(**args)


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
            for statement in ['UPDATE tenant_identity SET name = \'changed\'', 'DELETE FROM audit_logs', 'TRUNCATE tenant_identity']:
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
