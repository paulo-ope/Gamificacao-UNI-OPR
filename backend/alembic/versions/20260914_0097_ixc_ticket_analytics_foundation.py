"""Fase 0 da evolução analítica do Atendimento IXC: índices novos + taxonomia vazia

Revision ID: 20260914_0097
Revises: 20260914_0096
Create Date: 2026-09-14 00:00:00

Migração puramente ADITIVA (mesmo padrão das 5 migrations anteriores deste módulo): dois índices
compostos novos em `support_ixc_tickets` (base pra reincidência e pro baseline hora-do-dia do
burst, Fases 1/4 do plano) e a tabela `support_ixc_taxonomy_mappings`, criada VAZIA - nenhum dado
existente é tocado, nenhum comportamento muda até o código novo (Fases 1+) começar a ler/escrever
nelas.
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260914_0097"
down_revision = "20260914_0096"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_index(
        "ix_support_ixc_tickets_subject_created",
        "support_ixc_tickets",
        ["subject_id", "created_at"],
    )
    op.create_index(
        "ix_support_ixc_tickets_customer_created",
        "support_ixc_tickets",
        ["customer_id", "created_at"],
    )

    op.create_table(
        "support_ixc_taxonomy_mappings",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("subject_id", sa.String(length=100), nullable=False),
        sa.Column("theme_id", sa.String(length=80), nullable=False),
        sa.Column("theme_label", sa.String(length=160), nullable=False),
        sa.Column("category_id", sa.String(length=80), nullable=False),
        sa.Column("category_label", sa.String(length=160), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("effective_from", sa.Date(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "ix_support_ixc_taxonomy_mappings_subject_id",
        "support_ixc_taxonomy_mappings",
        ["subject_id"],
    )
    op.create_index(
        "ix_support_ixc_taxonomy_mappings_theme_id",
        "support_ixc_taxonomy_mappings",
        ["theme_id"],
    )
    op.create_index(
        "ix_support_ixc_taxonomy_mappings_category_id",
        "support_ixc_taxonomy_mappings",
        ["category_id"],
    )
    op.create_index(
        "ix_support_ixc_taxonomy_subject_effective",
        "support_ixc_taxonomy_mappings",
        ["subject_id", "effective_from"],
    )


def downgrade() -> None:
    op.drop_index("ix_support_ixc_taxonomy_subject_effective", table_name="support_ixc_taxonomy_mappings")
    op.drop_index("ix_support_ixc_taxonomy_mappings_category_id", table_name="support_ixc_taxonomy_mappings")
    op.drop_index("ix_support_ixc_taxonomy_mappings_theme_id", table_name="support_ixc_taxonomy_mappings")
    op.drop_index("ix_support_ixc_taxonomy_mappings_subject_id", table_name="support_ixc_taxonomy_mappings")
    op.drop_table("support_ixc_taxonomy_mappings")

    op.drop_index("ix_support_ixc_tickets_customer_created", table_name="support_ixc_tickets")
    op.drop_index("ix_support_ixc_tickets_subject_created", table_name="support_ixc_tickets")
