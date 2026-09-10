"""user_permission_overrides - permissão concedida ou negada diretamente numa pessoa

Revision ID: 20260909_0089
Revises: 20260909_0088
Create Date: 2026-09-09 12:00:00

Migration puramente ADITIVA: cria uma tabela nova, não toca em nenhuma tabela existente.

Pedido do usuário: dar (ou tirar) UMA permissão específica de uma pessoa sem precisar criar um
perfil só para ela. A tabela guarda a exceção; `permissions_for_user` (app/core/security.py)
passa a aplicá-la por cima do que o perfil já concede - concessão soma, negação subtrai e vence.
Ver docs/STATUS.md para o desenho completo.
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260909_0089"
down_revision = "20260909_0088"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "user_permission_overrides",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("permission", sa.String(length=120), nullable=False),
        sa.Column("effect", sa.String(length=10), nullable=False),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("created_by", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.CheckConstraint("effect IN ('grant', 'deny')", name="ck_user_permission_override_effect"),
        sa.UniqueConstraint("user_id", "permission", name="uq_user_permission_override"),
    )
    op.create_index("ix_user_permission_overrides_user_id", "user_permission_overrides", ["user_id"])
    op.create_index("ix_user_permission_overrides_permission", "user_permission_overrides", ["permission"])


def downgrade() -> None:
    op.drop_index("ix_user_permission_overrides_permission", table_name="user_permission_overrides")
    op.drop_index("ix_user_permission_overrides_user_id", table_name="user_permission_overrides")
    op.drop_table("user_permission_overrides")
