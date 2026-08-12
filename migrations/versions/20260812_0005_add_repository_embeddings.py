"""add repository embedding cache

Revision ID: 20260812_0005
Revises: 20260807_0004
Create Date: 2026-08-12
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260812_0005"
down_revision: str | Sequence[str] | None = "20260807_0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "repository_embeddings",
        sa.Column("repo_id", sa.BigInteger(), nullable=False),
        sa.Column("model", sa.String(length=160), nullable=False),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.Column("dimensions", sa.Integer(), nullable=False),
        sa.Column("vector_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(
            ["repo_id"],
            ["repositories.id"],
            name=op.f("fk_repository_embeddings_repo_id_repositories"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("repo_id", name=op.f("pk_repository_embeddings")),
    )
    op.create_index(
        op.f("ix_repository_embeddings_content_hash"),
        "repository_embeddings",
        ["content_hash"],
    )
    op.create_index(
        op.f("ix_repository_embeddings_model"),
        "repository_embeddings",
        ["model"],
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_repository_embeddings_model"), table_name="repository_embeddings")
    op.drop_index(
        op.f("ix_repository_embeddings_content_hash"),
        table_name="repository_embeddings",
    )
    op.drop_table("repository_embeddings")
