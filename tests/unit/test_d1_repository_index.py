import sqlite3
from pathlib import Path


def test_d1_repository_index_migration_and_filter_plan() -> None:
    migration = (
        Path(__file__).parents[2]
        / "apps"
        / "web"
        / "drizzle"
        / "0001_repository_index.sql"
    ).read_text(encoding="utf-8")
    connection = sqlite3.connect(":memory:")
    for statement in migration.split("--> statement-breakpoint"):
        if statement.strip():
            connection.execute(statement)

    connection.execute(
        """
        INSERT INTO repository_index (
            repository, language, license_spdx, archived, pushed_at,
            search_text, payload_json, fetched_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            "example/demo",
            "Python",
            "MIT",
            0,
            "2026-08-05T00:00:00Z",
            "example demo fastapi",
            "{}",
            "2026-08-06T00:00:00Z",
        ),
    )
    plan = connection.execute(
        """
        EXPLAIN QUERY PLAN
        SELECT payload_json FROM repository_index
        WHERE language = ? AND archived = ? AND license_spdx = ? AND pushed_at > ?
        """,
        ("Python", 0, "MIT", "2026-01-01T00:00:00Z"),
    ).fetchall()
    connection.close()

    assert any("idx_repository_index_filters" in row[3] for row in plan)
