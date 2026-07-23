"""operations team models and responsible assignments

Revision ID: 20260721_0015
Revises: 20260721_0014
Create Date: 2026-07-21 15:00:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision = "20260721_0015"
down_revision = "20260721_0014"
branch_labels = None
depends_on = None


def _tables() -> set[str]:
    return set(inspect(op.get_bind()).get_table_names())


def upgrade() -> None:
    tables = _tables()
    if "operations_team_models" not in tables:
        op.create_table(
            "operations_team_models",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("name", sa.String(length=120), nullable=False),
            sa.Column("daily_target", sa.Integer(), nullable=False, server_default="5"),
            sa.Column("critical_max_percent", sa.Integer(), nullable=False, server_default="69"),
            sa.Column("attention_max_percent", sa.Integer(), nullable=False, server_default="99"),
            sa.Column("target_max_percent", sa.Integer(), nullable=False, server_default="119"),
            sa.Column("zero_color", sa.String(length=7), nullable=False, server_default="#f1f5f9"),
            sa.Column("critical_color", sa.String(length=7), nullable=False, server_default="#fee2e2"),
            sa.Column("attention_color", sa.String(length=7), nullable=False, server_default="#fef3c7"),
            sa.Column("target_color", sa.String(length=7), nullable=False, server_default="#dcfce7"),
            sa.Column("exceeded_color", sa.String(length=7), nullable=False, server_default="#dbeafe"),
            sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column("created_by", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.UniqueConstraint("name", name="uq_operations_team_models_name"),
        )
        op.create_index("ix_operations_team_models_active", "operations_team_models", ["active"])
    if "operations_responsible_assignments" not in tables:
        op.create_table(
            "operations_responsible_assignments",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("responsible_name", sa.String(length=180), nullable=False),
            sa.Column("regional", sa.String(length=160), nullable=False),
            sa.Column("team_model_id", sa.Integer(), sa.ForeignKey("operations_team_models.id", ondelete="SET NULL"), nullable=True),
            sa.Column("collaborator_id", sa.Integer(), sa.ForeignKey("collaborators.id", ondelete="SET NULL"), nullable=True),
            sa.Column("updated_by", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.UniqueConstraint("responsible_name", "regional", name="uq_operations_responsible_assignment_identity"),
        )
        for column in ("responsible_name", "regional", "team_model_id", "collaborator_id"):
            op.create_index(f"ix_operations_responsible_assignments_{column}", "operations_responsible_assignments", [column])


def downgrade() -> None:
    tables = _tables()
    if "operations_responsible_assignments" in tables:
        op.drop_table("operations_responsible_assignments")
    if "operations_team_models" in tables:
        op.drop_table("operations_team_models")
