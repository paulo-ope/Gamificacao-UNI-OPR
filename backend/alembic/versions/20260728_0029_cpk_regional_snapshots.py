"""add cpk_regional_snapshots table

Revision ID: 20260728_0029
Revises: 20260725_0028
Create Date: 2026-07-28 15:00:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260728_0029"
down_revision = "20260725_0028"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "cpk_regional_snapshots",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("reference_year", sa.Integer(), nullable=False),
        sa.Column("reference_month", sa.Integer(), nullable=False),
        sa.Column("regional", sa.String(length=120), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("cpk_realizado", sa.Float(), nullable=True),
        sa.Column("cpk_meta", sa.Float(), nullable=True),
        sa.Column("mes_fechado", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("synced_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("reference_year", "reference_month", "regional", name="uq_cpk_snapshot_period_regional"),
    )
    op.create_index("ix_cpk_regional_snapshots_reference_year", "cpk_regional_snapshots", ["reference_year"])
    op.create_index("ix_cpk_regional_snapshots_reference_month", "cpk_regional_snapshots", ["reference_month"])
    op.create_index("ix_cpk_regional_snapshots_regional", "cpk_regional_snapshots", ["regional"])


def downgrade() -> None:
    op.drop_index("ix_cpk_regional_snapshots_regional", table_name="cpk_regional_snapshots")
    op.drop_index("ix_cpk_regional_snapshots_reference_month", table_name="cpk_regional_snapshots")
    op.drop_index("ix_cpk_regional_snapshots_reference_year", table_name="cpk_regional_snapshots")
    op.drop_table("cpk_regional_snapshots")
