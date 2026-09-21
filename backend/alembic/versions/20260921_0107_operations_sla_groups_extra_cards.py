"""semeia os 4 cards de SLA por tecnologia extras (endereco, tecnologia, remocao, viabilidade)

Revision ID: 20260921_0107
Revises: 20260918_0105
Create Date: 2026-09-21 00:00:00

Pedido do usuário em 2026-09-21: depois que `20260918_0105` tornou "SLA por tecnologia"
configurável pela tela (Operação Analítica -> Configurações), o usuário cadastrou 4 cards a mais
(Alteração de Endereço, Alteração de Tecnologia, Remoção de Equipamentos, Viabilidades) só no
ambiente local, direto pela tela - como essa configuração vive no banco (não em código), o
deploy do código sozinho não replica isso pra produção, e produção ficou só com os 2 cards
originais (Ativação/Suporte). Esta migration semeia os mesmos 4 cards/grupos/assuntos em
qualquer ambiente que ainda não os tenha, pra igualar local e produção e não depender de
configuração manual repetida em cada ambiente novo.

Assuntos aqui são os mesmos que caíam em `OTHER_TECHNOLOGY_GROUP` ("Outros") em
`operations/technology_group.py` antes de virarem grupos próprios - ver esse arquivo para a
lista original que este seed reproduz.

Idempotente: cada grupo só é inserido se não existir ainda um `operations_sla_groups.name` igual
(a coluna já tem UNIQUE); mesma lógica por assunto. Isso deixa rodar em qualquer ordem/ambiente
sem duplicar nem derrubar a corrente de migrations se um ambiente já tiver criado manualmente
algum desses grupos com o mesmo nome.
"""
from __future__ import annotations

from datetime import datetime, timezone

from alembic import op
import sqlalchemy as sa


revision = "20260921_0107"
down_revision = "20260918_0105"
branch_labels = None
depends_on = None


# (card_label, group_name, [assuntos granulares exatos como o IXC grava hoje])
_SEED_GROUPS: list[tuple[str, str, list[str]]] = [
    (
        "SLA de Alteração de Endereço",
        "Alteração de Endereço Fibra Urbana",
        [
            "Alteração de Endereço Fibra Urbana",
            "Pendência de Alteração de Endereço Fibra Urbana",
            "Retorno de Alteração de Endereço Fibra Urbana",
        ],
    ),
    (
        "SLA de Alteração de Endereço",
        "Alteração de Endereço Fibra Rural",
        [
            "Alteração de Endereço Fibra Rural",
            "Pendência de Alteração de Endereço Fibra Rural",
            "Retorno de Alteração de Endereço Fibra Rural",
        ],
    ),
    (
        "SLA de Alteração de Endereço",
        "Alteração de Endereço Radio",
        [
            "Alteração de Endereço Rádio",
            "Pendência de Alteração de Endereço Rádio",
            "Retorno de Alteração de Endereço Rádio",
        ],
    ),
    (
        "SLA de Alteração de Tecnologia",
        "Alteração da Tecnologia para Fibra/Rádio",
        [
            "Alteração da Tecnologia para Fibra",
            "Alteração da Tecnologia para Rádio",
            "Migração de Tecnologia de Rádio para Fibra",
            "Pendência de Alteração de Tecnologia para Fibra",
            "Pendência de Migração de Tecnologia",
            "Retorno de Alteração de Tecnologia para Fibra",
        ],
    ),
    (
        "SLA de Remoção de Equipamentos",
        "Remoção de Equipamentos",
        [
            "Recuperação de Equipamento por Cobrança",
            "Remoção de Equipamentos",
        ],
    ),
    (
        "SLA de Viabilidades",
        "Viabilidades",
        [
            "Retorno de Viabilidade",
            "Viabilidade",
        ],
    ),
]


def upgrade() -> None:
    connection = op.get_bind()
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
        sa.column("id", sa.Integer),
        sa.column("subject", sa.String),
        sa.column("group_id", sa.Integer),
        sa.column("created_at", sa.DateTime),
        sa.column("updated_at", sa.DateTime),
    )

    existing_group_names = {
        row[0] for row in connection.execute(sa.select(groups_table.c.name)).all()
    }
    existing_subjects = {
        row[0] for row in connection.execute(sa.select(subjects_table.c.subject)).all()
    }

    max_display_order = connection.execute(sa.select(sa.func.max(groups_table.c.display_order))).scalar() or 0

    for offset, (card_label, name, subjects) in enumerate(_SEED_GROUPS, start=1):
        if name in existing_group_names:
            continue
        result = connection.execute(
            groups_table.insert()
            .values(
                card_label=card_label,
                name=name,
                display_order=max_display_order + offset,
                active=True,
                created_at=now,
                updated_at=now,
            )
            .returning(groups_table.c.id)
        )
        group_id = result.scalar_one()
        for subject in subjects:
            if subject in existing_subjects:
                continue
            connection.execute(
                subjects_table.insert().values(subject=subject, group_id=group_id, created_at=now, updated_at=now)
            )
            existing_subjects.add(subject)


def downgrade() -> None:
    # Apaga as linhas-filha explicitamente antes do grupo: SQLite (usado nos testes) não aplica
    # ON DELETE CASCADE por padrão, então confiar só na FK quebraria o downgrade nesse ambiente
    # (mesma pegadinha documentada em `operations/router.py::delete_sla_group`).
    connection = op.get_bind()
    groups_table = sa.table("operations_sla_groups", sa.column("id", sa.Integer), sa.column("name", sa.String))
    subjects_table = sa.table("operations_sla_subject_groups", sa.column("group_id", sa.Integer))
    names = [name for _, name, _ in _SEED_GROUPS]
    group_ids = [
        row[0]
        for row in connection.execute(sa.select(groups_table.c.id).where(groups_table.c.name.in_(names))).all()
    ]
    if group_ids:
        connection.execute(subjects_table.delete().where(subjects_table.c.group_id.in_(group_ids)))
        connection.execute(groups_table.delete().where(groups_table.c.id.in_(group_ids)))
