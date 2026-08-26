"""add bot/human/handoff classification to support opa attendances

Revision ID: 20260825_0073
Revises: 20260820_0072
Create Date: 2026-08-25 00:00:00
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "20260825_0073"
down_revision = "20260820_0072"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("support_opa_attendances", sa.Column("handled_by_bot", sa.Boolean(), nullable=True))
    op.add_column("support_opa_attendances", sa.Column("reached_human", sa.Boolean(), nullable=True))
    op.add_column("support_opa_attendances", sa.Column("bot_to_human_handoff", sa.Boolean(), nullable=True))


def downgrade() -> None:
    op.drop_column("support_opa_attendances", "bot_to_human_handoff")
    op.drop_column("support_opa_attendances", "reached_human")
    op.drop_column("support_opa_attendances", "handled_by_bot")
