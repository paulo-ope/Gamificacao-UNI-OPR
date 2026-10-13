"""add human_wait_seconds (espera pelo humano: 1a resposta humana) to support opa attendances

Revision ID: 20261013_0115
Revises: 20261013_0114
Create Date: 2026-10-13 00:00:00

`human_wait_seconds` = da ultima mensagem do bot (a transferencia) ate a 1a mensagem do atendente
humano (sem bot, da ultima mensagem do cliente). Substitui, na tela, o "1a resposta humana" que
era abertura -> 1a mensagem humana e incluia a conversa com o bot. Migracao ADITIVA, so coluna
nullable; o historico fica NULL ate o backfill noturno de mensagens.
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20261013_0115"
down_revision = "20261013_0114"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("support_opa_attendances", sa.Column("human_wait_seconds", sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column("support_opa_attendances", "human_wait_seconds")
