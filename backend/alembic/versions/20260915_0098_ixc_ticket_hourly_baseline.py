"""Fase 4 da evolução analítica do Atendimento IXC: tabela de baseline hora-do-dia/dia-da-semana

Revision ID: 20260915_0098
Revises: 20260914_0097
Create Date: 2026-09-15 00:00:00

Migração puramente ADITIVA: cria `support_ixc_hourly_baselines`, VAZIA - nenhum dado existente é
tocado. A tabela é populada pelo job diário (`ixc_ticket_baseline.recompute_all_hourly_baselines`,
ligado em `main.py`) na primeira execução depois do deploy; até lá, `detect_bursts` devolve
`basis="none"` pra qualquer escopo (ver `ixc_ticket_baseline.py`).
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260915_0098"
down_revision = "20260914_0097"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "support_ixc_hourly_baselines",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("scope_type", sa.String(length=20), nullable=False),
        sa.Column("scope_id", sa.String(length=120), nullable=True),
        sa.Column("weekday", sa.Integer(), nullable=False),
        sa.Column("hour", sa.Integer(), nullable=False),
        sa.Column("avg_count", sa.Float(), nullable=False, server_default="0"),
        sa.Column("stddev_count", sa.Float(), nullable=False, server_default="0"),
        sa.Column("sample_weeks", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("computed_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "ix_support_ixc_hourly_baseline_scope",
        "support_ixc_hourly_baselines",
        ["scope_type", "scope_id"],
    )
    op.create_unique_constraint(
        "uq_support_ixc_hourly_baseline_scope_slot",
        "support_ixc_hourly_baselines",
        ["scope_type", "scope_id", "weekday", "hour"],
    )


def downgrade() -> None:
    op.drop_constraint(
        "uq_support_ixc_hourly_baseline_scope_slot", "support_ixc_hourly_baselines", type_="unique"
    )
    op.drop_index("ix_support_ixc_hourly_baseline_scope", table_name="support_ixc_hourly_baselines")
    op.drop_table("support_ixc_hourly_baselines")
