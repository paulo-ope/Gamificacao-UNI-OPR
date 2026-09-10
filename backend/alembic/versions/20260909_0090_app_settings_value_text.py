"""app_settings.value vira TEXT - achado real salvando o filtro padrão da Visão Geral

Revision ID: 20260909_0090
Revises: 20260909_0089
Create Date: 2026-09-09 15:00:00

Migration puramente de alargamento de coluna, sem perda de dado: `VARCHAR(255)` -> `TEXT`.

Achado ao vivo (2026-09-09): o novo formato do filtro padrão da Visão Geral
(`overview_default_filter`, ver `operations/router.py`) guarda um blob JSON com os filtros de O.S.
E do SGP Suporte - passa fácil de 255 caracteres mesmo com poucas seleções (o dump inclui todo
campo de `OperationSavedFilterValues`, não só os preenchidos). `app_settings` é um key-value
genérico reaproveitado por vários recursos (não só este); não existe motivo pra manter o teto de
255 agora que pelo menos um uso legítimo excede, e nenhum uso existente depende do limite.
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260909_0090"
down_revision = "20260909_0089"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column(
        "app_settings",
        "value",
        existing_type=sa.String(length=255),
        type_=sa.Text(),
        existing_nullable=False,
    )


def downgrade() -> None:
    op.alter_column(
        "app_settings",
        "value",
        existing_type=sa.Text(),
        type_=sa.String(length=255),
        existing_nullable=False,
    )
