"""TMA ativo e TMR agrupado do OPA: colunas novas em support_opa_attendances

Revision ID: 20261015_0117
Revises: 20261014_0116
Create Date: 2026-10-15 00:00:00

Conferindo o relatorio por atendente do OPA (07/10 a 14/10), o TMA e o TMR do sistema divergiam: o TMA
contava o silencio do cliente por inteiro e o TMR era a media das medias por conversa. As regras novas
(TMA com cada silencio limitado a 1 h; TMR como media de todas as respostas juntas) reduziram o erro medio
de ~30% para ~15%. Ver opa_ingestion._active_tma_seconds e _effective_tmr_gaps.

Migracao ADITIVA: so colunas nullable. O historico fica NULL ate o backfill noturno reprocessar (mais
recentes primeiro) ou ate rodar o comando de recalculo
(`python -m app.modules.support.recompute_active_metrics`). Enquanto isso os paineis mostram a cobertura.
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20261015_0117"
down_revision = "20261014_0116"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("support_opa_attendances", sa.Column("tma_active_seconds", sa.Integer(), nullable=True))
    op.add_column("support_opa_attendances", sa.Column("tmr_gap_sum_seconds", sa.Integer(), nullable=True))
    op.add_column("support_opa_attendances", sa.Column("tmr_gap_count", sa.Integer(), nullable=True))
    op.add_column("support_opa_attendances", sa.Column("active_metrics_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column("support_opa_attendances", "active_metrics_at")
    op.drop_column("support_opa_attendances", "tmr_gap_count")
    op.drop_column("support_opa_attendances", "tmr_gap_sum_seconds")
    op.drop_column("support_opa_attendances", "tma_active_seconds")
