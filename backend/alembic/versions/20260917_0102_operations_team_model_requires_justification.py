"""add requires_justification to operations team models

Revision ID: 20260917_0102
Revises: 20260917_0101
Create Date: 2026-09-17 00:00:00

Usuário pediu para tornar parametrizável se ficar abaixo da meta mínima
("meta mínima de 3 O.S.") precisa ou não abrir cobrança de justificativa no
calendário. Antes deste campo, todo modelo de equipe sempre cobrava - agora
cada modelo decide, com default True para preservar o comportamento atual.
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "20260917_0102"
down_revision = "20260917_0101"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "operations_team_models",
        sa.Column("requires_justification", sa.Boolean(), nullable=False, server_default=sa.true()),
    )
    op.alter_column("operations_team_models", "requires_justification", server_default=None)


def downgrade() -> None:
    op.drop_column("operations_team_models", "requires_justification")
