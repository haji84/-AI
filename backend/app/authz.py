from fastapi import Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session
from .db import get_db
from .models import User, UserSession, UserRole, RolePermission, Permission
from .security import token_digest
from .settings import settings
from .personnel import employee_available, effective_role_ids
from datetime import datetime, timezone

def authenticated_user(request: Request, db: Session = Depends(get_db)) -> User:
    raw = request.cookies.get(settings.cookie_name)
    if not raw:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="not authenticated")
    digest = token_digest(raw)
    session = db.scalar(select(UserSession).where(UserSession.token_hash == digest, UserSession.revoked_at.is_(None)))
    now = datetime.now(timezone.utc)
    if not session:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="session expired")
    expires_at = session.expires_at
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    if expires_at < now:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="session expired")
    user = db.get(User, session.user_id)
    if not user or not user.active or not employee_available(db, user):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="user disabled")
    session.last_seen_at = now
    db.commit()
    return user

def current_user(user: User = Depends(authenticated_user)) -> User:
    from .password_policy import password_expired
    if password_expired(user.password_expires_at):
        raise HTTPException(403,detail={'code':'password_expired','message':'パスワードの有効期限が切れています。更新してください。','renewal_url':'/ui/password.html'},headers={'X-FireAI-Password-Renewal':'required'})
    return user

def permission_codes(db: Session, user_id: str) -> set[str]:
    roles = effective_role_ids(db, user_id)
    if not roles:
        return set()
    query = (select(Permission.code)
             .join(RolePermission, RolePermission.permission_id == Permission.permission_id)
             .where(RolePermission.role_id.in_(roles)))
    return set(db.scalars(query))


def require_permission(code: str):
    def dependency(user: User = Depends(current_user), db: Session = Depends(get_db)) -> User:
        if code not in permission_codes(db, user.user_id):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=f"missing permission: {code}")
        return user
    return dependency
