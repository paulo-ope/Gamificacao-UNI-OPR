"""operations analytics foundation

Revision ID: 20260720_0012
Revises: 20260718_0011
Create Date: 2026-07-20 00:00:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision = "20260720_0012"
down_revision = "20260718_0011"
branch_labels = None
depends_on = None


def _tables() -> set[str]:
    return set(inspect(op.get_bind()).get_table_names())


def upgrade() -> None:
    tables = _tables()
    if "operations_import_runs" not in tables:
        op.create_table(
            "operations_import_runs",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("date_from", sa.Date(), nullable=False),
            sa.Column("date_to", sa.Date(), nullable=False),
            sa.Column("status", sa.String(length=40), nullable=False, server_default="running"),
            sa.Column("fetched_count", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("created_count", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("updated_count", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("unchanged_count", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("rejected_count", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("errors", sa.JSON(), nullable=False, server_default="[]"),
            sa.Column("imported_by", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
            sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        )
        op.create_index("ix_operations_import_runs_date_from", "operations_import_runs", ["date_from"])
        op.create_index("ix_operations_import_runs_date_to", "operations_import_runs", ["date_to"])
        op.create_index("ix_operations_import_runs_status", "operations_import_runs", ["status"])
        op.create_index("ix_operations_import_runs_imported_by", "operations_import_runs", ["imported_by"])

    if "operations_orders" not in tables:
        op.create_table(
            "operations_orders",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("source", sa.String(length=30), nullable=False, server_default="ixc"),
            sa.Column("source_order_id", sa.String(length=80), nullable=False),
            sa.Column("order_code", sa.String(length=100), nullable=False),
            sa.Column("protocol", sa.String(length=100), nullable=True),
            sa.Column("contract_id", sa.String(length=100), nullable=True),
            sa.Column("customer_id", sa.String(length=100), nullable=True),
            sa.Column("customer_login", sa.String(length=160), nullable=True),
            sa.Column("customer_name", sa.String(length=220), nullable=True),
            sa.Column("company_id", sa.String(length=80), nullable=True),
            sa.Column("regional", sa.String(length=160), nullable=True),
            sa.Column("state", sa.String(length=20), nullable=True),
            sa.Column("city", sa.String(length=160), nullable=True),
            sa.Column("contract_type", sa.String(length=120), nullable=True),
            sa.Column("person_type", sa.String(length=80), nullable=True),
            sa.Column("os_type", sa.String(length=160), nullable=True),
            sa.Column("os_subject", sa.String(length=220), nullable=True),
            sa.Column("diagnosis", sa.String(length=220), nullable=True),
            sa.Column("department", sa.String(length=160), nullable=True),
            sa.Column("sector", sa.String(length=160), nullable=True),
            sa.Column("priority", sa.String(length=80), nullable=True),
            sa.Column("creator", sa.String(length=180), nullable=True),
            sa.Column("responsible", sa.String(length=180), nullable=True),
            sa.Column("project", sa.String(length=160), nullable=True),
            sa.Column("pop", sa.String(length=160), nullable=True),
            sa.Column("status_code", sa.String(length=40), nullable=True),
            sa.Column("status", sa.String(length=120), nullable=True),
            sa.Column("is_closed", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column("is_internal", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column("sla_status", sa.String(length=40), nullable=False, server_default="unidentified"),
            sa.Column("sla_target_hours", sa.Float(), nullable=True),
            sa.Column("elapsed_hours", sa.Float(), nullable=True),
            sa.Column("opened_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("deadline_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("scheduled_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("source_updated_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("raw_payload", sa.JSON(), nullable=False, server_default="{}"),
            sa.Column("normalization_notes", sa.Text(), nullable=True),
            sa.Column("first_imported_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("last_imported_at", sa.DateTime(timezone=True), nullable=False),
            sa.UniqueConstraint("source", "source_order_id", name="uq_operations_orders_source_id"),
        )
        for column in (
            "source", "source_order_id", "order_code", "protocol", "contract_id", "customer_id", "customer_login",
            "company_id", "regional", "state", "city", "contract_type", "person_type", "os_type", "os_subject",
            "diagnosis", "department", "sector", "priority", "creator", "responsible", "project", "pop", "status_code",
            "status", "is_closed", "is_internal", "sla_status", "opened_at", "deadline_at", "closed_at", "source_updated_at",
        ):
            op.create_index(f"ix_operations_orders_{column}", "operations_orders", [column])
        op.create_index("ix_operations_orders_opened_closed", "operations_orders", ["opened_at", "closed_at"])
        op.create_index("ix_operations_orders_dimensions", "operations_orders", ["regional", "os_type", "os_subject"])


def downgrade() -> None:
    tables = _tables()
    if "operations_orders" in tables:
        op.drop_table("operations_orders")
    if "operations_import_runs" in tables:
        op.drop_table("operations_import_runs")
