"""add normalized execution timeline to operational orders

Revision ID: 20260721_0020
Revises: 20260721_0019
Create Date: 2026-07-21 20:30:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260721_0020"
down_revision = "20260721_0019"
branch_labels = None
depends_on = None


def _local_timestamp(expression: str) -> str:
    return f"""
        CASE
            WHEN LEFT(COALESCE({expression}, ''), 4) ~ '^[12][0-9]{{3}}$'
            THEN ({expression})::timestamp AT TIME ZONE 'America/Porto_Velho'
            ELSE NULL
        END
    """


def upgrade() -> None:
    op.add_column("operations_orders", sa.Column("assumed_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("operations_orders", sa.Column("execution_started_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("operations_orders", sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True))

    assumed = "raw_payload->>'data_hora_assumido'"
    execution = "COALESCE(NULLIF(raw_payload->>'data_hora_execucao', ''), NULLIF(raw_payload->>'data_inicio', ''))"
    finished = "COALESCE(NULLIF(raw_payload->>'data_final', ''), NULLIF(raw_payload->>'data_fechamento', ''))"
    op.execute(
        f"""
        UPDATE operations_orders
        SET assumed_at = {_local_timestamp(assumed)},
            execution_started_at = {_local_timestamp(execution)},
            finished_at = COALESCE({_local_timestamp(finished)}, closed_at)
        """
    )


def downgrade() -> None:
    op.drop_column("operations_orders", "finished_at")
    op.drop_column("operations_orders", "execution_started_at")
    op.drop_column("operations_orders", "assumed_at")
