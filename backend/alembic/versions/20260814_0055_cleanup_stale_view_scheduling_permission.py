"""cleanup: remove stale operations:view_scheduling permission rows

Revision ID: 20260814_0055
Revises: 20260814_0054
Create Date: 2026-08-14 00:00:00

A migration 20260729_0033 (módulo de Agendamento) migrou os perfis que tinham
"operations:view_scheduling" para as permissões novas (scheduling:read/sync/manage), mas nunca
apagou a linha antiga de `access_profile_permissions` - ela ficou órfã, sem correspondência em
`PERMISSION_LABELS` (app/core/security.py). Isso só vira problema visível quando alguém tenta
salvar de novo um perfil que ainda carrega essa permissão (a validação de `_validate_permissions`
rejeita corretamente qualquer permissão desconhecida, então o PUT falha com 422 "Permissão
inválida: operations:view_scheduling" - achado real, 2026-08-14).
"""
from __future__ import annotations

from alembic import op

revision = "20260814_0055"
down_revision = "20260814_0054"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("DELETE FROM access_profile_permissions WHERE permission = 'operations:view_scheduling'")


def downgrade() -> None:
    # Limpeza de dado órfão - não há como saber quais linhas existiam antes de apagar (a
    # permissão já era inválida, não fazia sentido re-inserir). Sem downgrade de dados de
    # propósito, como em outras migrations de limpeza deste projeto.
    pass
