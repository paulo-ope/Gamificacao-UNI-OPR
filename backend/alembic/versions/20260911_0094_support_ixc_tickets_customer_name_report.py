"""nome do cliente, titulo e relato protocolado do atendimento IXC

Revision ID: 20260911_0094
Revises: 20260911_0093
Create Date: 2026-09-11 00:15:00

Migration puramente ADITIVA: 3 colunas novas (nullable) em `support_ixc_tickets`, nao toca em
nenhum dado existente. Pedido explicito do usuario (2026-09-11): mostrar nome do cliente e o
relato protocolado (`su_ticket.menssagem`) no no final do drill-down (motivo/protocolo).
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260911_0094"
down_revision = "20260911_0093"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("support_ixc_tickets", sa.Column("customer_name", sa.String(length=220), nullable=True))
    op.add_column("support_ixc_tickets", sa.Column("title", sa.String(length=220), nullable=True))
    op.add_column("support_ixc_tickets", sa.Column("report", sa.Text(), nullable=True))
    op.create_index("ix_support_ixc_tickets_customer_name", "support_ixc_tickets", ["customer_name"])


def downgrade() -> None:
    op.drop_index("ix_support_ixc_tickets_customer_name", table_name="support_ixc_tickets")
    op.drop_column("support_ixc_tickets", "report")
    op.drop_column("support_ixc_tickets", "title")
    op.drop_column("support_ixc_tickets", "customer_name")
