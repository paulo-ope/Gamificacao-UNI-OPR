"""add IXC collaborator directory for operations

Revision ID: 20260722_0025
Revises: 20260722_0024
Create Date: 2026-07-22 16:20:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260722_0025"
down_revision = "20260722_0024"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "operations_ixc_collaborators",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("source_employee_id", sa.String(length=80), nullable=False, unique=True),
        sa.Column("name", sa.String(length=180), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("last_synced_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_operations_ixc_collaborators_name", "operations_ixc_collaborators", ["name"])
    op.create_index("ix_operations_ixc_collaborators_active", "operations_ixc_collaborators", ["active"])
    op.create_table(
        "operations_responsible_directory_settings",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("source", sa.String(length=20), nullable=False, server_default="orders"),
        sa.Column("updated_by", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("operations_responsible_directory_settings")
    op.drop_index("ix_operations_ixc_collaborators_active", table_name="operations_ixc_collaborators")
    op.drop_index("ix_operations_ixc_collaborators_name", table_name="operations_ixc_collaborators")
    op.drop_table("operations_ixc_collaborators")
