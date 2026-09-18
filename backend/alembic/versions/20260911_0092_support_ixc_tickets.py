"""atendimento real do IXC (su_ticket) dentro do modulo Suporte/SGP

Revision ID: 20260911_0092
Revises: 20260911_0091
Create Date: 2026-09-11 00:05:00

Migration puramente ADITIVA: cria duas tabelas novas (`support_ixc_tickets_raw` e
`support_ixc_tickets`), nao toca em nenhuma tabela existente. Ver docs/STATUS.md 2026-09-11 -
decisao deliberada de unificar atendimento IXC (su_ticket, o protocolo que dispara a O.S.) e
atendimento OPA Suite (chat, ja existente em support_opa_attendances) dentro do mesmo modulo.
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260911_0092"
down_revision = "20260911_0091"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "support_ixc_tickets_raw",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("source_id", sa.String(length=80), nullable=False),
        sa.Column("payload_json", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("source_updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("synced_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
    )
    op.create_unique_constraint("uq_support_ixc_tickets_raw_source_id", "support_ixc_tickets_raw", ["source_id"])
    op.create_index("ix_support_ixc_tickets_raw_created_at", "support_ixc_tickets_raw", ["created_at"])
    op.create_index("ix_support_ixc_tickets_raw_source_updated_at", "support_ixc_tickets_raw", ["source_updated_at"])

    op.create_table(
        "support_ixc_tickets",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("source_id", sa.String(length=80), nullable=False),
        sa.Column("protocol", sa.String(length=120), nullable=True),
        sa.Column("customer_id", sa.String(length=100), nullable=True),
        sa.Column("contract_id", sa.String(length=100), nullable=True),
        sa.Column("regional", sa.String(length=160), nullable=True),
        sa.Column("city", sa.String(length=160), nullable=True),
        sa.Column("neighborhood", sa.String(length=160), nullable=True),
        sa.Column("locality_type", sa.String(length=20), nullable=True),
        sa.Column("subject_id", sa.String(length=100), nullable=True),
        sa.Column("subject_name", sa.String(length=220), nullable=True),
        sa.Column("status", sa.String(length=40), nullable=True),
        sa.Column("sub_status", sa.String(length=40), nullable=True),
        sa.Column("channel_id", sa.String(length=100), nullable=True),
        sa.Column("workflow_process_id", sa.String(length=100), nullable=True),
        sa.Column("priority", sa.String(length=40), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("source_updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("raw_payload", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("first_imported_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("last_imported_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
    )
    op.create_unique_constraint("uq_support_ixc_tickets_source_id", "support_ixc_tickets", ["source_id"])
    op.create_index("ix_support_ixc_tickets_source_id", "support_ixc_tickets", ["source_id"])
    op.create_index("ix_support_ixc_tickets_protocol", "support_ixc_tickets", ["protocol"])
    op.create_index("ix_support_ixc_tickets_customer_id", "support_ixc_tickets", ["customer_id"])
    op.create_index("ix_support_ixc_tickets_contract_id", "support_ixc_tickets", ["contract_id"])
    op.create_index("ix_support_ixc_tickets_regional", "support_ixc_tickets", ["regional"])
    op.create_index("ix_support_ixc_tickets_city", "support_ixc_tickets", ["city"])
    op.create_index("ix_support_ixc_tickets_neighborhood", "support_ixc_tickets", ["neighborhood"])
    op.create_index("ix_support_ixc_tickets_locality_type", "support_ixc_tickets", ["locality_type"])
    op.create_index("ix_support_ixc_tickets_subject_id", "support_ixc_tickets", ["subject_id"])
    op.create_index("ix_support_ixc_tickets_subject_name", "support_ixc_tickets", ["subject_name"])
    op.create_index("ix_support_ixc_tickets_status", "support_ixc_tickets", ["status"])
    op.create_index("ix_support_ixc_tickets_sub_status", "support_ixc_tickets", ["sub_status"])
    op.create_index("ix_support_ixc_tickets_channel_id", "support_ixc_tickets", ["channel_id"])
    op.create_index("ix_support_ixc_tickets_created_at", "support_ixc_tickets", ["created_at"])
    op.create_index("ix_support_ixc_tickets_source_updated_at", "support_ixc_tickets", ["source_updated_at"])
    op.create_index("ix_support_ixc_tickets_regional_created", "support_ixc_tickets", ["regional", "created_at"])
    op.create_index("ix_support_ixc_tickets_city_neighborhood", "support_ixc_tickets", ["city", "neighborhood"])


def downgrade() -> None:
    op.drop_table("support_ixc_tickets")
    op.drop_table("support_ixc_tickets_raw")
