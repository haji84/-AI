from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker
from sqlalchemy.pool import StaticPool
from .settings import settings

class Base(DeclarativeBase):
    pass

connect_args = {"check_same_thread": False} if settings.database_url.startswith("sqlite") else {}
engine_kwargs = {"pool_pre_ping": True, "future": True, "connect_args": connect_args}
if settings.database_url == "sqlite+pysqlite:///:memory:":
    engine_kwargs["poolclass"] = StaticPool
engine = create_engine(settings.database_url, **engine_kwargs)
class BoundSession(Session):
    def __init__(self, *args, **kwargs):
        if settings.tenant_id is not None or settings.production_mode:
            from .tenant import validate_runtime_binding
            validate_runtime_binding(kwargs.get("bind", engine), settings)
        super().__init__(*args, **kwargs)

SessionLocal = sessionmaker(class_=BoundSession, bind=engine, expire_on_commit=False, autoflush=False, future=True)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
