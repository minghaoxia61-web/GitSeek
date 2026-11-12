"""Persist trusted fixer verification commands.

Revision ID: 20261028_0010
Revises: 20260830_0009
"""

import sqlalchemy as sa
from alembic import op

revision = "20261028_0010"
down_revision = "20260830_0009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("fixer_runs", sa.Column("test_command", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("fixer_runs", "test_command")
