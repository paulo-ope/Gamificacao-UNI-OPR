"""add tmr_all_responses_seconds (TMR geral, bot+humano) to support opa attendances

Revision ID: 20260825_0074
Revises: 20260825_0073
Create Date: 2026-08-25 00:00:00
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "20260825_0074"
down_revision = "20260825_0073"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("support_opa_attendances", sa.Column("tmr_all_responses_seconds", sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column("support_opa_attendances", "tmr_all_responses_seconds")
