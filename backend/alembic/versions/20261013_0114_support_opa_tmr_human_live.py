"""add tmr_human_live_seconds (TMR humano a partir da entrada do atendente) to support opa attendances

Revision ID: 20261013_0114
Revises: 20261013_0113
Create Date: 2026-10-13 00:00:00

TMR HUMANO ao vivo: media dos intervalos entre uma mensagem do cliente e a resposta do atendente
HUMANO, contando so depois da primeira mensagem humana (sem a espera pelo humano, que o
`tmr_seconds` legado inclui). Migracao ADITIVA, so coluna nullable; o historico fica NULL ate o
backfill noturno de mensagens reprocessar cada atendimento.
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20261013_0114"
down_revision = "20261013_0113"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("support_opa_attendances", sa.Column("tmr_human_live_seconds", sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column("support_opa_attendances", "tmr_human_live_seconds")
