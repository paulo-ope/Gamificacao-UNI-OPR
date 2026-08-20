"""operations onu signal history (append-only)

Revision ID: 20260817_0070
Revises: 20260817_0069
Create Date: 2026-08-17 00:00:01
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "20260817_0070"
down_revision = "20260817_0069"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "operations_onu_signal_snapshots",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("login_id", sa.Integer(), nullable=False),
        sa.Column("contract_id", sa.String(length=100), nullable=True),
        sa.Column("signal_rx_dbm", sa.Float(), nullable=True),
        sa.Column("signal_tx_dbm", sa.Float(), nullable=True),
        sa.Column("last_drop_cause", sa.String(length=120), nullable=True),
        sa.Column("onu_serial", sa.String(length=60), nullable=True),
        sa.Column("onu_model", sa.String(length=80), nullable=True),
        sa.Column("transmitter_id", sa.String(length=40), nullable=True),
        sa.Column("transmitter_name", sa.String(length=160), nullable=True),
        sa.Column("temperature_c", sa.Float(), nullable=True),
        sa.Column("voltage", sa.Float(), nullable=True),
        sa.Column("signal_measured_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("pon_id", sa.String(length=40), nullable=True),
        sa.Column("pon_no", sa.String(length=20), nullable=True),
        sa.Column("slot_no", sa.String(length=20), nullable=True),
        sa.Column("latitude", sa.Float(), nullable=True),
        sa.Column("longitude", sa.Float(), nullable=True),
        sa.Column("captured_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "ix_operations_onu_signal_snapshots_login_id", "operations_onu_signal_snapshots", ["login_id"]
    )
    op.create_index(
        "ix_operations_onu_signal_snapshots_captured_at", "operations_onu_signal_snapshots", ["captured_at"]
    )
    op.create_index(
        "ix_operations_onu_signal_snapshots_login_captured",
        "operations_onu_signal_snapshots",
        ["login_id", "captured_at"],
    )
    op.create_index(
        "ix_operations_onu_signal_snapshots_serial_captured",
        "operations_onu_signal_snapshots",
        ["onu_serial", "captured_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_operations_onu_signal_snapshots_serial_captured", table_name="operations_onu_signal_snapshots")
    op.drop_index("ix_operations_onu_signal_snapshots_login_captured", table_name="operations_onu_signal_snapshots")
    op.drop_index("ix_operations_onu_signal_snapshots_captured_at", table_name="operations_onu_signal_snapshots")
    op.drop_index("ix_operations_onu_signal_snapshots_login_id", table_name="operations_onu_signal_snapshots")
    op.drop_table("operations_onu_signal_snapshots")
