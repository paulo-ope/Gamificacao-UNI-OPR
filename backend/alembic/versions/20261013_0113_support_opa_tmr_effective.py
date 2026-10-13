"""add tmr_effective_seconds (TMR efetivo, aproximacao do TMR do OPA) to support opa attendances

Revision ID: 20261013_0113
Revises: 20261012_0112
Create Date: 2026-10-13 00:00:00

`tmr_effective_seconds` aproxima o TMR do painel do OPA (que nao e exposto pela API): intervalo da
ultima mensagem do cliente ate a resposta de um atendente, so depois da entrada do humano e
descartando intervalos acima de 1 h. Ajustado contra 5 atendentes exportados do OPA (erro maximo
1,37x). `tmr_seconds` e `tmr_all_responses_seconds` NAO mudam. Migracao ADITIVA, so coluna nullable.
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20261013_0113"
down_revision = "20261012_0112"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("support_opa_attendances", sa.Column("tmr_effective_seconds", sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column("support_opa_attendances", "tmr_effective_seconds")
