"""projeta as etiquetas do atendimento OPA numa coluna filtravel (tag_ids_text)

Revision ID: 20260826_0078
Revises: 20260826_0077
Create Date: 2026-08-26 00:00:00

Etiqueta e a unica dimensao de filtro que a API do OPA so entrega dentro do JSON do
atendimento (`raw_payload.tags[].id_tag`) - nao existe coluna propria como acontece com
atendente/departamento/motivo/canal. Filtrar direto no JSON foi medido na base real
(56.327 atendimentos, 416 etiquetas sincronizadas, 31.195 atendimentos com etiqueta):

    select count(*) ... where exists (
        select 1 from json_array_elements(raw_payload->'tags') t where t->>'id_tag' = :tag
    )
    -> ~410 ms por consulta

A tela de Visao Geral dispara cerca de 8 agregacoes por carga, o que colocaria ~3 s so
no filtro de etiqueta. Por isso a projecao numa coluna de texto delimitada.

Formato: sempre com separador nas DUAS pontas (",id1,id2," ou "," quando nao ha etiqueta),
para que `LIKE '%,id,%'` nunca case com um id que apenas contenha outro como prefixo ou
sufixo. Ver `SupportOpaAttendance.tag_ids_text` e `opa_filters.TAG_SEPARATOR`.

BACKFILL LOCAL: esta migration preenche os atendimentos ja importados a partir do proprio
`raw_payload` da mesma linha. Nao chama a API do OPA, nao importa nada, nao altera nenhuma
metrica (TMA/TMR/bot-humano ficam intactos) - so projeta um dado que ja estava gravado para
uma coluna consultavel. Sem isso o filtro de etiqueta nasceria funcionando apenas para
atendimentos importados dali pra frente, o que seria pior que nao ter o filtro (o usuario
veria "nenhum resultado" para historico que existe).
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "20260826_0078"
down_revision = "20260826_0077"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("support_opa_attendances", sa.Column("tag_ids_text", sa.String(length=2000), nullable=True))

    if op.get_bind().dialect.name != "postgresql":
        # Em SQLite (suite de testes) as tabelas nascem do metadata via create_all e
        # nao ha historico para reprojetar - o backfill nao se aplica.
        return

    # 1) Todo atendimento ja importado passa a declarar explicitamente "sem etiqueta".
    #    NULL continuaria significando "nao sei", e aqui a gente sabe: o payload esta salvo.
    op.execute(sa.text("UPDATE support_opa_attendances SET tag_ids_text = ','"))

    # 2) Quem tem etiqueta recebe a lista real. `json_typeof` guarda contra payload em que
    #    `tags` nao veio como array (json_array_elements explodiria nesses casos).
    op.execute(
        sa.text(
            """
            UPDATE support_opa_attendances AS a
            SET tag_ids_text = sub.ids
            FROM (
                SELECT
                    inner_a.id AS id,
                    ',' || string_agg(DISTINCT tag.value ->> 'id_tag', ',') || ',' AS ids
                FROM support_opa_attendances AS inner_a
                CROSS JOIN LATERAL json_array_elements(inner_a.raw_payload -> 'tags') AS tag(value)
                WHERE json_typeof(inner_a.raw_payload -> 'tags') = 'array'
                  AND tag.value ->> 'id_tag' IS NOT NULL
                GROUP BY inner_a.id
            ) AS sub
            WHERE a.id = sub.id
            """
        )
    )


def downgrade() -> None:
    op.drop_column("support_opa_attendances", "tag_ids_text")
