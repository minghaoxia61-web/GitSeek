"""add issue maintainer response evidence

Revision ID: 20260823_0008
Revises: 20260814_0007
Create Date: 2026-08-23
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260823_0008"
down_revision: str | Sequence[str] | None = "20260814_0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "contribution_issues",
        sa.Column("github_created_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "contribution_issues",
        sa.Column(
            "response_status",
            sa.String(length=20),
            server_default="unknown",
            nullable=False,
        ),
    )
    op.add_column(
        "contribution_issues",
        sa.Column("first_maintainer_response_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "contribution_issues",
        sa.Column("maintainer_response_hours", sa.Float(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("contribution_issues", "maintainer_response_hours")
    op.drop_column("contribution_issues", "first_maintainer_response_at")
    op.drop_column("contribution_issues", "response_status")
    op.drop_column("contribution_issues", "github_created_at")
