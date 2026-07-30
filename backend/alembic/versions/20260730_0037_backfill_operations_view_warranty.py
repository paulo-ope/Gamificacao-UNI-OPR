"""backfill operations:view_warranty for existing access profiles

Revision ID: 20260730_0037
Revises: 20260730_0036
Create Date: 2026-07-30 00:00:00

A nova aba Garantias (operations:view_warranty) e uma permissao dedicada, separada de
operations:view_sla, para permitir controle granular no futuro. Mas sem este backfill, todo perfil
que ja enxerga SLA hoje perderia acesso silencioso a uma analise irma no deploy - dai em diante um
admin pode desmarcar a permissao individualmente por perfil.
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260730_0037"
down_revision = "20260730_0036"
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
                "SELECT profile_id FROM access_profile_permissions WHERE permission = 'operations:view_sla'"
            )
        )
    ]
    if not profile_ids:
        return
    existing = {
        row[0]
        for row in bind.execute(
            sa.text(
                "SELECT profile_id FROM access_profile_permissions WHERE permission = 'operations:view_warranty'"
            )
        )
    }
    missing = [profile_id for profile_id in profile_ids if profile_id not in existing]
    if missing:
        op.bulk_insert(
            _ACCESS_PROFILE_PERMISSIONS,
            [{"profile_id": profile_id, "permission": "operations:view_warranty"} for profile_id in missing],
        )


def downgrade() -> None:
    op.execute(sa.text("DELETE FROM access_profile_permissions WHERE permission = 'operations:view_warranty'"))
