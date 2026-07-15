"""phase 2 import audit and resilient import run summary

Revision ID: 20260612_0002
Revises: 20260608_0001
Create Date: 2026-06-12 00:00:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision = "20260612_0002"
down_revision = "20260608_0001"
branch_labels = None
depends_on = None


def _table_names() -> set[str]:
    bind = op.get_bind()
    return set(inspect(bind).get_table_names())


def _column_names(table_name: str) -> set[str]:
    bind = op.get_bind()
    return {column["name"] for column in inspect(bind).get_columns(table_name)}


def _index_names(table_name: str) -> set[str]:
    bind = op.get_bind()
    return {index["name"] for index in inspect(bind).get_indexes(table_name)}


def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    table_names = set(inspector.get_table_names())

    if "imports" in table_names:
        import_columns = _column_names("imports")
        additions: list[sa.Column] = [
            sa.Column("file_hash", sa.String(length=64), nullable=True),
            sa.Column("status", sa.String(length=40), nullable=False, server_default="completed"),
            sa.Column("processed_rows", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("created_count", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("updated_count", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("skipped_count", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("rejected_count", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("duplicate_count", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("missing_date_count", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("unknown_collaborator_count", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("required_field_missing_count", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("paid_period_blocked_count", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("imported_by", sa.Integer(), nullable=True),
            sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("error_message", sa.Text(), nullable=True),
            sa.Column("notes", sa.Text(), nullable=True),
        ]
        for column in additions:
            if column.name not in import_columns:
                op.add_column("imports", column)

        op.execute("UPDATE imports SET processed_rows = COALESCE(imported_rows, 0) + COALESCE(ignored_rows, 0) WHERE processed_rows = 0")
        op.execute("UPDATE imports SET created_count = COALESCE(imported_rows, 0) WHERE created_count = 0")
        op.execute("UPDATE imports SET rejected_count = COALESCE(ignored_rows, 0) WHERE rejected_count = 0")
        op.execute("UPDATE imports SET started_at = created_at WHERE started_at IS NULL")
        op.execute("UPDATE imports SET finished_at = created_at WHERE finished_at IS NULL")
        op.execute(
            "UPDATE imports SET status = CASE "
            "WHEN COALESCE(error_rows, 0) > 0 OR COALESCE(ignored_rows, 0) > 0 THEN 'completed_with_warnings' "
            "ELSE 'completed' END "
            "WHERE status IS NULL OR status = '' OR status = 'completed'"
        )

        index_names = _index_names("imports")
        if "ix_imports_file_hash" not in index_names:
            op.create_index("ix_imports_file_hash", "imports", ["file_hash"], unique=False)
        if "ix_imports_status" not in index_names:
            op.create_index("ix_imports_status", "imports", ["status"], unique=False)
        if "ix_imports_imported_by" not in index_names:
            op.create_index("ix_imports_imported_by", "imports", ["imported_by"], unique=False)

    if "import_service_order_audits" not in table_names:
        op.create_table(
            "import_service_order_audits",
            sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
            sa.Column("import_run_id", sa.Integer(), sa.ForeignKey("imports.id"), nullable=False),
            sa.Column("os_code", sa.String(length=80), nullable=True),
            sa.Column("service_order_id", sa.Integer(), sa.ForeignKey("service_orders.id"), nullable=True),
            sa.Column("action", sa.String(length=40), nullable=False),
            sa.Column("field_name", sa.String(length=120), nullable=True),
            sa.Column("old_value", sa.Text(), nullable=True),
            sa.Column("new_value", sa.Text(), nullable=True),
            sa.Column("reason", sa.Text(), nullable=True),
            sa.Column("row_number", sa.Integer(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("created_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        )
        op.create_index("ix_import_service_order_audits_import_run_id", "import_service_order_audits", ["import_run_id"], unique=False)
        op.create_index("ix_import_service_order_audits_os_code", "import_service_order_audits", ["os_code"], unique=False)
        op.create_index("ix_import_service_order_audits_action", "import_service_order_audits", ["action"], unique=False)


def downgrade() -> None:
    table_names = _table_names()
    if "import_service_order_audits" in table_names:
        for index_name in [
            "ix_import_service_order_audits_action",
            "ix_import_service_order_audits_os_code",
            "ix_import_service_order_audits_import_run_id",
        ]:
            try:
                op.drop_index(index_name, table_name="import_service_order_audits")
            except Exception:
                pass
        op.drop_table("import_service_order_audits")

    if "imports" in table_names:
        for index_name in ["ix_imports_imported_by", "ix_imports_status", "ix_imports_file_hash"]:
            try:
                op.drop_index(index_name, table_name="imports")
            except Exception:
                pass

        import_columns = _column_names("imports")
        for column_name in [
            "notes",
            "error_message",
            "finished_at",
            "started_at",
            "imported_by",
            "paid_period_blocked_count",
            "required_field_missing_count",
            "unknown_collaborator_count",
            "missing_date_count",
            "duplicate_count",
            "rejected_count",
            "skipped_count",
            "updated_count",
            "created_count",
            "processed_rows",
            "status",
            "file_hash",
        ]:
            if column_name in import_columns:
                op.drop_column("imports", column_name)
