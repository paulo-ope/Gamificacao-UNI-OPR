"""operations orders: add neighborhood/latitude/longitude, confirmed against real IXC data

Revision ID: 20260811_0048
Revises: 20260811_0047
Create Date: 2026-08-11 02:00:00

Confirmado contra uma amostra real de 104k+ O.S. já importadas (consulta direta ao banco local):
`raw_payload` traz "bairro" (~96% preenchido), "latitude" e "longitude" (~92% preenchidas) como
campos SEPARADOS do IXC - diferente de número/CEP, que só existem embutidos dentro da string única
de "endereco" (ex.: "Rua Curitiba, 2477 - Nova Brasília Ji-Paraná RO - 76908-650"), sem chave
própria em nenhuma amostra observada. "descricao"/"descricao_servico"/"relato_tecnico"/"relato"/
"endereco_os"/"endereco_cliente"/"logradouro"/"complemento_endereco"/"ponto_referencia"/
"referencia_endereco" (candidatas antigas em schemas.py) NUNCA aparecem em nenhuma das 104.203
linhas verificadas - removidas em conjunto com esta migration (ver schemas.py).

Backfill: extrai as três colunas do `raw_payload` já armazenado (sem precisar reconsultar o IXC).
Latitude/longitude usam vírgula como separador decimal em parte dos registros (achado real,
confirmado em 177 linhas) - REPLACE(...,',','.') antes do cast, mesma conversão de
`_float_or_none` em ixc_ingestion.py.
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260811_0048"
down_revision = "20260811_0047"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("operations_orders", sa.Column("neighborhood", sa.String(length=160), nullable=True))
    op.add_column("operations_orders", sa.Column("latitude", sa.Float(), nullable=True))
    op.add_column("operations_orders", sa.Column("longitude", sa.Float(), nullable=True))
    op.create_index(
        "ix_operations_orders_neighborhood", "operations_orders", ["neighborhood"], unique=False
    )

    # `raw_payload` é do tipo `json` (não `jsonb`) - o operador `?` (existência de chave) só existe
    # para `jsonb`, mas não precisamos dele aqui: `->>'chave'` já resolve pra NULL tanto numa chave
    # ausente quanto num valor vazio, então o WHERE só precisa filtrar o que sobra depois disso.
    op.execute(
        """
        UPDATE operations_orders
        SET neighborhood = NULLIF(TRIM(raw_payload->>'bairro'), '')
        """
    )
    op.execute(
        """
        UPDATE operations_orders
        SET latitude = REPLACE(raw_payload->>'latitude', ',', '.')::double precision
        WHERE NULLIF(TRIM(raw_payload->>'latitude'), '') IS NOT NULL
          AND REPLACE(raw_payload->>'latitude', ',', '.') ~ '^-?[0-9]+\\.?[0-9]*$'
        """
    )
    op.execute(
        """
        UPDATE operations_orders
        SET longitude = REPLACE(raw_payload->>'longitude', ',', '.')::double precision
        WHERE NULLIF(TRIM(raw_payload->>'longitude'), '') IS NOT NULL
          AND REPLACE(raw_payload->>'longitude', ',', '.') ~ '^-?[0-9]+\\.?[0-9]*$'
        """
    )


def downgrade() -> None:
    op.drop_index("ix_operations_orders_neighborhood", table_name="operations_orders")
    op.drop_column("operations_orders", "longitude")
    op.drop_column("operations_orders", "latitude")
    op.drop_column("operations_orders", "neighborhood")
