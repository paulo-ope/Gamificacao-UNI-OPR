"""account_action_tokens - convite (Fase 2C) e reset de senha (Fase 2E, futuro)

Revision ID: 20260828_0082
Revises: 20260828_0081
Create Date: 2026-08-28 00:00:00

Migration puramente ADITIVA: cria uma tabela nova, não toca em nenhuma tabela existente, nenhuma
métrica e nenhum dado já gravado.

Ver docs/portal-ciclo-vida-conta-colaborador.md seção 8 (modelo de dados sugerido) e seção 5
(Fase 2C - convite seguro com token). A tabela é compartilhada entre convite (`purpose="invite"`,
implementado nesta entrega) e reset de senha por e-mail (`purpose="password_reset"`, Fase 2E,
ainda não implementada) - mesmo mecanismo de token de uso único, pra não duplicar essa lógica
quando a 2E existir.
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260828_0082"
down_revision = "20260828_0081"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "account_action_tokens",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("purpose", sa.String(length=20), nullable=False),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=True),
        sa.Column("email", sa.String(length=180), nullable=False),
        sa.Column("collaborator_id", sa.Integer(), sa.ForeignKey("collaborators.id", ondelete="CASCADE"), nullable=True),
        sa.Column("role", sa.String(length=30), nullable=True),
        sa.Column("token_hash", sa.String(length=255), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="pending"),
        sa.Column("created_by_user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("accepted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
    )
    op.create_index("ix_account_action_tokens_purpose", "account_action_tokens", ["purpose"])
    op.create_index("ix_account_action_tokens_user_id", "account_action_tokens", ["user_id"])
    op.create_index("ix_account_action_tokens_email", "account_action_tokens", ["email"])
    op.create_index("ix_account_action_tokens_collaborator_id", "account_action_tokens", ["collaborator_id"])
    op.create_index("ix_account_action_tokens_status", "account_action_tokens", ["status"])
    op.create_index("ix_account_action_tokens_token_hash", "account_action_tokens", ["token_hash"], unique=True)


def downgrade() -> None:
    op.drop_index("ix_account_action_tokens_token_hash", table_name="account_action_tokens")
    op.drop_index("ix_account_action_tokens_status", table_name="account_action_tokens")
    op.drop_index("ix_account_action_tokens_collaborator_id", table_name="account_action_tokens")
    op.drop_index("ix_account_action_tokens_email", table_name="account_action_tokens")
    op.drop_index("ix_account_action_tokens_user_id", table_name="account_action_tokens")
    op.drop_index("ix_account_action_tokens_purpose", table_name="account_action_tokens")
    op.drop_table("account_action_tokens")
