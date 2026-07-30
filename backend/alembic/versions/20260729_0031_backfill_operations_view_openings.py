"""backfill operations:view_openings for existing access profiles

Revision ID: 20260729_0031
Revises: 20260729_0030
Create Date: 2026-07-29 00:00:00

A aba Aberturas (operations:view_openings) nao tinha permissao propria - qualquer perfil com
operations:read sempre a via, sem controle. Ao introduzir a permissao dedicada, todo perfil de
acesso que ja tinha operations:read precisa ganha-la tambem, senao usuarios que hoje enxergam
Aberturas perderiam o acesso silenciosamente no deploy. Dai em diante, um admin pode desmarcar a
permissao individualmente por perfil.
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260729_0031"
down_revision = "20260729_0030"
branch_labels = None
depends_on = None

_ACCESS_PROFILE_PERMISSIONS = sa.table(
    "access_profile_permissions",
    sa.column("profile_id", sa.Integer),
    sa.column("permission", sa.String),
)


def upgrade() -> None:
    bind = op.get_bind()
    profile_ids = [
        row[0]
        for row in bind.execute(
            sa.text(
                "SELECT profile_id FROM access_profile_permissions WHERE permission = 'operations:read'"
            )
        )
    ]
    if not profile_ids:
        return
    existing = {
        row[0]
        for row in bind.execute(
            sa.text(
                "SELECT profile_id FROM access_profile_permissions WHERE permission = 'operations:view_openings'"
            )
        )
    }
    missing = [profile_id for profile_id in profile_ids if profile_id not in existing]
    if missing:
        op.bulk_insert(
            _ACCESS_PROFILE_PERMISSIONS,
            [{"profile_id": profile_id, "permission": "operations:view_openings"} for profile_id in missing],
        )


def downgrade() -> None:
    op.execute(sa.text("DELETE FROM access_profile_permissions WHERE permission = 'operations:view_openings'"))
