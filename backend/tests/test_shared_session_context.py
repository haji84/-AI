"""Actual originating sessions provide nonsecret, freshly evaluated authority bindings."""
from datetime import datetime, timedelta, timezone
from sqlalchemy import select
from sqlalchemy.orm import Session
from test_personnel import environment


def test_context_is_no_store_nonsecret_and_distinguishes_same_user_sessions(environment):
 client,engine,roles,app=environment
 from app.models import UserSession
 first=client.get('/auth/context');assert first.status_code==200,first.text
 assert first.headers['Cache-Control']=='no-store'
 data=first.json();assert set(data)=={'user_id','session_id','tenant_id','permissions'}
 assert data['permissions']==sorted(data['permissions']) and 'account.manage' in data['permissions']
 with Session(engine) as db:
  original=db.scalar(select(UserSession).where(UserSession.session_id==data['session_id']))
  assert original and original.user_id==data['user_id']
  assert original.token_hash not in first.text
 assert client.post('/auth/login',json={'username':'admin','password':'synthetic-admin-password'}).status_code==200
 second=client.get('/auth/context').json()
 assert second['user_id']==data['user_id'] and second['session_id']!=data['session_id']


def test_context_tracks_effective_rights_and_rejects_revoked_or_expired_sessions(environment):
 client,engine,roles,app=environment
 from app.models import RolePermission,Permission,UserSession,User
 first=client.get('/auth/context');assert first.status_code==200,first.text
 data=first.json()
 with Session(engine) as db:
  permission=db.scalar(select(Permission).where(Permission.code=='account.manage'))
  grant=db.scalar(select(RolePermission).where(RolePermission.role_id==roles['system_admin'],RolePermission.permission_id==permission.permission_id));db.delete(grant);db.commit()
 second=client.get('/auth/context').json();assert second['session_id']==data['session_id']
 assert 'account.manage' not in second['permissions']
 with Session(engine) as db:
  user=db.get(User,data['user_id']);user.password_expires_at=datetime.now(timezone.utc)-timedelta(seconds=1);db.commit()
 expired=client.get('/auth/context');assert expired.status_code==403
 assert expired.headers['X-FireAI-Password-Renewal']=='required'
 with Session(engine) as db:
  user=db.get(User,data['user_id']);user.password_expires_at=None
  session=db.get(UserSession,data['session_id']);session.revoked_at=datetime.now(timezone.utc);db.commit()
 assert client.get('/auth/context').status_code==401


def test_context_rejects_signed_out_client(environment):
 client,*_=environment;client.cookies.clear()
 assert client.get('/auth/context').status_code==401
