"""Application configuration via environment variables."""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+psycopg://postgres:postgres@localhost:5432/certificates"
    storage_dir: str = "./generated"
    log_level: str = "INFO"
    max_recipients: int = 10000


settings = Settings()
