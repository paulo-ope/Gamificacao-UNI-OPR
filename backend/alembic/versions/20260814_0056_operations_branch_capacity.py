"""operations branch capacity table

Revision ID: 20260814_0056
Revises: 20260814_0055
Create Date: 2026-08-14 00:00:00
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "20260814_0056"
down_revision = "20260814_0055"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "operations_branch_capacity",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("regional", sa.String(length=160), nullable=False),
        sa.Column("good_threshold", sa.Integer(), nullable=False, server_default="2500"),
        sa.Column("great_threshold", sa.Integer(), nullable=False, server_default="3000"),
        sa.Column("excellent_threshold", sa.Integer(), nullable=False, server_default="3500"),
        sa.Column("good_color", sa.String(length=7), nullable=False, server_default="#dcfce7"),
        sa.Column("great_color", sa.String(length=7), nullable=False, server_default="#dbeafe"),
        sa.Column("excellent_color", sa.String(length=7), nullable=False, server_default="#ede9fe"),
        sa.Column("updated_by", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("regional", name="uq_operations_branch_capacity_regional"),
        sa.ForeignKeyConstraint(["updated_by"], ["users.id"], ondelete="SET NULL"),
    )
    op.create_index(
        "ix_operations_branch_capacity_regional",
        "operations_branch_capacity",
        ["regional"],
    )


def downgrade() -> None:
    op.drop_index("ix_operations_branch_capacity_regional", table_name="operations_branch_capacity")
    op.drop_table("operations_branch_capacity")
