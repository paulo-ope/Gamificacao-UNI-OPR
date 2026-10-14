"""retroalimenta o operador (opened_by_user_id) dos protocolos N2 do IXC (motivos 80 e 81)

Revision ID: 20261014_0116
Revises: 20261013_0115
Create Date: 2026-10-14 00:00:00

Pedido do usuário (2026-10-14): Atendimento Operacional N2 e Dashboard Suporte mostram quantos
atendimentos Interno (motivo 80) e Externo (motivo 81) cada colaborador N2 abriu. A coluna
`opened_by_user_id` só tinha sido retroalimentada para os motivos 29 e 90 (migração 20260922_0109);
os protocolos N2 importados antes disso ficaram sem operador, embora o `raw_payload` traga
`id_usuarios`. Sem este passo, a tabela por colaborador mandava esses protocolos para "Outros
operadores" (~176 só nas duas primeiras semanas de outubro).

Migração só de dados, sem mudança de schema: um UPDATE restrito aos motivos 80 e 81 e às linhas ainda
sem operador (poucas centenas por mês, não o histórico inteiro - ver incidente de disco da VM,
2026-09-12). `id_usuarios = 0` (sem operador de verdade) continua NULL. O `downgrade` não desfaz: não
há como separar o que era NULL de origem do que foi preenchido aqui, e o valor preenchido é correto.
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20261014_0116"
down_revision = "20261013_0115"
branch_labels = None
depends_on = None

N2_SUBJECT_IDS = ("80", "81")


def upgrade() -> None:
    dialect = op.get_bind().dialect.name
    operator_expr = (
        "raw_payload->>'id_usuarios'" if dialect == "postgresql" else "json_extract(raw_payload, '$.id_usuarios')"
    )
    subjects = ", ".join(f"'{subject}'" for subject in N2_SUBJECT_IDS)
    op.execute(
        sa.text(
            f"UPDATE support_ixc_tickets SET opened_by_user_id = CAST({operator_expr} AS VARCHAR(40)) "
            f"WHERE subject_id IN ({subjects}) AND opened_by_user_id IS NULL "
            f"AND {operator_expr} IS NOT NULL AND CAST({operator_expr} AS VARCHAR(40)) NOT IN ('', '0')"
        )
    )


def downgrade() -> None:
    # Migração só de dados: ver a docstring.
    pass
