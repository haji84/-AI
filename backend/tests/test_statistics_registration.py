"""A fresh headquarters can reach statistics without broadening ordinary roles."""
import os
from pathlib import Path
import subprocess
import sys
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.db import Base
from app.main import app
from app.models import FeatureFlag, ModuleDefinition, Permission, Role, RolePermission
from app.module_seed import seed_modules
from app.rbac_seed import seed_rbac


def test_statistics_registration_preserves_human_role_and_module_choices():
    engine = create_engine('sqlite+pysqlite:///:memory:')
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        roles = seed_rbac(db)
        seed_modules(db)
        commands = {'statistics.read', 'statistics.record', 'statistics.export'}
        permissions = {row.code: row for row in db.scalars(select(Permission))}
        assert commands <= permissions.keys()
        assigned = list(db.execute(select(Role.code, Permission.code).join(RolePermission, RolePermission.role_id == Role.role_id).join(Permission, Permission.permission_id == RolePermission.permission_id).where(Permission.code.in_(commands))))
        assert set(assigned) == {('system_admin', code) for code in commands}
        module = db.scalar(select(ModuleDefinition).where(ModuleDefinition.code == 'statistics'))
        assert module and module.manifest['operational_api'] == '/statistics'
        flag = db.scalar(select(FeatureFlag).where(FeatureFlag.key == 'module.statistics.enabled'))
        assert flag is not None
        flag.enabled = False
        # Human custom roles remain outside the canonical seeded role policy.
        custom = Role(code='synthetic-human-statistics', name='Synthetic custom role', system_role=False)
        db.add(custom)
        db.flush()
        db.add(RolePermission(role_id=custom.role_id, permission_id=permissions['statistics.read'].permission_id))
        db.commit()
        seed_rbac(db)
        seed_modules(db)
        db.commit()
        db.expire_all()
        assert not db.get(FeatureFlag, flag.feature_flag_id).enabled
        human_grant = db.get(RolePermission, (custom.role_id, permissions['statistics.read'].permission_id))
        assert human_grant is not None
        assert not db.get(RolePermission, (roles['operations_reporter'].role_id, permissions['statistics.record'].permission_id))
        assert not db.get(RolePermission, (roles['operations_reporter'].role_id, permissions['statistics.export'].permission_id))
    engine.dispose()


def test_statistics_router_is_available_in_the_actual_application():
    paths = app.openapi()['paths']
    assert 'get' in paths.get('/statistics/metrics', {})
    assert 'post' in paths.get('/statistics/query', {})
    assert 'post' in paths.get('/statistics/reports', {})


def test_fresh_bootstrap_serves_saved_statistics_without_manual_database_setup(tmp_path):
    root = Path(__file__).resolve().parents[2]
    env = {key: value for key, value in os.environ.items() if not key.startswith('FIRE_AI_')}
    env.update(PYTHONPATH=str(root / 'backend'), FIRE_AI_DATABASE_URL='sqlite+pysqlite:///' + str(tmp_path / 'synthetic-statistics.db'),
               FIRE_AI_STORAGE_ROOT=str(tmp_path / 'storage'), FIRE_AI_PRODUCTION_MODE='false', FIRE_AI_STATISTICS_BUSINESS_TIMEZONE='Asia/Tokyo')
    boot = subprocess.run([sys.executable, '-m', 'app.bootstrap', '--username', 'synthetic-statistics-admin',
                           '--display-name', 'Synthetic statistics setup', '--password', 'synthetic-statistics-setup-password'],
                          cwd=root, env=env, capture_output=True, text=True, timeout=30)
    assert boot.returncode == 0, boot.stderr
    script = '''
from fastapi.testclient import TestClient
from app.main import app
with TestClient(app, raise_server_exceptions=False) as client:
    assert client.post('/auth/login', json={'username':'synthetic-statistics-admin','password':'synthetic-statistics-setup-password'}).status_code == 200
    catalog = client.get('/statistics/metrics')
    assert catalog.status_code == 200, catalog.text
    assert catalog.json()['business_timezone'] == 'Asia/Tokyo'
    query = {'start_date':'2026-01-01','end_date':'2026-01-31','metric_keys':[item['key'] for item in catalog.json()['metrics']]}
    saved = client.post('/statistics/reports', json=query)
    assert saved.status_code == 201, saved.text
    report = saved.json()
    assert report['snapshot']['coverage_status'] == 'unknown'
    assert all(item['coverage_status'] == 'unknown' for item in report['snapshot']['metrics'])
    confirmed = client.post('/statistics/reports/' + report['report_id'] + '/confirm', json={'expected_version':report['version'],'acknowledged':True,'review_note':'Synthetic observed zero, coverage unknown'})
    assert confirmed.status_code == 200, confirmed.text
    assert confirmed.json()['snapshot'] == report['snapshot']
    export = client.get('/statistics/reports/' + report['report_id'] + '/export?format=csv')
    assert export.status_code == 200, export.text
    assert '汎用統計出力（正式様式ではありません）' in export.text
    assert client.post('/auth/logout').status_code == 200
    assert client.get('/statistics/reports/' + report['report_id']).status_code == 401
'''
    result = subprocess.run([sys.executable, '-c', script], cwd=root, env=env, capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stderr
