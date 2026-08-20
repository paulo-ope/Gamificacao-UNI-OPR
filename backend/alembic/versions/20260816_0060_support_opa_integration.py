"""add support OPA Suite attendance ingestion tables

Revision ID: 20260816_0060
Revises: 20260815_0059
Create Date: 2026-08-16 00:00:00
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "20260816_0060"
down_revision = "20260815_0059"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "support_opa_import_runs",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("date_from", sa.Date(), nullable=False),
        sa.Column("date_to", sa.Date(), nullable=False),
        sa.Column("status", sa.String(length=40), nullable=False),
        sa.Column("fetched_count", sa.Integer(), nullable=False),
        sa.Column("created_count", sa.Integer(), nullable=False),
        sa.Column("updated_count", sa.Integer(), nullable=False),
        sa.Column("unchanged_count", sa.Integer(), nullable=False),
        sa.Column("rejected_count", sa.Integer(), nullable=False),
        sa.Column("errors", sa.JSON(), nullable=False),
        sa.Column("imported_by", sa.Integer(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["imported_by"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_support_opa_import_runs_date_from"), "support_opa_import_runs", ["date_from"])
    op.create_index(op.f("ix_support_opa_import_runs_date_to"), "support_opa_import_runs", ["date_to"])
    op.create_index(op.f("ix_support_opa_import_runs_imported_by"), "support_opa_import_runs", ["imported_by"])
    op.create_index(op.f("ix_support_opa_import_runs_status"), "support_opa_import_runs", ["status"])

    op.create_table(
        "support_opa_attendances_raw",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("source_id", sa.String(length=100), nullable=False),
        sa.Column("payload_json", sa.JSON(), nullable=False),
        sa.Column("opened_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("source_updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("synced_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("source_id", name="uq_support_opa_attendances_raw_source_id"),
    )
    op.create_index("ix_support_opa_raw_opened_closed", "support_opa_attendances_raw", ["opened_at", "closed_at"])
    op.create_index(op.f("ix_support_opa_attendances_raw_closed_at"), "support_opa_attendances_raw", ["closed_at"])
    op.create_index(op.f("ix_support_opa_attendances_raw_opened_at"), "support_opa_attendances_raw", ["opened_at"])
    op.create_index(op.f("ix_support_opa_attendances_raw_source_id"), "support_opa_attendances_raw", ["source_id"])
    op.create_index(op.f("ix_support_opa_attendances_raw_source_updated_at"), "support_opa_attendances_raw", ["source_updated_at"])

    op.create_table(
        "support_opa_attendances",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("source_id", sa.String(length=100), nullable=False),
        sa.Column("protocol", sa.String(length=120), nullable=True),
        sa.Column("customer_id", sa.String(length=100), nullable=True),
        sa.Column("customer_name", sa.String(length=220), nullable=True),
        sa.Column("attendant_id", sa.String(length=100), nullable=True),
        sa.Column("attendant_name", sa.String(length=180), nullable=True),
        sa.Column("department_id", sa.String(length=100), nullable=True),
        sa.Column("department_name", sa.String(length=180), nullable=True),
        sa.Column("reason_id", sa.String(length=100), nullable=True),
        sa.Column("reason_name", sa.String(length=220), nullable=True),
        sa.Column("status", sa.String(length=80), nullable=True),
        sa.Column("opened_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("first_response_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("rating", sa.Float(), nullable=True),
        sa.Column("tma_seconds", sa.Integer(), nullable=True),
        sa.Column("tmr_seconds", sa.Integer(), nullable=True),
        sa.Column("source_updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("raw_payload", sa.JSON(), nullable=False),
        sa.Column("first_imported_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_imported_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("source_id", name="uq_support_opa_attendances_source_id"),
    )
    op.create_index("ix_support_opa_attendances_attendant_reason", "support_opa_attendances", ["attendant_name", "reason_name"])
    op.create_index("ix_support_opa_attendances_opened_closed", "support_opa_attendances", ["opened_at", "closed_at"])
    for column in (
        "attendant_id",
        "attendant_name",
        "closed_at",
        "customer_id",
        "department_id",
        "department_name",
        "opened_at",
        "protocol",
        "reason_id",
        "reason_name",
        "source_id",
        "source_updated_at",
        "status",
    ):
        op.create_index(op.f(f"ix_support_opa_attendances_{column}"), "support_opa_attendances", [column])


def downgrade() -> None:
    for column in (
        "status",
        "source_updated_at",
        "source_id",
        "reason_name",
        "reason_id",
        "protocol",
        "opened_at",
        "department_name",
        "department_id",
        "customer_id",
        "closed_at",
        "attendant_name",
        "attendant_id",
    ):
        op.drop_index(op.f(f"ix_support_opa_attendances_{column}"), table_name="support_opa_attendances")
    op.drop_index("ix_support_opa_attendances_opened_closed", table_name="support_opa_attendances")
    op.drop_index("ix_support_opa_attendances_attendant_reason", table_name="support_opa_attendances")
    op.drop_table("support_opa_attendances")

    op.drop_index(op.f("ix_support_opa_attendances_raw_source_updated_at"), table_name="support_opa_attendances_raw")
    op.drop_index(op.f("ix_support_opa_attendances_raw_source_id"), table_name="support_opa_attendances_raw")
    op.drop_index(op.f("ix_support_opa_attendances_raw_opened_at"), table_name="support_opa_attendances_raw")
    op.drop_index(op.f("ix_support_opa_attendances_raw_closed_at"), table_name="support_opa_attendances_raw")
    op.drop_index("ix_support_opa_raw_opened_closed", table_name="support_opa_attendances_raw")
    op.drop_table("support_opa_attendances_raw")

    op.drop_index(op.f("ix_support_opa_import_runs_status"), table_name="support_opa_import_runs")
    op.drop_index(op.f("ix_support_opa_import_runs_imported_by"), table_name="support_opa_import_runs")
    op.drop_index(op.f("ix_support_opa_import_runs_date_to"), table_name="support_opa_import_runs")
    op.drop_index(op.f("ix_support_opa_import_runs_date_from"), table_name="support_opa_import_runs")
    op.drop_table("support_opa_import_runs")
