"""operations onu signal transmitter name

Revision ID: 20260817_0069
Revises: 20260817_0068
Create Date: 2026-08-17 00:00:00
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "20260817_0069"
down_revision = "20260817_0068"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "operations_onu_signal_current",
        sa.Column("transmitter_name", sa.String(length=160), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("operations_onu_signal_current", "transmitter_name")
