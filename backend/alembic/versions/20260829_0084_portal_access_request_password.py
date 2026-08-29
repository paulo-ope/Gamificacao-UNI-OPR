"""portal_access_requests.password_hash - aprovacao passa a criar a conta direto

Revision ID: 20260829_0084
Revises: 20260828_0083
Create Date: 2026-08-29 00:00:00

Migration puramente ADITIVA: coluna nova, nullable, sem backfill. Solicitacoes pendentes criadas
antes desta coluna existir (ha pelo menos uma real em uso, 2026-08-28) ficam com `password_hash`
NULL - a aprovacao recusa essas com um erro claro em vez de criar conta sem senha ou apagar dado
existente (ver `approve_access_request`).
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260829_0084"
down_revision = "20260828_0083"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("portal_access_requests", sa.Column("password_hash", sa.String(length=255), nullable=True))


def downgrade() -> None:
    op.drop_column("portal_access_requests", "password_hash")
