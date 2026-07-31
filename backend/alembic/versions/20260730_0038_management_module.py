"""management module

Revision ID: 20260730_0038
Revises: 20260730_0037
Create Date: 2026-07-30 00:37:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260730_0038"
down_revision = "20260730_0037"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "management_operational_members",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("collaborator_id", sa.Integer(), sa.ForeignKey("collaborators.id", ondelete="SET NULL"), nullable=True),
        sa.Column("ixc_employee_id", sa.Integer(), nullable=True),
        sa.Column("responsible_name", sa.String(length=180), nullable=False),
        sa.Column("regional", sa.String(length=160), nullable=False),
        sa.Column("supervisor_user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("team_model_id", sa.Integer(), sa.ForeignKey("operations_team_models.id", ondelete="SET NULL"), nullable=True),
        sa.Column("status", sa.String(length=40), nullable=False, server_default="pending_validation"),
        sa.Column("source", sa.String(length=40), nullable=False, server_default="operations"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("last_order_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("validated_by", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("validated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("responsible_name", "regional", name="uq_management_member_name_regional"),
    )
    op.create_index("ix_management_operational_members_collaborator_id", "management_operational_members", ["collaborator_id"])
    op.create_index("ix_management_operational_members_ixc_employee_id", "management_operational_members", ["ixc_employee_id"])
    op.create_index("ix_management_operational_members_responsible_name", "management_operational_members", ["responsible_name"])
    op.create_index("ix_management_operational_members_regional", "management_operational_members", ["regional"])
    op.create_index("ix_management_operational_members_status", "management_operational_members", ["status"])
    op.create_index("ix_management_member_supervisor_status", "management_operational_members", ["supervisor_user_id", "status"])

    op.create_table(
        "management_case_reasons",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(length=140), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("requires_description", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("name", name="uq_management_case_reason_name"),
    )
    op.create_index("ix_management_case_reasons_name", "management_case_reasons", ["name"])
    op.create_index("ix_management_case_reasons_active", "management_case_reasons", ["active"])

    op.create_table(
        "management_cases",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("case_type", sa.String(length=60), nullable=False),
        sa.Column("source_module", sa.String(length=40), nullable=False),
        sa.Column("reference_date", sa.Date(), nullable=True),
        sa.Column("reference_month", sa.Integer(), nullable=True),
        sa.Column("reference_year", sa.Integer(), nullable=True),
        sa.Column("regional", sa.String(length=160), nullable=True),
        sa.Column("collaborator_id", sa.Integer(), sa.ForeignKey("collaborators.id", ondelete="SET NULL"), nullable=True),
        sa.Column("responsible_name", sa.String(length=180), nullable=True),
        sa.Column("supervisor_user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("team_model_id", sa.Integer(), sa.ForeignKey("operations_team_models.id", ondelete="SET NULL"), nullable=True),
        sa.Column("metric_name", sa.String(length=120), nullable=False),
        sa.Column("expected_value", sa.Float(), nullable=True),
        sa.Column("actual_value", sa.Float(), nullable=True),
        sa.Column("deviation_value", sa.Float(), nullable=True),
        sa.Column("severity", sa.String(length=20), nullable=False, server_default="medium"),
        sa.Column("status", sa.String(length=30), nullable=False, server_default="pending"),
        sa.Column("reason_id", sa.Integer(), sa.ForeignKey("management_case_reasons.id", ondelete="SET NULL"), nullable=True),
        sa.Column("justification_text", sa.Text(), nullable=True),
        sa.Column("action_plan", sa.Text(), nullable=True),
        sa.Column("due_date", sa.Date(), nullable=True),
        sa.Column("created_by", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("justified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("reviewed_by", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_management_cases_case_type", "management_cases", ["case_type"])
    op.create_index("ix_management_cases_status", "management_cases", ["status"])
    op.create_index("ix_management_case_status_severity", "management_cases", ["status", "severity"])
    op.create_index("ix_management_case_period_regional", "management_cases", ["reference_year", "reference_month", "regional"])

    op.create_table(
        "management_case_comments",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("case_id", sa.Integer(), sa.ForeignKey("management_cases.id", ondelete="CASCADE"), nullable=False),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("comment", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_management_case_comments_case_id", "management_case_comments", ["case_id"])


def downgrade() -> None:
    op.drop_index("ix_management_case_comments_case_id", table_name="management_case_comments")
    op.drop_table("management_case_comments")
    op.drop_index("ix_management_case_period_regional", table_name="management_cases")
    op.drop_index("ix_management_case_status_severity", table_name="management_cases")
    op.drop_index("ix_management_cases_status", table_name="management_cases")
    op.drop_index("ix_management_cases_case_type", table_name="management_cases")
    op.drop_table("management_cases")
    op.drop_index("ix_management_case_reasons_active", table_name="management_case_reasons")
    op.drop_index("ix_management_case_reasons_name", table_name="management_case_reasons")
    op.drop_table("management_case_reasons")
    op.drop_index("ix_management_member_supervisor_status", table_name="management_operational_members")
    op.drop_index("ix_management_operational_members_status", table_name="management_operational_members")
    op.drop_index("ix_management_operational_members_regional", table_name="management_operational_members")
    op.drop_index("ix_management_operational_members_responsible_name", table_name="management_operational_members")
    op.drop_index("ix_management_operational_members_ixc_employee_id", table_name="management_operational_members")
    op.drop_index("ix_management_operational_members_collaborator_id", table_name="management_operational_members")
    op.drop_table("management_operational_members")
