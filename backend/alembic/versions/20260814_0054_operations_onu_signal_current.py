"""operations onu signal current table

Revision ID: 20260814_0054
Revises: 20260814_0053
Create Date: 2026-08-14 00:00:00
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "20260814_0054"
down_revision = "20260814_0053"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "operations_onu_signal_current",
        sa.Column("login_id", sa.Integer(), primary_key=True),
        sa.Column("contract_id", sa.String(length=100), nullable=True),
        sa.Column("signal_rx_dbm", sa.Float(), nullable=True),
        sa.Column("signal_tx_dbm", sa.Float(), nullable=True),
        sa.Column("last_drop_cause", sa.String(length=120), nullable=True),
        sa.Column("onu_serial", sa.String(length=60), nullable=True),
        sa.Column("onu_model", sa.String(length=80), nullable=True),
        sa.Column("transmitter_id", sa.String(length=40), nullable=True),
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
    op.create_index("ix_operations_onu_signal_current_contract_id", "operations_onu_signal_current", ["contract_id"])
    op.create_index("ix_operations_onu_signal_current_drop_cause", "operations_onu_signal_current", ["last_drop_cause"])
    op.create_index("ix_operations_onu_signal_current_transmitter", "operations_onu_signal_current", ["transmitter_id"])


def downgrade() -> None:
    op.drop_index("ix_operations_onu_signal_current_transmitter", table_name="operations_onu_signal_current")
    op.drop_index("ix_operations_onu_signal_current_drop_cause", table_name="operations_onu_signal_current")
    op.drop_index("ix_operations_onu_signal_current_contract_id", table_name="operations_onu_signal_current")
    op.drop_table("operations_onu_signal_current")
