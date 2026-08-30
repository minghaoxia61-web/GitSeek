"""add fixer agent tables

Revision ID: 20260830_0009
Revises: 20260823_0008
Create Date: 2026-08-30
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260830_0009"
down_revision: str | Sequence[str] | None = "20260823_0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "fixer_runs",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("repo_full_name", sa.String(length=255), nullable=False),
        sa.Column("issue_url", sa.String(length=500), nullable=True),
        sa.Column("issue_number", sa.Integer(), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=True),
        sa.Column("model", sa.String(length=160), nullable=True),
        sa.Column("max_rounds", sa.Integer(), nullable=False),
        sa.Column("token_budget", sa.Integer(), nullable=False),
        sa.Column("rounds", sa.Integer(), nullable=False),
        sa.Column("token_in", sa.Integer(), nullable=False),
        sa.Column("token_out", sa.Integer(), nullable=False),
        sa.Column("cost_usd", sa.Float(), nullable=False),
        sa.Column("success", sa.Boolean(), nullable=True),
        sa.Column("failure_category", sa.String(length=60), nullable=True),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("result_json", sa.JSON(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_fixer_runs")),
    )
    op.create_index(op.f("ix_fixer_runs_repo_full_name"), "fixer_runs", ["repo_full_name"])
    op.create_index(op.f("ix_fixer_runs_issue_number"), "fixer_runs", ["issue_number"])
    op.create_index(op.f("ix_fixer_runs_status"), "fixer_runs", ["status"])

    op.create_table(
        "fixer_steps",
        sa.Column(
            "id",
            sa.BigInteger().with_variant(sa.Integer(), "sqlite"),
            autoincrement=True,
            nullable=False,
        ),
        sa.Column("run_id", sa.String(length=36), nullable=False),
        sa.Column("seq", sa.Integer(), nullable=False),
        sa.Column("round", sa.Integer(), nullable=False),
        sa.Column("tool", sa.String(length=40), nullable=False),
        sa.Column("input_json", sa.JSON(), nullable=True),
        sa.Column("output", sa.Text(), nullable=True),
        sa.Column("latency_ms", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["run_id"],
            ["fixer_runs.id"],
            name=op.f("fk_fixer_steps_run_id_fixer_runs"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_fixer_steps")),
    )
    op.create_index(op.f("ix_fixer_steps_run_id"), "fixer_steps", ["run_id"])
    op.create_index(op.f("ix_fixer_steps_seq"), "fixer_steps", ["seq"])

    op.create_table(
        "fixer_patches",
        sa.Column(
            "id",
            sa.BigInteger().with_variant(sa.Integer(), "sqlite"),
            autoincrement=True,
            nullable=False,
        ),
        sa.Column("run_id", sa.String(length=36), nullable=False),
        sa.Column("round", sa.Integer(), nullable=False),
        sa.Column("diff", sa.Text(), nullable=True),
        sa.Column("apply_ok", sa.Boolean(), nullable=True),
        sa.Column("test_ok", sa.Boolean(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["run_id"],
            ["fixer_runs.id"],
            name=op.f("fk_fixer_patches_run_id_fixer_runs"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_fixer_patches")),
    )
    op.create_index(op.f("ix_fixer_patches_run_id"), "fixer_patches", ["run_id"])

    op.create_table(
        "agent_code_chunks",
        sa.Column(
            "id",
            sa.BigInteger().with_variant(sa.Integer(), "sqlite"),
            autoincrement=True,
            nullable=False,
        ),
        sa.Column("repo_full_name", sa.String(length=255), nullable=False),
        sa.Column("path", sa.String(length=400), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("kind", sa.String(length=20), nullable=False),
        sa.Column("start_line", sa.Integer(), nullable=False),
        sa.Column("end_line", sa.Integer(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("model", sa.String(length=160), nullable=True),
        sa.Column("content_hash", sa.String(length=64), nullable=True),
        sa.Column("vector_json", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_agent_code_chunks")),
    )
    op.create_index(
        op.f("ix_agent_code_chunks_repo_full_name"),
        "agent_code_chunks",
        ["repo_full_name"],
    )
    op.create_index(op.f("ix_agent_code_chunks_model"), "agent_code_chunks", ["model"])

    op.create_table(
        "agent_bench_results",
        sa.Column(
            "id",
            sa.BigInteger().with_variant(sa.Integer(), "sqlite"),
            autoincrement=True,
            nullable=False,
        ),
        sa.Column("config_id", sa.String(length=120), nullable=False),
        sa.Column("dataset", sa.String(length=120), nullable=False),
        sa.Column("instance_id", sa.String(length=160), nullable=False),
        sa.Column("metric", sa.String(length=60), nullable=False),
        sa.Column("value", sa.Float(), nullable=False),
        sa.Column("details_json", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_agent_bench_results")),
    )
    op.create_index(
        op.f("ix_agent_bench_results_config_id"),
        "agent_bench_results",
        ["config_id"],
    )
    op.create_index(
        op.f("ix_agent_bench_results_instance_id"),
        "agent_bench_results",
        ["instance_id"],
    )

    if op.get_bind().dialect.name == "postgresql":
        op.execute(
            "ALTER TABLE agent_code_chunks ADD COLUMN search_document tsvector "
            "GENERATED ALWAYS AS (to_tsvector('simple', coalesce(content,'') || ' ' || "
            "coalesce(path,'') || ' ' || coalesce(name,''))) STORED"
        )
        op.execute(
            "CREATE INDEX ix_agent_code_chunks_search_document "
            "ON agent_code_chunks USING gin (search_document)"
        )


def downgrade() -> None:
    if op.get_bind().dialect.name == "postgresql":
        op.execute("DROP INDEX IF EXISTS ix_agent_code_chunks_search_document")
        op.execute("ALTER TABLE agent_code_chunks DROP COLUMN IF EXISTS search_document")
    op.drop_table("agent_bench_results")
    op.drop_table("agent_code_chunks")
    op.drop_table("fixer_patches")
    op.drop_table("fixer_steps")
    op.drop_table("fixer_runs")
