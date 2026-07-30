"""scheduling: saved filters (views) with personal/global visibility

Revision ID: 20260730_0036
Revises: 20260730_0035
Create Date: 2026-07-30

Mesmo conceito de `operations_saved_filters` do módulo Operação Analítica - padronizando a
experiência de filtros entre os dois módulos (pedido do dono do produto). Guarda só o recorte
(filial/setor/assunto/operador/contagem), nunca o período.
"""

from alembic import op
import sqlalchemy as sa


revision = "20260730_0036"
down_revision = "20260730_0035"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "scheduling_saved_filters",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("filters", sa.JSON(), nullable=False),
        sa.Column("visibility", sa.String(length=20), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "name", "visibility", name="uq_scheduling_saved_filters_user_name_visibility"),
    )
    op.create_index("ix_scheduling_saved_filters_user_id", "scheduling_saved_filters", ["user_id"])
    op.create_index("ix_scheduling_saved_filters_visibility", "scheduling_saved_filters", ["visibility"])


def downgrade() -> None:
    op.drop_index("ix_scheduling_saved_filters_visibility", table_name="scheduling_saved_filters")
    op.drop_index("ix_scheduling_saved_filters_user_id", table_name="scheduling_saved_filters")
    op.drop_table("scheduling_saved_filters")
