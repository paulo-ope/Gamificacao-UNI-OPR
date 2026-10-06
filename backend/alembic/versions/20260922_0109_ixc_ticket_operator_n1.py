"""operador do protocolo IXC (opened_by_user_id) + support_ixc_users

Revision ID: 20260922_0109
Revises: 20260921_0108
Create Date: 2026-09-22 00:00:00

Pedido do usuário (2026-10-06): tela "Atendimento Suporte Interno N1" contando só protocolos
abertos por colaboradores do N1 (grupo 105 do IXC) nos motivos 90 (operacional) e 29 (financeiro).
O IXC guarda quem abriu o protocolo em `su_ticket.id_usuarios`, que já está no `raw_payload` mas
não tinha coluna própria.

Migração ADITIVA: uma coluna nullable + uma tabela nova. O histórico é retroalimentado a partir do
`raw_payload` SÓ para os motivos 29 e 90 (os únicos que a tela usa) - um UPDATE no histórico
inteiro (~550 mil linhas) leria o JSON de todas e gera bloat desnecessário (ver incidente de disco
da VM, 2026-09-12). `id_usuarios = 0` (sem operador) fica NULL.
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260922_0109"
down_revision = "20260921_0108"
branch_labels = None
depends_on = None

N1_SUBJECT_IDS = ("29", "90")


def upgrade() -> None:
    op.add_column("support_ixc_tickets", sa.Column("opened_by_user_id", sa.String(length=40), nullable=True))
    op.create_index("ix_support_ixc_tickets_opened_by_user_id", "support_ixc_tickets", ["opened_by_user_id"])

    op.create_table(
        "support_ixc_users",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("ixc_user_id", sa.String(length=40), nullable=False),
        sa.Column("name", sa.String(length=220), nullable=True),
        sa.Column("group_id", sa.String(length=40), nullable=True),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("synced_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("ixc_user_id", name="uq_support_ixc_users_ixc_user_id"),
    )
    op.create_index("ix_support_ixc_users_ixc_user_id", "support_ixc_users", ["ixc_user_id"])
    op.create_index("ix_support_ixc_users_group_id", "support_ixc_users", ["group_id"])

    dialect = op.get_bind().dialect.name
    operator_expr = (
        "raw_payload->>'id_usuarios'" if dialect == "postgresql" else "json_extract(raw_payload, '$.id_usuarios')"
    )
    subjects = ", ".join(f"'{subject}'" for subject in N1_SUBJECT_IDS)
    op.execute(
        sa.text(
            f"UPDATE support_ixc_tickets SET opened_by_user_id = CAST({operator_expr} AS VARCHAR(40)) "
            f"WHERE subject_id IN ({subjects}) "
            f"AND {operator_expr} IS NOT NULL AND CAST({operator_expr} AS VARCHAR(40)) NOT IN ('', '0')"
        )
    )


def downgrade() -> None:
    op.drop_index("ix_support_ixc_users_group_id", table_name="support_ixc_users")
    op.drop_index("ix_support_ixc_users_ixc_user_id", table_name="support_ixc_users")
    op.drop_table("support_ixc_users")
    op.drop_index("ix_support_ixc_tickets_opened_by_user_id", table_name="support_ixc_tickets")
    op.drop_column("support_ixc_tickets", "opened_by_user_id")
