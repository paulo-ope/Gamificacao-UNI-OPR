"""add configurable minimum-hours gap to recurrence classification rules

Revision ID: 20260723_0027
Revises: 20260722_0026
Create Date: 2026-07-23 09:00:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260723_0027"
down_revision = "20260722_0026"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "recurrence_classification_rules",
        sa.Column("min_hours_between", sa.Float(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("recurrence_classification_rules", "min_hours_between")
