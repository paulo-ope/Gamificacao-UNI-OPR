"""add tma_effective_seconds (TMA efetivo do OPA) to support opa attendances

Revision ID: 20261012_0112
Revises: 20261010_0111
Create Date: 2026-10-12 00:00:00

`tma_effective_seconds` = da 1a mensagem do atendente humano ate a mensagem de conclusao do
atendimento, que e como o painel do OPA calcula o TMA (validado em 2026-10-12 contra os 203
atendimentos da Jennyfer, 04-10/10: 8m55s calculado contra 9m04s no OPA). `tma_seconds` (duracao
total, abertura -> encerramento) NAO muda. Migracao ADITIVA, so coluna nullable: o historico fica
NULL ate o backfill noturno de mensagens reprocessar cada atendimento.
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20261012_0112"
down_revision = "20261010_0111"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("support_opa_attendances", sa.Column("tma_effective_seconds", sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column("support_opa_attendances", "tma_effective_seconds")
