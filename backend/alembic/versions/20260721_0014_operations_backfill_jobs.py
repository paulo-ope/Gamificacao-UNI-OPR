"""operations backfill jobs

Revision ID: 20260721_0014
Revises: 20260720_0013
Create Date: 2026-07-21 00:00:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision = "20260721_0014"
down_revision = "20260720_0013"
branch_labels = None
depends_on = None


def _tables() -> set[str]:
    return set(inspect(op.get_bind()).get_table_names())


def upgrade() -> None:
    if "operations_backfill_jobs" in _tables():
        return
    op.create_table(
        "operations_backfill_jobs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("date_from", sa.Date(), nullable=False),
        sa.Column("date_to", sa.Date(), nullable=False),
        sa.Column("next_date", sa.Date(), nullable=False),
        sa.Column("sector_ids", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("status", sa.String(length=40), nullable=False, server_default="pending"),
        sa.Column("total_days", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("processed_days", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("fetched_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("updated_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("unchanged_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("rejected_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("errors", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("requested_by", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
    )
    for column in ("date_from", "date_to", "next_date", "status", "requested_by"):
        op.create_index(f"ix_operations_backfill_jobs_{column}", "operations_backfill_jobs", [column])


def downgrade() -> None:
    if "operations_backfill_jobs" in _tables():
        op.drop_table("operations_backfill_jobs")
