import os
from pathlib import Path
import subprocess
import sys
from sqlalchemy import create_engine,text


def invoke(tmp_path,password):
    root=Path(__file__).resolve().parents[2]
    url='sqlite+pysqlite:///'+str(tmp_path/'synthetic-bootstrap.db')
    env={**os.environ,'PYTHONPATH':str(root/'backend'),'FIRE_AI_DATABASE_URL':url,'FIRE_AI_STORAGE_ROOT':str(tmp_path/'storage'),'FIRE_AI_PRODUCTION_MODE':'false'}
    env.pop('FIRE_AI_TENANT_ID',None)
    result=subprocess.run([sys.executable,'-m','app.bootstrap','--username','synthetic-admin','--display-name','Synthetic operator','--password',password],cwd=tmp_path,env=env,capture_output=True,text=True)
    return result,url


def test_bootstrap_rejects_weak_password_before_creating_admin(tmp_path):
    result,_=invoke(tmp_path,'elevenchars')
    assert result.returncode!=0
    assert 'created admin' not in result.stdout


def test_bootstrap_records_initial_password_and_human_audit_without_secrets(tmp_path):
    password='synthetic-strong-bootstrap-password';result,url=invoke(tmp_path,password)
    assert result.returncode==0,result.stderr
    engine=create_engine(url)
    with engine.connect() as db:
        assert db.execute(text('SELECT COUNT(*) FROM account_password_history')).scalar_one()==1
        events=db.execute(text("SELECT after_data FROM audit_logs WHERE action='account.bootstrap'")).all()
        assert len(events)==1
        assert password not in str(events) and 'argon2' not in str(events)
    result,_=invoke(tmp_path,password)
    assert result.returncode!=0
    with engine.connect() as db:assert db.execute(text("SELECT COUNT(*) FROM audit_logs WHERE action='account.bootstrap'")).scalar_one()==1
    engine.dispose()


def test_bootstrap_applies_human_department_password_age_policy(tmp_path,monkeypatch):
    from datetime import datetime,timedelta
    monkeypatch.setenv('FIRE_AI_PASSWORD_MAX_AGE_DAYS','7')
    result,url=invoke(tmp_path,'synthetic-policy-bootstrap-password')
    assert result.returncode==0,result.stderr
    engine=create_engine(url)
    with engine.connect() as db:
        changed,expiry=db.execute(text('SELECT password_changed_at,password_expires_at FROM app_users')).one()
        assert datetime.fromisoformat(expiry)-datetime.fromisoformat(changed)==timedelta(days=7)
        event=db.execute(text("SELECT after_data FROM audit_logs WHERE action='account.bootstrap'")).scalar_one()
        assert 'password_max_age_days' in str(event) and 'synthetic-policy-bootstrap-password' not in str(event)
    engine.dispose()
