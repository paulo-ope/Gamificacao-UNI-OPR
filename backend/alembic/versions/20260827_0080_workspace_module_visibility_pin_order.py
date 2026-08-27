"""sidebar: fixar/reordenar atalhos por usuario (pinned/order_index)

Revision ID: 20260827_0080
Revises: 20260826_0079
Create Date: 2026-08-27 00:00:00

Migracao puramente ADITIVA: duas colunas novas em workspace_module_visibility,
nenhuma tabela existente e afetada.
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "20260827_0080"
down_revision = "20260826_0079"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "workspace_module_visibility",
        sa.Column("pinned", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.add_column(
        "workspace_module_visibility",
        sa.Column("order_index", sa.Integer(), nullable=True),
    )
    op.alter_column("workspace_module_visibility", "pinned", server_default=None)


def downgrade() -> None:
    op.drop_column("workspace_module_visibility", "order_index")
    op.drop_column("workspace_module_visibility", "pinned")
