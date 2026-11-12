"""Bind fixer tasks to a benchmark revision and execution environment."""

import sqlalchemy as sa
from alembic import op

revision = "20261028_0011"
down_revision = "20261028_0010"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("fixer_runs", sa.Column("execution_spec", sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column("fixer_runs", "execution_spec")
