"""base de contratos de cliente do IXC por regional + vinculo O.S. -> atendimento (id_ticket)

Revision ID: 20260911_0091
Revises: 20260909_0090
Create Date: 2026-09-11 00:00:00

Migration puramente ADITIVA: cria uma tabela nova (`operations_customer_contracts`, base de
clientes por regional/filial - denominador de "atendimento por 1.000 clientes", ver
docs/STATUS.md 2026-09-11) e adiciona uma coluna nullable (`ticket_id`) em
`operations_orders`, existente. Nao altera nenhum dado ja gravado nem nenhuma metrica atual.
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260911_0091"
down_revision = "20260909_0090"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("operations_orders", sa.Column("ticket_id", sa.String(length=80), nullable=True))
    op.create_index("ix_operations_orders_ticket_id", "operations_orders", ["ticket_id"])

    op.create_table(
        "operations_customer_contracts",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("source_contract_id", sa.String(length=80), nullable=False),
        sa.Column("customer_id", sa.String(length=100), nullable=True),
        sa.Column("regional", sa.String(length=160), nullable=True),
        sa.Column("city", sa.String(length=160), nullable=True),
        sa.Column("status", sa.String(length=40), nullable=True),
        sa.Column("status_internet", sa.String(length=40), nullable=True),
        sa.Column("raw_payload", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("first_imported_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("last_imported_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
    )
    op.create_unique_constraint(
        "uq_operations_customer_contracts_source_id", "operations_customer_contracts", ["source_contract_id"]
    )
    op.create_index(
        "ix_operations_customer_contracts_regional_status",
        "operations_customer_contracts",
        ["regional", "status"],
    )
    op.create_index("ix_operations_customer_contracts_customer_id", "operations_customer_contracts", ["customer_id"])


def downgrade() -> None:
    op.drop_index("ix_operations_customer_contracts_customer_id", table_name="operations_customer_contracts")
    op.drop_index("ix_operations_customer_contracts_regional_status", table_name="operations_customer_contracts")
    op.drop_constraint(
        "uq_operations_customer_contracts_source_id", "operations_customer_contracts", type_="unique"
    )
    op.drop_table("operations_customer_contracts")

    op.drop_index("ix_operations_orders_ticket_id", table_name="operations_orders")
    op.drop_column("operations_orders", "ticket_id")
