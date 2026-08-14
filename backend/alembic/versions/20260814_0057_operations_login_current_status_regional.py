"""add regional column to operations_login_current_status

Revision ID: 20260814_0057
Revises: 20260814_0056
Create Date: 2026-08-14 00:00:00
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "20260814_0057"
down_revision = "20260814_0056"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("operations_login_current_status", sa.Column("regional", sa.String(length=80), nullable=True))
    op.create_index(
        "ix_operations_login_current_status_regional", "operations_login_current_status", ["regional"]
    )


def downgrade() -> None:
    op.drop_index("ix_operations_login_current_status_regional", table_name="operations_login_current_status")
    op.drop_column("operations_login_current_status", "regional")
