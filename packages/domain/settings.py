from functools import lru_cache

from pydantic import AliasChoices, Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_prefix="OPENSCOUT_",
        extra="ignore",
    )

    app_name: str = "gitseek-api"
    app_version: str = "1.0.0"
    environment: str = Field(default="local", validation_alias="OPENSCOUT_ENV")
    api_host: str = "0.0.0.0"
    api_port: int = 8000
    cors_origins: str = (
        "http://127.0.0.1:5173,http://localhost:5173,tauri://localhost,http://tauri.localhost"
    )
    database_url: str = Field(
        default="postgresql+psycopg://openscout:openscout@localhost:5432/openscout",
        validation_alias=AliasChoices("OPENSCOUT_DATABASE_URL", "DATABASE_URL"),
    )
    github_token: SecretStr | None = Field(default=None, validation_alias="GITHUB_TOKEN")
    github_api_url: str = "https://api.github.com"
    github_api_version: str = "2026-03-10"
    cron_secret: SecretStr | None = Field(default=None, validation_alias="CRON_SECRET")
    openai_api_key: SecretStr | None = Field(default=None, validation_alias="OPENAI_API_KEY")
    openai_model: str = "gpt-5.6-luna"
    openai_api_url: str = "https://api.openai.com/v1"
    embedding_api_key: SecretStr | None = Field(
        default=None,
        validation_alias=AliasChoices("EMBEDDING_API_KEY", "OPENSCOUT_EMBEDDING_API_KEY"),
    )
    embedding_model: str | None = None
    embedding_api_url: str = "https://api.openai.com/v1"
    public_rate_limit_per_minute: int = 120
    agent_rate_limit_per_minute: int = 30
    model_input_cost_per_million: float = 0.0
    model_output_cost_per_million: float = 0.0
    embedding_cost_per_million: float = 0.0

    @field_validator("database_url", mode="before")
    @classmethod
    def use_psycopg_driver(cls, value: object) -> object:
        if not isinstance(value, str):
            return value
        if value.startswith("postgresql://"):
            return value.replace("postgresql://", "postgresql+psycopg://", 1)
        if value.startswith("postgres://"):
            return value.replace("postgres://", "postgresql+psycopg://", 1)
        return value

    @property
    def allowed_cors_origins(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
