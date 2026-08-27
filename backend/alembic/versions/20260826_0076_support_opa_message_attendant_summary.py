"""add message-derived human attendant summary to support opa attendances

Revision ID: 20260826_0076
Revises: 20260826_0075
Create Date: 2026-08-26 00:00:00
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "20260826_0076"
down_revision = "20260826_0075"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("support_opa_attendances", sa.Column("distinct_human_attendant_ids", sa.JSON(), nullable=True))
    op.add_column("support_opa_attendances", sa.Column("first_human_attendant_id", sa.String(length=100), nullable=True))
    op.add_column("support_opa_attendances", sa.Column("last_human_attendant_id", sa.String(length=100), nullable=True))
    op.add_column("support_opa_attendances", sa.Column("human_message_count", sa.Integer(), nullable=True))
    op.add_column("support_opa_attendances", sa.Column("bot_message_count", sa.Integer(), nullable=True))
    op.add_column("support_opa_attendances", sa.Column("client_message_count", sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column("support_opa_attendances", "client_message_count")
    op.drop_column("support_opa_attendances", "bot_message_count")
    op.drop_column("support_opa_attendances", "human_message_count")
    op.drop_column("support_opa_attendances", "last_human_attendant_id")
    op.drop_column("support_opa_attendances", "first_human_attendant_id")
    op.drop_column("support_opa_attendances", "distinct_human_attendant_ids")
