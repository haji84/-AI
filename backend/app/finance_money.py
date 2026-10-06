"""Canonical exact decimal binding with PostgreSQL NUMERIC compatibility."""
from decimal import Decimal
from sqlalchemy import Numeric, String
from sqlalchemy.types import TypeDecorator

class ExactMoney(TypeDecorator):
    """Numeric on PostgreSQL; canonical decimal text on SQLite avoids REAL loss."""
    impl = Numeric(18,2)
    cache_ok = True
    def load_dialect_impl(self,dialect):
        return dialect.type_descriptor(String(24) if dialect.name=='sqlite' else Numeric(18,2))
    def process_bind_param(self,value,dialect):
        if value is None:return None
        exact=Decimal(value)
        if not exact.is_finite() or exact!=exact.quantize(Decimal('.01')) or abs(exact)>=Decimal('10000000000000000'):
            raise ValueError('finite exact NUMERIC(18,2) required')
        return format(exact,'.2f') if dialect.name=='sqlite' else exact
    def process_result_value(self,value,dialect):
        return Decimal(str(value)) if value is not None else None

