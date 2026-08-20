"""fix: intelligence_alerts.dedupe_key must not be globally unique

Revision ID: 20260816_0066
Revises: 20260816_0065
Create Date: 2026-08-16 00:00:00

Achado durante a implementacao de alerts.py (Lote C): a migration anterior (0065) criou
`dedupe_key` como UNIQUE na coluna inteira. Isso impede reincidencia - um alerta RESOLVED/
DISMISSED ocuparia a chave pra sempre, e o requisito de teste "evento volta depois de resolvido
-> nova ocorrencia, nunca reaproveitar o alerta antigo" (item 7 dos testes obrigatorios) exige
que uma linha NOVA possa nascer com a mesma dedupe_key depois que a anterior foi encerrada.

A unicidade real passa a ser aplicada em app/modules/intelligence/alerts.py, restrita aos
alertas ATIVOS (nunca aos RESOLVED/DISMISSED/EXPIRED) - o scheduler e sequencial (uma execucao de
monitor por vez, nunca duas do mesmo monitor em paralelo), entao nao ha corrida real a proteger
no banco nesta fase. Ver comentario em models.py::IntelligenceAlert.dedupe_key para o debt
documentado (indice unico parcial, se o scheduler virar multi-worker no futuro).
"""
from __future__ import annotations

from alembic import op

revision = "20260816_0066"
down_revision = "20260816_0065"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # SQLite cria UNIQUE constraints como um indice implicito com o mesmo nome do
    # UniqueConstraint - dropamos pelo nome usado em 0065 (uq_intelligence_alerts_dedupe_key).
    with op.batch_alter_table("intelligence_alerts") as batch_op:
        batch_op.drop_constraint("uq_intelligence_alerts_dedupe_key", type_="unique")
    # O indice normal (nao-unico) ja existe desde 0065 (ix_intelligence_alerts_dedupe_key) -
    # continua servindo a busca por dedupe_key, só deixou de impor unicidade global.


def downgrade() -> None:
    with op.batch_alter_table("intelligence_alerts") as batch_op:
        batch_op.create_unique_constraint("uq_intelligence_alerts_dedupe_key", ["dedupe_key"])
