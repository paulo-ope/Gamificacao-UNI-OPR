"""phase 1 closure status and calculation snapshot

Revision ID: 20260608_0001
Revises:
Create Date: 2026-06-08 00:00:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision = "20260608_0001"
down_revision = None
branch_labels = None
depends_on = None


def _column_names(table_name: str) -> set[str]:
    bind = op.get_bind()
    inspector = inspect(bind)
    return {column["name"] for column in inspector.get_columns(table_name)}


def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    table_names = set(inspector.get_table_names())
    if "calculation_runs" not in table_names:
        return

    is_postgres = bind.dialect.name == "postgresql"
    calculation_run_columns = _column_names("calculation_runs")

    additions: list[tuple[str, sa.types.TypeEngine, bool, str | None]] = [
        ("status", sa.String(length=20), False, "draft"),
        ("status_changed_at", sa.DateTime(timezone=True), True, None),
        ("status_changed_by", sa.Integer(), True, None),
        ("status_note", sa.Text(), True, None),
        ("approved_at", sa.DateTime(timezone=True), True, None),
        ("approved_by", sa.Integer(), True, None),
        ("paid_at", sa.DateTime(timezone=True), True, None),
        ("paid_by", sa.Integer(), True, None),
        ("executed_by", sa.Integer(), True, None),
        ("executed_at", sa.DateTime(timezone=True), True, None),
        ("config_snapshot", sa.JSON(), True, None),
    ]

    for column_name, column_type, nullable, default in additions:
        if column_name in calculation_run_columns:
            continue
        if default is None:
            op.add_column("calculation_runs", sa.Column(column_name, column_type, nullable=nullable))
        else:
            op.add_column("calculation_runs", sa.Column(column_name, column_type, nullable=nullable, server_default=default))

    if "status" not in calculation_run_columns:
        op.execute("UPDATE calculation_runs SET status = 'draft' WHERE status IS NULL")
        if is_postgres:
            op.alter_column("calculation_runs", "status", server_default=None)

    if "status_changed_at" not in calculation_run_columns:
        op.execute("UPDATE calculation_runs SET status_changed_at = created_at WHERE status_changed_at IS NULL")
    if "executed_at" not in calculation_run_columns:
        op.execute("UPDATE calculation_runs SET executed_at = created_at WHERE executed_at IS NULL")


def downgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    table_names = set(inspector.get_table_names())
    if "calculation_runs" not in table_names:
        return

    calculation_run_columns = _column_names("calculation_runs")
    for column_name in [
        "config_snapshot",
        "executed_at",
        "executed_by",
        "paid_by",
        "paid_at",
        "approved_by",
        "approved_at",
        "status_note",
        "status_changed_by",
        "status_changed_at",
        "status",
    ]:
        if column_name in calculation_run_columns:
            op.drop_column("calculation_runs", column_name)
