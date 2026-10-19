"""cria support_occurrence_details (diagnóstico e finalização das ocorrências, assunto 211 do IXC)

Revision ID: 20261019_0118
Revises: 20261015_0117
Create Date: 2026-10-19 00:00:00

Pedido do usuário (2026-10-19): a aba Ocorrências do Suporte mostra diagnóstico mais usado,
ocorrências ainda não finalizadas e o horário/relato de cada finalização. Tabela nova e pequena (uma
linha por atendimento do assunto 211, dezenas por dia), sem tocar em `support_ixc_tickets`.
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20261019_0118"
down_revision = "20261015_0117"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "support_occurrence_details",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("source_id", sa.String(length=80), nullable=False),
        sa.Column("diagnosis_id", sa.String(length=40), nullable=True),
        sa.Column("diagnosis_name", sa.String(length=220), nullable=True),
        sa.Column("ticket_status", sa.String(length=20), nullable=True),
        sa.Column("finalized_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finalization_report", sa.Text(), nullable=True),
        sa.Column("finalized_by_id", sa.String(length=40), nullable=True),
        sa.Column("synced_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("source_id", name="uq_support_occurrence_details_source_id"),
    )
    op.create_index("ix_support_occurrence_details_source_id", "support_occurrence_details", ["source_id"])
    op.create_index("ix_support_occurrence_details_finalized_at", "support_occurrence_details", ["finalized_at"])
    op.create_index("ix_support_occurrence_details_diagnosis", "support_occurrence_details", ["diagnosis_id"])


def downgrade() -> None:
    op.drop_index("ix_support_occurrence_details_diagnosis", table_name="support_occurrence_details")
    op.drop_index("ix_support_occurrence_details_finalized_at", table_name="support_occurrence_details")
    op.drop_index("ix_support_occurrence_details_source_id", table_name="support_occurrence_details")
    op.drop_table("support_occurrence_details")
