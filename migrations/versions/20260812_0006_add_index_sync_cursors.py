"""add persistent index synchronization cursors

Revision ID: 20260812_0006
Revises: 20260812_0005
Create Date: 2026-08-12
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260812_0006"
down_revision: str | Sequence[str] | None = "20260812_0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "index_sync_cursors",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("query", sa.String(length=500), nullable=False),
        sa.Column("next_page", sa.Integer(), nullable=False),
        sa.Column("last_success_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("failure_count", sa.Integer(), nullable=False),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_index_sync_cursors")),
        sa.UniqueConstraint("query", name=op.f("uq_index_sync_cursors_query")),
    )
    op.create_index(
        op.f("ix_index_sync_cursors_query"),
        "index_sync_cursors",
        ["query"],
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_index_sync_cursors_query"), table_name="index_sync_cursors")
    op.drop_table("index_sync_cursors")
