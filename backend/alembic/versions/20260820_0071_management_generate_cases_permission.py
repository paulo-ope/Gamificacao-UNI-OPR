"""backfill management:generate_cases for existing access profiles

Revision ID: 20260820_0071
Revises: 20260817_0070
Create Date: 2026-08-20 00:00:00

O botão "Gerar casos do mês" (POST /management/cases/generate) usava a MESMA permissão de
aprovar/rejeitar a decisão da matriz (management:review) - achado real: quem precisava só gerar
(ex.: "Operador Operacional") também ganhava poder de aprovação, e não dava para tirar um sem
tirar o outro. Esta migration separa "gerar" numa permissão própria (management:generate_cases) e
backfilla todo perfil que já tinha review, para ninguém perder acesso a gerar no deploy - dai em
diante um admin pode desmarcar management:review de um perfil sem afetar o botão de gerar.
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260820_0071"
down_revision = "20260817_0070"
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
            sa.text("SELECT profile_id FROM access_profile_permissions WHERE permission = 'management:review'")
        )
    ]
    if not profile_ids:
        return
    existing = {
        row[0]
        for row in bind.execute(
            sa.text("SELECT profile_id FROM access_profile_permissions WHERE permission = 'management:generate_cases'")
        )
    }
    missing = [profile_id for profile_id in profile_ids if profile_id not in existing]
    if missing:
        op.bulk_insert(
            _ACCESS_PROFILE_PERMISSIONS,
            [{"profile_id": profile_id, "permission": "management:generate_cases"} for profile_id in missing],
        )


def downgrade() -> None:
    op.execute(sa.text("DELETE FROM access_profile_permissions WHERE permission = 'management:generate_cases'"))
