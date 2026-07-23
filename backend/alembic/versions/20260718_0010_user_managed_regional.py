"""add managed_regional to users

Perfil "regional_manager_viewer" (Gestor regional) não representa um colaborador individual -
acompanha a equipe inteira de uma filial. `users.collaborator_id` (migration 20260717_0009) é
1-para-1 e não serve pra isso; este campo guarda a regional gerenciada como texto (normalizado na
leitura, igual toda outra comparação de regional no sistema - não existe tabela de regional própria
pra virar FK).

Revision ID: 20260718_0010
Revises: 20260717_0009
Create Date: 2026-07-18 00:00:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect

revision = "20260718_0010"
down_revision = "20260717_0009"
branch_labels = None
depends_on = None


def _table_names() -> set[str]:
    return set(inspect(op.get_bind()).get_table_names())


def upgrade() -> None:
    if "users" not in _table_names():
        return
    op.add_column("users", sa.Column("managed_regional", sa.String(120), nullable=True))


def downgrade() -> None:
    if "users" not in _table_names():
        return
    op.drop_column("users", "managed_regional")
