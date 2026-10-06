"""Server-selected department identity; HTTP clients never select a database."""
import json
import os
from pathlib import Path
from uuid import UUID

from sqlalchemy import CheckConstraint, String, Integer, MetaData, Table, inspect, select, text
from sqlalchemy.orm import Mapped, mapped_column
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse
from starlette.concurrency import run_in_threadpool

from .db import Base


class TenantBoundaryError(RuntimeError):
    pass


class TenantIdentity(Base):
    __tablename__ = 'tenant_identity'
    __table_args__ = (CheckConstraint('singleton_id = 1', name='tenant_identity_singleton'),)
    singleton_id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)
    tenant_id: Mapped[str] = mapped_column(String(36), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)


def _paths(config):
    root = Path(config.storage_root).absolute()
    if root.is_symlink():
        raise TenantBoundaryError('Storage root must not be a symbolic link')
    return root, root / 'tenant-identity.json'


def _marker(marker, expected):
    if marker.is_symlink():
        raise TenantBoundaryError('Invalid storage identity')
    if not marker.exists():
        return False
    try:
        value = json.loads(marker.read_text(encoding='utf-8'))
        if str(UUID(value['tenant_id'])) != expected:
            raise ValueError('mismatch')
    except (OSError, ValueError, KeyError, TypeError):
        raise TenantBoundaryError('Storage identity does not match configured department') from None
    return True


def validate_binding(engine, config):
    if config.tenant_id is None and not config.production_mode:
        return None
    try:
        with engine.connect() as connection:
            identity = connection.execute(select(TenantIdentity.tenant_id).where(TenantIdentity.singleton_id == 1)).scalar_one_or_none()
        if identity != config.tenant_id:
            raise TenantBoundaryError('Database identity does not match configured department')
        _, marker = _paths(config)
        if not _marker(marker, config.tenant_id):
            raise TenantBoundaryError('Storage identity is not initialized')
        return {'tenant_id': identity}
    except TenantBoundaryError:
        raise
    except Exception:
        raise TenantBoundaryError('Department binding could not be verified') from None


def validate_runtime_binding(engine, config):
    result = validate_binding(engine, config)
    if not config.production_mode:
        return result
    try:
        if engine.dialect.name != 'postgresql':
            raise TenantBoundaryError('Production runtime requires PostgreSQL')
        with engine.connect() as connection:
            flags = connection.execute(text("SELECT rolsuper, rolcreatedb, rolcreaterole, rolbypassrls FROM pg_roles WHERE rolname = current_user")).one()
            if any(flags):
                raise TenantBoundaryError('Privileged PostgreSQL role is forbidden for application runtime')
            mutable_identity = connection.execute(text("SELECT has_table_privilege(current_user, 'public.tenant_identity', 'INSERT,UPDATE,DELETE,TRUNCATE')")).scalar_one()
            mutable_audit = connection.execute(text("SELECT has_table_privilege(current_user, 'public.audit_logs', 'UPDATE,DELETE,TRUNCATE')")).scalar_one()
            if mutable_identity or mutable_audit:
                raise TenantBoundaryError('Runtime role must not modify department identity or existing audit records')
        return result
    except TenantBoundaryError:
        raise
    except Exception:
        raise TenantBoundaryError('Runtime database privileges could not be verified') from None


def initialize_tenant(engine, config, name, adopt_existing=False):
    if not config.tenant_id or not name.strip() or len(name) > 200:
        raise TenantBoundaryError('Configured department UUID and name are required')
    root, marker = _paths(config)
    marked = _marker(marker, config.tenant_id)
    created_marker = False
    try:
        with engine.begin() as connection:
            if engine.dialect.name == 'postgresql':
                connection.execute(text("SELECT pg_advisory_xact_lock(hashtext('fire-ai-tenant-initialization'))"))
            identity = connection.execute(select(TenantIdentity.tenant_id).where(TenantIdentity.singleton_id == 1)).scalar_one_or_none()
            if identity is not None and identity != config.tenant_id:
                raise TenantBoundaryError('Database already belongs to another department')
            if identity is None and not adopt_existing:
                for table_name in inspect(connection).get_table_names():
                    if table_name not in {'tenant_identity', 'schema_migrations', 'permissions'}:
                        table = Base.metadata.tables.get(table_name)
                        if table is None:
                            table = Table(table_name, MetaData(), autoload_with=connection)
                        if connection.execute(select(table).limit(1)).first() is not None:
                            raise TenantBoundaryError('Existing database requires explicit adoption')
            if not marked and root.exists() and any(root.iterdir()) and not adopt_existing:
                raise TenantBoundaryError('Existing originals require explicit adoption')
            root.mkdir(parents=True, exist_ok=True, mode=0o700)
            if not marked:
                try:
                    descriptor = os.open(marker, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
                except FileExistsError:
                    _marker(marker, config.tenant_id)
                else:
                    created_marker = True
                    with os.fdopen(descriptor, 'w', encoding='utf-8') as stream:
                        json.dump({'tenant_id': config.tenant_id}, stream)
                        stream.flush()
                        os.fsync(stream.fileno())
            if identity is None:
                connection.execute(TenantIdentity.__table__.insert().values(singleton_id=1, tenant_id=config.tenant_id, name=name.strip()))
                from .models import AuditLog
                connection.execute(AuditLog.__table__.insert().values(
                    action='tenant.initialize', entity_type='tenant', entity_id=config.tenant_id,
                    user_id=None, success=True, ai_used=False,
                    after_data={'tenant_id': config.tenant_id, 'name': name.strip(), 'adopt_existing': adopt_existing}))
    except Exception:
        if created_marker:
            marker.unlink(missing_ok=True)
        raise
    return validate_binding(engine, config)


class TenantBoundaryMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, engine, config):
        super().__init__(app)
        self.engine, self.config = engine, config

    async def dispatch(self, request, call_next):
        if self.config.tenant_id is not None:
            hosts = request.headers.getlist('host')
            try:
                hostname = request.url.hostname
            except ValueError:
                hostname = None
            if len(hosts) != 1 or hostname not in self.config.trusted_hosts:
                return JSONResponse({'detail': 'Unrecognized department host'}, status_code=421)
            try:
                await run_in_threadpool(validate_runtime_binding, self.engine, self.config)
            except TenantBoundaryError:
                return JSONResponse({'detail': 'Department binding unavailable'}, status_code=503)
        return await call_next(request)
