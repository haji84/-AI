"""Explicit preflight → read-only coherent capture → fresh guarded release."""
from contextlib import contextmanager
from dataclasses import dataclass
from sqlalchemy.engine import Engine
from fastapi import HTTPException
from .audit import write_audit
from .authz import current_user, permission_codes, revalidate_session
from .db import BoundSession
from .models import User
from .personnel import account_change_lock, employee_available
from .settings import settings
from .statistics_sources import capture_sources, pin_period, required_permissions, require_workforce_available


@dataclass(frozen=True)
class RequestIdentity:
    engine: Engine
    user_id: str
    session_digest: str


def authorize(db, identity, codes, *, mutation=False):
    db.expire_all()
    if mutation:
        account_change_lock(db)
    db.info['authenticated_session_token_hash'] = identity.session_digest
    revalidate_session(db, identity.user_id)
    user = db.get(User, identity.user_id, populate_existing=True)
    if not user or not user.active or not employee_available(db, user):
        raise HTTPException(403, 'Account is no longer available')
    current_user(user)
    if not set(codes).issubset(permission_codes(db, identity.user_id)):
        raise HTTPException(403, 'Statistics source or command permission is no longer effective')
    if any(code.startswith('workforce.') for code in codes):
        require_workforce_available(db)
    return user


def preflight(db, user, codes):
    digest = db.info.get('authenticated_session_token_hash')
    if not digest:
        raise HTTPException(401, 'Originating session is required')
    bind = db.get_bind()
    engine = bind if isinstance(bind, Engine) else bind.engine
    identity = RequestIdentity(engine, user.user_id, digest)
    authorize(db, identity, codes)
    # Do not carry ORM identity or any already-started authentication transaction into capture.
    db.rollback()
    return identity


@contextmanager
def bound_transaction(identity, *, capture=False):
    # An OptionEngine preserves BoundSession's existing engine-based tenant validation.
    # Its connection options are installed before after_begin's maintenance SELECT.
    engine = identity.engine
    if engine.dialect.name == 'postgresql':
        engine = engine.execution_options(isolation_level='REPEATABLE READ' if capture else 'READ COMMITTED', postgresql_readonly=capture)
    with BoundSession(bind=engine, expire_on_commit=False, autoflush=False) as db:
        try:
            if capture and engine.dialect.name == 'sqlite':
                db.connection().exec_driver_sql('BEGIN')
            yield db
        finally:
            db.rollback()
    # Session close returns its connection to the pool and resets connection options.


def capture_in_snapshot(identity, period, keys):
    with bound_transaction(identity, capture=True) as db:
        return capture_sources(db, period, keys)


@contextmanager
def final_session(identity, codes, *, mutation=False):
    with bound_transaction(identity) as db:
        authorize(db, identity, codes, mutation=mutation)
        yield db


def audit_statistics(db, identity, action, *, report_id=None, version=None, metric_keys=None, format=None):
    # No individual source identifiers, evidence fingerprints, excerpts or review prose.
    metadata = {'metric_keys': metric_keys or [], 'version': version}
    if format:
        metadata['format'] = format
    write_audit(db, user_id=identity.user_id, action='statistics.' + action,
                entity_type='statistics_report', entity_id=report_id, after=metadata)


def query_statistics(db, user, query):
    codes = {'statistics.read'} | required_permissions(query.metric_keys)
    identity = preflight(db, user, codes)
    result = capture_in_snapshot(identity, pin_period(query, settings.statistics_business_timezone), query.metric_keys)
    with final_session(identity, codes) as final:
        audit_statistics(final, identity, 'query', metric_keys=query.metric_keys)
        final.commit()
    return result.public
