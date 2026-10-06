"""Human-selected department policy; no guessed expiry interval."""
from datetime import datetime,timedelta,timezone


def utc(value):
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


def next_password_expiry(changed_at,max_age_days):
    if max_age_days is None:return None
    if not 1<=max_age_days<=3650:raise ValueError('password age must be1..3650 days')
    return utc(changed_at)+timedelta(days=max_age_days)


def password_expired(expires_at,now=None):
    return expires_at is not None and utc(expires_at)<=utc(now or datetime.now(timezone.utc))


def initial_password_dates():
    from .settings import settings
    changed=datetime.now(timezone.utc)
    return {'password_changed_at':changed,'password_expires_at':next_password_expiry(changed,settings.password_max_age_days)}


def password_metadata(user):
    from .settings import settings
    return {'password_changed_at':utc(user.password_changed_at).isoformat(),
        'password_expires_at':utc(user.password_expires_at).isoformat() if user.password_expires_at else None,
        'password_max_age_days':settings.password_max_age_days}
