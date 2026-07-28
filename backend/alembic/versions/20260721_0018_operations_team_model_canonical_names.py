"""canonicalize standard operational team model names

Revision ID: 20260721_0018
Revises: 20260721_0017
Create Date: 2026-07-21 17:20:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260721_0018"
down_revision = "20260721_0017"
branch_labels = None
depends_on = None


STANDARD_MODELS = (
    "INSTALAÇÃO CIDADE",
    "TECNICO 12/36H",
    "SUPORTE MOTO",
    "SUPORTE CARRO",
    "RURAL",
    "FAZ TUDO",
    "AUXILIAR",
    "Nao informado",
)


def upgrade() -> None:
    statement = sa.text(
        """
        UPDATE operations_team_models
        SET name = CAST(:name AS VARCHAR(120)), updated_at = CURRENT_TIMESTAMP
        WHERE LOWER(name) = LOWER(CAST(:name AS VARCHAR(120)))
        """
    )
    connection = op.get_bind()
    for name in STANDARD_MODELS:
        connection.execute(statement, {"name": name})


def downgrade() -> None:
    pass
