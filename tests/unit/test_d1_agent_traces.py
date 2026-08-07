import sqlite3
from pathlib import Path

DRIZZLE_DIR = Path(__file__).parents[2] / "apps" / "web" / "drizzle"


def _apply_migration(connection: sqlite3.Connection, filename: str) -> None:
    sql = (DRIZZLE_DIR / filename).read_text(encoding="utf-8")
    for statement in sql.split("--> statement-breakpoint"):
        if statement.strip():
            connection.executescript(statement)


def test_agent_trace_d1_migration_is_executable() -> None:
    connection = sqlite3.connect(":memory:")
    connection.execute("PRAGMA foreign_keys = ON")
    _apply_migration(connection, "0000_product_activity.sql")
    _apply_migration(connection, "0002_agent_traces.sql")

    connection.execute(
        "INSERT INTO search_sessions VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        ("search-1", "python cli", "{}", "python cli", 1, 1, "v1", "2026-08-07"),
    )
    connection.execute(
        "INSERT INTO agent_runs VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (
            "run-1",
            "search-1",
            "succeeded",
            "{}",
            "{}",
            0,
            "2026-08-07T00:00:00Z",
            "2026-08-07T00:00:01Z",
        ),
    )
    connection.execute(
        """
        INSERT INTO agent_steps
          (run_id, node, status, duration_ms, attempts, summary, started_at, completed_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            "run-1",
            "verify_evidence",
            "completed",
            12,
            1,
            "verified",
            "2026-08-07T00:00:00Z",
            "2026-08-07T00:00:01Z",
        ),
    )

    assert connection.execute("SELECT status FROM agent_runs").fetchone() == ("succeeded",)
    assert connection.execute("SELECT node FROM agent_steps").fetchone() == (
        "verify_evidence",
    )
    indexes = {
        row[0]
        for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type = 'index'"
        )
    }
    assert "idx_agent_runs_status" in indexes
    assert "idx_agent_steps_run_id" in indexes

