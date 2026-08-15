"""add index on operations_onu_signal_current.pon_id

Revision ID: 20260815_0059
Revises: 20260815_0058
Create Date: 2026-08-15 00:00:00
"""
from __future__ import annotations

from alembic import op

revision = "20260815_0059"
down_revision = "20260815_0058"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # EXPLAIN ANALYZE real (70953 linhas, ambiente de teste local) confirmou seq scan de ~840ms
    # filtrando por pon_id sem índice - dimensão usada diretamente na detecção de queda coletiva
    # por PON (pedido do usuário em 2026-08-15), consulta esperada com frequência por
    # monitoramento. pon_no/slot_no ficam de fora por ora - sem evidência real de custo que
    # justifique (menor cardinalidade de filtro isolado, geralmente combinados com pon_id).
    op.create_index("ix_operations_onu_signal_current_pon_id", "operations_onu_signal_current", ["pon_id"])


def downgrade() -> None:
    op.drop_index("ix_operations_onu_signal_current_pon_id", table_name="operations_onu_signal_current")
