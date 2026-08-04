from functools import lru_cache

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_prefix="OPENSCOUT_",
        extra="ignore",
    )

    app_name: str = "openscout-api"
    app_version: str = "0.1.0"
    environment: str = Field(default="local", validation_alias="OPENSCOUT_ENV")
    api_host: str = "0.0.0.0"
    api_port: int = 8000
    database_url: str = (
        "postgresql+psycopg://openscout:openscout@localhost:5432/openscout"
    )
    github_token: SecretStr | None = Field(default=None, validation_alias="GITHUB_TOKEN")
    github_api_url: str = "https://api.github.com"
    github_api_version: str = "2026-03-10"


@lru_cache
def get_settings() -> Settings:
    return Settings()
