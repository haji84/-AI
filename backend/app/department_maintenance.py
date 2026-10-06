"""PostgreSQL exclusion for runtime transactions and explicit server maintenance."""
from contextlib import contextmanager
from uuid import UUID
from sqlalchemy import create_engine,inspect,text


class MaintenanceUnavailable(RuntimeError):
    pass


def lock_key(tenant_id):return 'fire-ai-department-maintenance:'+str(UUID(tenant_id))


def acquire_runtime_lock(connection,tenant_id):
    acquired=connection.execute(text('SELECT pg_try_advisory_xact_lock_shared(hashtext(:key))'),{'key':lock_key(tenant_id)}).scalar_one()
    if not acquired:
        # after_begin has already created a SessionTransaction. Raising alone
        # permits a caught exception to reuse it without running this event again.
        connection.invalidate()
        raise MaintenanceUnavailable('Department is under maintenance')


@contextmanager
def exclusive_maintenance(database_url,tenant_id,*,allow_uninitialized=False):
    if not database_url.startswith('postgresql'):raise ValueError('department maintenance requires PostgreSQL')
    key=lock_key(tenant_id);engine=create_engine(database_url,pool_pre_ping=True)
    connection=None;acquired=False
    try:
        connection=engine.connect()
        identity=None
        if inspect(connection).has_table('tenant_identity'):
            identity=connection.execute(text('SELECT tenant_id FROM tenant_identity WHERE singleton_id=1')).scalar_one_or_none()
        if identity is None and not allow_uninitialized:raise ValueError('initialized target department required')
        if identity is not None and str(identity)!=str(UUID(tenant_id)):raise ValueError('maintenance target department mismatch')
        acquired=connection.execute(text('SELECT pg_try_advisory_lock(hashtext(:key))'),{'key':key}).scalar_one()
        connection.commit()
        if not acquired:raise MaintenanceUnavailable('Active writers or another maintenance operation prevent maintenance')
        yield connection
    finally:
        try:
            if connection is not None:
                try:
                    connection.rollback()
                    if acquired:
                        connection.execute(text('SELECT pg_advisory_unlock(hashtext(:key))'),{'key':key})
                        connection.commit()
                finally:
                    connection.close()
        finally:
            engine.dispose()
