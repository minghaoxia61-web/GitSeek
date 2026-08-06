"""create product activity tables

Revision ID: 20260806_0002
Revises: 20260803_0001
Create Date: 2026-08-06
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260806_0002"
down_revision: str | Sequence[str] | None = "20260803_0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "repository_snapshots",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("repo_id", sa.BigInteger(), nullable=False),
        sa.Column("fetched_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("metrics_json", sa.JSON(), nullable=False),
        sa.Column("source_sha", sa.String(length=255), nullable=True),
        sa.ForeignKeyConstraint(
            ["repo_id"],
            ["repositories.id"],
            name=op.f("fk_repository_snapshots_repo_id_repositories"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_repository_snapshots")),
    )
    op.create_index(op.f("ix_repository_snapshots_repo_id"), "repository_snapshots", ["repo_id"])

    op.create_table(
        "search_sessions",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("query", sa.Text(), nullable=False),
        sa.Column("constraints", sa.JSON(), nullable=False),
        sa.Column("generated_github_query", sa.Text(), nullable=False),
        sa.Column("source_total_count", sa.Integer(), nullable=False),
        sa.Column("eligible_candidate_count", sa.Integer(), nullable=False),
        sa.Column("ranking_version", sa.String(length=100), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_search_sessions")),
    )

    op.create_table(
        "recommendations",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("session_id", sa.String(length=36), nullable=False),
        sa.Column("repository_full_name", sa.String(length=255), nullable=False),
        sa.Column("rank", sa.Integer(), nullable=False),
        sa.Column("score", sa.Float(), nullable=False),
        sa.Column("score_json", sa.JSON(), nullable=False),
        sa.Column("evidence_json", sa.JSON(), nullable=False),
        sa.ForeignKeyConstraint(
            ["session_id"],
            ["search_sessions.id"],
            name=op.f("fk_recommendations_session_id_search_sessions"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_recommendations")),
        sa.UniqueConstraint("session_id", "rank", name=op.f("uq_recommendations_session_id")),
    )
    op.create_index(
        op.f("ix_recommendations_repository_full_name"),
        "recommendations",
        ["repository_full_name"],
    )
    op.create_index(op.f("ix_recommendations_session_id"), "recommendations", ["session_id"])

    op.create_table(
        "feedback",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("session_id", sa.String(length=36), nullable=True),
        sa.Column("repository", sa.String(length=255), nullable=False),
        sa.Column("action", sa.String(length=40), nullable=False),
        sa.Column("reason", sa.String(length=240), nullable=True),
        sa.Column("query", sa.String(length=500), nullable=True),
        sa.Column("device_id", sa.String(length=64), nullable=True),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["session_id"],
            ["search_sessions.id"],
            name=op.f("fk_feedback_session_id_search_sessions"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_feedback")),
    )
    for column in ("action", "device_id", "repository", "session_id"):
        op.create_index(op.f(f"ix_feedback_{column}"), "feedback", [column])

    op.create_table(
        "saved_repositories",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("device_id", sa.String(length=64), nullable=False),
        sa.Column("repository", sa.String(length=255), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_saved_repositories")),
        sa.UniqueConstraint(
            "device_id",
            "repository",
            name=op.f("uq_saved_repositories_device_id"),
        ),
    )
    op.create_index(op.f("ix_saved_repositories_device_id"), "saved_repositories", ["device_id"])
    op.create_index(op.f("ix_saved_repositories_repository"), "saved_repositories", ["repository"])

    op.create_table(
        "contribution_issues",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("repository_full_name", sa.String(length=255), nullable=False),
        sa.Column("issue_number", sa.Integer(), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("html_url", sa.String(length=500), nullable=False),
        sa.Column("state", sa.String(length=20), nullable=False),
        sa.Column("labels", sa.JSON(), nullable=False),
        sa.Column("assigned", sa.Boolean(), nullable=False),
        sa.Column("comments", sa.Integer(), nullable=False),
        sa.Column("difficulty", sa.String(length=20), nullable=False),
        sa.Column("score", sa.Float(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("fetched_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_contribution_issues")),
        sa.UniqueConstraint(
            "repository_full_name",
            "issue_number",
            name=op.f("uq_contribution_issues_repository_full_name"),
        ),
    )
    op.create_index(
        op.f("ix_contribution_issues_repository_full_name"),
        "contribution_issues",
        ["repository_full_name"],
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_contribution_issues_repository_full_name"),
        table_name="contribution_issues",
    )
    op.drop_table("contribution_issues")
    op.drop_index(op.f("ix_saved_repositories_repository"), table_name="saved_repositories")
    op.drop_index(op.f("ix_saved_repositories_device_id"), table_name="saved_repositories")
    op.drop_table("saved_repositories")
    for column in ("session_id", "repository", "device_id", "action"):
        op.drop_index(op.f(f"ix_feedback_{column}"), table_name="feedback")
    op.drop_table("feedback")
    op.drop_index(op.f("ix_recommendations_session_id"), table_name="recommendations")
    op.drop_index(op.f("ix_recommendations_repository_full_name"), table_name="recommendations")
    op.drop_table("recommendations")
    op.drop_table("search_sessions")
    op.drop_index(op.f("ix_repository_snapshots_repo_id"), table_name="repository_snapshots")
    op.drop_table("repository_snapshots")
