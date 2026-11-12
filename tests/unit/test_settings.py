from sqlalchemy import create_engine, inspect

from packages.database import ensure_database_schema
from packages.domain.settings import Settings


def test_database_url_accepts_cloud_provider_variable() -> None:
    settings = Settings(
        _env_file=None,
        DATABASE_URL="postgresql://gitseek:secret@database.example/gitseek?sslmode=require",
    )

    assert settings.database_url == (
        "postgresql+psycopg://gitseek:secret@database.example/gitseek?sslmode=require"
    )


def test_database_url_preserves_explicit_psycopg_driver() -> None:
    url = "postgresql+psycopg://gitseek:secret@database.example/gitseek"

    settings = Settings(_env_file=None, OPENSCOUT_DATABASE_URL=url)

    assert settings.database_url == url


def test_schema_bootstrap_creates_missing_tables() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")

    assert ensure_database_schema(engine) is True
    assert "repositories" in inspect(engine).get_table_names()
    assert "search_sessions" in inspect(engine).get_table_names()


def test_legacy_zero_price_placeholders_are_unknown_unless_confirmed():
    values = {
        "fixer_input_cost_per_million": 0,
        "fixer_output_cost_per_million": 0,
        "fixer_embedding_cost_per_million": 0,
    }
    unknown = Settings(_env_file=None, fixer_zero_price_confirmed=False, **values)
    assert unknown.fixer_input_cost_per_million is None
    assert unknown.fixer_output_cost_per_million is None
    assert unknown.fixer_embedding_cost_per_million is None
    confirmed = Settings(_env_file=None, fixer_zero_price_confirmed=True, **values)
    assert confirmed.fixer_input_cost_per_million == 0
    assert confirmed.fixer_output_cost_per_million == 0
    assert confirmed.fixer_embedding_cost_per_million == 0
