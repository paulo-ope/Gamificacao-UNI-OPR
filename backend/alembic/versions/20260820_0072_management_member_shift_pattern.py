"""add shift pattern fields to management_operational_members

Revision ID: 20260820_0072
Revises: 20260820_0071
Create Date: 2026-08-20 00:00:00

Pedido do usuário em 2026-08-20: a geração automática de caso diário tratava o dia de folga de
equipes 12x36 (trabalha um dia, folga no seguinte) como "produção zero num dia esperado", abrindo
caso indevido. Estes campos deixam registrado, por colaborador, que ele segue uma escala alternada
e a partir de qual dia contar o ciclo - ver `management.cases.is_scheduled_workday`.
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260820_0072"
down_revision = "20260820_0071"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("management_operational_members", sa.Column("shift_pattern", sa.String(length=20), nullable=True))
    op.add_column("management_operational_members", sa.Column("shift_cycle_days_on", sa.Integer(), nullable=True))
    op.add_column("management_operational_members", sa.Column("shift_cycle_days_off", sa.Integer(), nullable=True))
    op.add_column("management_operational_members", sa.Column("shift_anchor_date", sa.Date(), nullable=True))


def downgrade() -> None:
    op.drop_column("management_operational_members", "shift_anchor_date")
    op.drop_column("management_operational_members", "shift_cycle_days_off")
    op.drop_column("management_operational_members", "shift_cycle_days_on")
    op.drop_column("management_operational_members", "shift_pattern")
