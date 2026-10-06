"""The supported initial setup must initialize the complete administration surface."""
import os
from pathlib import Path
import subprocess
import sys


def test_fresh_bootstrap_serves_department_context_and_human_role_registry(tmp_path):
    root=Path(__file__).resolve().parents[2]
    env={**os.environ,'PYTHONPATH':str(root/'backend'),'FIRE_AI_DATABASE_URL':'sqlite+pysqlite:///'+str(tmp_path/'synthetic-bootstrap.db'),'FIRE_AI_STORAGE_ROOT':str(tmp_path/'storage'),'FIRE_AI_PRODUCTION_MODE':'false'}
    env.pop('FIRE_AI_TENANT_ID',None)
    subprocess.run([sys.executable,'-m','app.bootstrap','--username','bootstrap-human','--display-name','Synthetic setup administrator','--password','synthetic-bootstrap-password'],cwd=root,env=env,check=True,capture_output=True)
    script="""
from app.main import app
from fastapi.testclient import TestClient
with TestClient(app,raise_server_exceptions=False) as client:
    assert client.post('/auth/login',json={'username':'bootstrap-human','password':'synthetic-bootstrap-password'}).status_code==200
    for route in ['/administration/context','/administration/own-role-explanation','/administration/permissions','/administration/permission-roles']:
        result=client.get(route)
        assert result.status_code==200,(route,result.status_code,result.text)
"""
    result=subprocess.run([sys.executable,'-c',script],cwd=root,env=env,capture_output=True,text=True,timeout=30)
    assert result.returncode==0,result.stderr
