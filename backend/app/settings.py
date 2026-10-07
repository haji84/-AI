from pathlib import Path
from uuid import UUID
from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="FIRE_AI_", env_file=".env", extra="ignore")
    database_url: str = "sqlite+pysqlite:///./fire_ai_dev.db"
    session_hours: int = 12
    password_max_age_days: int | None = Field(default=None, ge=1, le=3650)
    cookie_secure: bool = False
    cookie_name: str = "fire_ai_session"
    app_name: str = "消防業務 Local AI"
    storage_root: str = "./runtime/storage"
    production_mode: bool = False
    legal_update_trust_file: str | None = None
    tenant_id: str | None = None
    trusted_hosts: list[str] = []
    statistics_business_timezone: str = "Asia/Tokyo"

    @field_validator("statistics_business_timezone")
    @classmethod
    def statistics_zone(cls, value):
        from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
        try:
            ZoneInfo(value)
        except (ZoneInfoNotFoundError, ValueError) as exc:
            raise ValueError("statistics_business_timezone must name an IANA timezone") from exc
        return value

    @field_validator('tenant_id')
    @classmethod
    def canonical_id(cls, value):
        return str(UUID(value)) if value is not None else None

    @field_validator('trusted_hosts')
    @classmethod
    def exact_hosts(cls, values):
        for value in values:
            if not value or any(char in value for char in '*/@?#\\ ') or ':' in value:
                raise ValueError('Use exact DNS names or IPv4 addresses without ports')
        return [value.lower() for value in values]

    @model_validator(mode='after')
    def production_boundary(self):
        if self.tenant_id and not self.trusted_hosts:
            raise ValueError('Department binding requires exact trusted hosts')
        if self.production_mode:
            if not self.tenant_id or not self.cookie_secure or not self.database_url.startswith('postgresql') or not Path(self.storage_root).is_absolute():
                raise ValueError('Production requires department UUID, PostgreSQL, Secure cookies and absolute storage root')
        return self

settings = Settings()
