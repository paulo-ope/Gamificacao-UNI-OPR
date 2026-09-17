"""setor do atendimento IXC (su_ticket.id_ticket_setor -> empresa_setor)

Revision ID: 20260912_0095
Revises: 20260911_0094
Create Date: 2026-09-12 00:00:00

Migration puramente ADITIVA: 2 colunas novas (nullable) em `support_ixc_tickets`, nao toca em
nenhum dado existente. Pedido do usuario (2026-09-12): filtro por setor do atendimento, alem do
motivo - `id_ticket_setor` resolve contra a mesma tabela `empresa_setor` que a O.S. ja usa.
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260912_0095"
down_revision = "20260911_0094"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("support_ixc_tickets", sa.Column("sector_id", sa.String(length=100), nullable=True))
    op.add_column("support_ixc_tickets", sa.Column("sector_name", sa.String(length=220), nullable=True))
    op.create_index("ix_support_ixc_tickets_sector_id", "support_ixc_tickets", ["sector_id"])
    op.create_index("ix_support_ixc_tickets_sector_name", "support_ixc_tickets", ["sector_name"])


def downgrade() -> None:
    op.drop_index("ix_support_ixc_tickets_sector_name", table_name="support_ixc_tickets")
    op.drop_index("ix_support_ixc_tickets_sector_id", table_name="support_ixc_tickets")
    op.drop_column("support_ixc_tickets", "sector_name")
    op.drop_column("support_ixc_tickets", "sector_id")
