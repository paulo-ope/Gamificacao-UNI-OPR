"""add collaborator_id link to users

Bloco "identidade do portal": hoje o /portal resolve qual colaborador pertence a um usuário
comparando nome ou o prefixo do e-mail (services/portal_dashboard.py), com um fallback perigoso
que devolve o primeiro colocado do ranking pra qualquer admin/operator/viewer sem match - achado
de revisão. Este vínculo direto (`users.collaborator_id`, único e opcional) substitui essa
heurística por uma referência explícita, criada pelo admin ao vincular/criar o acesso na aba
Colaboradores.

Revision ID: 20260717_0009
Revises: 20260717_0008
Create Date: 2026-07-17 00:00:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect

revision = "20260717_0009"
down_revision = "20260717_0008"
branch_labels = None
depends_on = None


def _table_names() -> set[str]:
    return set(inspect(op.get_bind()).get_table_names())


def upgrade() -> None:
    if "users" not in _table_names():
        return
    op.add_column("users", sa.Column("collaborator_id", sa.Integer(), nullable=True))
    op.create_unique_constraint("uq_users_collaborator_id", "users", ["collaborator_id"])
    op.create_foreign_key(
        "fk_users_collaborator_id_collaborators",
        "users",
        "collaborators",
        ["collaborator_id"],
        ["id"],
    )


def downgrade() -> None:
    if "users" not in _table_names():
        return
    op.drop_constraint("fk_users_collaborator_id_collaborators", "users", type_="foreignkey")
    op.drop_constraint("uq_users_collaborator_id", "users", type_="unique")
    op.drop_column("users", "collaborator_id")
