"""standardize operational team models and calendar performance ranges

Revision ID: 20260721_0017
Revises: 20260721_0016
Create Date: 2026-07-21 17:00:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260721_0017"
down_revision = "20260721_0016"
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
    op.add_column("operations_team_models", sa.Column("attention_from_quantity", sa.Integer(), nullable=False, server_default="4"))
    op.add_column("operations_team_models", sa.Column("highlight_from_quantity", sa.Integer(), nullable=False, server_default="7"))
    op.add_column("operations_team_models", sa.Column("attention_color", sa.String(length=7), nullable=False, server_default="#fef3c7"))
    op.add_column("operations_team_models", sa.Column("achieved_color", sa.String(length=7), nullable=False, server_default="#dcfce7"))
    op.add_column("operations_team_models", sa.Column("above_target_color", sa.String(length=7), nullable=False, server_default="#dbeafe"))
    op.execute(
        """
        UPDATE operations_team_models
        SET attention_from_quantity = GREATEST(1, daily_target - 1),
            highlight_from_quantity = GREATEST(daily_target + 1, good_max_quantity + 1),
            attention_color = median_color,
            achieved_color = good_color,
            above_target_color = excellent_color
        """
    )
    for column in ("median_max_quantity", "good_max_quantity", "median_color", "good_color", "excellent_color"):
        op.drop_column("operations_team_models", column)

    connection = op.get_bind()
    insert_model = sa.text(
        """
        INSERT INTO operations_team_models (
            name, daily_target, attention_from_quantity, highlight_from_quantity,
            below_target_color, attention_color, achieved_color, above_target_color,
            active, created_at, updated_at
        )
        SELECT CAST(:name AS VARCHAR(120)), 5, 4, 7, '#fef2f2', '#fffbeb', '#ecfdf5', '#eff6ff', TRUE, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
        WHERE NOT EXISTS (
            SELECT 1 FROM operations_team_models WHERE LOWER(name) = LOWER(CAST(:name AS VARCHAR(120)))
        )
        """
    )
    for name in STANDARD_MODELS:
        connection.execute(insert_model, {"name": name})


def downgrade() -> None:
    op.add_column("operations_team_models", sa.Column("median_max_quantity", sa.Integer(), nullable=False, server_default="6"))
    op.add_column("operations_team_models", sa.Column("good_max_quantity", sa.Integer(), nullable=False, server_default="8"))
    op.add_column("operations_team_models", sa.Column("median_color", sa.String(length=7), nullable=False, server_default="#fef3c7"))
    op.add_column("operations_team_models", sa.Column("good_color", sa.String(length=7), nullable=False, server_default="#dcfce7"))
    op.add_column("operations_team_models", sa.Column("excellent_color", sa.String(length=7), nullable=False, server_default="#dbeafe"))
    op.execute(
        """
        UPDATE operations_team_models
        SET median_max_quantity = daily_target + 1,
            good_max_quantity = GREATEST(daily_target + 3, highlight_from_quantity - 1),
            median_color = attention_color,
            good_color = achieved_color,
            excellent_color = above_target_color
        """
    )
    for column in ("attention_from_quantity", "highlight_from_quantity", "attention_color", "achieved_color", "above_target_color"):
        op.drop_column("operations_team_models", column)
