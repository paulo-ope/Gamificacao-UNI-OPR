"""operations saved filters

Revision ID: 20260720_0013
Revises: 20260720_0012
Create Date: 2026-07-20 00:00:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision = "20260720_0013"
down_revision = "20260720_0012"
branch_labels = None
depends_on = None


def _tables() -> set[str]:
    return set(inspect(op.get_bind()).get_table_names())


def upgrade() -> None:
    if "operations_saved_filters" in _tables():
        return
    op.create_table(
        "operations_saved_filters",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("filters", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("user_id", "name", name="uq_operations_saved_filters_user_name"),
    )
    op.create_index("ix_operations_saved_filters_user_id", "operations_saved_filters", ["user_id"])


def downgrade() -> None:
    if "operations_saved_filters" in _tables():
        op.drop_table("operations_saved_filters")

