from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session
from ..db import get_db
from ..models import User, UserSession
from ..schemas import LoginRequest, UserOut
from ..security import verify_password, new_session_token, session_expiry, token_digest
from ..settings import settings
from ..authz import current_user, authenticated_user, permission_codes
from ..password_policy import password_expired
from ..audit import write_audit
from ..personnel import employee_available, account_change_lock

router = APIRouter(prefix="/auth", tags=["auth"])

@router.post("/login", response_model=UserOut)
def login(payload: LoginRequest, response: Response, db: Session = Depends(get_db)):
    account_change_lock(db)
    user = db.scalar(select(User).where(User.username == payload.username))
    if not user or not user.active or not employee_available(db, user) or not verify_password(user.password_hash, payload.password):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid credentials")
    expired=password_expired(user.password_expires_at)
    if expired:response.headers['X-FireAI-Password-Renewal']='required'
    raw, digest = new_session_token()
    db.add(UserSession(user_id=user.user_id, token_hash=digest, expires_at=session_expiry(settings.session_hours)))
    user.last_login_at = datetime.now(timezone.utc)
    write_audit(db, user_id=user.user_id, action="auth.login", entity_type="user", entity_id=user.user_id)
    db.commit()
    response.set_cookie(settings.cookie_name, raw, httponly=True, secure=settings.cookie_secure,
                        samesite="strict", max_age=settings.session_hours * 3600, path="/")
    return UserOut(user_id=user.user_id, username=user.username,password_change_required=password_expired(user.password_expires_at),password_expires_at=user.password_expires_at)

@router.post("/logout")
def logout(response: Response, user: User = Depends(authenticated_user), db: Session = Depends(get_db)):
    # Revoke all active sessions for this user in Phase 1. Per-device revoke can be added later.
    sessions=db.scalars(select(UserSession).where(UserSession.user_id == user.user_id, UserSession.revoked_at.is_(None))).all()
    now=datetime.now(timezone.utc)
    for s in sessions: s.revoked_at=now
    write_audit(db, user_id=user.user_id, action="auth.logout", entity_type="user", entity_id=user.user_id)
    db.commit()
    response.delete_cookie(settings.cookie_name, path="/")
    return {"ok": True}

@router.get("/me", response_model=UserOut)
def me(user: User = Depends(authenticated_user)):
    return UserOut(user_id=user.user_id, username=user.username,password_change_required=password_expired(user.password_expires_at),password_expires_at=user.password_expires_at)


@router.get("/permissions")
def permissions(user: User = Depends(current_user), db: Session = Depends(get_db)):
    return {"permissions": sorted(permission_codes(db, user.user_id))}
