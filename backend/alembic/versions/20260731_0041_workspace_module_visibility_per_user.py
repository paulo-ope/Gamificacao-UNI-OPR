"""workspace module visibility per user

Revision ID: 20260731_0041
Revises: 20260730_0040
Create Date: 2026-07-31 13:00:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260731_0041"
down_revision = "20260730_0040"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "workspace_module_visibility",
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=True),
    )
    op.create_index("ix_workspace_module_visibility_user_id", "workspace_module_visibility", ["user_id"])

    op.alter_column("workspace_module_visibility", "profile_id", nullable=True)
    op.drop_constraint("uq_workspace_module_visibility_profile", "workspace_module_visibility", type_="unique")
    # NULL nunca é igual a NULL em SQL, então uma UNIQUE simples aqui já garante que várias linhas
    # de usuário (profile_id NULL) para o mesmo módulo não colidem entre si - não precisa de índice
    # parcial.
    op.create_unique_constraint(
        "uq_workspace_module_visibility_profile",
        "workspace_module_visibility",
        ["module_key", "profile_id"],
    )
    op.create_unique_constraint(
        "uq_workspace_module_visibility_user",
        "workspace_module_visibility",
        ["module_key", "user_id"],
    )
    op.create_check_constraint(
        "ck_workspace_module_visibility_target",
        "workspace_module_visibility",
        "(profile_id IS NOT NULL AND user_id IS NULL) OR (profile_id IS NULL AND user_id IS NOT NULL)",
    )


def downgrade() -> None:
    op.drop_constraint("ck_workspace_module_visibility_target", "workspace_module_visibility", type_="check")
    op.drop_constraint("uq_workspace_module_visibility_user", "workspace_module_visibility", type_="unique")
    op.drop_constraint("uq_workspace_module_visibility_profile", "workspace_module_visibility", type_="unique")
    op.alter_column("workspace_module_visibility", "profile_id", nullable=False)
    op.create_unique_constraint(
        "uq_workspace_module_visibility_profile",
        "workspace_module_visibility",
        ["module_key", "profile_id"],
    )
    op.drop_index("ix_workspace_module_visibility_user_id", table_name="workspace_module_visibility")
    op.drop_column("workspace_module_visibility", "user_id")
