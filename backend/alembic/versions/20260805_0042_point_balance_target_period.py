"""point balance entries gain a target reference period (month of the warranty return)

Revision ID: 20260805_0042
Revises: 20260731_0041
Create Date: 2026-08-05 00:00:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision = "20260805_0042"
down_revision = "20260731_0041"
branch_labels = None
depends_on = None


def _column_names(table_name: str) -> set[str]:
    bind = op.get_bind()
    return {column["name"] for column in inspect(bind).get_columns(table_name)}


def upgrade() -> None:
    columns = _column_names("point_balance_entries")
    if "target_reference_month" not in columns:
        op.add_column("point_balance_entries", sa.Column("target_reference_month", sa.Integer(), nullable=True))
    if "target_reference_year" not in columns:
        op.add_column("point_balance_entries", sa.Column("target_reference_year", sa.Integer(), nullable=True))


def downgrade() -> None:
    columns = _column_names("point_balance_entries")
    if "target_reference_year" in columns:
        op.drop_column("point_balance_entries", "target_reference_year")
    if "target_reference_month" in columns:
        op.drop_column("point_balance_entries", "target_reference_month")
