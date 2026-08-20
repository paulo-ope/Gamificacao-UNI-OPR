"""add support OPA dimension cache

Revision ID: 20260816_0062
Revises: 20260815_0061
Create Date: 2026-08-16 00:00:00
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "20260816_0062"
down_revision = "20260815_0061"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "support_opa_dimensions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("dimension_type", sa.String(length=40), nullable=False),
        sa.Column("source_id", sa.String(length=100), nullable=False),
        sa.Column("name", sa.String(length=220), nullable=True),
        sa.Column("payload_json", sa.JSON(), nullable=False),
        sa.Column("synced_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("dimension_type", "source_id", name="uq_support_opa_dimensions_type_source"),
    )
    op.create_index(op.f("ix_support_opa_dimensions_dimension_type"), "support_opa_dimensions", ["dimension_type"])
    op.create_index(op.f("ix_support_opa_dimensions_name"), "support_opa_dimensions", ["name"])
    op.create_index(op.f("ix_support_opa_dimensions_source_id"), "support_opa_dimensions", ["source_id"])


def downgrade() -> None:
    op.drop_index(op.f("ix_support_opa_dimensions_source_id"), table_name="support_opa_dimensions")
    op.drop_index(op.f("ix_support_opa_dimensions_name"), table_name="support_opa_dimensions")
    op.drop_index(op.f("ix_support_opa_dimensions_dimension_type"), table_name="support_opa_dimensions")
    op.drop_table("support_opa_dimensions")
