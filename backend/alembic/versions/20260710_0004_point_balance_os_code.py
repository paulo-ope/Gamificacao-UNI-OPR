"""store os_code alongside the O.S ids on point_balance_entries

Deleting/re-importing a period's raw O.S rows creates new ServiceOrder ids, which broke
idempotent detection and forced blocking period deletion whenever a ledger entry
referenced an O.S from that period. Storing the stable os_code lets the ledger survive
O.S re-import without losing its identity or duplicating debits.

Revision ID: 20260710_0004
Revises: 20260707_0003
Create Date: 2026-07-10 00:00:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect

revision = "20260710_0004"
down_revision = "20260707_0003"
branch_labels = None
depends_on = None


def _column_names(table_name: str) -> set[str]:
    bind = op.get_bind()
    return {column["name"] for column in inspect(bind).get_columns(table_name)}


def upgrade() -> None:
    columns = _column_names("point_balance_entries")
    if "original_os_code" not in columns:
        op.add_column("point_balance_entries", sa.Column("original_os_code", sa.String(length=80), nullable=True))
    if "related_os_code" not in columns:
        op.add_column("point_balance_entries", sa.Column("related_os_code", sa.String(length=80), nullable=True))

    op.execute(
        """
        UPDATE point_balance_entries
        SET original_os_code = (SELECT os_code FROM service_orders WHERE service_orders.id = point_balance_entries.original_service_order_id)
        WHERE original_os_code IS NULL AND original_service_order_id IS NOT NULL
        """
    )
    op.execute(
        """
        UPDATE point_balance_entries
        SET related_os_code = (SELECT os_code FROM service_orders WHERE service_orders.id = point_balance_entries.related_service_order_id)
        WHERE related_os_code IS NULL AND related_service_order_id IS NOT NULL
        """
    )


def downgrade() -> None:
    columns = _column_names("point_balance_entries")
    if "related_os_code" in columns:
        op.drop_column("point_balance_entries", "related_os_code")
    if "original_os_code" in columns:
        op.drop_column("point_balance_entries", "original_os_code")
