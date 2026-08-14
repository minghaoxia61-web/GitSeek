"""add repository investigation and issue cache

Revision ID: 20260814_0007
Revises: 20260812_0006
Create Date: 2026-08-14
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260814_0007"
down_revision: str | Sequence[str] | None = "20260812_0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "repository_detail_cache",
        sa.Column("repository_full_name", sa.String(length=255), nullable=False),
        sa.Column("investigation_json", sa.JSON(), nullable=True),
        sa.Column("investigation_fetched_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("issues_json", sa.JSON(), nullable=True),
        sa.Column("issues_fetched_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint(
            "repository_full_name",
            name=op.f("pk_repository_detail_cache"),
        ),
    )


def downgrade() -> None:
    op.drop_table("repository_detail_cache")
