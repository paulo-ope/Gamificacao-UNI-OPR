"""enable ai.offline_login_clusters by default (user request 2026-08-15)

Revision ID: 20260815_0061
Revises: 20260816_0060
Create Date: 2026-08-15 00:00:00
"""
from __future__ import annotations

from alembic import op

revision = "20260815_0061"
down_revision = "20260815_0059"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Achado real (relatorio do usuario, 2026-08-15): a tool MCP opr_offline_login_clusters nunca
    # existiu, so agora exposta - mas a chave de governanca ja estava semeada com enabled_ai=false
    # desde a Fase 5, inconsistente com a versao REST equivalente
    # (operations.network.offline_login_clusters, ja True). Sem esta migration, a tool nova ficaria
    # bloqueada silenciosamente pra todo mundo ate um admin habilitar manualmente pela tela.
    op.execute(
        "UPDATE ai_endpoints SET enabled_api = true, enabled_mcp = true, enabled_ai = true "
        "WHERE key = 'ai.offline_login_clusters'"
    )


def downgrade() -> None:
    pass
