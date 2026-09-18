"""add tmr_backfill_attempted_at to support opa attendances

Revision ID: 20260916_0100
Revises: 20260915_0099
Create Date: 2026-09-16 00:00:00

Suporta o backfill noturno de TMR histórico (usuário pediu: "implementa o backfill
de TMR histórico rodando de madrugada" — 45 mil de 55 mil atendimentos ainda sem
`tmr_all_responses_seconds`, cobertura cai a 0% antes de 2026-08-20, quando o campo
entrou em produção). A coluna nova marca a última tentativa (sucesso ou falha) por
atendimento, pra o job noturno priorizar quem nunca foi tentado e não bater sempre
nos mesmos registros com mensagem indisponível na API do OPA.
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "20260916_0100"
down_revision = "20260915_0099"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "support_opa_attendances",
        sa.Column("tmr_backfill_attempted_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "ix_support_opa_attendances_tmr_backfill",
        "support_opa_attendances",
        ["closed_at", "tmr_all_responses_seconds", "tmr_backfill_attempted_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_support_opa_attendances_tmr_backfill", table_name="support_opa_attendances")
    op.drop_column("support_opa_attendances", "tmr_backfill_attempted_at")
