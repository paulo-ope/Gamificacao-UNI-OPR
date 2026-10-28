"""resultados-chave e ações no planejamento do Suporte, com check-in nas ações

Revision ID: 20261028_0122
Revises: 20261021_0120
Create Date: 2026-10-28 00:00:00

Pedido do usuário (2026-10-28): o Projeto passa a ter Resultados-chave e cada Resultado-chave tem
Ações, onde se dá check-in. Reaproveita `support_plan_items` (novos `kind`: key_result e action) e
`support_plan_updates` (o check-in é um andamento com avanço e situação). Só colunas novas, todas
com valor padrão: nada do que já foi lançado muda. É idempotente (pula coluna que já existe), para
poder rodar num banco local onde as colunas foram criadas à mão para testar.

Atenção: a Jornada N1/N2 tem uma migration `20261022_0121` que também parte da `0120`. Quando as
duas estiverem no master, uma delas precisa apontar `down_revision` para a outra (senão o Alembic
acusa duas cabeças).
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20261028_0122"
down_revision = "20261021_0120"
branch_labels = None
depends_on = None

_ITEM_COLUMNS = (
    ("progress", lambda: sa.Column("progress", sa.Integer(), nullable=False, server_default="0")),
    ("health", lambda: sa.Column("health", sa.String(length=20), nullable=True)),
    ("last_check_in_at", lambda: sa.Column("last_check_in_at", sa.DateTime(timezone=True), nullable=True)),
)
_UPDATE_COLUMNS = (
    ("progress", lambda: sa.Column("progress", sa.Integer(), nullable=True)),
    ("health", lambda: sa.Column("health", sa.String(length=20), nullable=True)),
    ("is_check_in", lambda: sa.Column("is_check_in", sa.Boolean(), nullable=False, server_default=sa.false())),
)


def _existing(table: str) -> set[str]:
    return {column["name"] for column in sa.inspect(op.get_bind()).get_columns(table)}


def upgrade() -> None:
    for table, columns in (("support_plan_items", _ITEM_COLUMNS), ("support_plan_updates", _UPDATE_COLUMNS)):
        present = _existing(table)
        for name, build in columns:
            if name not in present:
                op.add_column(table, build())


def downgrade() -> None:
    for table, columns in (("support_plan_updates", _UPDATE_COLUMNS), ("support_plan_items", _ITEM_COLUMNS)):
        present = _existing(table)
        for name, _ in reversed(columns):
            if name in present:
                op.drop_column(table, name)
