from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect, text

from packages.domain.settings import Settings


def test_test_command_migration_preserves_old_runs_and_roundtrips(tmp_path, monkeypatch):
    database_url = f"sqlite+pysqlite:///{(tmp_path / 'migration.db').as_posix()}"
    settings = Settings(_env_file=None, DATABASE_URL=database_url)
    assert settings.database_url == database_url
    monkeypatch.setattr("packages.domain.settings.get_settings", lambda: settings)
    config = Config(str(Path(__file__).resolve().parents[2] / "alembic.ini"))
    command.upgrade(config, "20260830_0009")
    engine = create_engine(database_url)
    with engine.begin() as connection:
        connection.execute(
            text("""
            INSERT INTO fixer_runs
            (id, repo_full_name, status, max_rounds, token_budget, rounds, token_in,
             token_out, cost_usd, created_at, updated_at)
            VALUES ('old', 'owner/repo', 'succeeded', 5, 1000, 1, 10, 5, 0,
                    CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
        """)
        )
    command.upgrade(config, "head")
    with engine.begin() as connection:
        assert (
            connection.execute(
                text("SELECT test_command FROM fixer_runs WHERE id = 'old'")
            ).scalar_one()
            is None
        )
        assert (
            connection.execute(
                text("SELECT execution_spec FROM fixer_runs WHERE id = 'old'")
            ).scalar_one()
            is None
        )
        connection.execute(
            text("UPDATE fixer_runs SET test_command = 'pytest -q' WHERE id = 'old'")
        )
    command.downgrade(config, "20261028_0010")
    columns = {column["name"] for column in inspect(engine).get_columns("fixer_runs")}
    assert "execution_spec" not in columns
    with engine.connect() as connection:
        assert (
            connection.execute(
                text("SELECT test_command FROM fixer_runs WHERE id = 'old'")
            ).scalar_one()
            == "pytest -q"
        )
    command.upgrade(config, "head")
    command.downgrade(config, "20260830_0009")
    columns = {column["name"] for column in inspect(engine).get_columns("fixer_runs")}
    assert "test_command" not in columns
    assert "execution_spec" not in columns
    command.upgrade(config, "head")
    with engine.connect() as connection:
        assert connection.execute(text("SELECT count(*) FROM fixer_runs")).scalar_one() == 1
    engine.dispose()


def test_nullable_cost_migration_keeps_unknown_and_rejects_false_zero_downgrade(
    tmp_path, monkeypatch
):
    database_url = f"sqlite+pysqlite:///{(tmp_path / 'unknown-cost.db').as_posix()}"
    settings = Settings(_env_file=None, DATABASE_URL=database_url)
    assert settings.database_url == database_url
    monkeypatch.setattr("packages.domain.settings.get_settings", lambda: settings)
    config = Config(str(Path(__file__).resolve().parents[2] / "alembic.ini"))
    command.upgrade(config, "head")
    engine = create_engine(database_url)
    with engine.begin() as connection:
        connection.execute(
            text("""
            INSERT INTO fixer_runs
            (id, repo_full_name, status, max_rounds, token_budget, rounds, token_in,
             token_out, cost_usd, created_at, updated_at)
            VALUES ('unknown', 'owner/repo', 'failed', 5, 1000, 1, 10, 5, NULL,
                    CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
        """)
        )
    with pytest.raises(RuntimeError, match="unknown fixer costs"):
        command.downgrade(config, "20261028_0011")
    with engine.connect() as connection:
        assert connection.execute(text("SELECT cost_usd FROM fixer_runs")).scalar_one() is None
    engine.dispose()
