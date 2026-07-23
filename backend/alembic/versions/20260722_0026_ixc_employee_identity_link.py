"""link collaborators and operations orders to the ixc employee id

Revision ID: 20260722_0026
Revises: 20260722_0025
Create Date: 2026-07-22 17:00:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260722_0026"
down_revision = "20260722_0025"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "operations_orders",
        sa.Column("responsible_ixc_id", sa.Integer(), nullable=True),
    )
    op.create_index(
        "ix_operations_orders_responsible_ixc_id",
        "operations_orders",
        ["responsible_ixc_id"],
    )

    op.add_column(
        "collaborators",
        sa.Column("ixc_employee_id", sa.Integer(), nullable=True),
    )
    op.create_index(
        "ix_collaborators_ixc_employee_id",
        "collaborators",
        ["ixc_employee_id"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("ix_collaborators_ixc_employee_id", table_name="collaborators")
    op.drop_column("collaborators", "ixc_employee_id")

    op.drop_index("ix_operations_orders_responsible_ixc_id", table_name="operations_orders")
    op.drop_column("operations_orders", "responsible_ixc_id")
