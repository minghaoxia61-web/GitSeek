"""create repository tables

Revision ID: 20260803_0001
Revises:
Create Date: 2026-08-03
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260803_0001"
down_revision: str | Sequence[str] | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "repositories",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("github_id", sa.BigInteger(), nullable=False),
        sa.Column("full_name", sa.String(length=255), nullable=False),
        sa.Column("owner", sa.String(length=100), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("html_url", sa.String(length=500), nullable=False),
        sa.Column("default_branch", sa.String(length=255), nullable=False),
        sa.Column("primary_language", sa.String(length=100), nullable=True),
        sa.Column("topics", sa.JSON(), nullable=False),
        sa.Column("license_spdx", sa.String(length=100), nullable=True),
        sa.Column("stars", sa.Integer(), nullable=False),
        sa.Column("forks", sa.Integer(), nullable=False),
        sa.Column("open_issues", sa.Integer(), nullable=False),
        sa.Column("archived", sa.Boolean(), nullable=False),
        sa.Column("pushed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("github_created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("github_updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("fetched_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("source_etag", sa.String(length=255), nullable=True),
        sa.Column("raw_metadata", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_repositories")),
        sa.UniqueConstraint("full_name", name=op.f("uq_repositories_full_name")),
        sa.UniqueConstraint("github_id", name=op.f("uq_repositories_github_id")),
    )
    op.create_index(op.f("ix_repositories_archived"), "repositories", ["archived"])
    op.create_index(op.f("ix_repositories_full_name"), "repositories", ["full_name"])
    op.create_index(op.f("ix_repositories_github_id"), "repositories", ["github_id"])
    op.create_index(
        op.f("ix_repositories_license_spdx"), "repositories", ["license_spdx"]
    )
    op.create_index(
        op.f("ix_repositories_primary_language"), "repositories", ["primary_language"]
    )
    op.create_index(op.f("ix_repositories_owner"), "repositories", ["owner"])
    op.create_index(op.f("ix_repositories_pushed_at"), "repositories", ["pushed_at"])

    op.create_table(
        "repository_features",
        sa.Column("repo_id", sa.BigInteger(), nullable=False),
        sa.Column("has_readme", sa.Boolean(), nullable=True),
        sa.Column("has_contributing", sa.Boolean(), nullable=True),
        sa.Column("has_tests", sa.Boolean(), nullable=True),
        sa.Column("has_ci", sa.Boolean(), nullable=True),
        sa.Column("has_pyproject", sa.Boolean(), nullable=True),
        sa.Column("recently_active", sa.Boolean(), nullable=True),
        sa.Column("activity_score", sa.Float(), nullable=True),
        sa.Column("documentation_score", sa.Float(), nullable=True),
        sa.Column("learning_friendliness_score", sa.Float(), nullable=True),
        sa.Column("feature_version", sa.String(length=50), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(
            ["repo_id"],
            ["repositories.id"],
            name=op.f("fk_repository_features_repo_id_repositories"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("repo_id", name=op.f("pk_repository_features")),
    )


def downgrade() -> None:
    op.drop_table("repository_features")
    op.drop_index(op.f("ix_repositories_pushed_at"), table_name="repositories")
    op.drop_index(op.f("ix_repositories_owner"), table_name="repositories")
    op.drop_index(op.f("ix_repositories_primary_language"), table_name="repositories")
    op.drop_index(op.f("ix_repositories_license_spdx"), table_name="repositories")
    op.drop_index(op.f("ix_repositories_github_id"), table_name="repositories")
    op.drop_index(op.f("ix_repositories_full_name"), table_name="repositories")
    op.drop_index(op.f("ix_repositories_archived"), table_name="repositories")
    op.drop_table("repositories")

