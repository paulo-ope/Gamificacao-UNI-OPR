"""add displacement start to operational orders

Revision ID: 20260722_0021
Revises: 20260721_0020
Create Date: 2026-07-22 00:10:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260722_0021"
down_revision = "20260721_0020"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "operations_orders",
        sa.Column("displacement_started_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.execute(
        """
        UPDATE operations_orders
        SET displacement_started_at = CASE
                WHEN LEFT(COALESCE(raw_payload->>'data_inicio', ''), 4) ~ '^[12][0-9]{3}$'
                THEN (raw_payload->>'data_inicio')::timestamp AT TIME ZONE 'America/Porto_Velho'
                ELSE NULL
            END,
            execution_started_at = CASE
                WHEN LEFT(COALESCE(raw_payload->>'data_hora_execucao', ''), 4) ~ '^[12][0-9]{3}$'
                THEN (raw_payload->>'data_hora_execucao')::timestamp AT TIME ZONE 'America/Porto_Velho'
                ELSE NULL
            END
        WHERE source = 'ixc'
        """
    )


def downgrade() -> None:
    op.drop_column("operations_orders", "displacement_started_at")
