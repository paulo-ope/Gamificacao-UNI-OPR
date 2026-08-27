"""filtros salvos da tela /suporte (pessoais e globais)

Revision ID: 20260826_0079
Revises: 20260826_0078
Create Date: 2026-08-26 00:00:00

Migration puramente ADITIVA: cria uma tabela nova, nao toca em nenhuma tabela
existente, nenhuma metrica e nenhum dado ja gravado.
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "20260826_0079"
down_revision = "20260826_0078"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "support_opa_saved_filters",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("scope", sa.String(length=20), nullable=False, server_default="personal"),
        sa.Column("filters_json", sa.JSON(), nullable=False),
        sa.Column("owner_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
    )
    op.create_index("ix_support_opa_saved_filters_owner_id", "support_opa_saved_filters", ["owner_id"])
    op.create_index("ix_support_opa_saved_filters_scope_owner", "support_opa_saved_filters", ["scope", "owner_id"])


def downgrade() -> None:
    op.drop_index("ix_support_opa_saved_filters_scope_owner", table_name="support_opa_saved_filters")
    op.drop_index("ix_support_opa_saved_filters_owner_id", table_name="support_opa_saved_filters")
    op.drop_table("support_opa_saved_filters")
