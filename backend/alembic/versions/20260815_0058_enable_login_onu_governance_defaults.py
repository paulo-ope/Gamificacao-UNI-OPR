"""enable login/onu governance defaults (user request 2026-08-15)

Revision ID: 20260815_0058
Revises: 20260814_0057
Create Date: 2026-08-15 00:00:00
"""
from __future__ import annotations

from alembic import op

revision = "20260815_0058"
down_revision = "20260814_0057"
branch_labels = None
depends_on = None

_ENDPOINT_KEYS = (
    "operations.network.logins",
    "operations.network.onu_signal",
    "ai.login_status",
    "ai.offline_login_clusters",
    "ai.onu_signal",
)


def upgrade() -> None:
    # Deleta as linhas de AiFieldPermission das duas entidades de login/ONU - o startup do backend
    # (`ensure_ai_governance_seed`) reinsere automaticamente com os valores atuais do registro de
    # campos (`field_registry.py`, já com `default_enabled=True` e `filterable`/`groupable`
    # corretos pra regional/pon_id/pon_no/slot_no/campos de data) - mesma técnica de limpeza da
    # migration 20260814_0055, mais simples e confiável que tentar replicar manualmente cada flag
    # aqui. Nenhuma configuração administrativa customizada existia ainda para essas duas entidades
    # (capacidade nova, nunca usada de fato até este pedido), então não há override real perdido.
    op.execute(
        "DELETE FROM ai_field_permissions WHERE entity IN "
        "('operations_login_current_status', 'operations_onu_signal_current')"
    )
    keys_sql = ", ".join(f"'{key}'" for key in _ENDPOINT_KEYS)
    op.execute(
        f"UPDATE ai_endpoints SET enabled_api = true, enabled_mcp = true, enabled_ai = true "
        f"WHERE key IN ({keys_sql})"
    )


def downgrade() -> None:
    # Sem downgrade de dado de propósito - mesmo racional de 20260814_0055 (reverter faria as
    # linhas voltarem a ser criadas desabilitadas no próximo restart, não há estado anterior
    # significativo a restaurar).
    pass
