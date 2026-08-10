"""ai module: api key credentials for machine-to-machine analytics access

Revision ID: 20260810_0043
Revises: 20260805_0042
Create Date: 2026-08-10 00:00:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260810_0043"
down_revision = "20260805_0042"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "api_key_credentials",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("key_prefix", sa.String(length=16), nullable=False),
        sa.Column("key_hash", sa.String(length=255), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_api_key_credentials_user_id", "api_key_credentials", ["user_id"])
    op.create_index("ix_api_key_credentials_key_prefix", "api_key_credentials", ["key_prefix"])


def downgrade() -> None:
    op.drop_index("ix_api_key_credentials_key_prefix", table_name="api_key_credentials")
    op.drop_index("ix_api_key_credentials_user_id", table_name="api_key_credentials")
    op.drop_table("api_key_credentials")
