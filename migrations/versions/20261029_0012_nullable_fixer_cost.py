"""Allow unknown fixer estimates without replacing them with zero."""

import sqlalchemy as sa
from alembic import op

revision = "20261029_0012"
down_revision = "20261028_0011"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("fixer_runs") as batch:
        batch.alter_column("cost_usd", existing_type=sa.Float(), nullable=True)


def downgrade() -> None:
    # Old schema cannot represent unknown; do not silently falsify historical costs.
    connection = op.get_bind()
    if connection.execute(
        sa.text("SELECT count(*) FROM fixer_runs WHERE cost_usd IS NULL")
    ).scalar():
        raise RuntimeError("cannot downgrade: unknown fixer costs require explicit archival first")
    with op.batch_alter_table("fixer_runs") as batch:
        batch.alter_column("cost_usd", existing_type=sa.Float(), nullable=False)
