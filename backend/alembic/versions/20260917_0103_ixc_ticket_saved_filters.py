"""cria support_ixc_ticket_saved_filters

Revision ID: 20260917_0103
Revises: 20260917_0102
Create Date: 2026-09-17 00:00:00

Item 10 do plano de evolução analítica do Atendimento IXC (2026-09-17): "filtros mais fácil de
utilizar e poder salvar visão e ela ser padrão ou não". Recorte SEMPRE pessoal (decisão do
usuário) - `owner_id` não é nullable, diferente de `support_opa_saved_filters` que também aceita
escopo global. `is_default` marca a visão que a tela aplica sozinha ao abrir.
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260917_0103"
down_revision = "20260917_0102"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "support_ixc_ticket_saved_filters",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("filters_json", sa.JSON(), nullable=False),
        sa.Column("is_default", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("owner_id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["owner_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_support_ixc_ticket_saved_filters_owner", "support_ixc_ticket_saved_filters", ["owner_id"]
    )


def downgrade() -> None:
    op.drop_index("ix_support_ixc_ticket_saved_filters_owner", table_name="support_ixc_ticket_saved_filters")
    op.drop_table("support_ixc_ticket_saved_filters")
