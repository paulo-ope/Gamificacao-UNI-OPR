"""bairro do contrato de cliente do IXC - fallback de localizacao do atendimento sem filial

Revision ID: 20260911_0093
Revises: 20260911_0092
Create Date: 2026-09-11 00:10:00

Migration puramente ADITIVA: uma coluna nova (nullable) em `operations_customer_contracts`,
nao toca em nenhum dado existente. Ver docs/STATUS.md 2026-09-11 - pedido do usuario de usar o
contrato do cliente (que tem id_filial e bairro proprios) como fallback quando o atendimento IXC
(su_ticket) nao tem filial valida.
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260911_0093"
down_revision = "20260911_0092"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("operations_customer_contracts", sa.Column("neighborhood", sa.String(length=160), nullable=True))
    op.create_index(
        "ix_operations_customer_contracts_neighborhood", "operations_customer_contracts", ["neighborhood"]
    )


def downgrade() -> None:
    op.drop_index("ix_operations_customer_contracts_neighborhood", table_name="operations_customer_contracts")
    op.drop_column("operations_customer_contracts", "neighborhood")
