"""replace team percentage bands with operational quantity bands

Revision ID: 20260721_0016
Revises: 20260721_0015
Create Date: 2026-07-21 16:20:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision = "20260721_0016"
down_revision = "20260721_0015"
branch_labels = None
depends_on = None


def _foreign_key_name(table: str, column: str) -> str | None:
    for foreign_key in inspect(op.get_bind()).get_foreign_keys(table):
        if foreign_key.get("constrained_columns") == [column]:
            return foreign_key.get("name")
    return None


def upgrade() -> None:
    op.add_column("operations_team_models", sa.Column("median_max_quantity", sa.Integer(), nullable=False, server_default="6"))
    op.add_column("operations_team_models", sa.Column("good_max_quantity", sa.Integer(), nullable=False, server_default="8"))
    op.add_column("operations_team_models", sa.Column("below_target_color", sa.String(length=7), nullable=False, server_default="#fee2e2"))
    op.add_column("operations_team_models", sa.Column("median_color", sa.String(length=7), nullable=False, server_default="#fef3c7"))
    op.add_column("operations_team_models", sa.Column("good_color", sa.String(length=7), nullable=False, server_default="#dcfce7"))
    op.add_column("operations_team_models", sa.Column("excellent_color", sa.String(length=7), nullable=False, server_default="#dbeafe"))
    op.execute(
        """
        UPDATE operations_team_models
        SET median_max_quantity = daily_target + 1,
            good_max_quantity = daily_target + 3,
            below_target_color = critical_color,
            median_color = attention_color,
            good_color = target_color,
            excellent_color = exceeded_color
        """
    )
    for column in (
        "critical_max_percent", "attention_max_percent", "target_max_percent", "zero_color",
        "critical_color", "attention_color", "target_color", "exceeded_color",
    ):
        op.drop_column("operations_team_models", column)

    foreign_key_name = _foreign_key_name("operations_responsible_assignments", "collaborator_id")
    if foreign_key_name:
        op.drop_constraint(foreign_key_name, "operations_responsible_assignments", type_="foreignkey")
    op.drop_index("ix_operations_responsible_assignments_collaborator_id", table_name="operations_responsible_assignments")
    op.drop_column("operations_responsible_assignments", "collaborator_id")


def downgrade() -> None:
    op.add_column("operations_responsible_assignments", sa.Column("collaborator_id", sa.Integer(), nullable=True))
    op.create_foreign_key(
        "operations_responsible_assignments_collaborator_id_fkey",
        "operations_responsible_assignments", "collaborators", ["collaborator_id"], ["id"], ondelete="SET NULL",
    )
    op.create_index("ix_operations_responsible_assignments_collaborator_id", "operations_responsible_assignments", ["collaborator_id"])

    for column, default in (
        ("critical_max_percent", "69"), ("attention_max_percent", "99"), ("target_max_percent", "119"),
        ("zero_color", "#f1f5f9"), ("critical_color", "#fee2e2"), ("attention_color", "#fef3c7"),
        ("target_color", "#dcfce7"), ("exceeded_color", "#dbeafe"),
    ):
        op.add_column("operations_team_models", sa.Column(column, sa.Integer() if "percent" in column else sa.String(length=7), nullable=False, server_default=default))
    op.execute(
        """
        UPDATE operations_team_models
        SET critical_color = below_target_color,
            attention_color = median_color,
            target_color = good_color,
            exceeded_color = excellent_color
        """
    )
    for column in ("median_max_quantity", "good_max_quantity", "below_target_color", "median_color", "good_color", "excellent_color"):
        op.drop_column("operations_team_models", column)
