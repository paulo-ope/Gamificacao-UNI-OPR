"""add support OPA attendance channel fields

Revision ID: 20260816_0064
Revises: 20260816_0063
Create Date: 2026-08-16 00:00:00
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "20260816_0064"
down_revision = "20260816_0063"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("support_opa_attendances", sa.Column("channel", sa.String(length=80), nullable=True))
    op.add_column("support_opa_attendances", sa.Column("channel_id", sa.String(length=100), nullable=True))
    op.add_column("support_opa_attendances", sa.Column("channel_customer", sa.String(length=160), nullable=True))
    op.create_index(op.f("ix_support_opa_attendances_channel"), "support_opa_attendances", ["channel"])
    op.create_index(op.f("ix_support_opa_attendances_channel_customer"), "support_opa_attendances", ["channel_customer"])
    op.create_index(op.f("ix_support_opa_attendances_channel_id"), "support_opa_attendances", ["channel_id"])


def downgrade() -> None:
    op.drop_index(op.f("ix_support_opa_attendances_channel_id"), table_name="support_opa_attendances")
    op.drop_index(op.f("ix_support_opa_attendances_channel_customer"), table_name="support_opa_attendances")
    op.drop_index(op.f("ix_support_opa_attendances_channel"), table_name="support_opa_attendances")
    op.drop_column("support_opa_attendances", "channel_customer")
    op.drop_column("support_opa_attendances", "channel_id")
    op.drop_column("support_opa_attendances", "channel")
