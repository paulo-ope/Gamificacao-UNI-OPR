"""drop the dead health_rules.condition_operator column

Revision ID: 20260725_0028
Revises: 20260723_0027
Create Date: 2026-07-25 12:00:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260725_0028"
down_revision = "20260723_0027"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_column("health_rules", "condition_operator")


def downgrade() -> None:
    op.add_column(
        "health_rules",
        sa.Column("condition_operator", sa.String(length=20), nullable=False, server_default="and"),
    )
