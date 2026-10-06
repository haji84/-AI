"""Known-secret renewal, Human policy and expiry enforcement on real sessions."""
from datetime import datetime,timedelta,timezone
import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session
from test_learning import learning_environment


@pytest.fixture
def expiry_environment(learning_environment):
    from app.routers import administration
    client,engine=learning_environment
    client.app.include_router(administration.router)
    return client,engine


def expire(engine):
    from app.models import User
    with Session(engine) as db:
        user=db.scalar(select(User).where(User.username=='learning-admin'))
        user.password_expires_at=datetime.now(timezone.utc)-timedelta(seconds=1)
        db.commit()
        return user.user_id


def test_expiry_stops_existing_session_but_allows_known_secret_renewal(expiry_environment):
    client,engine=expiry_environment
    from fastapi.testclient import TestClient
    second=TestClient(client.app)
    assert second.post('/auth/login',json={'username':'learning-admin','password':'synthetic-learning-password'}).status_code==200
    identity=expire(engine)
    response=client.get('/learning/context')
    assert response.status_code==403,response.text
    assert response.json()['detail']['code']=='password_expired'
    assert response.headers['X-FireAI-Password-Renewal']=='required'
    assert client.get('/auth/permissions').status_code==403
    own=client.get('/auth/me');assert own.status_code==200
    assert own.json()['password_change_required'] is True
    assert client.post('/administration/password',json={'current_password':'wrong','new_password':'synthetic-renewed-password'}).status_code==401
    changed=client.post('/administration/password',json={'current_password':'synthetic-learning-password','new_password':'synthetic-renewed-password'})
    assert changed.status_code==200,changed.text
    assert client.get('/auth/me').status_code==401
    assert second.get('/auth/me').status_code==401
    second.close()
    logged=client.post('/auth/login',json={'username':'learning-admin','password':'synthetic-renewed-password'})
    assert logged.status_code==200 and logged.json()['password_change_required'] is False
    assert client.get('/learning/context').status_code==200


def test_expired_login_is_restricted_and_logout_remains_available(expiry_environment):
    client,engine=expiry_environment;expire(engine)
    client.cookies.clear()
    logged=client.post('/auth/login',json={'username':'learning-admin','password':'synthetic-learning-password'})
    assert logged.status_code==200,logged.text
    assert logged.json()['password_change_required'] is True
    assert client.get('/administration/accounts').status_code==403
    assert client.post('/auth/logout').status_code==200
    assert client.get('/auth/me').status_code==401


def test_department_policy_is_optional_bounded_and_uses_actual_change_time():
    from app.password_policy import next_password_expiry,password_expired
    from app.settings import Settings
    changed=datetime(2026,1,1,tzinfo=timezone.utc)
    assert next_password_expiry(changed,None) is None
    assert next_password_expiry(changed,30)==changed+timedelta(days=30)
    assert password_expired(changed,changed) is True
    for days in [0,-1,3651]:
        with pytest.raises(ValueError):Settings(password_max_age_days=days,_env_file=None)


def target_account(engine):
    from app.models import Employee,User
    from app.security import hash_password
    with Session(engine) as db:
        staff=Employee(display_name='Synthetic expiry target');db.add(staff);db.flush()
        user=User(employee_id=staff.employee_id,username='expiry-target',password_hash=hash_password('synthetic-target-password'))
        db.add(user);db.commit();return user.user_id


def test_human_expiry_setting_requires_cas_reason_and_traceable_policy(expiry_environment,monkeypatch):
    from app.models import User,AuditLog
    from app.settings import settings
    client,engine=expiry_environment;identity=target_account(engine)
    changed=datetime.now(timezone.utc)-timedelta(days=10)
    with Session(engine) as db:db.get(User,identity).password_changed_at=changed;db.commit()
    monkeypatch.setattr(settings,'password_max_age_days',30)
    path='/administration/accounts/'+identity+'/password-expiry'
    response=client.post(path,json={'expected_version':1,'mode':'policy','reason':'Human department policy approval'})
    assert response.status_code==200,response.text
    value=response.json();assert value['version']==2
    assert abs((datetime.fromisoformat(value['password_expires_at'])-(changed+timedelta(days=30))).total_seconds())<1
    assert client.post(path,json={'expected_version':1,'mode':'clear','reason':'stale'}).status_code==409
    assert client.post(path,json={'expected_version':2,'mode':'clear','reason':' '}).status_code==422
    assert client.post(path,json={'expected_version':2,'mode':'explicit','expires_at':'2027-01-01T00:00:00','reason':'missing time zone'}).status_code==422
    assert client.post(path,json={'expected_version':2,'mode':'clear','reason':'Human clear approval'}).json()['password_expires_at'] is None
    with Session(engine) as db:
        events=db.scalars(select(AuditLog).where(AuditLog.action=='account.password.expiry')).all()
        assert len(events)==2 and 'synthetic-target-password' not in str([e.after_data for e in events])


def test_password_reset_uses_configured_policy_and_revokes_every_session(expiry_environment,monkeypatch):
    from app.models import UserSession
    from app.security import new_session_token,session_expiry
    from app.settings import settings
    client,engine=expiry_environment;identity=target_account(engine)
    with Session(engine) as db:
        for _ in range(2):
            _,digest=new_session_token();db.add(UserSession(user_id=identity,token_hash=digest,expires_at=session_expiry(12)))
        db.commit()
    monkeypatch.setattr(settings,'password_max_age_days',45)
    response=client.post('/administration/accounts/'+identity+'/password-reset',json={'expected_version':1,'new_password':'synthetic-reset-new-password','reason':'Human verified reset'})
    assert response.status_code==200,response.text
    record=next(x for x in client.get('/administration/accounts').json() if x['user_id']==identity)
    assert record.get('password_changed_at') and record.get('password_expires_at'),record
    assert datetime.fromisoformat(record['password_expires_at'])-datetime.fromisoformat(record['password_changed_at'])==timedelta(days=45)
    with Session(engine) as db:assert all(s.revoked_at is not None for s in db.scalars(select(UserSession).where(UserSession.user_id==identity)))


def test_disabled_employee_cannot_use_expired_credential_renewal(expiry_environment):
    from app.models import User,Employee
    client,engine=expiry_environment;identity=expire(engine)
    with Session(engine) as db:db.get(Employee,db.get(User,identity).employee_id).active=False;db.commit()
    assert client.get('/auth/me').status_code==403
    assert client.post('/administration/password',json={'current_password':'synthetic-learning-password','new_password':'synthetic-renewed-password'}).status_code==403
    assert client.post('/auth/login',json={'username':'learning-admin','password':'synthetic-learning-password'}).status_code==401


def test_human_mutation_rechecks_expiry_after_account_lock(expiry_environment,monkeypatch):
    from app.routers import administration
    from app.models import User
    client,_=expiry_environment;original=administration.account_change_lock
    def locked_expiry(db):
        original(db)
        user=db.scalar(select(User).where(User.username=='learning-admin'))
        user.password_expires_at=datetime.now(timezone.utc)-timedelta(seconds=1);db.flush()
    monkeypatch.setattr(administration,'account_change_lock',locked_expiry)
    response=client.post('/administration/staff',json={'employee_code':'EXPIRED','display_name':'Synthetic expired write'})
    assert response.status_code==403,response.text
    assert response.json()['detail']['code']=='password_expired'


def test_learning_human_gate_rechecks_expiry_after_lock(expiry_environment,monkeypatch):
    from app.routers import learning
    from app.models import User
    client,_=expiry_environment;original=learning.account_change_lock
    def locked_expiry(db):
        original(db)
        db.scalar(select(User).where(User.username=='learning-admin')).password_expires_at=datetime.now(timezone.utc)-timedelta(seconds=1);db.flush()
    monkeypatch.setattr(learning,'account_change_lock',locked_expiry)
    response=client.post('/learning/corrections',json={'task':'ocr','synthetic':True,'input_text':'old','output_text':'new','reason':'Synthetic expired mutation'})
    assert response.status_code==403,response.text


def test_migration_backfill_uses_current_hash_history_and_preserves_legacy_credentials():
    from pathlib import Path
    from sqlalchemy import create_engine,text
    from app.migrations import split_sql
    engine=create_engine('sqlite:///:memory:')
    statements=split_sql((next((Path(__file__).resolve().parents[2]/'db/migrations').glob('*_password_expiry.sql'))).read_text())
    backfill=next(s for s in statements if s.lstrip().startswith('UPDATE app_users'))
    with engine.begin() as db:
        db.execute(text('CREATE TABLE app_users(user_id TEXT, password_hash TEXT, created_at TEXT, password_changed_at TEXT, password_expires_at TEXT)'))
        db.execute(text('CREATE TABLE account_password_history(user_id TEXT,password_hash TEXT,changed_at TEXT)'))
        db.execute(text("INSERT INTO app_users VALUES('known','current-hash','2020-01-01',NULL,NULL),('legacy','legacy-hash','2021-01-01',NULL,NULL)"))
        db.execute(text("INSERT INTO account_password_history VALUES('known','current-hash','2025-01-01'),('known','different-hash','2026-01-01')"))
        db.execute(text(backfill))
        rows=db.execute(text('SELECT user_id,password_hash,password_changed_at,password_expires_at FROM app_users ORDER BY user_id')).all()
        assert rows==[('known','current-hash','2025-01-01',None),('legacy','legacy-hash','2021-01-01',None)]
    engine.dispose()


def test_postgresql_migration_preserves_existing_hash_and_uses_matching_history(tmp_path):
    import os
    from pathlib import Path
    from uuid import uuid4
    from sqlalchemy import create_engine,text
    from sqlalchemy.engine import make_url
    from app.migrations import apply_migrations
    base=os.environ.get('FIRE_AI_TEST_POSTGRES_URL')
    if not base:pytest.skip('real PostgreSQL legacy password migration executes in CI')
    name='fi_expiry_'+uuid4().hex[:16];cluster=create_engine(make_url(base).set(database='postgres'),isolation_level='AUTOCOMMIT');engine=None
    with cluster.connect() as db:db.exec_driver_sql('CREATE DATABASE '+name)
    try:
        target=make_url(base).set(database=name).render_as_string(hide_password=False)
        migrations=Path(__file__).resolve().parents[2]/'db/migrations'
        before=tmp_path/'before';before.mkdir();expiry=next(migrations.glob('*_password_expiry.sql'))
        for path in sorted(migrations.glob('*.sql')):
            if path.name<expiry.name:(before/path.name).write_bytes(path.read_bytes())
        apply_migrations(target,before);engine=create_engine(target)
        identity=str(uuid4());history=str(uuid4());created=datetime(2020,1,1,tzinfo=timezone.utc);changed=datetime(2025,1,1,tzinfo=timezone.utc)
        with engine.begin() as db:
            db.execute(text('INSERT INTO app_users(user_id,username,password_hash,created_at) VALUES(:id,:name,:hash,:created)'),{'id':identity,'name':'synthetic-legacy','hash':'synthetic-credential-hash','created':created})
            db.execute(text('INSERT INTO account_password_history(history_id,user_id,password_hash,changed_at) VALUES(:id,:user,:hash,:changed)'),{'id':history,'user':identity,'hash':'synthetic-credential-hash','changed':changed})
        apply_migrations(target,migrations)
        with engine.connect() as db:
            row=db.execute(text('SELECT password_hash,password_changed_at,password_expires_at FROM app_users WHERE user_id=:id'),{'id':identity}).one()
            assert row[0]=='synthetic-credential-hash' and row[1]==changed and row[2] is None
        assert apply_migrations(target,migrations)==[]
    finally:
        if engine:engine.dispose()
        with cluster.connect() as db:db.exec_driver_sql('DROP DATABASE '+name+' WITH (FORCE)')
        cluster.dispose()
