"""tentativas de confirmação em account_action_tokens (recuperação de senha por código)

Revision ID: 20261010_0110
Revises: 20260922_0109
Create Date: 2026-10-10 00:00:00

Esqueci minha senha por código de 6 dígitos enviado por e-mail: como são só 1 milhão de
combinações, cada código aceita poucas tentativas erradas antes de ser revogado. Migração ADITIVA:
uma coluna com default no servidor, sem reescrita relevante (tabela pequena).
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20261010_0110"
down_revision = "20260922_0109"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "account_action_tokens",
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
    )


def downgrade() -> None:
    op.drop_column("account_action_tokens", "attempts")
