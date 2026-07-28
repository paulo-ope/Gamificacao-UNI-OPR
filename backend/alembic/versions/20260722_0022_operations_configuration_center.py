"""add operational configuration center structures

Revision ID: 20260722_0022
Revises: 20260722_0021
Create Date: 2026-07-22 02:30:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260722_0022"
down_revision = "20260722_0021"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "operations_team_target_rules",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("team_model_id", sa.Integer(), sa.ForeignKey("operations_team_models.id", ondelete="CASCADE"), nullable=False),
        sa.Column("period_type", sa.String(length=20), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("median_from_quantity", sa.Integer(), nullable=False),
        sa.Column("good_from_quantity", sa.Integer(), nullable=False),
        sa.Column("target_quantity", sa.Integer(), nullable=False),
        sa.Column("start_time", sa.Time(), nullable=True),
        sa.Column("end_time", sa.Time(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("team_model_id", "period_type", name="uq_operations_team_target_rule_period"),
    )
    op.create_index("ix_operations_team_target_rules_team_model_id", "operations_team_target_rules", ["team_model_id"])
    op.create_index("ix_operations_team_target_rule_model_period", "operations_team_target_rules", ["team_model_id", "period_type"])
    op.execute(
        """
        INSERT INTO operations_team_target_rules
            (team_model_id, period_type, enabled, median_from_quantity, good_from_quantity, target_quantity, start_time, end_time)
        SELECT model.id, rule.period_type,
               CASE WHEN rule.period_type = 'sunday' THEN FALSE ELSE TRUE END,
               CASE WHEN rule.period_type = 'monthly' THEN model.median_from_quantity * 22 ELSE model.median_from_quantity END,
               CASE WHEN rule.period_type = 'monthly' THEN model.good_from_quantity * 22 ELSE model.good_from_quantity END,
               CASE WHEN rule.period_type = 'monthly' THEN model.daily_target * 22 ELSE model.daily_target END,
               CASE WHEN rule.period_type = 'monthly' THEN NULL ELSE TIME '08:00' END,
               CASE WHEN rule.period_type = 'monthly' THEN NULL ELSE TIME '18:00' END
        FROM operations_team_models model
        CROSS JOIN (VALUES ('weekday'), ('saturday'), ('sunday'), ('monthly')) AS rule(period_type)
        """
    )

    op.create_table(
        "operations_subject_type_mappings",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("subject", sa.String(length=220), nullable=False),
        sa.Column("os_type", sa.String(length=160), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("updated_by", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("subject", name="uq_operations_subject_type_mapping_subject"),
    )
    op.create_index("ix_operations_subject_type_mappings_subject", "operations_subject_type_mappings", ["subject"])
    op.create_index("ix_operations_subject_type_mappings_os_type", "operations_subject_type_mappings", ["os_type"])
    op.create_index("ix_operations_subject_type_mappings_active", "operations_subject_type_mappings", ["active"])
    op.execute(
        """
        INSERT INTO operations_subject_type_mappings (subject, os_type, active)
        SELECT os_subject, MIN(os_type), TRUE
        FROM operations_orders
        WHERE os_subject IS NOT NULL AND os_subject <> ''
          AND os_type IS NOT NULL AND os_type <> ''
          AND os_type <> 'Pendente de classificação'
        GROUP BY os_subject
        ON CONFLICT (subject) DO NOTHING
        """
    )


def downgrade() -> None:
    op.drop_table("operations_subject_type_mappings")
    op.drop_table("operations_team_target_rules")
