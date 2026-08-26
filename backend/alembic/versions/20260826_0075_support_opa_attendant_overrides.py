"""add support_opa_attendant_overrides (manual bot/virtual-agent classification)

Revision ID: 20260826_0075
Revises: 20260825_0074
Create Date: 2026-08-26 00:00:00
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "20260826_0075"
down_revision = "20260825_0074"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "support_opa_attendant_overrides",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("attendant_id", sa.String(length=100), nullable=False),
        sa.Column("attendant_name", sa.String(length=180), nullable=True),
        sa.Column("classification", sa.String(length=40), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_by", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="SET NULL"),
        sa.UniqueConstraint("attendant_id", name="uq_support_opa_attendant_overrides_attendant_id"),
    )
    op.create_index(
        "ix_support_opa_attendant_overrides_attendant_id",
        "support_opa_attendant_overrides",
        ["attendant_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_support_opa_attendant_overrides_attendant_id", table_name="support_opa_attendant_overrides")
    op.drop_table("support_opa_attendant_overrides")
