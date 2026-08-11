"""operations backlog snapshot: add city as a captured dimension

Revision ID: 20260811_0047
Revises: 20260811_0046
Create Date: 2026-08-11 01:00:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260811_0047"
down_revision = "20260811_0046"
branch_labels = None
depends_on = None

OLD_CONSTRAINT = "uq_operations_backlog_snapshot_identity"


def upgrade() -> None:
    op.add_column(
        "operations_backlog_snapshots",
        sa.Column("city", sa.String(length=160), nullable=False, server_default="Não identificado"),
    )
    op.drop_constraint(OLD_CONSTRAINT, "operations_backlog_snapshots", type_="unique")
    op.create_unique_constraint(
        OLD_CONSTRAINT, "operations_backlog_snapshots", ["snapshot_date", "regional", "team_model", "sector", "city"]
    )


def downgrade() -> None:
    op.drop_constraint(OLD_CONSTRAINT, "operations_backlog_snapshots", type_="unique")
    op.create_unique_constraint(
        OLD_CONSTRAINT, "operations_backlog_snapshots", ["snapshot_date", "regional", "team_model", "sector"]
    )
    op.drop_column("operations_backlog_snapshots", "city")
