"""verificação de e-mail na solicitação de acesso (código de 6 dígitos)

Revision ID: 20261010_0111
Revises: 20261010_0110
Create Date: 2026-10-10 00:00:00

`portal_access_requests.email_verified_at` guarda quando a pessoa provou ser dona da caixa de e-mail
informada; `account_action_tokens.access_request_id` liga o código de verificação à solicitação.
Migração ADITIVA, só colunas nullable. Solicitações já existentes ficam SEM verificação de propósito
(decisão do usuário, 2026-10-10): a pessoa reenvia o pedido e confirma o código, sem exceção do admin.
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20261010_0111"
down_revision = "20261010_0110"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("portal_access_requests", sa.Column("email_verified_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("account_action_tokens", sa.Column("access_request_id", sa.Integer(), nullable=True))
    op.create_index("ix_account_action_tokens_access_request_id", "account_action_tokens", ["access_request_id"])
    op.create_foreign_key(
        "fk_account_action_tokens_access_request_id",
        "account_action_tokens",
        "portal_access_requests",
        ["access_request_id"],
        ["id"],
        ondelete="CASCADE",
    )


def downgrade() -> None:
    op.drop_constraint("fk_account_action_tokens_access_request_id", "account_action_tokens", type_="foreignkey")
    op.drop_index("ix_account_action_tokens_access_request_id", table_name="account_action_tokens")
    op.drop_column("account_action_tokens", "access_request_id")
    op.drop_column("portal_access_requests", "email_verified_at")
