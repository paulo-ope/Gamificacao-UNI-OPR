"""workspace module visibility

Revision ID: 20260730_0040
Revises: 20260730_0039
Create Date: 2026-07-30 23:55:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260730_0040"
down_revision = "20260730_0039"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "workspace_module_visibility",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("module_key", sa.String(length=80), nullable=False),
        sa.Column("profile_id", sa.Integer(), sa.ForeignKey("access_profiles.id", ondelete="CASCADE"), nullable=False),
        sa.Column("visible", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("updated_by", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("module_key", "profile_id", name="uq_workspace_module_visibility_profile"),
    )
    op.create_index("ix_workspace_module_visibility_module_key", "workspace_module_visibility", ["module_key"])
    op.create_index("ix_workspace_module_visibility_profile_id", "workspace_module_visibility", ["profile_id"])
    op.create_index("ix_workspace_module_visibility_visible", "workspace_module_visibility", ["visible"])


def downgrade() -> None:
    op.drop_index("ix_workspace_module_visibility_visible", table_name="workspace_module_visibility")
    op.drop_index("ix_workspace_module_visibility_profile_id", table_name="workspace_module_visibility")
    op.drop_index("ix_workspace_module_visibility_module_key", table_name="workspace_module_visibility")
    op.drop_table("workspace_module_visibility")

