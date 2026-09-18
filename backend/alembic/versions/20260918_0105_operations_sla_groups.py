"""cria operations_sla_groups e operations_sla_subject_groups

Revision ID: 20260918_0105
Revises: 20260917_0104
Create Date: 2026-09-18 00:00:00

Pedido do usuário em 2026-09-18: o "SLA por tecnologia" da Visão Geral (Ativação/Suporte x Fibra
Urbana/Fibra Rural/Rádio, feature de 2026-09-17) era um dicionário Python fixo
(`operations/technology_group.py`) - sem tela pra editar. Esta migration cria as duas tabelas que
tornam isso configurável (card/grupo/assunto) e semeia com EXATAMENTE os mesmos 2 cards, 6 grupos
e assuntos que já estavam em produção, pra não mudar nada visualmente no primeiro deploy - só
passa a ser editável a partir daqui. Os dados de semeadura ficam inline aqui (não importam
`technology_group.py`) de propósito: uma migration não deve depender de um módulo de app que pode
mudar de forma incompatível depois.
"""
from __future__ import annotations

from datetime import datetime, timezone

from alembic import op
import sqlalchemy as sa


revision = "20260918_0105"
down_revision = "20260917_0104"
branch_labels = None
depends_on = None


# (card_label, group_name, [assuntos granulares exatos como o IXC grava hoje])
_SEED_GROUPS: list[tuple[str, str, list[str]]] = [
    (
        "SLA de Ativação",
        "Ativação Fibra Urbana",
        [
            "Instalação Fibra Urbana",
            "Retorno de Instalação Fibra Urbana",
            "Instalação Evento/Permuta Fibra Urbana",
            "Retorno de Instalação Evento/Permuta Fibra Urbana",
            "Instalação Fibra Urbana com Ativação de Câmeras",
        ],
    ),
    (
        "SLA de Ativação",
        "Ativação Fibra Rural",
        [
            "Instalação Fibra Rural",
            "Retorno de Instalação Fibra Rural",
            "Instalação Evento/Permuta Fibra Rural",
            "Retorno de Instalação Evento/Permuta Fibra Rural",
        ],
    ),
    (
        "SLA de Ativação",
        "Ativação Rádio",
        [
            "Instalação Rádio",
            "Retorno de Instalação Rádio",
            "INSTALACAO RADIO",
            "RETORNO DE INSTALACAO RADIO",
        ],
    ),
    (
        "SLA de Suporte",
        "Suporte Fibra Urbana",
        [
            "Suporte Externo Fibra Urbana",
            "Sem Conexão Fibra Urbana",
            "Alteração na Rede Interna Fibra Urbana",
            "Reincidência de Suporte Fibra Urbana",
            "Sem Conexão (Link LOS)",
            "Troca de Equipamentos",
            "Suporte Streaming/Apps",
            "Regulagem de Sinal",
            "Suporte Prioritário",
            "Manutenção Preventiva Operacional",
            "Ativação de Login Presencial",
            "Remoção de Flashman",
            "Reativação de Suspensão Temporária - Externo",
            "Migração de Rede Neutra",
        ],
    ),
    (
        "SLA de Suporte",
        "Suporte Fibra Rural",
        [
            "Suporte Externo Fibra Rural",
            "Sem Conexão Fibra Rural",
            "Alteração na Rede Interna Fibra Rural",
            "Reincidência de Suporte Fibra Rural",
        ],
    ),
    (
        "SLA de Suporte",
        "Suporte Rádio",
        [
            "Suporte Externo Rádio",
            "Sem Conexão Rádio",
            "Alteração na Rede Interna Rádio",
            "Reincidência de Suporte Rádio",
        ],
    ),
]


def upgrade() -> None:
    op.create_table(
        "operations_sla_groups",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("card_label", sa.String(length=120), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("display_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_by", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name", name="uq_operations_sla_groups_name"),
    )
    op.create_index("ix_operations_sla_groups_card_label", "operations_sla_groups", ["card_label"])
    op.create_index("ix_operations_sla_groups_active", "operations_sla_groups", ["active"])

    op.create_table(
        "operations_sla_subject_groups",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("subject", sa.String(length=220), nullable=False),
        sa.Column("group_id", sa.Integer(), nullable=False),
        sa.Column("updated_by", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["group_id"], ["operations_sla_groups.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["updated_by"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("subject", name="uq_operations_sla_subject_groups_subject"),
    )
    op.create_index("ix_operations_sla_subject_groups_subject", "operations_sla_subject_groups", ["subject"])
    op.create_index("ix_operations_sla_subject_groups_group_id", "operations_sla_subject_groups", ["group_id"])

    now = datetime.now(timezone.utc)
    groups_table = sa.table(
        "operations_sla_groups",
        sa.column("id", sa.Integer),
        sa.column("card_label", sa.String),
        sa.column("name", sa.String),
        sa.column("display_order", sa.Integer),
        sa.column("active", sa.Boolean),
        sa.column("created_at", sa.DateTime),
        sa.column("updated_at", sa.DateTime),
    )
    subjects_table = sa.table(
        "operations_sla_subject_groups",
        sa.column("subject", sa.String),
        sa.column("group_id", sa.Integer),
        sa.column("created_at", sa.DateTime),
        sa.column("updated_at", sa.DateTime),
    )

    connection = op.get_bind()
    groups_table_with_id = sa.table(
        "operations_sla_groups",
        sa.column("id", sa.Integer),
        sa.column("card_label", sa.String),
        sa.column("name", sa.String),
        sa.column("display_order", sa.Integer),
        sa.column("active", sa.Boolean),
        sa.column("created_at", sa.DateTime),
        sa.column("updated_at", sa.DateTime),
    )
    for order, (card_label, name, subjects) in enumerate(_SEED_GROUPS):
        result = connection.execute(
            groups_table_with_id.insert()
            .values(
                card_label=card_label,
                name=name,
                display_order=order,
                active=True,
                created_at=now,
                updated_at=now,
            )
            .returning(groups_table_with_id.c.id)
        )
        group_id = result.scalar_one()
        for subject in subjects:
            connection.execute(
                subjects_table.insert().values(subject=subject, group_id=group_id, created_at=now, updated_at=now)
            )


def downgrade() -> None:
    op.drop_index("ix_operations_sla_subject_groups_group_id", table_name="operations_sla_subject_groups")
    op.drop_index("ix_operations_sla_subject_groups_subject", table_name="operations_sla_subject_groups")
    op.drop_table("operations_sla_subject_groups")
    op.drop_index("ix_operations_sla_groups_active", table_name="operations_sla_groups")
    op.drop_index("ix_operations_sla_groups_card_label", table_name="operations_sla_groups")
    op.drop_table("operations_sla_groups")
