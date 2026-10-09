"""Fresh installation must work without create_all after importing the app."""
import os
from pathlib import Path
import subprocess
import sys


def test_fresh_bootstrap_registers_personnel_original_and_candidate_tables(tmp_path):
    root = Path(__file__).resolve().parents[2]
    env = {key: value for key, value in os.environ.items() if not key.startswith('FIRE_AI_')}
    env.update(PYTHONPATH=str(root / 'backend'), FIRE_AI_DATABASE_URL='sqlite+pysqlite:///' + str(tmp_path / 'synthetic-notice.db'),
        FIRE_AI_STORAGE_ROOT=str(tmp_path / 'storage'), FIRE_AI_PRODUCTION_MODE='false')
    boot = subprocess.run([sys.executable, '-m', 'app.bootstrap', '--username', 'synthetic-notice-bootstrap',
        '--display-name', 'Synthetic notice setup', '--password', 'synthetic-notice-bootstrap-password'],
        cwd=root, env=env, capture_output=True, text=True, timeout=30)
    assert boot.returncode == 0, boot.stderr
    # Reuse the same synthetic source fixture as the failing canonical browser.
    from test_hazardous_browser import SEED
    seed = SEED.replace('hazardous-browser', 'synthetic-notice-bootstrap').replace(
        'synthetic-hazardous-password', 'synthetic-notice-bootstrap-password')
    sources = subprocess.run([sys.executable, '-c', seed], cwd=root, env=env,
        capture_output=True, text=True, timeout=30)
    assert sources.returncode == 0, sources.stderr
    script = '''
import json
from sqlalchemy import inspect
from fastapi.testclient import TestClient
from app.main import app
from app.db import engine
assert 'personnel_document_proposals' in inspect(engine).get_table_names(), 'bootstrap omitted personnel candidate table'
assert 'hazardous_rule_approvals' in inspect(engine).get_table_names(), 'bootstrap omitted hazardous approval evidence table'
with TestClient(app, raise_server_exceptions=False) as client:
    assert client.post('/auth/login', json={'username':'synthetic-notice-bootstrap','password':'synthetic-notice-bootstrap-password'}).status_code == 200
    legal = client.get('/hazardous/sources/legal')
    assert legal.status_code == 200, legal.text
    assert any(row['label'].startswith('Synthetic hazardous legal source') for row in legal.json()), legal.text
    source = json.dumps({'employee_code':'UNKNOWN','organization_code':'UNKNOWN','title':'UNKNOWN','kind':'primary','valid_from':'2026-11-01','mode':'transfer'})
    uploaded = client.post('/documents/upload', data={'document_type':'personnel_notice'}, files={'file':('synthetic-notice.txt',source.encode(),'text/plain')})
    assert uploaded.status_code == 201, uploaded.text
    identity = uploaded.json()['document_id']
    original = client.get('/documents/' + identity)
    assert original.status_code == 200, original.text
    created = client.post('/personnel-intake/proposals', json={'document_id':identity})
    assert created.status_code == 201, created.text
    row = created.json()
    assert row['status'] == 'candidate' and row['errors']
    assert row['source_document_id'] == identity
    listed = client.get('/personnel-intake/proposals')
    assert listed.status_code == 200 and len(listed.json()) == 1, listed.text
'''
    result = subprocess.run([sys.executable, '-c', script], cwd=root, env=env, capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stderr
