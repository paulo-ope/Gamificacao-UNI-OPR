"""add managed_regionals (list) to users

Sucessor de managed_regional (migration 20260718_0010): um gestor regional pode cobrir várias
filiais, não só uma - mesmo caso de uso que leadership_profile_regionals resolve pra líderes.
Backfill: quem já tinha managed_regional preenchido ganha uma lista com esse único valor, pra não
perder o vínculo já cadastrado.

Revision ID: 20260718_0011
Revises: 20260718_0010
Create Date: 2026-07-18 00:00:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect

revision = "20260718_0011"
down_revision = "20260718_0010"
branch_labels = None
depends_on = None


def _table_names() -> set[str]:
    return set(inspect(op.get_bind()).get_table_names())


def upgrade() -> None:
    if "users" not in _table_names():
        return
    op.add_column("users", sa.Column("managed_regionals", sa.JSON(), nullable=False, server_default="[]"))
    op.execute(
        """
        UPDATE users
        SET managed_regionals = json_build_array(managed_regional)
        WHERE managed_regional IS NOT NULL
        """
    )
    op.alter_column("users", "managed_regionals", server_default=None)


def downgrade() -> None:
    if "users" not in _table_names():
        return
    op.drop_column("users", "managed_regionals")
