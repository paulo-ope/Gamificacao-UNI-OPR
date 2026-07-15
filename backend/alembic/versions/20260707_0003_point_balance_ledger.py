"""point balance ledger for post-payment warranty debits

Revision ID: 20260707_0003
Revises: 20260612_0002
Create Date: 2026-07-07 00:00:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision = "20260707_0003"
down_revision = "20260612_0002"
branch_labels = None
depends_on = None


def _table_names() -> set[str]:
    bind = op.get_bind()
    return set(inspect(bind).get_table_names())


def _column_names(table_name: str) -> set[str]:
    bind = op.get_bind()
    return {column["name"] for column in inspect(bind).get_columns(table_name)}


def upgrade() -> None:
    table_names = _table_names()

    if "collaborator_scores" in table_names:
        score_columns = _column_names("collaborator_scores")
        if "balance_adjustment_points" not in score_columns:
            op.add_column(
                "collaborator_scores",
                sa.Column("balance_adjustment_points", sa.Float(), nullable=False, server_default="0"),
            )
        if "balance_after" not in score_columns:
            op.add_column(
                "collaborator_scores",
                sa.Column("balance_after", sa.Float(), nullable=False, server_default="0"),
            )

    if "collaborator_point_balances" not in table_names:
        op.create_table(
            "collaborator_point_balances",
            sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
            sa.Column("collaborator_id", sa.Integer(), sa.ForeignKey("collaborators.id"), nullable=False, unique=True),
            sa.Column("balance_points", sa.Float(), nullable=False, server_default="0"),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        )
        op.create_index(
            "ix_collaborator_point_balances_collaborator_id",
            "collaborator_point_balances",
            ["collaborator_id"],
            unique=True,
        )

    if "point_balance_entries" not in table_names:
        op.create_table(
            "point_balance_entries",
            sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
            sa.Column("collaborator_id", sa.Integer(), sa.ForeignKey("collaborators.id"), nullable=False),
            sa.Column("entry_type", sa.String(length=40), nullable=False),
            sa.Column("points", sa.Float(), nullable=False),
            sa.Column("original_service_order_id", sa.Integer(), sa.ForeignKey("service_orders.id"), nullable=True),
            sa.Column("related_service_order_id", sa.Integer(), sa.ForeignKey("service_orders.id"), nullable=True),
            sa.Column("origin_calculation_run_id", sa.Integer(), sa.ForeignKey("calculation_runs.id"), nullable=True),
            sa.Column("applied_calculation_run_id", sa.Integer(), sa.ForeignKey("calculation_runs.id"), nullable=True),
            sa.Column("applied_reference_month", sa.Integer(), nullable=True),
            sa.Column("applied_reference_year", sa.Integer(), nullable=True),
            sa.Column("status", sa.String(length=20), nullable=False, server_default="pending"),
            sa.Column("requires_review", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column("recurrence_classification", sa.String(length=60), nullable=True),
            sa.Column("recurrence_action", sa.String(length=40), nullable=True),
            sa.Column("reason", sa.Text(), nullable=True),
            sa.Column("created_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        )
        op.create_index(
            "ix_point_balance_entries_collaborator_id", "point_balance_entries", ["collaborator_id"], unique=False
        )
        op.create_index("ix_point_balance_entries_entry_type", "point_balance_entries", ["entry_type"], unique=False)
        op.create_index("ix_point_balance_entries_status", "point_balance_entries", ["status"], unique=False)
        op.create_index(
            "ix_point_balance_entries_applied_calculation_run_id",
            "point_balance_entries",
            ["applied_calculation_run_id"],
            unique=False,
        )


def downgrade() -> None:
    table_names = _table_names()

    if "point_balance_entries" in table_names:
        for index_name in [
            "ix_point_balance_entries_applied_calculation_run_id",
            "ix_point_balance_entries_status",
            "ix_point_balance_entries_entry_type",
            "ix_point_balance_entries_collaborator_id",
        ]:
            try:
                op.drop_index(index_name, table_name="point_balance_entries")
            except Exception:
                pass
        op.drop_table("point_balance_entries")

    if "collaborator_point_balances" in table_names:
        try:
            op.drop_index("ix_collaborator_point_balances_collaborator_id", table_name="collaborator_point_balances")
        except Exception:
            pass
        op.drop_table("collaborator_point_balances")

    if "collaborator_scores" in table_names:
        score_columns = _column_names("collaborator_scores")
        if "balance_after" in score_columns:
            op.drop_column("collaborator_scores", "balance_after")
        if "balance_adjustment_points" in score_columns:
            op.drop_column("collaborator_scores", "balance_adjustment_points")
