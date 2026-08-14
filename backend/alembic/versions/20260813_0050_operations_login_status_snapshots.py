"""operations login status snapshot table

Revision ID: 20260813_0050
Revises: 20260811_0049
Create Date: 2026-08-13 00:00:00
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "20260813_0050"
down_revision = "20260811_0049"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "operations_login_status_snapshots",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("captured_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("login_id", sa.Integer(), nullable=False),
        sa.Column("login", sa.String(length=160), nullable=False),
        sa.Column("online", sa.String(length=10), nullable=False, server_default=""),
        sa.Column("latitude", sa.Float(), nullable=True),
        sa.Column("longitude", sa.Float(), nullable=True),
        sa.Column("last_connected_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_disconnected_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "ix_operations_login_status_snapshots_captured_at",
        "operations_login_status_snapshots",
        ["captured_at"],
    )
    op.create_index(
        "ix_operations_login_status_snapshots_login_id",
        "operations_login_status_snapshots",
        ["login_id"],
    )
    op.create_index(
        "ix_operations_login_status_snapshots_login_captured",
        "operations_login_status_snapshots",
        ["login_id", "captured_at"],
    )
    op.create_index(
        "ix_operations_login_status_snapshots_online_geo",
        "operations_login_status_snapshots",
        ["online", "latitude", "longitude"],
    )


def downgrade() -> None:
    op.drop_index("ix_operations_login_status_snapshots_online_geo", table_name="operations_login_status_snapshots")
    op.drop_index("ix_operations_login_status_snapshots_login_captured", table_name="operations_login_status_snapshots")
    op.drop_index("ix_operations_login_status_snapshots_login_id", table_name="operations_login_status_snapshots")
    op.drop_index("ix_operations_login_status_snapshots_captured_at", table_name="operations_login_status_snapshots")
    op.drop_table("operations_login_status_snapshots")
