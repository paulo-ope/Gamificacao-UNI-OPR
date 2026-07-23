"""simplify operational team performance bands

Revision ID: 20260721_0019
Revises: 20260721_0018
Create Date: 2026-07-21 17:45:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260721_0019"
down_revision = "20260721_0018"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column(
        "operations_team_models",
        "attention_from_quantity",
        new_column_name="median_from_quantity",
        existing_type=sa.Integer(),
        existing_nullable=False,
        server_default="3",
    )
    op.add_column(
        "operations_team_models",
        sa.Column("good_from_quantity", sa.Integer(), nullable=False, server_default="4"),
    )
    op.execute(
        """
        UPDATE operations_team_models
        SET daily_target = GREATEST(daily_target, 4),
            median_from_quantity = GREATEST(2, GREATEST(daily_target, 4) - 2),
            good_from_quantity = GREATEST(3, GREATEST(daily_target, 4) - 1)
        """
    )
    op.alter_column(
        "operations_team_models",
        "attention_color",
        new_column_name="median_color",
        existing_type=sa.String(length=7),
        existing_nullable=False,
    )
    op.alter_column(
        "operations_team_models",
        "achieved_color",
        new_column_name="good_color",
        existing_type=sa.String(length=7),
        existing_nullable=False,
    )
    op.alter_column(
        "operations_team_models",
        "above_target_color",
        new_column_name="excellent_color",
        existing_type=sa.String(length=7),
        existing_nullable=False,
    )
    op.drop_column("operations_team_models", "highlight_from_quantity")


def downgrade() -> None:
    op.add_column(
        "operations_team_models",
        sa.Column("highlight_from_quantity", sa.Integer(), nullable=False, server_default="7"),
    )
    op.execute(
        """
        UPDATE operations_team_models
        SET highlight_from_quantity = daily_target + 2
        """
    )
    op.alter_column(
        "operations_team_models",
        "median_color",
        new_column_name="attention_color",
        existing_type=sa.String(length=7),
        existing_nullable=False,
    )
    op.alter_column(
        "operations_team_models",
        "good_color",
        new_column_name="achieved_color",
        existing_type=sa.String(length=7),
        existing_nullable=False,
    )
    op.alter_column(
        "operations_team_models",
        "excellent_color",
        new_column_name="above_target_color",
        existing_type=sa.String(length=7),
        existing_nullable=False,
    )
    op.drop_column("operations_team_models", "good_from_quantity")
    op.alter_column(
        "operations_team_models",
        "median_from_quantity",
        new_column_name="attention_from_quantity",
        existing_type=sa.Integer(),
        existing_nullable=False,
        server_default="4",
    )
