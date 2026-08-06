"""add repository full text index

Revision ID: 20260806_0003
Revises: 20260806_0002
Create Date: 2026-08-06
"""

from collections.abc import Sequence

from alembic import op

revision: str = "20260806_0003"
down_revision: str | Sequence[str] | None = "20260806_0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

INDEX_NAME = "ix_repositories_search_document"


def upgrade() -> None:
    if op.get_bind().dialect.name != "postgresql":
        return
    op.execute(
        """
        ALTER TABLE repositories
        ADD COLUMN search_document tsvector
        GENERATED ALWAYS AS (
            to_tsvector(
                'simple',
                coalesce(name, '') || ' ' ||
                coalesce(description, '') || ' ' ||
                coalesce(topics::text, '')
            )
        ) STORED
        """
    )
    op.execute(f"CREATE INDEX {INDEX_NAME} ON repositories USING gin (search_document)")


def downgrade() -> None:
    if op.get_bind().dialect.name == "postgresql":
        op.execute(f"DROP INDEX IF EXISTS {INDEX_NAME}")
        op.execute("ALTER TABLE repositories DROP COLUMN IF EXISTS search_document")
