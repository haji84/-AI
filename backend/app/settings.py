from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="FIRE_AI_", env_file=".env", extra="ignore")
    database_url: str = "sqlite+pysqlite:///./fire_ai_dev.db"
    session_hours: int = 12
    cookie_secure: bool = False
    cookie_name: str = "fire_ai_session"
    app_name: str = "消防業務 Local AI"
    storage_root: str = "./runtime/storage"

settings = Settings()
