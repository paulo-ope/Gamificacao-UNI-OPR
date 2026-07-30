"""scheduling: technician cache + drill-through support

Revision ID: 20260729_0034
Revises: 20260729_0033
Create Date: 2026-07-29

Suporte ao drill-through "qual O.S. está atrasada, com o colaborador completo": adiciona
`first_technician_id` em scheduling_orders (o técnico de campo do primeiro agendamento, distinto do
operador que marcou a agenda) e a tabela de cache `scheduling_technicians` para resolver esse id em
nome sem bater na API do IXC a cada consulta.
"""

from alembic import op
import sqlalchemy as sa


revision = "20260729_0034"
down_revision = "20260729_0033"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("scheduling_orders", sa.Column("first_technician_id", sa.Integer(), nullable=True))
    op.create_index("ix_scheduling_orders_first_technician_id", "scheduling_orders", ["first_technician_id"])

    op.create_table(
        "scheduling_technicians",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("ixc_funcionario_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=180), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_scheduling_technicians_ixc_funcionario_id", "scheduling_technicians", ["ixc_funcionario_id"], unique=True)


def downgrade() -> None:
    op.drop_table("scheduling_technicians")
    op.drop_index("ix_scheduling_orders_first_technician_id", table_name="scheduling_orders")
    op.drop_column("scheduling_orders", "first_technician_id")
