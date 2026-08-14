"""operations login current status table

Revision ID: 20260813_0052
Revises: 20260813_0051
Create Date: 2026-08-13 00:00:00
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "20260813_0052"
down_revision = "20260813_0051"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "operations_login_current_status",
        sa.Column("login_id", sa.Integer(), primary_key=True),
        sa.Column("login", sa.String(length=160), nullable=False),
        sa.Column("online", sa.String(length=10), nullable=False, server_default=""),
        sa.Column("latitude", sa.Float(), nullable=True),
        sa.Column("longitude", sa.Float(), nullable=True),
        sa.Column("last_connected_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_disconnected_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status_changed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("captured_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "ix_operations_login_current_status_online_changed",
        "operations_login_current_status",
        ["online", "status_changed_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_operations_login_current_status_online_changed", table_name="operations_login_current_status")
    op.drop_table("operations_login_current_status")
