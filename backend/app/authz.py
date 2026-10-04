from fastapi import Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session
from .db import get_db
from .models import User, UserSession, UserRole, RolePermission, Permission
from .security import token_digest
from .settings import settings
from datetime import datetime, timezone

def current_user(request: Request, db: Session = Depends(get_db)) -> User:
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
    if not user or not user.active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="user disabled")
    session.last_seen_at = now
    db.commit()
    return user

def permission_codes(db: Session, user_id: str) -> set[str]:
    q=(select(Permission.code)
       .join(RolePermission, RolePermission.permission_id == Permission.permission_id)
       .join(UserRole, UserRole.role_id == RolePermission.role_id)
       .where(UserRole.user_id == user_id))
    return set(db.scalars(q).all())

def require_permission(code: str):
    def dependency(user: User = Depends(current_user), db: Session = Depends(get_db)) -> User:
        if code not in permission_codes(db, user.user_id):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=f"missing permission: {code}")
        return user
    return dependency
