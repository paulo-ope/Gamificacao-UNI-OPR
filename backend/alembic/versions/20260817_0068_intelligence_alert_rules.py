"""add intelligence alert rules (configurable rule layer)

Revision ID: 20260817_0068
Revises: 20260817_0067
Create Date: 2026-08-17 00:00:00
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "20260817_0068"
down_revision = "20260817_0067"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "intelligence_alert_rules",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("key", sa.String(length=80), nullable=False),
        sa.Column("name", sa.String(length=160), nullable=False),
        sa.Column("rule_type", sa.String(length=40), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("scope_json", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("params_json", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("severity", sa.String(length=20), nullable=False, server_default="MEDIUM"),
        sa.Column("cooldown_minutes", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("confirm_cycles", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("resolve_cycles", sa.Integer(), nullable=False, server_default="2"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("key", name="uq_intelligence_alert_rules_key"),
    )
    op.create_index("ix_intelligence_alert_rules_key", "intelligence_alert_rules", ["key"])
    op.create_index("ix_intelligence_alert_rules_rule_type", "intelligence_alert_rules", ["rule_type"])
    op.create_index("ix_intelligence_alert_rules_active", "intelligence_alert_rules", ["active"])


def downgrade() -> None:
    op.drop_index("ix_intelligence_alert_rules_active", table_name="intelligence_alert_rules")
    op.drop_index("ix_intelligence_alert_rules_rule_type", table_name="intelligence_alert_rules")
    op.drop_index("ix_intelligence_alert_rules_key", table_name="intelligence_alert_rules")
    op.drop_table("intelligence_alert_rules")
