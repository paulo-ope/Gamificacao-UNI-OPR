"""operations backlog daily snapshot table

Revision ID: 20260811_0044
Revises: 20260810_0043
Create Date: 2026-08-11 00:00:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260811_0044"
down_revision = "20260810_0043"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "operations_backlog_snapshots",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("snapshot_date", sa.Date(), nullable=False),
        sa.Column("regional", sa.String(length=160), nullable=False),
        sa.Column("team_model", sa.String(length=120), nullable=False),
        sa.Column("backlog_count", sa.Integer(), nullable=False),
        sa.Column("backlog_atrasado_count", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("snapshot_date", "regional", "team_model", name="uq_operations_backlog_snapshot_identity"),
    )
    op.create_index("ix_operations_backlog_snapshots_snapshot_date", "operations_backlog_snapshots", ["snapshot_date"])
    op.create_index("ix_operations_backlog_snapshots_regional", "operations_backlog_snapshots", ["regional"])


def downgrade() -> None:
    op.drop_index("ix_operations_backlog_snapshots_regional", table_name="operations_backlog_snapshots")
    op.drop_index("ix_operations_backlog_snapshots_snapshot_date", table_name="operations_backlog_snapshots")
    op.drop_table("operations_backlog_snapshots")
